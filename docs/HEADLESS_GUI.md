# Headless GUI worker on Windows

DipTrace MCP can isolate the remaining native GUI operations from the user's normal
Windows desktop without requiring a virtual machine. The worker creates a separate
Win32 desktop object inside the current interactive Windows session and launches a
small helper process there. DipTrace is then started as a child of that helper.

This is **not** the Windows 10/11 Virtual Desktops feature. It uses Win32 desktop
objects under `WinSta0`, for example:

```text
WinSta0
├── Default              <- the user's visible desktop
└── DipTraceMCP-...      <- isolated DipTrace worker desktop
```

The implementation deliberately never calls `SwitchDesktop`, `SendInput`,
`SetCursorPos`, `mouse_event` or `keybd_event`. If a native action cannot be
performed through bounded Win32/UI automation, the operation fails instead of
stealing the user's physical keyboard or mouse.

## Scope

The primary authoring path remains DipTrace XML plus semantic MCP operations. The
headless GUI worker is only for host actions that require a real DipTrace process.
The first supported native operation is a bounded round trip:

1. create a private Win32 desktop;
2. launch the worker on that desktop;
3. launch the requested DipTrace editor and open an existing project;
4. invoke `File -> Save` through the Win32 automation backend;
5. close the editor;
6. return structured evidence including PIDs, desktop names and file SHA-256 before
   and after the operation.

The same isolation layer is intended for later verified host actions such as
exports, ERC/DRC, refill/generation commands and other operations that cannot be
completed safely from XML alone. Those actions should be added only after the
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

## Isolation smoke test

Run this before testing DipTrace itself:

```powershell
py -m diptrace_mcp.headless_gui smoke
```

A successful result is JSON with `"ok": true`. The test creates a private desktop,
starts a child process there, verifies that the child reports the expected desktop
name, and verifies that the physical input desktop did not change when Windows
allows it to be queried.

The test does not require DipTrace.

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
- `physical_input_fallback: false` as an explicit safety invariant.

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
The command returns JSON. `ok: false` is a bounded failure and should be treated as
host evidence, not silently retried with coordinate/mouse automation.

## Launch mode

The worker supports two launch modes, selected with `--desktop`:

- `hidden` (default): the editor starts on a private Win32 desktop under `WinSta0`
  and stays invisible to the operator. This is the original isolation behaviour.
- `native`: the editor starts directly on the operator's current interactive desktop
  and remains visible. Use this when an operator wants to watch the round trip, or
  when a sandbox/VM already provides isolation and the extra hidden desktop is
  undesirable.

Native example:

```powershell
py -m diptrace_mcp.headless_gui roundtrip `
  --diptrace-root "C:\Program Files\DipTrace" `
  --editor pcb `
  --project "C:\work\board.dip" `
  --desktop native
```

In `native` mode the worker inherits the current desktop, so the window is visible
and the worker verifies it landed on the expected (`before`) input desktop. If the
current input desktop cannot be determined, the operation fails closed with
`native launch declined` instead of guessing. All other safety invariants
(no `SwitchDesktop`, no synthesized input, bounded timeouts) apply unchanged. The
evidence JSON reports the chosen `desktop_mode` so a caller can distinguish the two.

## Bundled Windows build

`scripts/build_windows_server.ps1` now builds the helper together with the normal
standalone MCP server. The helper is placed under the server distribution at:

```text
diptrace_mcp_server\
└── tools\
    └── diptrace_mcp_headless_gui\
        └── diptrace_mcp_headless_gui.exe
```

Because the existing Windows installer copies the complete standalone server
folder, the same helper is included in the normal installer/portable artifact.
No separate Python installation is required for that packaged executable.

Example after installation:

```powershell
& "<install-root>\app\tools\diptrace_mcp_headless_gui\diptrace_mcp_headless_gui.exe" smoke
```

## Safety invariants

The implementation must retain all of these properties:

- never switch the user's input desktop;
- never synthesize physical mouse or keyboard input from the hidden worker;
- never fall back from a failed control operation to screen coordinates;
- keep XML/semantic operations as the default authoring path;
- validate the selected DipTrace installation and project before starting the host;
- use bounded timeouts and terminate a stuck worker rather than block indefinitely;
- return structured failure evidence;
- do not expand the public MCP tool contract merely to expose implementation
  details of the Windows worker.

## CI and real-host evidence

The normal Windows CI suite contains a real Win32 hidden-desktop smoke test. It
verifies desktop creation/process attachment without requiring DipTrace to be
installed on the hosted runner. The Windows packaging workflow also builds the
frozen helper and starts it with `--help`.

A real DipTrace open/save/reopen validation is still a real-host acceptance gate:
hosted GitHub runners do not provide the licensed/local DipTrace installation used
for product acceptance. Passing CI therefore proves the isolation primitive and
packaging, not universal DipTrace UI compatibility.
