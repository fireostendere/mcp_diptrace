# Headless GUI worker on Windows

DipTrace MCP can keep bounded native GUI operations away from the operator's normal
input desktop without requiring a virtual machine. Hidden mode creates a separate,
randomly named Win32 desktop object inside the current interactive Windows session
and launches a small helper there. Native mode is an explicit opt-in that runs on
the verified current `WinSta0` input desktop so the operator can see the editor.

This is **not** the Windows 10/11 Virtual Desktops feature. It uses Win32 desktop
objects under `WinSta0`, for example:

```text
WinSta0
├── Default              <- the user's visible desktop
└── DipTraceMCP-...      <- separate hidden DipTrace worker desktop
```

Desktop separation prevents UI interference with the operator's input desktop. It
is **not** a process, filesystem, network, token, privilege, or malware sandbox.

The implementation deliberately never calls `SwitchDesktop`, `SendInput`,
`SetCursorPos`, `mouse_event` or `keybd_event`. If a native action cannot be
performed through bounded Win32/UI automation, the operation fails instead of
stealing the user's physical keyboard or mouse.

## Scope

The primary authoring path remains DipTrace XML plus semantic MCP operations. The
Windows GUI worker is only for host actions that require a real DipTrace process.
The first supported native operation is a bounded round trip:

1. choose `hidden` or explicit `native` desktop mode;
2. launch the worker on the verified target desktop;
3. launch the requested DipTrace editor and open an existing project;
4. post the resolved native `File -> Save` menu command without focus or physical input;
5. post `WM_CLOSE` to the same window queue after Save and require normal process exit;
6. return structured evidence including PIDs, desktop/window-station/session
   identity and file SHA-256 before and after the operation.

Hidden mode is the default. Native mode is refused when the worker is elevated,
when the input desktop cannot be resolved, when the process is not attached to
`WinSta0`, or when the worker lands in a different Windows session.

The same worker can later support verified host actions such as exports, ERC/DRC
and refill/generation commands. Those actions should be added only after the
corresponding DipTrace controls have been verified on a real host.

## Requirements

- Windows 10 or Windows 11 in an interactive user session;
- a normal DipTrace installation accessible to that user;
- no elevation/UAC prompt required to start the selected DipTrace editor;
- for source installs, the optional `headless-gui` dependency group.

The hidden desktop is not Session 0 and is not designed to run as a Windows
service. Run the worker from the same normal user session that owns the DipTrace
installation and profile.

## Install from source

From PowerShell in the repository:

```powershell
py -m pip install -e ".[headless-gui]"
```

The source checkout does not install a separate `diptrace-mcp-headless-gui`
console entry point. Invoke the maintained module directly:

```powershell
py -m diptrace_mcp.headless_gui --help
```

## Hidden isolation smoke test

Run this before testing DipTrace itself:

```powershell
py -m diptrace_mcp.headless_gui smoke
```

A successful result is JSON with `"ok": true`. The test creates a separate hidden
desktop, starts a child process there, verifies that the child reports the expected
desktop name, and verifies that the physical input desktop did not change when
Windows allows it to be queried.

The test does not require DipTrace.

## Native desktop security smoke

The native launch primitive has a separate no-DipTrace probe:

```powershell
py -m diptrace_mcp.headless_gui native-smoke
```

It launches only the bundled probe process and verifies:

- the child's thread desktop matches the current input desktop;
- both processes are attached to `WinSta0`;
- the child remains in the same Windows session.

This probe may run on an elevated CI runner because it performs no DipTrace or UI
mutation. A real `roundtrip --desktop native` still fails closed when the caller
has an elevated token.

## Readiness check

Auto-detect DipTrace and verify that the automation backend is installed:

```powershell
py -m diptrace_mcp.headless_gui doctor --require-automation
```

Or specify the install directory explicitly:

```powershell
py -m diptrace_mcp.headless_gui doctor `
  --diptrace-root "C:\Program Files\DipTrace" `
  --require-automation
```

The report includes:

- hidden desktop smoke result;
- resolved DipTrace installation root;
- whether `pywinauto` is available;
- `physical_input_fallback: false`;
- `desktop_is_security_sandbox: false`.

## Native open/save/close round trip

PCB example:

```powershell
py -m diptrace_mcp.headless_gui roundtrip `
  --diptrace-root "C:\Program Files\DipTrace" `
  --editor pcb `
  --project "C:\work\board.dip"
```

Schematic example:

```powershell
py -m diptrace_mcp.headless_gui roundtrip `
  --diptrace-root "C:\Program Files\DipTrace" `
  --editor schematic `
  --project "C:\work\design.dch"
```

Available editor identifiers are `pcb`, `schematic`, `component` and `pattern`.
The command returns JSON. `ok: false` is bounded failure evidence and must not be
silently retried with coordinate/mouse automation.

### Save delivery and completion

The worker resolves the project window by project filename and native menu. It
uses the menu's own `WM_COMMAND` or `WM_MENUCOMMAND` value; it does not call
`menu_select()`, focus the window, or synthesize `Ctrl+S`. DipTrace 5.3's
owner-drawn default `File -> Save` item has a validated numeric-menu fallback.

Save and `WM_CLOSE` are posted to the same target window queue in that order.
The result is successful only when DipTrace exits normally. A timeout requires
forced termination and is returned as `ok: false`, so a posted-but-unprocessed
Save cannot be reported as a completed round trip.

## Hidden cinematic capture

The same isolation layer also supports presentation-only MP4/GIF capture. The
capture worker renders the real DipTrace project window into BGRA frames with
`PrintWindow`/`WM_PRINT` and pipes them to ffmpeg without switching desktops or
using physical input. See [Cinematic Demo Mode](CINEMATIC_DEMO_MODE.md) and the
[I²C level-shifter GIF](../i2c-level-shifter-demo.gif).

## Launch modes

The worker supports two modes selected with `--desktop`:

- `hidden` (default): the editor starts on a separate randomly named Win32 desktop
  under `WinSta0` and stays invisible to the operator;
- `native`: the editor starts visibly on the verified current input desktop.

Native example:

```powershell
py -m diptrace_mcp.headless_gui roundtrip `
  --diptrace-root "C:\Program Files\DipTrace" `
  --editor pcb `
  --project "C:\work\board.dip" `
  --desktop native
```

Native launch does not rely on an unspecified inherited desktop. The launcher sets
`STARTUPINFO.lpDesktop` explicitly to `WinSta0\<current-input-desktop>`, verifies
the child session, and the worker verifies its desktop, window station and session
again before performing DipTrace work.

Native mode fails closed when:

- the input desktop cannot be resolved;
- the process window station is not `WinSta0`;
- the caller/worker is elevated;
- the worker is attached to an unexpected desktop/window station/session.

If the input desktop changes after a Save may already have occurred, the caller
does not discard the result. It returns `ok: false` with
`desktop_changed: true` and retains PID/SHA/evidence fields so an operator can
review the side effect without unsafe automatic retry.

## Bundled Windows build

`scripts/build_windows_server.ps1` builds the helper with the standalone MCP
server. The helper is placed under:

```text
diptrace_mcp_server\
└── tools\
    └── diptrace_mcp_headless_gui\
        └── diptrace_mcp_headless_gui.exe
```

The Windows build runs both the hidden-desktop test and the real native desktop
security probe without requiring DipTrace. The packaged helper is included with
the per-user server installer and portable artifact.

Example after installation:

```powershell
& "<install-root>\app\tools\diptrace_mcp_headless_gui\diptrace_mcp_headless_gui.exe" smoke
```

## Installer privilege boundary

Windows distribution deliberately separates the per-user MCP installation from
the administrator-only DipTrace plug-in installation:

- `DipTrace-MCP-Setup-<version>.exe` uses `PrivilegesRequired=lowest`, installs
  the server/configurator under the user's selected/per-user path, and never
  contains or launches a privileged plug-in installation path;
- `DipTrace-MCP-Plugin-Setup-<version>.exe` uses
  `PrivilegesRequired=admin`, contains its bridge/settings payload inside that
  installer, and writes only the bounded `Plugins\<module>\DipTraceMCP`
  integration plus its own administrator-owned uninstall metadata.

The elevated plug-in installer does **not** execute scripts or copy executable
payload from `%LOCALAPPDATA%` or from the per-user MCP installation. It does not
modify Codex/Claude configuration, workspace, state, or user profiles.

## Safety invariants

The implementation must retain all of these properties:

- never switch the user's input desktop;
- never synthesize physical mouse or keyboard input;
- never fall back from a failed control operation to screen coordinates;
- keep XML/semantic operations as the default authoring path;
- validate the selected DipTrace installation and project before starting the host;
- refuse visible/native DipTrace work from an elevated token;
- explicitly verify desktop, `WinSta0` window station and session identity;
- use bounded timeouts and terminate a stuck worker rather than block indefinitely;
- require normal DipTrace exit before reporting an open/Save/close round trip as successful;
- retain structured evidence when a post-side-effect desktop change is detected;
- keep the admin plug-in payload separate from user-writable installer payload;
- do not expand the public MCP tool contract merely to expose Windows-worker details.

## CI and real-host evidence

Windows CI contains real Win32 hidden-desktop and native-desktop process probes.
They verify desktop creation/targeting, `WinSta0` attachment and session identity
without requiring DipTrace. The Windows packaging workflow also builds and tests
the split per-user/admin installer boundary.

The repository includes one real-host I²C schematic capture and controlled
open/save/reopen evidence. Hosted GitHub runners do not provide the licensed/local
DipTrace installation used for that evidence. Passing CI proves the bounded
Windows primitives and packaging, not universal DipTrace UI compatibility.
