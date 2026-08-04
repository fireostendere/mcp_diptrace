# Windows installer audit and design

Status: development-stage implementation on branch `feat/windows-one-click-installer`.
This document records the source audit and the intended evidence boundary. A
Linux/WSL checkout cannot substitute for the native Windows workflow.

## Baseline audit

The baseline was `main` at `e61e0637d246d0d2c3cdb27118fb221724a6027f`. The
existing path was:

| User action | Required program/permission | Failure point | Automation/rollback |
| --- | --- | --- | --- |
| Clone and create a venv | Git, Python, pip; no admin | missing tools or incompatible SDK | manual cleanup only |
| Install editable wheel and optional geometry | Python/pip; no admin | dependency/network/build failure | remove venv |
| Build bridge | Python, PyInstaller, PowerShell; no admin | missing runtime dependency or PyInstaller failure | replace the ignored bridge output |
| Copy four settings profiles | PowerShell; admin under Program Files | wrong DipTrace root, locked module, elevation | existing uninstall mode removes owned folders |
| Register Codex | Codex CLI and hand-written command | quoting, duplicate entry, wrong environment | manual edit; no transaction |
| Edit Claude config | JSON editor/manual edit | malformed JSON or lost unknown fields | no atomic backup path |
| Verify server/bridge | Python and manual MCP client | wrong state/workspace or stale process | manual diagnosis |

The baseline bridge was the checked-in `plugin/bridge_entry.py` packaged by
`plugin/build_bridge.ps1` with PyInstaller `--onefile`. The source uses the
existing SHA/session guards, allowed-root validation, Windows Job Object
handling, apply/cancel controls, and native Windows exchange metadata. The new
installer reuses that artifact and does not introduce a second bridge.

The four settings profiles are generated/maintained in `plugin/settings/`:

| DipTrace module | Profile | Import/export behavior |
| --- | --- | --- |
| PCB Layout | `pcb.settings.xml` | `Exp/Imp=All` |
| Schematic Capture | `schematic.settings.xml` | `Exp/Imp=All` |
| Component Editor | `component.settings.xml` | `Library=All`, `ImpMode=None` |
| Pattern Editor | `pattern.settings.xml` | `Library=All`, `ImpMode=None` |

The existing installer supported `C:\Program Files\DipTrace5` and
`C:\Program Files\DipTrace`, selected the first directory, and did not prove
module executables or registry evidence. The new detection checks both native
Program Files roots, matching uninstall registry entries, and known module
executables/plugin directories. Multiple candidates are shown for selection;
an unknown directory is rejected unless it passes the same layout check.

The server runtime needs the `diptrace_mcp` package, MCP SDK and Pydantic
runtime modules/metadata, `typing_extensions`, packaged skills, catalog and
shared schemas, provenance data, generated resources, and Shapely/GEOS only
when the geometry build is enabled and its probe passes. Tests, source PDFs,
`extracted_text`, local/private materials, secrets, release drafts, and dev
tools are not runtime data. The onedir spec records these boundaries.

Writable state is `%LOCALAPPDATA%\DipTraceMCP` by default (or the selected
state directory): sessions, records, backups, logs, and deferred Codex setup
commands. Projects remain in the user-selected workspace. Neither state nor
runtime metadata is intentionally written into Program Files or the installed
application directory.

## Target bundle

```text
%LOCALAPPDATA%\Programs\DipTraceMCP\
    app\diptrace_mcp_server.exe + runtime files
    bridge\diptrace_mcp_bridge.exe
    settings-templates\*.settings.xml
    tools\diptrace_mcp_configure\diptrace_mcp_configure.exe
    tools\install_plugin.ps1
    tools\uninstall_plugin.ps1
    LICENSE, README_FIRST.txt, VERSION
    installation-manifest.json
```

The server and configurator are PyInstaller `--onedir` applications. The
existing onefile bridge remains unchanged. Onedir avoids temporary extraction
at stdio startup, makes native geometry/import diagnostics inspectable, and
keeps replacement/rollback predictable.

The Inno Setup wizard supports Full, Server only, and Custom types, plus
workspace/state/client/DipTrace command-line parameters for silent CI. It uses
`PrivilegesRequired=lowest`; only a plugin copy/removal under protected
Program Files is launched through a narrowly scoped `runas` child. Client
configuration always runs in the original user context. The installer does
not download or execute remote code and does not alter Defender/SmartScreen.

## Configurator behavior

`src/diptrace_mcp/windows_configurator.py` is a separately testable,
stdlib-first module. It supports Codex, Claude Desktop, both, none, dry-run,
JSON output, unconfigure, and backup restore. It canonicalizes and validates
workspace/state/server paths, rejects symlink/reparse surprises where the
operation is critical, rejects state under the app/Program Files, and quotes
Unicode/spaced paths through argument vectors.

Codex uses the documented CLI registration shape when the CLI is available,
detects an existing `diptrace` entry, and updates idempotently without touching
other MCP servers. If the CLI is absent, a ready command is saved under the
state directory. Claude configuration is parsed as JSON, backed up with a
timestamped adjacent name, updated as one object, atomically replaced, and
parsed again. Malformed JSON fails closed without changing the original.

## Upgrade, repair, and uninstall

An upgrade replaces only manifest-owned application files, rechecks client
configuration, and refuses to proceed while an active
`diptrace_mcp_server.exe` process is present. It preserves workspace/state and
does not silently remove a live session. The manifest records version, app
root, plugin roots, state directory, and owned state categories.

Uninstall removes files recorded by Inno Setup/manifest and plugin directories
created by this installer. Client entry removal is an explicit checkbox and
uses the configurator's fail-closed unconfigure path. State/log removal is a
separate opt-in checkbox and is restricted to `logs`, `sessions`, `records`,
`offline_backups`, and `codex_setup.txt`. Workspaces, unknown files, client
backups, and user projects are never removed by the owned-state helper.

Rollback is file-level: restore the timestamped Claude/Codex backup or rerun
the previous installer, then use the manifest and preserved state to recover.
No Git history, release tag, or live workspace is rewritten.

## Evidence boundary

The Windows workflow is responsible for building the server/bridge/configurator,
compiling Inno Setup 6.4.2 from a hash-checked maintainer prerequisite,
creating `DipTrace-MCP-Setup-<version>.exe` and
`DipTrace-MCP-Portable-<version>.zip`, checking hashes/inventory, running
MCP stdio and installer smoke, measuring sizes/timings, and recording
Authenticode status. Until that workflow runs for this exact head, these are
source-level claims only. Synthetic DipTrace directory evidence is not live
DipTrace semantics; Q1 rotation and Novarm permission remain explicitly
unclaimed.
