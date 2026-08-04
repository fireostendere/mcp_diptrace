# MCP distribution preparation

## Current state

GitHub prerelease `v0.2.0` is published as an explicitly unsigned
alpha/development release. It does not contain an MCPB artifact and has not been
submitted to the official MCP Registry or Smithery.

This repository prepares those channels without publishing another release.
Existing tags and release assets must never be replaced.

Canonical future registry name:

```text
io.github.fireostendere/diptrace-mcp
```

The hidden `mcp-name` marker in `README.md` uses the same value so a future PyPI
package can also satisfy registry ownership verification. The planned primary
route is MCPB, not PyPI.

## Why MCPB

The official MCP Registry accepts MCPB files hosted in GitHub or GitLab
releases. The concrete `server.json` entry must contain the immutable public
asset URL and its SHA-256. Smithery also accepts a local stdio server as an MCPB
bundle.

The prepared bundle is Windows-only and contains the self-contained stdio
server. It does not silently install files into DipTrace. Live exchange requires
the matching bridge plug-in and settings from the same future release.

## Build a candidate without publishing

On Windows:

```powershell
.\scripts\build_windows_server.ps1 `
  -PythonCommand python `
  -OutputDir dist\windows-server `
  -Clean

python scripts/build_mcpb.py `
  --server-dir dist\windows-server\diptrace_mcp_server `
  --output-dir dist\mcpb
```

Outputs:

```text
dist/mcpb/DipTrace-MCP-<version>-windows.mcpb
dist/mcpb/DipTrace-MCP-<version>-windows.mcpb.sha256
```

This preparation does not create a tag, GitHub Release, registry entry, or
Smithery listing.

## Future official MCP Registry publication

Only after a new reviewed version is released:

1. Upload the exact `.mcpb` file as an immutable GitHub Release asset.
2. Download the public file again and verify its SHA-256.
3. Generate concrete metadata:

   ```bash
   python scripts/generate_registry_server_json.py \
     --version <version> \
     --mcpb-url https://github.com/fireostendere/mcp_diptrace/releases/download/v<version>/DipTrace-MCP-<version>-windows.mcpb \
     --mcpb-file DipTrace-MCP-<version>-windows.mcpb \
     --output server.json
   ```

4. Validate the generated file with the current official schema and
   `mcp-publisher` version.
5. Authenticate using `mcp-publisher login github`.
6. Run `mcp-publisher publish`.
7. Query the registry API and record the immutable published metadata.

The official registry is in preview. Re-check its current schema and package
requirements at publication time.

## Future Smithery publication

After the same MCPB has been publicly released and verified:

```bash
smithery auth login
smithery mcp publish ./DipTrace-MCP-<version>-windows.mcpb \
  -n fireostendere/diptrace-mcp
```

Record the Smithery release identifier and confirm that installation asks for
workspace and state directories. Do not describe the MCPB as installing the
DipTrace bridge automatically.

## awesome-mcp-servers entry

The repository is already suitable for a listing under Developer Tools:

```markdown
- [fireostendere/mcp_diptrace](https://github.com/fireostendere/mcp_diptrace) 🐍 🏠 🪟 - Local MCP server and Windows bridge for reading, reviewing and guarded editing of DipTrace PCB and schematic projects; also supports cross-platform offline XML analysis.
```

That listing does not require MCPB or registry publication.
