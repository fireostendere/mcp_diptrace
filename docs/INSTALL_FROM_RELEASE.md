# Install from Published Release Assets

## Current published release

Version `v0.4.0` is the current published GitHub/PyPI distribution line. Keep
every downloaded artifact on the same immutable version and verify checksums
before execution.

Published GitHub assets:

```text
DipTrace-MCP-Setup-0.4.0.exe
DipTrace-MCP-Plugin-Setup-0.4.0.exe
DipTrace-MCP-Portable-0.4.0.zip
SHA256SUMS.txt
```

Published PyPI artifacts:

```text
diptrace_mcp-0.4.0-py3-none-any.whl
diptrace_mcp-0.4.0.tar.gz
```

A v0.4.0 MCPB was not attached to this release. Do not invent or mix an older
MCPB with the v0.4.0 bridge/runtime identity.

## Linux one-command installation

Validated release path: Ubuntu/Debian-style x86-64, with Ubuntu 24.04 used by the
permanent clean-install gate.

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/v0.4.0/scripts/install_linux.sh \
  | bash -s -- --accept-diptrace-license
```

The installer verifies the v0.4.0 portable bundle/checksum manifest, installs the
pinned DipTrace/Wine path after explicit license acceptance, installs bridge and
wrappers, and provides visible plus private-Xvfb headless GUI modes. See
[LINUX.md](LINUX.md).

## macOS one-command installation

The tested macOS 15 path covers Apple Silicon and Intel and uses the Wine runtime
bundled in the official DipTrace.app:

```bash
curl -fsSL https://raw.githubusercontent.com/fireostendere/mcp_diptrace/v0.4.0/scripts/install_macos.sh \
  | bash -s -- --accept-diptrace-license
```

On Apple Silicon without Rosetta, after reviewing Apple's terms, add
`--accept-rosetta-license`. See [MACOS.md](MACOS.md).

## PyPI

Python 3.10 or newer:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.4.0
diptrace-mcp --help
```

The Python package contains the MCP server and packaged skills. It does not
silently install the native DipTrace bridge plug-in.

`0.4.0` was published through GitHub OIDC Trusted Publishing. That establishes
publication provenance, not Authenticode trust, universal compatibility or
production readiness.

## Verify GitHub release hashes

Download `SHA256SUMS.txt` from the same `v0.4.0` GitHub release.

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

PowerShell for an individual file:

```powershell
Get-FileHash .\DipTrace-MCP-Setup-0.4.0.exe -Algorithm SHA256
```

The digest must match the release manifest. A matching SHA-256 proves byte
identity, not publisher signing.

## Recommended Windows installation

1. Close affected DipTrace modules and the MCP client being configured.
2. Verify the installer hash from the same v0.4.0 release.
3. Run `DipTrace-MCP-Setup-0.4.0.exe` normally for the per-user MCP
   server/configurator.
4. Run `DipTrace-MCP-Plugin-Setup-0.4.0.exe` separately with administrator
   privileges when machine-wide DipTrace integration is required.
5. Restart DipTrace and the configured MCP client.
6. Call `get_capabilities` before relying on document-specific paths.

Windows binaries remain unsigned, so SmartScreen may warn. Workspaces and user
state are preserved by default on uninstall; owned-state removal is explicit.

## Portable Windows installation

1. Verify `DipTrace-MCP-Portable-0.4.0.zip` against `SHA256SUMS.txt`.
2. Extract it to a stable local directory.
3. Read `README_FIRST.txt` and verify the internal checksums.
4. Run the included helper/configuration path as appropriate.
5. Restart the MCP client and call `get_capabilities`.

A separate Python installation is not required for the frozen Windows runtime.

## Exact released source

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
git checkout v0.4.0
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

A checkout of current `main` may contain post-release changes not present in
published v0.4.0 bytes. Use the tag when reproducibility matters.

## Evidence and limitations

The v0.4.0 release is backed by exact-candidate Windows, Ubuntu 24.04, macOS
Apple Silicon/Intel and package validation gates plus the recorded historical
manual DipTrace evidence. Those are bounded claims, not universal compatibility.

The project still does not claim trusted Authenticode signing, native
manufacturing sign-off, Novarm/DipTrace endorsement, independent review,
field-solver/PI/EMC/thermal sign-off or production readiness.

Runtime `get_capabilities` remains authoritative for an installed build and
active document.
