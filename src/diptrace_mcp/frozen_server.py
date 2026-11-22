"""PyInstaller entry point for the production MCP server.

This module deliberately delegates to the same ``server.main`` used by the
console entry point.  It contains no alternate protocol or tool registration
path.
"""

from importlib import import_module
from importlib.util import find_spec

from diptrace_mcp.server import main

if __name__ == "__main__":
    # Initialize NumPy/GEOS on the main thread: first import in frozen Windows
    # AnyIO workers can hang. Geometry-free bundles have no Shapely spec.
    if find_spec("shapely") is not None:
        import_module("shapely")
    main()
