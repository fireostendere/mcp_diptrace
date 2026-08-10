# Install from Published Release Assets

## Current published release

Version `v0.2.1` is the current published distribution line for PyPI and the GitHub development prerelease.

Keep every downloaded artifact on the same immutable version.

Windows assets:

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

Published release files are immutable. A corrected build requires a new version; do not mix `v0.2.0`, `v0.2.1` or future-version files.

## PyPI

Python 3.10 or newer:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.2.1
diptrace-mcp --help
```

The Python package contains the MCP server and packaged skills. It does not install the Windows DipTrace bridge plug-in.

`0.2.1` was published through GitHub OIDC Trusted Publishing. That establishes publication provenance, not Authenticode trust, universal compatibility or production readiness.

## Verify GitHub release hashes

Download `SHA256SUMS.txt` from the same `v0.2.1` GitHub prerelease.

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

PowerShell for an individual file:

```powershell
Get-FileHash .\DipTrace-MCP-Setup-0.2.1.exe -Algorithm SHA256
```

The digest must match the release manifest. A matching SHA-256 proves byte identity, not publisher signing.

## Recommended Windows installation

1. Close affected DipTrace modules and the MCP client being configured.
2. Verify the installer hash.
3. Run `DipTrace-MCP-Setup-0.2.1.exe`.
4. Select the DipTrace installation, workspace, local state directory and optional MCP client configuration.
5. Restart DipTrace and the configured MCP client.
6. Call `get_capabilities` before relying on document-specific paths.

The installer is unsigned, so Windows may display a SmartScreen warning. Verify the release identity and checksum before continuing.

Workspaces and user state are preserved by default on uninstall. State removal is ownership-gated and requires explicit selection.

## Portable Windows installation

1. Verify `DipTrace-MCP-Portable-0.2.1.zip`.
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

## MCPB

`DipTrace-MCP-0.2.1-windows.mcpb` contains the self-contained Windows stdio server for compatible MCP clients.

Before using it:

1. verify its SHA-256 from the same release;
2. confirm version `0.2.1` and identity `io.github.fireostendere/diptrace-mcp`;
3. configure workspace/state paths;
4. start the server and call `get_capabilities`.

The MCPB does **not** silently install the DipTrace bridge. Live exchange requires the matching bridge/settings. See [MCP_DISTRIBUTION.md](MCP_DISTRIBUTION.md).

## Source installation for review/development

For the exact released source:

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
git checkout v0.2.1
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

A checkout of current `main` may contain post-release development that is not present in the published `v0.2.1` artifacts. Use a tag/commit when reproducibility matters.

## Post-release `main` features

Current `main` has additional internal schematic intelligence, PCB Generations A-D, 90% aggregate CI coverage and cinematic presentation tools after the immutable `v0.2.1` release.

Installing `diptrace-mcp==0.2.1` from PyPI does not imply that every later `main` feature is included in that published package.

## Evidence/limitations of the released artifacts

The immutable `v0.2.1` release record retains the evidence status that was true when it was cut, including Q1 Component Angle `NOT_RUN` at release time.

A later manual project campaign completed Q1 as PASS on a later accepted production checkpoint. That does not retroactively modify the released artifact's evidence record.

Similarly, an internal raw-preserving Component/Pattern Library mutation core now exists on later development and has controlled real-editor evidence, but it is not part of a newly expanded public native-library MCP write contract.

The project still does not claim:

- trusted Authenticode signing;
- universal DipTrace 5.x compatibility;
- native manufacturing generation/sign-off;
- Novarm/DipTrace endorsement;
- independent review or production readiness.

Runtime `get_capabilities` remains authoritative for an installed build and active document.
