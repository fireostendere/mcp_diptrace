# PyInstaller onedir specification for the standalone DipTrace MCP server.
# Build from the repository root; the absolute paths below are build inputs and
# are not embedded in the application metadata.
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
SKILLS = ROOT / "skills"
INCLUDE_GEOMETRY = os.environ.get("DIPTRACE_MCP_INCLUDE_GEOMETRY", "0") == "1"


def _existing_files(directory: Path) -> list[tuple[str, str]]:
    if not directory.is_dir():
        raise RuntimeError(f"required packaging directory is missing: {directory}")
    files: list[tuple[str, str]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        destination = Path("diptrace_mcp") / "skills" / relative.parent
        files.append((str(path), destination.as_posix()))
    return files


datas: list[tuple[str, str]] = collect_data_files("diptrace_mcp", excludes=["skills/**"])
binaries: list[tuple[str, str]] = []
datas.extend(_existing_files(SKILLS))
datas.extend(copy_metadata("mcp"))
datas.extend(copy_metadata("pydantic"))
datas.extend(copy_metadata("typing_extensions"))

hiddenimports = [
    *collect_submodules("diptrace_mcp"),
    # Only MCP server/shared runtime modules are needed. Client and CLI modules
    # are not part of the stdio server and pull in optional/dev dependencies.
    *collect_submodules(
        "mcp.server",
        filter=lambda name: not name.startswith("mcp.server.__main__"),
        on_error="ignore",
    ),
    *collect_submodules(
        "mcp.shared",
        on_error="ignore",
    ),
    *collect_submodules(
        "pydantic",
        filter=lambda name: name not in {
            "pydantic.mypy",
            "pydantic.v1._hypothesis_plugin",
            "pydantic.v1.mypy",
        },
    ),
]
excludes = [
    "pytest",
    "hypothesis",
    "ruff",
    "mypy",
    "hatchling",
    "tkinter",
    "_tkinter",
]

if INCLUDE_GEOMETRY and importlib.util.find_spec("shapely") is not None:
    datas.extend(collect_data_files("shapely", excludes=["tests/**", "conftest.py"]))
    datas.extend(copy_metadata("shapely"))
    binaries.extend(collect_dynamic_libs("shapely"))
    hiddenimports.extend(
        collect_submodules(
            "shapely",
            filter=lambda name: not (
                name.startswith("shapely.tests")
                or name in {"shapely.conftest", "shapely.testing", "shapely.speedups"}
                or name == "shapely.plotting"
            ),
            on_error="ignore",
        )
    )
    hiddenimports.extend(collect_submodules("shapely.libs"))
else:
    excludes.append("shapely")

analysis = Analysis(
    [str(SRC / "diptrace_mcp" / "frozen_server.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="diptrace_mcp_server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="diptrace_mcp_server",
)
