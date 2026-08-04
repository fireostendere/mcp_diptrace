# PyInstaller onedir specification for the standalone client configurator.
from __future__ import annotations

import importlib.util
from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ


ROOT = Path.cwd().resolve()
SRC = ROOT / "src"

analysis = Analysis(
    [str(SRC / "diptrace_mcp" / "windows_configurator.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=["tomli"] if importlib.util.find_spec("tomli") is not None else [],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "hypothesis", "ruff", "mypy", "hatchling", "mcp", "pydantic"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="diptrace_mcp_configure",
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
    name="diptrace_mcp_configure",
)
