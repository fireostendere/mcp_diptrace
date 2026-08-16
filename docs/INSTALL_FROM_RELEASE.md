# Install from Published Release Assets

## Current published release

Version `v0.3.0` is the current published distribution line for PyPI and the
GitHub development prerelease.

Keep every downloaded artifact on the same immutable version.


> **v0.4.0 release-candidate boundary:** the repository currently prepares
> `v0.4.0`, including Windows 0.4.0 artifacts and the Linux/macOS one-command
> installers. Until the v0.4.0 tag, GitHub release assets, and PyPI publication
> actually exist and pass post-publication verification, this page intentionally
> keeps its install commands pinned to immutable published `v0.3.0`. Do not
> substitute `0.4.0` into the published-release commands prematurely.

Windows assets:

```text
DipTrace-MCP-Setup-0.3.0.exe
DipTrace-MCP-Plugin-Setup-0.3.0.exe
DipTrace-MCP-Portable-0.3.0.zip
DipTrace-MCP-0.3.0-windows.mcpb
SHA256SUMS.txt
RELEASE_PROVENANCE.txt
```

Python assets:

```text
diptrace_mcp-0.3.0-py3-none-any.whl
diptrace_mcp-0.3.0.tar.gz
```

Published release files are immutable. A corrected build requires a new version;
do not mix artifacts from different tags.

## PyPI

Python 3.10 or newer:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.3.0
diptrace-mcp --help
```

The Python package contains the MCP server and packaged skills. It does not install the Windows DipTrace bridge plug-in.

`0.3.0` was published through GitHub OIDC Trusted Publishing. That establishes
publication provenance, not Authenticode trust, universal compatibility or
production readiness.

## Verify GitHub release hashes

Download `SHA256SUMS.txt` from the same `v0.3.0` GitHub prerelease.

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

PowerShell for an individual file:

```powershell
Get-FileHash .\DipTrace-MCP-Setup-0.3.0.exe -Algorithm SHA256
```

The digest must match the release manifest. A matching SHA-256 proves byte identity, not publisher signing.

## Recommended Windows installation

1. Close affected DipTrace modules and the MCP client being configured.
2. Verify the installer hash.
3. Run `DipTrace-MCP-Setup-0.3.0.exe` for the per-user server/configurator and
   select the workspace, local state directory and optional MCP client setup.
4. When machine-wide DipTrace integration is required, run
   `DipTrace-MCP-Plugin-Setup-0.3.0.exe` with administrator privileges.
5. Select the DipTrace installation in the plug-in installer.
6. Restart DipTrace and the configured MCP client.
7. Call `get_capabilities` before relying on document-specific paths.

The installer is unsigned, so Windows may display a SmartScreen warning. Verify the release identity and checksum before continuing.

Workspaces and user state are preserved by default on uninstall. State removal is ownership-gated and requires explicit selection.

## Portable Windows installation

1. Verify `DipTrace-MCP-Portable-0.3.0.zip`.
2. Extract it to a stable local directory.
3. Read `README_FIRST.txt` and verify the internal checksums.
4. Run the included configuration/installation helper as appropriate.
5. Restart the MCP client and call `get_capabilities`.

The portable bundle contains the standalone server, bridge, four DipTrace settings profiles, configurator and helper scripts. A separate Python installation is not required for the frozen Windows executables.

## Install the GitHub wheel directly

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install `
  .\diptrace_mcp-0.3.0-py3-none-any.whl
.\.venv\Scripts\diptrace-mcp.exe --help
```

Linux/WSL:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install ./diptrace_mcp-0.3.0-py3-none-any.whl
diptrace-mcp --help
```

## MCPB

`DipTrace-MCP-0.3.0-windows.mcpb` contains the self-contained Windows stdio
server for compatible MCP clients.

Before using it:

1. verify its SHA-256 from the same release;
2. confirm version `0.3.0` and identity `io.github.fireostendere/diptrace-mcp`;
3. configure workspace/state paths;
4. start the server and call `get_capabilities`.

The MCPB does **not** silently install the DipTrace bridge. Live exchange requires the matching bridge/settings. See [MCP_DISTRIBUTION.md](MCP_DISTRIBUTION.md).

## Source installation for review/development

For the exact released source:

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
git checkout v0.3.0
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

A checkout of current `main` may contain post-release changes not present in the
published `v0.3.0` artifacts. Use the tag when reproducibility matters.

## Published release versus `main`

The immutable `v0.3.0` package includes the schematic intelligence, PCB
Generations A-D, 90% aggregate CI coverage gate and cinematic presentation work
listed in its release record. Later `main` changes are not part of those bytes.

## Evidence/limitations of the released artifacts

The immutable `v0.3.0` release record retains the exact operator acceptance,
workflow and public-redownload evidence that was true when it was published.

Similarly, an internal raw-preserving Component/Pattern Library mutation core now exists on later development and has controlled real-editor evidence, but it is not part of a newly expanded public native-library MCP write contract.

The project still does not claim:

- trusted Authenticode signing;
- universal DipTrace 5.x compatibility;
- native manufacturing generation/sign-off;
- Novarm/DipTrace endorsement;
- independent review or production readiness.

Runtime `get_capabilities` remains authoritative for an installed build and active document.
