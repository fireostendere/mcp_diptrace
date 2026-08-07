"""Architecture facade for the MCP server.

Input schemas and boundary helpers live in :mod:`server_inputs`; runtime tool
registration and transports live in :mod:`server_runtime`.  The compatibility
module preserves the historic ``diptrace_mcp.server`` import path.
"""
from __future__ import annotations

from typing import Any

from . import server_inputs as _inputs
from . import server_runtime as _runtime
from .server_runtime import create_server as create_server
from .server_runtime import main as main


def __getattr__(name: str) -> Any:
    if hasattr(_runtime, name):
        return getattr(_runtime, name)
    if hasattr(_inputs, name):
        return getattr(_inputs, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_runtime)) | set(dir(_inputs)))


if __name__ == "__main__":
    main()
