# DipTrace MCP bundle

This MCPB contains the self-contained Windows stdio server.

Live exchange with a project currently open in DipTrace requires the matching
`diptrace_mcp_bridge.exe` plug-in and settings profiles from the same GitHub
release or source tree. Installing this MCPB alone does not copy files into the
DipTrace installation directory.

The server is unsigned alpha/development software. Verify release hashes, keep
backups, use preview/dry-run flows, and treat runtime `get_capabilities` as
authoritative for the active document.
