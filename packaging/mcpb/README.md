# MCPB packaging

This directory prepares a Windows MCP Bundle for a future release. It does not
publish a release, modify an existing tag, or register the server.

Build the standalone Windows server first, then run:

```powershell
python scripts/build_mcpb.py `
  --server-dir dist\windows-server\diptrace_mcp_server `
  --output-dir dist\mcpb
```

The builder reads the package version from `pyproject.toml`, writes a
deterministic `.mcpb` ZIP archive, and creates a sibling `.sha256` file. The
bundle is Windows-only because it contains the frozen Windows binary.

The bundle installs the stdio server. The DipTrace executable bridge and
settings profiles remain a separate host integration and must come from the
same future release.
