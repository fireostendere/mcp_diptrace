# Install from GitHub Release Assets

## Published release

The latest published GitHub release is
[`v0.2.0`](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0),
an explicitly unsigned alpha/development prerelease tagged at commit
`31766cb6e667dc24f3e2921decfd65c03eebd271`.

Download every file from that exact release page. Do not mix the server, bridge,
installer, portable bundle, or checksums from different versions.

Main Windows assets:

```text
DipTrace-MCP-Setup-0.2.0.exe
DipTrace-MCP-Portable-0.2.0.zip
SHA256SUMS.txt
```

Python assets:

```text
diptrace_mcp-0.2.0-py3-none-any.whl
diptrace_mcp-0.2.0.tar.gz
```

The release also contains SBOM, dependency, notice, provenance, Windows bundle,
license, and release-record files. The project is not published to PyPI. No
`.mcpb` asset is part of v0.2.0.

## Verify SHA-256

Download `SHA256SUMS.txt` from the same release.

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell for a selected file:

```powershell
Get-FileHash .\DipTrace-MCP-Setup-0.2.0.exe -Algorithm SHA256
```

The value must match `SHA256SUMS.txt`. A matching hash proves byte identity,
not trusted publisher signing.

## Recommended Windows installation

1. Close DipTrace modules and the MCP client being configured.
2. Verify the installer hash.
3. Run `DipTrace-MCP-Setup-0.2.0.exe`.
4. Select the DipTrace installation, project workspace, local state directory,
   and optional Codex/Claude configuration.
5. Restart the selected MCP client and DipTrace.
6. Call `get_capabilities` before relying on document-specific tools.

The installer is unsigned. Windows may show a SmartScreen warning. Check the
release URL and SHA-256 before continuing.

The installer preserves workspaces and user state by default on uninstall.
State removal is ownership-gated and must be selected explicitly.

## Portable Windows installation

1. Verify `DipTrace-MCP-Portable-0.2.0.zip`.
2. Extract it to a stable local directory.
3. Read `README_FIRST.txt` and verify the internal `SHA256SUMS.txt`.
4. Run the included configuration or installation helper.
5. Restart the MCP client and call `get_capabilities`.

The portable bundle contains the standalone server, bridge, four settings
profiles, configurator, and helper scripts. It does not require a separate
Python installation.

## Install the Python wheel

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install `
  .\diptrace_mcp-0.2.0-py3-none-any.whl
.\.venv\Scripts\diptrace-mcp.exe --help
```

Linux/WSL:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install ./diptrace_mcp-0.2.0-py3-none-any.whl
diptrace-mcp --help
```

The wheel contains the MCP server and packaged skills. It does not install the
Windows DipTrace bridge plug-in.

## MCPB, official Registry, and Smithery

Version 0.2.0 does not contain MCPB. The repository prepares a Windows MCPB
builder and official Registry metadata generator for a future version. See
[`MCP_DISTRIBUTION.md`](MCP_DISTRIBUTION.md).

Do not add a new asset to the existing v0.2.0 release or move the tag. A future
MCPB must be published under a new immutable version.

## Known limitations

Publication and successful CI do not establish:

- trusted Authenticode signing;
- universal DipTrace 5.x compatibility;
- validation of every registered write tool or XML object;
- Q1 Component Angle GUI/re-export evidence;
- native Component/Pattern Library mutation;
- native Gerber/NC Drill/manufacturing generation;
- Novarm/DipTrace endorsement;
- production, fabrication, assembly, or regulatory sign-off.

Runtime `get_capabilities` remains authoritative for the installed version and
active document.
