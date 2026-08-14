# Windows Installer and Portable Bundle

## Status

The Windows installer/portable/configurator implementation is merged and published in the immutable `v0.2.1` development prerelease. The old `feat/windows-one-click-installer` wording was a historical implementation-branch note and is no longer the current project status.

Published `v0.2.1` Windows distribution includes:

- `DipTrace-MCP-Setup-0.2.1.exe`;
- `DipTrace-MCP-Portable-0.2.1.zip`;
- `DipTrace-MCP-0.2.1-windows.mcpb`;
- the separately packaged live XML bridge/settings in the installer/portable path;
- release checksums/provenance records.

The binaries are unsigned alpha/development assets.

## Design goals

The Windows packaging path is designed to:

- avoid requiring a developer Git/Python environment for normal installation;
- keep writable state out of Program Files;
- preserve user workspaces/state on ordinary uninstall;
- keep client configuration in the original user context;
- elevate only the narrowly scoped DipTrace plug-in copy/removal when Program Files requires it;
- support deterministic installer/portable CI smoke and checksum/provenance auditing;
- reuse the existing bridge/session/SHA safety model rather than creating a second bridge implementation.

## Components

The installer/portable build is assembled from project-owned artifacts including:

- standalone `diptrace_mcp` server runtime;
- `diptrace_mcp_bridge.exe` live XML bridge;
- PCB/Schematic/Component/Pattern settings profiles;
- Windows configurator;
- plug-in install/uninstall helpers;
- license/version/readme metadata;
- installation manifest/checksums where applicable.

The server/configurator use frozen Windows application builds. The bridge remains the project-owned DipTrace exchange process and uses the same allowed-root/session/SHA/apply/cancel boundaries as source execution.

## DipTrace module profiles

The shipped settings profiles cover:

| DipTrace module | Profile purpose |
| --- | --- |
| PCB Layout | PCB XML import/export bridge path |
| Schematic Capture | schematic XML import/export bridge path |
| Component Editor | Component Library bridge/settings path |
| Pattern Editor | Pattern Library bridge/settings path |

A profile being present in the bundle does not by itself prove every semantic operation for every DipTrace version. Runtime capability and real-host acceptance remain separate.

## Install location and writable state

The frozen application is installed under the selected Windows application location. Writable project-owned state defaults to the user's local application-data area rather than Program Files.

State includes sessions, records, backups/logs and related local metadata. Project files remain in the user-selected workspace.

Uninstall preserves user workspace/state by default. Owned-state removal is explicit and ownership-gated.

## Privilege boundary

Normal application/client configuration should run without silently changing user identity/context.

When a DipTrace installation under protected Program Files requires elevation, only the narrow plug-in copy/removal action is elevated. Client JSON/configuration continues in the original user's profile so an administrator token does not redirect configuration into the wrong account.

## Client configuration

The configurator supports project-owned configuration for supported MCP clients while preserving unknown existing fields and using backup/atomic-update rules.

A configuration change requires an actual client restart before it can be considered tested. The accepted project campaign has real Codex restart evidence and operator-confirmed Claude Desktop restart evidence from a separate machine.

## Build

Typical source build commands on Windows:

```powershell
.\scripts\build_windows_server.ps1 -PythonCommand python -Clean
.\plugin\build_bridge.ps1 -PythonCommand python -Clean
.\scripts\build_windows_configurator.ps1 -PythonCommand python -Clean
.\scripts\build_windows_installer.ps1 `
  -Version 0.2.1 `
  -IsccPath "$env:ISCC_PATH"
```

Use the actual selected future version when preparing a new release; do not rebuild a different binary under the immutable `0.2.1` identity.

## CI / automated evidence

Windows automation covers implementation-level checks such as:

- frozen server/bridge/configurator build and startup smoke;
- installer and portable creation;
- silent install/repair/uninstall paths in CI;
- paths containing spaces/Unicode where covered by tests;
- client configuration backup/atomic update;
- workspace/state preservation/ownership behavior;
- checksums/provenance inventories;
- explicit unsigned-binary status.

CI evidence is necessary but not equivalent to the project-level clean real-machine acceptance gate.

## Current manual acceptance boundary

Post-release real-host validation now has:

- `windows_clean_install_repair_uninstall` PASS, including operator-confirmed from-zero installation on a separate new Windows machine;
- `elevated_plugin_install_profile_preservation` PASS on exact candidate `9af6da2` and Windows 11 build `26200` with DipTrace `5.3.0.2`;
- `custom_state_preservation` PASS by operator confirmation from a separate machine.

The formal lifecycle sequence is complete. The elevated gate found and fixed protected-root detection and a flattened frozen-configurator runtime; schematic/native gates were unaffected and were not repeated.

These gates should be run against the exact production candidate/artifacts whose compatibility is being claimed. Do not copy a PASS from an older candidate onto later `main` merely because the installer code looks similar.

## Installation verification

For the published version:

1. download the installer/portable asset and `SHA256SUMS.txt` from the same `v0.2.1` prerelease;
2. verify SHA-256;
3. install/configure;
4. restart DipTrace and the selected MCP client;
5. call `get_capabilities`;
6. use native open/save/re-export acceptance when a specific live semantic path requires proof.

See [INSTALL_FROM_RELEASE.md](INSTALL_FROM_RELEASE.md).

## Boundaries and non-claims

- Windows executables are unsigned;
- successful CI build/install smoke is not Authenticode trust;
- the installer does not prove universal DipTrace 5.x compatibility;
- the MCPB does not silently install the DipTrace bridge;
- a shipped settings profile does not prove every write path;
- clean-machine/project lifecycle gates remain evidence-bound to the exact candidate;
- Novarm/DipTrace endorsement, independent review and production readiness are not claimed.
