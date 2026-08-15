# Windows Installer and Portable Bundle

## Status

The immutable `v0.3.0` development prerelease publishes the hardened split
Windows packaging line. It separates the per-user MCP installation from the
administrator-only DipTrace plug-in installation:

- `DipTrace-MCP-Setup-<version>.exe` — per-user server/configurator installer;
- `DipTrace-MCP-Plugin-Setup-<version>.exe` — administrator-only DipTrace plug-in
  installer with a self-contained bridge/settings payload;
- `DipTrace-MCP-Portable-<version>.zip`;
- release checksums/provenance records.

These `v0.3.0` binaries remain unsigned. Older published assets retain their
original identities and checksums, and a future signed/corrected build requires
a new version.

## Design goals

The Windows packaging path is designed to:

- avoid requiring a developer Git/Python environment for normal installation;
- keep writable state out of Program Files;
- preserve user workspaces/state on ordinary uninstall;
- keep MCP client configuration in the original user context;
- keep the user installer permanently non-elevated;
- put all Program Files/DipTrace plug-in writes behind a separate, narrowly
  scoped administrator installer;
- prevent an elevated component from executing scripts or copying executable
  payload out of the per-user `%LOCALAPPDATA%` installation;
- support deterministic installer/portable CI smoke and checksum/provenance
  auditing;
- reuse the existing bridge/session/SHA safety model rather than creating a
  second bridge implementation.

## Split privilege architecture

### Per-user installer

`DipTrace-MCP-Setup-<version>.exe` uses:

```text
PrivilegesRequired=lowest
```

It installs only:

- the standalone MCP server/runtime;
- the Windows configurator;
- state/manifest helpers;
- license/readme/version metadata.

It configures Codex/Claude only in the original user's profile context. It does
not contain the DipTrace bridge/settings plug-in payload, does not contain an
elevation script, and never calls `runas`.

Default application/state locations remain under the user's local application
data unless explicitly changed.

### Administrator plug-in installer

`DipTrace-MCP-Plugin-Setup-<version>.exe` uses:

```text
PrivilegesRequired=admin
```

It is a separate self-contained artifact. Its installer payload contains the
exact bridge executable and four settings profiles that it will copy into the
validated DipTrace installation.

The elevated installer:

- does not read bridge/scripts/settings from `%LOCALAPPDATA%`;
- does not read payload from the per-user DipTrace MCP installation;
- does not configure Codex or Claude;
- does not read/write MCP workspace or state;
- writes only its own admin-owned uninstall metadata/payload and the bounded
  `Plugins\<module>\DipTraceMCP` directories;
- verifies copied bridge/settings SHA-256 against its own extracted
  administrator-owned payload;
- removes only those owned plug-in directories on uninstall.

This is the security boundary. The user installer and administrator installer
are intentionally independent; the per-user installer does not launch the
administrator installer as a child.

## Components

The full Windows build pipeline still assembles project-owned artifacts including:

- standalone `diptrace_mcp` server runtime;
- `diptrace_mcp_bridge.exe`;
- PCB/Schematic/Component/Pattern settings profiles;
- Windows configurator;
- portable install/uninstall helpers;
- license/version/readme metadata;
- installation manifests/checksums where applicable.

The split Inno Setup artifacts select different subsets of that controlled build
stage. The portable ZIP still contains the complete maintenance bundle; for
protected DipTrace roots the dedicated administrator plug-in installer is the
preferred packaged privilege boundary.

## DipTrace module profiles

The shipped settings profiles cover:

| DipTrace module | Profile purpose |
| --- | --- |
| PCB Layout | PCB XML import/export bridge path |
| Schematic Capture | schematic XML import/export bridge path |
| Component Editor | Component Library bridge/settings path |
| Pattern Editor | Pattern Library bridge/settings path |

A profile being present in an artifact does not by itself prove every semantic
operation for every DipTrace version. Runtime capability and real-host acceptance
remain separate.

## Install location and writable state

The per-user application is installed under the selected user application
location. Writable project-owned state defaults to the user's local
application-data area rather than Program Files.

State includes sessions, records, backups/logs and related local metadata.
Project files remain in the user-selected workspace.

Uninstall preserves user workspace/state by default. Owned-state removal is
explicit and ownership-gated.

The administrator plug-in install stores only its own uninstall metadata/payload
under its administrator-owned application directory and the owned DipTrace
`DipTraceMCP` plug-in directories. It does not own user workspace/state.

## Client configuration

The configurator supports project-owned configuration for supported MCP clients
while preserving unknown existing fields and using backup/atomic-update rules.

A configuration change requires an actual client restart before it can be
considered tested. The accepted project campaign has real Codex restart evidence
and operator-confirmed Claude Desktop restart evidence from a separate machine.

The administrator plug-in installer never runs the client configurator.

## Build

Typical source build commands on Windows:

```powershell
.\scripts\build_windows_server.ps1 -PythonCommand python -Clean
.\plugin\build_bridge.ps1 -PythonCommand python -Clean
.\scripts\build_windows_configurator.ps1 -PythonCommand python -Clean
.\scripts\build_windows_installer.ps1 `
  -Version <next-version> `
  -IsccPath "$env:ISCC_PATH"
```

The installer build emits both Inno Setup executables plus the portable ZIP and
one release checksum manifest covering all three assets.

Use the actual selected future version when preparing a new release. Do not
rebuild different binaries under any immutable published identity, including
`0.3.0`.

## CI / automated evidence

Windows automation covers:

- frozen server/bridge/configurator build and startup smoke;
- a real hidden Win32 desktop process-isolation probe;
- a real native `WinSta0` desktop/window-station/session targeting probe that
  does not require DipTrace;
- separate per-user and administrator Inno Setup builds;
- proof that the per-user install contains no bridge/settings/elevation script;
- separate plug-in install/repair/uninstall against a synthetic validated
  DipTrace root;
- per-user install/repair/uninstall and owned-state preservation/removal;
- paths containing spaces/Unicode;
- frozen MCP stdio initialize/tools/list/capabilities/XML smoke;
- checksums/provenance inventories;
- explicit unsigned-binary fail-closed signing checks for both installers.

CI evidence is necessary but not equivalent to a real licensed DipTrace semantic
round trip.

## Current manual acceptance boundary

Historical project acceptance already records:

- `windows_clean_install_repair_uninstall` PASS;
- `elevated_plugin_install_profile_preservation` PASS;
- `custom_state_preservation` PASS.

Those PASS records remain valid historical evidence for their exact accepted
candidates. The new split-installer architecture is a changed packaging/security
claim and therefore receives its own impact-based CI evidence; a future release
candidate should receive claim-appropriate real-host verification without
restarting unrelated historical acceptance campaigns.

## Installation verification

For the published split-installer build:

1. obtain the per-user installer, plug-in installer and `SHA256SUMS.txt` from the
   same release/tag;
2. verify SHA-256;
3. run the per-user installer normally, without elevation;
4. run the plug-in installer separately when DipTrace integration is desired;
5. restart DipTrace and the selected MCP client;
6. call `get_capabilities`;
7. use native open/save/re-export acceptance only when a specific live semantic
   path requires proof.

For immutable `v0.3.0` filenames and checksums, see
[INSTALL_FROM_RELEASE.md](INSTALL_FROM_RELEASE.md).

## Boundaries and non-claims

- current development Windows executables are unsigned unless signing is
  explicitly required and verified;
- successful CI build/install smoke is not Authenticode trust;
- the split privilege boundary is not a claim that Win32 desktop isolation is a
  security sandbox;
- the installer does not prove universal DipTrace 5.x compatibility;
- the MCPB does not silently install the DipTrace bridge;
- a shipped settings profile does not prove every write path;
- clean-machine/project lifecycle evidence remains bound to the exact candidate;
- Novarm/DipTrace endorsement, independent review and production readiness are
  not claimed.
