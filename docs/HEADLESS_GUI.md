# Headless GUI worker

## Linux: private Xvfb + Wine

The validated Linux deployment uses the same bundled Win32 automation helper as
Windows, but isolates it at the X-server boundary. `diptrace-gui-headless`
creates a fresh Xvfb display with TCP listening disabled, starts the helper under
the shared Wine prefix, and forces the helper verified `native` Win32 desktop
mode inside that virtual display. The real DipTrace GUI therefore exists and can
be automated without appearing on the operator physical desktop.

This is intentionally not a second Linux automation implementation: the same
bounded Win32/UI operations, failure rules, project validation, and no-physical-
input invariants remain authoritative. The Linux wrapper translates ordinary
Linux project paths to Wine paths and owns `--diptrace-root` / `--desktop` so a
caller cannot accidentally escape the private-display boundary.

```bash
diptrace-gui-headless native-smoke --timeout 20

diptrace-gui-headless roundtrip \
  --editor schematic \
  --project "$HOME/DipTrace/design.dch" \
  --timeout 30
```

The virtual display defaults to `1920x1080x24`; override it with
`DIPTRACE_MCP_HEADLESS_SCREEN`, for example `2560x1440x24`. Full installation and
clean-host acceptance details are in [Linux installation and GUI modes](LINUX.md).

Hosted Linux CI verifies a fresh one-command install, real `Schematic.exe` GUI
liveness under Xvfb, the bundled Win32 worker on the same private display, MCP
stdio, bridge state, and idempotent reinstall. This proves the GUI runtime and
worker plumbing, not every possible DipTrace dialog or future native action.

## Windows: isolated Win32 desktop
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
The base supported native operation is a bounded round trip:

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

A bounded PCB evidence profile now composes the same primitives for a verified
native-action sequence: copper-pour refill, DRC, Save/Close/Reopen and PCB XML
Save As. It is intentionally an evidence workflow rather than a new MCP tool.
Unknown or localized controls fail closed or return `HUMAN_REVIEW_REQUIRED`;
they never trigger coordinate or physical-input fallback. See
[DipTrace evidence capture](EVIDENCE_CAPTURE.md).

Other editors/actions still require their own verified control profile before
they can be added. In particular, this PCB profile does not imply generic ERC,
manufacturing-output generation, or arbitrary DipTrace-dialog automation.

## Requirements

- Windows 10 or Windows 11 in an interactive user session;
- a normal DipTrace installation accessible to that user;
- no elevation/UAC prompt required to start the selected DipTrace editor;
- for source installs, the optional `headless-gui` dependency group (pywinauto and
  Pillow; Pillow is required by native screenshot/startup-dialog capture).

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

The native PCB evidence profile is likewise module-invoked from a source install:

```powershell
py -m diptrace_mcp.pcb_native_acceptance --help
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

## Native PCB evidence profile

The Windows source-install entry point is:

```powershell
py -m diptrace_mcp.pcb_native_acceptance run `
  --diptrace-root "C:\Program Files\DipTrace" `
  --project "C:\work\board.dipxml" `
  --output-xml "C:\work\evidence\board.native.dipxml"
```

The bundled helper exposes the same profile through its internal dispatcher:

```powershell
& "<helper>\diptrace_mcp_headless_gui.exe" pcb-acceptance run `
  --diptrace-root "C:\Program Files\DipTrace" `
  --project "C:\work\board.dipxml" `
  --output-xml "C:\work\evidence\board.native.dipxml"
```

The profile records the native menu paths actually used, DRC dialog texts,
project/export hashes, whole-board structural summaries, XML semantic delta,
PIDs and Win32 isolation identity in a `*.native-evidence.json` sidecar. A binary
`.dip` project needs `--baseline-xml` for an automatic semantic verdict.

`PASS` is deliberately strict: successful native execution alone is insufficient.
A known DRC success result and exact semantic equality with the immutable baseline
are also required. Structurally stable but unexplained native canonicalization is
`HUMAN_REVIEW_REQUIRED`, not PASS.

## Hidden cinematic capture

The same isolation layer also supports presentation-only MP4/GIF capture. The
capture worker renders the real DipTrace project window into BGRA frames with
`PrintWindow`/`WM_PRINT` and pipes them to ffmpeg without switching desktops or
using physical input. See [Cinematic Demo Mode](CINEMATIC_DEMO_MODE.md), the
[I²C schematic GIF](../i2c-level-shifter/i2c-level-shifter-demo.gif), and the
[matching PCB GIF](../i2c-level-shifter/i2c-level-shifter-pcb-demo.gif).

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

The current development constraints use MCP 1.30.0 and Pillow 13.0.0, replacing
versions with known security advisories. The optional Windows `headless-gui` extra
requires Python 3.11+ through Pillow; base XML/MCP operation still supports 3.10+.
These are development inputs, not a change to the immutable published v0.4.0 bytes.

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
The build constraints pin Pillow so a clean build does not depend on an incidental
capture dependency. MCP stdio emits UTF-8 bytes even when Windows configures the
process text stream with an ANSI encoding.
Geometry-enabled frozen servers initialize Shapely/NumPy on the main thread
before serving tools: first import inside an AnyIO worker was observed to hang
in NumPy's Windows C-extension loader. This does not change geometry validation
or introduce a fallback for a broken bundled dependency.

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

PCB DRC does not pass from the `TFMyMessage` class alone. A positive error count
overrides success text; otherwise PASS requires an explicit success token or the
existing exact reviewed bitmap signature. Unknown image dimensions/font/DPI and
capture failures stay `review_required`, with the captured PNG/hash retained when
available. A separately viewed image reading "No errors found" is operator evidence,
not permission to rewrite the native report or waive XML/connectivity differences.
Historical DRC `pass` records below predate removal of the class-only fallback;
they are not independently verified success signatures.

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

The public `run_native_check` job now supports source and frozen-helper dispatch
for PCB acceptance, schematic acceptance/ERC and native binary XML export. Inputs
are SHA-checked job-owned copies; originals are not passed to a saving helper.
Optional `startup_dialog_sha256` approvals require exact explicitly reviewed
client PNG hashes, with no default approval (schematic: at most eight; XML export:
one; PCB acceptance: unsupported). `run_native_export` similarly collects raw CAM
evidence from a private PCB XML copy; it is not inspected CAM or fabrication sign-off.

On the current 5.3.0.3 host, all four public check variants were executed.
Schematic acceptance/ERC and native binary XML export returned zero after exact
startup images were inspected and explicitly supplied. The ERC client image was
viewed and reads "No errors found". Label deletion preserved the compared semantics.
R1 deletion after removal of all wires preserved parts and physical pin-to-pad
mappings, but native re-export removed all 22 remaining net memberships: this is
execution evidence, not connectivity acceptance. The base schematic preserved
24 pin/net/NC records and 14 physical pin-to-pad mappings, but library and wire
geometry changed and still require visual review.
A separate bounded R1-deletion case now uses a public frozen-server transaction
to remove only its two local wires, R1 and its exclusive PS5 port. Direct wired
deletion was safely refused; native save/re-export preserves 14 parts, 21 pin/net/NC
records, 12 physical pin-to-pad mappings, 12 wires and six nets with equal compared
semantics, including wire geometry. The zoom-extents capture was inspected; it is
not formal page-fit acceptance. ERC correctly remains `review_required`, with an
inspected `Single pin in net: SDA_3V3, Q1:S` error on the deliberately altered copy.
Helper completion and bounded preservation do not imply an ERC-clean design.
A bounded wait now handles the observed owned DRC progress form
without dismissing it or relaxing unknown-dialog/ownership checks.

Top-pour add/delete and outline copies completed refill/DRC/save/re-export with
DRC `pass`, but strict comparison returned `FAIL`: raw endpoints changed from
22 to 20 and scoped ID inventories differed. The missing raw records are GND `J1`
pad `1` and GND `J2` pad `1`; safe canonicalization is not established. These are not
promoted to PASS. Component-level pad assignments still name GND, so the raw delta
alone does not prove a physical disconnection. Native CAM produced actual Gerber/NC Drill/placement outputs
and a complete manifest; no CAM inspection or fabrication approval is implied.
The final clean frozen build completed MCP `tools/list` (161 tools), all four
native check variants and CAM export with unchanged source SHAs. Schematic/ERC,
binary XML export and CAM helpers returned zero. On the native-authored PCB
baseline, DRC passed and structural records were unchanged, but full XML
semantics differed: `HUMAN_REVIEW_REQUIRED` / exit 2, not PASS. The ERC result
matched the viewed "No errors found" image. CAM's complete manifest covers 16
archive members and still reports `fabrication_approved: false`.
A read-only baseline comparison locates all changed XML records in copper-refill
data (19), two embedded pattern dimensions, working-directory metadata and removal
of a class-to-class cell (`NetClass1=0`, `NetClass2=0`, `Clearance=-1`). This does not
establish copper equivalence or the sentinel's native fallback semantics; neither
the native verdict nor the semantic fingerprint/gate was changed.

Session evidence (including `frozen-final-summary.json`,
`schematic-record-comparison.json`, `pcb-endpoint-comparison.json`,
`pcb-baseline-delta-classification.json` and `m2-local-delete/comparison.json`) is retained
under `.local/roadmap-closure-20261111/`, outside the public trust registry and
release artifacts. A generic MCP ClientSession is not named-client M5 acceptance.

Windows CI contains real Win32 hidden-desktop and native-desktop process probes.
They verify desktop creation/targeting, `WinSta0` attachment and session identity
without requiring DipTrace. The Windows packaging workflow also builds and tests
the split per-user/admin installer boundary.

Unit/packaging CI validates the native PCB evidence state machine, bounded verdict
rules and frozen-helper dispatch, but hosted GitHub runners still do not provide
the licensed/local DipTrace installation needed to prove the actual PCB 5.3 menu
profile. The first target-host run therefore remains required before that profile
is treated as real-host validated.

The repository includes one real-host I²C schematic capture and controlled
open/save/reopen evidence. Passing hosted CI proves the bounded Windows primitives
and packaging, not universal DipTrace UI compatibility.


## macOS hidden-desktop backend

The v0.4.0 macOS path reuses the packaged Win32 GUI worker inside the Wine runtime
bundled with the official DipTrace 5.3.0.3 `DipTrace.app`. Unlike Linux, macOS does
not require Xvfb or XQuartz for headless automation. The helper creates a private
randomly named Win32 desktop inside the bundled Wine prefix and keeps the input
desktop `Default` before and after the worker run.

The permanent macOS clean-install gate covers macOS 15 on Apple Silicon and Intel,
real Schematic GUI liveness, hidden/native worker smokes, automation doctor, MCP
stdio, shared-prefix bridge state and idempotent reinstall. Apple Silicon uses
Rosetta for the official bundle's x86-64 Wine runtime. No physical-input fallback is
enabled. See `docs/MACOS.md` for the exact installation and evidence boundary.
