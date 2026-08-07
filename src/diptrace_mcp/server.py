"""Architecture facade for the MCP server.

Input schemas and boundary helpers live in :mod:`server_inputs`; runtime tool
registration and transports live in :mod:`server_runtime`.  The compatibility
module preserves the historic ``diptrace_mcp.server`` import path.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from inspect import isasyncgenfunction
from typing import Any, cast

from . import server_inputs as _inputs
from . import server_runtime as _runtime
from .server_runtime import create_server as create_server

# ``_robust_stdio_server`` is an async-generator transport.  The original
# monolithic server decorated it with ``asynccontextmanager``; keep that
# contract after the runtime extraction, including for the PyInstaller entry
# point which imports ``diptrace_mcp.server:main``.
if isasyncgenfunction(_runtime._robust_stdio_server):
    _runtime._robust_stdio_server = cast(
        Any,
        asynccontextmanager(_runtime._robust_stdio_server),
    )


def main(argv: list[str] | None = None) -> None:
    _runtime.main(argv)


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
