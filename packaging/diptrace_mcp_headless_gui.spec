# PyInstaller onedir specification for the isolated Windows GUI helper.
from __future__ import annotations

from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


ROOT = Path.cwd().resolve()
SRC = ROOT / "src"
ENTRY = ROOT / "scripts" / "headless_gui_entry.py"

datas: list[tuple[str, str]] = []
datas.extend(collect_data_files("pywinauto"))
datas.extend(copy_metadata("pywinauto"))

hiddenimports = [
    *collect_submodules("pywinauto", on_error="ignore"),
    "diptrace_mcp.headless_gui",
    "diptrace_mcp.windows_configurator",
]

analysis = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "hypothesis",
        "ruff",
        "mypy",
        "hatchling",
        "mcp",
        "pydantic",
        "shapely",
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="diptrace_mcp_headless_gui",
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
    name="diptrace_mcp_headless_gui",
)
