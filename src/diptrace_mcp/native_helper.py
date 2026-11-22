"""Fixed native-helper dispatch for source and bundled installations."""

from __future__ import annotations

import sys
from pathlib import Path

from .errors import ExternalToolUnavailableError

MODULES = {
    "pcb-acceptance": "diptrace_mcp.pcb_native_acceptance",
    "schematic-acceptance": "diptrace_mcp.schematic_native_acceptance",
    "xml-export": "diptrace_mcp.native_xml_export",
    "native-cam": "diptrace_mcp.native_cam_export",
    "native-cad-worker": "diptrace_mcp.native_cad",
}


def helper_command(dispatch: str, *args: str) -> list[str]:
    module = MODULES[dispatch]
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", module, *args]
    executable = Path(sys.executable)
    if executable.name.casefold() != "diptrace_mcp_headless_gui.exe":
        executable = (executable.parent / "tools" / "diptrace_mcp_headless_gui"
                      / "diptrace_mcp_headless_gui.exe")
    if not executable.is_file():
        raise ExternalToolUnavailableError("The bundled native GUI helper is missing")
    return [str(executable), dispatch, *args]
