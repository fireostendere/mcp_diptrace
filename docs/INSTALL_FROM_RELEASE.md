# Install from GitHub Release Assets

## Publication status

The latest published GitHub release is `v0.1.2`.

The current source/package version is `0.2.0`, but `v0.2.0` is not tagged or
published while the remaining real Windows/DipTrace/client acceptance gates are
open. The 0.2.0 installer and portable bundle are successful CI build outputs,
not public release downloads yet.

Do not infer that a candidate filename exists on the Releases page until an
actual `v0.2.0` release is published.

## Published v0.1.2 assets

Use the immutable
[GitHub Release v0.1.2](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.2)
and download assets from that same release.

The v0.1.2 release includes the Python package, bridge/plugin assets,
`SHA256SUMS.txt`, and its dated review/acceptance records. It does not include
the later 0.2.0 one-click installer and portable bundle.

The project is not published to PyPI. The v0.1.2 Windows binary is unsigned.

## Verify SHA-256

Linux/WSL:

```bash
sha256sum -c SHA256SUMS.txt
```

Windows PowerShell:

```powershell
Get-FileHash .\diptrace_mcp-0.1.2-py3-none-any.whl -Algorithm SHA256
Get-FileHash .\diptrace_mcp_bridge.exe -Algorithm SHA256
Get-FileHash .\diptrace_mcp_windows_plugin-0.1.2.zip -Algorithm SHA256
```

Each value must match the corresponding line in the release's
`SHA256SUMS.txt`. A matching hash proves correspondence with the published
bytes; it does not prove trusted signing or safety.

## Install the v0.1.2 wheel

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install `
  .\diptrace_mcp-0.1.2-py3-none-any.whl
.\.venv\Scripts\diptrace-mcp.exe --help
```

Linux/WSL:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install ./diptrace_mcp-0.1.2-py3-none-any.whl
diptrace-mcp --help
```

The wheel contains the MCP server and packaged skills. It does not contain a
complete Windows plug-in installation.

## Install the v0.1.2 Windows plug-in package

1. Unpack `diptrace_mcp_windows_plugin-0.1.2.zip`.
2. Close every DipTrace module.
3. Open PowerShell as Administrator only when installing below a protected
   DipTrace directory.
4. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install_plugin.ps1
   ```

5. Check the PCB, Schematic, Component, and Pattern settings profiles.
6. Restart DipTrace and open `Tools → Plugins → DipTrace MCP Bridge`.

The plug-in package and server must come from the same published release.

## Configure an MCP client for v0.1.2

### Codex on Windows

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\Users\you\path\to\.venv\Scripts\diptrace-mcp.exe"
```

### Codex in WSL

```bash
codex mcp add diptrace \
  --env DIPTRACE_MCP_WORKSPACE=/mnt/c/Users/you/Documents/DipTrace \
  --env DIPTRACE_MCP_STATE_DIR=/mnt/c/Users/you/AppData/Local/DipTraceMCP \
  -- /path/to/.venv/bin/diptrace-mcp
```

The Windows bridge owns the Windows-native exchange path. A WSL server may
derive `/mnt/<drive>/...` only in memory and must not persist the translated path
back into Windows-origin session metadata.

After updating either the server or bridge, finish or abandon the old session
through supported operations and start a fresh DipTrace plug-in session.

## Planned v0.2.0 ordinary Windows path

After `v0.2.0` is actually published, the intended primary asset is:

```text
DipTrace-MCP-Setup-0.2.0.exe
```

The intended fallback is:

```text
DipTrace-MCP-Portable-0.2.0.zip
```

The one-click installer is designed to:

- install a self-contained server under
  `%LOCALAPPDATA%\Programs\DipTraceMCP`;
- keep writable state under `%LOCALAPPDATA%\DipTraceMCP` or a selected state
  directory;
- configure Codex, Claude Desktop, both, or neither;
- preserve JSON/TOML formatting and create client-configuration backups;
- install plug-in files into validated DipTrace locations;
- request elevation only for protected Program Files paths;
- preserve workspaces, backups, logs, and user state by default on uninstall;
- avoid downloading Python or runtime code during end-user installation.

The portable bundle is intended to contain the same standalone server, bridge,
four settings profiles, configurator, and helper scripts without requiring
Python.

These are design and CI-build facts, not claims that the 0.2.0 files are already
available publicly.

## Intended v0.2.0 verification flow

Once a real `v0.2.0` release exists:

1. download the installer or portable ZIP from that exact release;
2. download `SHA256SUMS.txt` from the same release;
3. verify the selected asset hash;
4. run the installer or extract the portable bundle;
5. restart the configured MCP client;
6. call `get_capabilities`;
7. verify the expected workspace, state directory, client configuration, and
   DipTrace plug-in profiles;
8. keep in mind that the executables are unsigned unless the release record
   explicitly proves otherwise.

## Current candidate limitations

A successful Windows build or install does not establish:

- universal DipTrace 5.x compatibility;
- real semantics for every registered write tool;
- Component Angle GUI/re-export validation;
- native Component/Pattern Library mutation;
- native Gerber/NC Drill/manufacturing output;
- trusted signing;
- Novarm/DipTrace endorsement or permission;
- production readiness.

Runtime `get_capabilities` remains authoritative for the installed version and
active document.