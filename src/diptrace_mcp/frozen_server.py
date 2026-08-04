"""PyInstaller entry point for the production MCP server.

This module deliberately delegates to the same ``server.main`` used by the
console entry point.  It contains no alternate protocol or tool registration
path.
"""

from diptrace_mcp.server import main

if __name__ == "__main__":
    main()
