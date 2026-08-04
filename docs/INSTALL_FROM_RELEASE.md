# Install from GitHub Release Assets

## Windows one-click path

The target primary Windows asset is `DipTrace-MCP-Setup-<version>.exe`. This is
the ordinary user flow once a release publishes it:

1. Download the installer and verify its SHA-256 against `SHA256SUMS.txt`.
2. Run it and choose the DipTrace project workspace.
3. Choose Codex, Claude Desktop, both, or no client configuration.
4. Click Install, then restart the MCP client.
5. Verify `get_capabilities`.

The installer is Windows-only, currently unsigned, and development-stage. It
does not download code, Python, or dependencies during installation. The
server is installed as an onedir self-contained application under
`%LOCALAPPDATA%\Programs\DipTraceMCP`; writable state and install logs are
kept under `%LOCALAPPDATA%\DipTraceMCP` (or the chosen state directory).
DipTrace plug-in files under protected `Program Files` paths are the only
operation that may trigger a narrowly scoped elevation prompt. The workspace,
state backups, logs, and client backups are preserved by default on uninstall.

The target fallback asset is `DipTrace-MCP-Portable-<version>.zip`. Extract it, run
`tools\diptrace_mcp_configure.exe` or the packaged helper, choose a workspace,
and run the server smoke check. It does not require Python.

The bundle's current geometry status is determined by the Windows CI exact
geometry probe. Do not infer full geometry, universal DipTrace compatibility,
Q1 rotation validation, or Novarm permission from a successful install.

This is the no-clone installation path for the development-stage `v0.1.2`
release. Use the [GitHub Release v0.1.2](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.2)
page and download the assets for the same version:

- `diptrace_mcp-0.1.2-py3-none-any.whl`;
- `diptrace_mcp-0.1.2.tar.gz`;
- `diptrace_mcp_bridge.exe`;
- `diptrace_mcp_windows_plugin-0.1.2.zip`;
- `SHA256SUMS.txt`; and
- `LIVE_ACCEPTANCE_2026-07-31.md` and `CODE_REVIEW_2026-07-31.md`.

The Python package is not published to PyPI. The Windows binary is unsigned.
Use the GitHub release URL as the source and verify the checksums before use.

No new release or tag was created by the installer work. Therefore the two
`DipTrace-MCP-*` names above describe the future asset set and are not claims
that the existing `v0.1.2` page already contains them.

The wheel/source procedure below is the Advanced / Developer installation
path. It remains useful for Linux, macOS, WSL, maintainers, and users who need
editable Python code.

## 1. Verify SHA-256

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

Each reported value must exactly match the corresponding line in
`SHA256SUMS.txt`. A matching hash proves correspondence with the published
asset; it does not prove that an unsigned binary is safe or signed.

## 2. Install the wheel in a clean environment

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install `
  .\diptrace_mcp-0.1.2-py3-none-any.whl
.\.venv\Scripts\diptrace-mcp.exe --help
```

WSL/Linux:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install ./diptrace_mcp-0.1.2-py3-none-any.whl
diptrace-mcp --help
```

The release wheel contains the MCP server and packaged skills. It does not
contain the Windows plug-in installer or settings.

## 3. Install the Windows plug-in package

1. Unpack `diptrace_mcp_windows_plugin-0.1.2.zip`.
2. Close every DipTrace module.
3. Open PowerShell as Administrator when installing below a protected DipTrace
   directory.
4. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install_plugin.ps1
   ```

5. Check all four settings profiles: PCB, Schematic, Component, and Pattern.
6. Restart DipTrace and open `Tools → Plugins → DipTrace MCP Bridge`.

The package must contain `diptrace_mcp_bridge.exe`, the installer, four
`settings/*.settings.xml` profiles, `LICENSE`, `LIVE_EXCHANGE_PATHS.md`, and
this release-install guidance (or its short packaged equivalent).

## 4. Configure an MCP client

Codex on Windows:

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\Users\you\path\to\.venv\Scripts\diptrace-mcp.exe"
```

Codex in WSL:

```bash
codex mcp add diptrace \
  --env DIPTRACE_MCP_WORKSPACE=/mnt/c/Users/you/Documents/DipTrace \
  --env DIPTRACE_MCP_STATE_DIR=/mnt/c/Users/you/AppData/Local/DipTraceMCP \
  -- /path/to/.venv/bin/diptrace-mcp
```

The Windows bridge owns the Windows-native exchange path. The WSL server may
derive a `/mnt/<drive>/...` path only in memory. Every live session must report
`exchange_path_platform="windows"`.

## 5. Start a fresh session after an update

After replacing the wheel or plug-in:

1. close the old bridge session;
2. delete or abandon stale session state only through the supported MCP/client
   operation;
3. do not edit `metadata.json` manually;
4. start a new DipTrace plug-in session; and
5. verify `exchange_path_platform="windows"` before reading or requesting an
   edit.

The WSL path is computed in memory only and must not be persisted back into
session metadata. A fresh session avoids mixing state created by different
bridge versions.

## 6. Unsigned status and limitations

The Windows bridge is unsigned. A SmartScreen warning is not evidence of either
maliciousness or safety. Verify the SHA-256 values and the source GitHub Release
URL. This is an alpha/development-stage integration, not a production-ready
replacement for DipTrace. Runtime availability and supported operations remain
document- and installation-specific; use `get_capabilities` as the source of
truth.
