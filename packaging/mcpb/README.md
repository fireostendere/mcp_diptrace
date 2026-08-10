# MCPB packaging

This directory contains the deterministic Windows MCP Bundle build source. Version `0.2.1` has already been published as `DipTrace-MCP-0.2.1-windows.mcpb`; future builds must use a new version and must not replace the published `v0.2.1` bytes.

Build the standalone Windows server first, then run:

```powershell
python scripts/build_mcpb.py `
  --server-dir dist\windows-server\diptrace_mcp_server `
  --output-dir dist\mcpb
```

The builder reads the package version from `pyproject.toml`, writes a deterministic `.mcpb` ZIP archive and creates a sibling `.sha256` file. The bundle is Windows-only because it contains the frozen Windows server binary.

The MCPB installs/provides the stdio server only. Live exchange with DipTrace still requires the matching `diptrace_mcp_bridge.exe` and editor settings profiles from the same release/source candidate; installing the MCPB alone does not copy files into the DipTrace installation directory.

For a future release:

1. freeze a new version/candidate;
2. build the standalone server and MCPB from that exact candidate;
3. verify deterministic contents and SHA-256;
4. publish immutable bytes with the matching release assets;
5. redownload and verify the public bundle before registry/directory metadata references it.

See `docs/MCP_DISTRIBUTION.md` and `docs/RELEASE_PROCESS.md` for the current publication/evidence boundaries.
