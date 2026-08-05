# Install from Published Release Assets

## Versioned release set

Version `v0.2.1` is the distribution release for PyPI, Windows MCPB, the
installer, portable bundle, wheel, and source distribution. Download every file
from the same immutable GitHub Release and do not mix versions.

Main Windows assets:

```text
DipTrace-MCP-Setup-0.2.1.exe
DipTrace-MCP-Portable-0.2.1.zip
DipTrace-MCP-0.2.1-windows.mcpb
SHA256SUMS.txt
```

Python assets:

```text
diptrace_mcp-0.2.1-py3-none-any.whl
diptrace_mcp-0.2.1.tar.gz
```

The release also contains SBOM, dependency, notice, provenance, Windows bundle,
license, and release-record files. Existing `v0.2.0` files remain available and
must not be replaced.

## Install from PyPI

Python 3.10 or newer is required:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.2.1
diptrace-mcp --help
```

The PyPI project is published through GitHub OpenID Connect Trusted Publishing.
The release files should expose the expected GitHub source links and PyPI
attestations. Trusted Publishing establishes publication provenance, not code
quality, Authenticode trust, or real DipTrace compatibility.

The Python package contains the MCP server, command-line entry points, and
packaged skills. It does not install the Windows DipTrace bridge plug-in.

## Verify GitHub release SHA-256

Download `SHA256SUMS.txt` from the same GitHub Release.

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell for a selected file:

```powershell
Get-FileHash .\DipTrace-MCP-Setup-0.2.1.exe -Algorithm SHA256
```

The value must match `SHA256SUMS.txt`. A matching hash proves byte identity,
not trusted publisher signing.

## Recommended Windows installation

1. Close DipTrace modules and the MCP client being configured.
2. Verify the installer hash.
3. Run `DipTrace-MCP-Setup-0.2.1.exe`.
4. Select the DipTrace installation, project workspace, local state directory,
   and optional Codex/Claude configuration.
5. Restart the selected MCP client and DipTrace.
6. Call `get_capabilities` before relying on document-specific tools.

The installer is unsigned. Windows may show a SmartScreen warning. Check the
release URL and SHA-256 before continuing.

The installer preserves workspaces and user state by default on uninstall.
State removal is ownership-gated and must be selected explicitly.

## Portable Windows installation

1. Verify `DipTrace-MCP-Portable-0.2.1.zip`.
2. Extract it to a stable local directory.
3. Read `README_FIRST.txt` and verify the internal `SHA256SUMS.txt`.
4. Run the included configuration or installation helper.
5. Restart the MCP client and call `get_capabilities`.

The portable bundle contains the standalone server, bridge, four settings
profiles, configurator, and helper scripts. It does not require a separate
Python installation.

## Install the GitHub wheel directly

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install `
  .\diptrace_mcp-0.2.1-py3-none-any.whl
.\.venv\Scripts\diptrace-mcp.exe --help
```

Linux/WSL:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install ./diptrace_mcp-0.2.1-py3-none-any.whl
diptrace-mcp --help
```

## MCPB installation

The file `DipTrace-MCP-0.2.1-windows.mcpb` contains the self-contained Windows
stdio server for compatible MCP clients.

Before installing it:

1. verify the MCPB file against `SHA256SUMS.txt` from the same GitHub Release;
2. confirm the client shows version `0.2.1` and the expected package identity;
3. configure a workspace and state directory;
4. start the server and call `get_capabilities`.

The MCPB does not silently install the DipTrace bridge. Live exchange requires
the matching bridge and settings from the same release. See
[`MCP_DISTRIBUTION.md`](MCP_DISTRIBUTION.md).

## Source installation

For development or review:

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
git checkout v0.2.1
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

Use an immutable tag or commit for reproducible installations. Do not treat a
moving branch as a release identity.

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
