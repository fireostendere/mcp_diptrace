# DipTrace runtime access

Read this once when choosing how to inspect, edit, open, verify, or record a design.
Use public `tools/list` for exact callable names and `get_capabilities` for session,
document, feature, policy, and configured-adapter availability. Also discover the
local CLI when the task needs a real editor: a missing MCP tool is not evidence that
the headless helper is unavailable. [capability-map.json](../capability-map.json)
keeps these interfaces separate.

## Choose the interface

| Need | Interface | What it actually does |
|---|---|---|
| Inspect/edit exported XML | MCP with an explicit `path` | Parses models, runs offline checks, previews and commits semantic changes; no GUI required |
| Work on the active editor exchange | MCP live session | Omitting `path` uses a confirmed bridge session; `finish_live_session` applies/cancels its exchange |
| Open a native file without desktop interference | Headless GUI `roundtrip` | Launches the selected real editor, opens, saves, closes, and returns process/file evidence |
| Native PCB refill and DRC | PCB acceptance CLI | Refill, DRC, save/close/reopen, XML Save As, and evidence comparison |
| Record the real editor | Cinematic headless capture CLI | Runs a validated replay manifest and records the project window to MP4/GIF |
| Preview PCB without running DipTrace | `pipeline_render_board_preview` or transaction preview | Derived SVG, not a native screenshot or native DRC |
| Convert generated XML to a native-shaped template | `pipeline_nativeize_document` | Writes a separate XML file; does not open DipTrace or prove acceptance |
| Fetch catalog component data | `pipeline_source_component` | Network download of JSON/PDF; no native library import or stock reservation |
| Choose engineering methods or DipTrace workflows | Separately configured Knowledge MCP / RAG | Retrieves the user's MIT, design/layout and DipTrace courses; apply and verify their guidance |
| Export manufacture data through MCP | BOM/assembly/fabrication exports | Generic CSV/placement/manifests; no authoritative Gerber/NC Drill |

An absent live session does not block explicit-path XML work. Binary `.dip`, `.dch`,
`.eli`, and `.lib` files belong to the native editors; do not feed arbitrary binaries
to the XML parser or rename a binary to `.xml`. Native opening and native XML export
are different operations. The base roundtrip does not export XML or run ERC/DRC.

`diptrace-mcp-bridge --headless` only services apply/cancel requests without the bridge
dialog. It does not launch, render, or validate a DipTrace editor.

## Knowledge and engineering decisions

Use [RAG engineering memory](rag.md) by default throughout hardware work, without
an extra role prompt. Build and maintain context from the user's MIT, schematic/PCB
and DipTrace courses, then apply it to decisions, editor workflows and review.
Knowledge search/read
tools belong to their configured provider, not the DipTrace `get_capabilities` list.
Discover them independently; no Knowledge server is bundled by these skills. A
retrieved recommendation needs an applicable source and verification on the design.

## Windows host, including access from WSL

Locate the installed helper or a Windows Python environment containing this package.
For source installations use module entry points; the module's parser name does not
mean a same-named console executable was installed.

```powershell
py -m diptrace_mcp.headless_gui --help
py -m diptrace_mcp.headless_gui doctor --require-automation
py -m diptrace_mcp.headless_gui roundtrip --diptrace-root "C:\Program Files\DipTrace" --editor schematic --project "C:\work\checks\design.dch" --timeout 30
```

The editor identifiers are `schematic`, `pcb`, `component`, and `pattern`:
Schematic.exe, Pcb.exe, CompEdit.exe, and PattEdit.exe. Roundtrip defaults to
`--desktop hidden`; it creates a private Win32 desktop in the current interactive
Windows session. `--desktop native` is an explicit visible mode, not the definition
of native verification. A normal timeout is 30 seconds; the request accepts
strictly positive timeouts up to 300 seconds.

The bundled executable is under
`app/tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe` relative to the
installation. It dispatches ordinary headless commands, `pcb-acceptance`, and
`cinematic`. Resolve its actual location; do not assume a checkout contains a built EXE.

```powershell
& "C:\resolved-install\app\tools\diptrace_mcp_headless_gui\diptrace_mcp_headless_gui.exe" roundtrip --diptrace-root "C:\Program Files\DipTrace" --editor pcb --project "C:\work\checks\board.dip"
py -m diptrace_mcp.pcb_native_acceptance run --diptrace-root "C:\Program Files\DipTrace" --project "C:\work\checks\board.dipxml" --output-xml "C:\work\checks\board.native.dipxml"
```

For a binary `.dip`, supply `--baseline-xml` for semantic comparison. See
[evidence capture](../diptrace-evidence-capture/SKILL.md) for verdict interpretation.
From WSL, use the Windows helper/Windows Python via available Windows interoperability
and convert host arguments to Windows paths (`wslpath -w` where appropriate). Running
the Win32 Python module with Linux Python is not a Windows backend test. Check the
actual executable, dependencies, and session before declaring the operation blocked.

## Linux and macOS installed Wine wrappers

Locate `diptrace-gui-headless` with `command -v` and inspect its `--help`/installed
wrapper. These wrappers are created by the platform installers, not by a bare wheel.

Linux:

```bash
diptrace-gui-headless native-smoke --timeout 20
diptrace-gui-headless roundtrip --editor schematic --project /work/checks/design.dch --timeout 30
```

The Linux wrapper creates private Xvfb, runs the Win32 helper in Wine, and forces
`--desktop native` inside that virtual display. For **roundtrip only**, it translates
the Linux `--project` path and supplies `--diptrace-root`; do not pass those managed
desktop/root flags. It rejects `smoke`; use `native-smoke`. Its default screen is
1920x1080x24, configurable through `DIPTRACE_MCP_HEADLESS_SCREEN`.

Other commands are forwarded to the helper; Linux path/root translation is not
implemented for their additional arguments. Do not promise that a Linux-path
`pcb-acceptance` or `cinematic` example works unchanged. Inspect the installed wrapper
and establish the required Wine paths and verified desktop profile before those runs.

macOS:

```bash
diptrace-gui-headless doctor --require-automation
diptrace-gui-headless roundtrip --diptrace-root 'C:\Program Files\DipTrace' --editor schematic --project /work/checks/design.dch --timeout 30
```

The macOS wrapper uses the Wine runtime bundled with DipTrace.app and hidden Win32
desktops; it does not require Xvfb/XQuartz. It converts separate `--project PATH`
arguments only. Supply the resolved Windows installation root; output/baseline/manifest
paths also require Wine paths. Do not assume the Linux and macOS wrappers have the
same argument conversion. Apple Silicon installations use the official runtime through
Rosetta. Availability is installation-specific.

## Recording and previews

For real native capture on the Windows backend:

```powershell
py -m diptrace_mcp.cinematic_recording headless-capture capture --diptrace-root "C:\Program Files\DipTrace" --editor pcb --project "C:\work\checks\board.dip" --manifest "C:\work\checks\demo.cinematic.json" --video "C:\work\checks\demo.mp4" --gif "C:\work\checks\demo.gif"
```

The frozen helper uses `cinematic capture` instead of the module's
`headless-capture capture`. ffmpeg, a preflight-valid manifest, and an established
editor/profile are required. Capture uses PrintWindow/WM_PRINT on the real project
window; it is not equivalent to rendering XML. Validated output paths can be cleared
before capture, so choose new output paths or preserve previous artifacts first.
Replay is presentation, not engineering acceptance. Keep the project house rules for
construction order, design-boundary framing, and inspection of sequence/final frame.

## Mutation and evidence boundaries

- Preserve task scope and existing authorization. A request to edit/verify a design
  includes normal preview, validation, and supported local verification steps; do not
  require another generic confirmation just because a helper runs a real editor.
- Roundtrip and PCB acceptance **save the input project**. For read-only reviews or
  protected originals, run on an isolated copy and bind the copy's baseline hash to
  the original. Return generated exports separately. Capture can replay changes too.
- Respect permissions, locks, expected SHA, and bounded batches. A local helper is
  not a way around an explicit denial. `pipeline_*` functions are file-producing
  helpers, not guarded document transactions: resolve inputs and use fresh outputs.
- Inspect preview geometry/connectivity, validate, commit only authorized changes,
  and run post-checks. Reconcile changed hashes; never overwrite intervening user edits.
- `ok: true` from roundtrip proves its bounded open/save/close operation only. PCB
  acceptance requires its DRC and semantic verdict. A screenshot, SVG, nativeization,
  bridge handshake, or smoke test cannot substitute for those checks.
- Ordinary roundtrip has no generic native schematic ERC, CAM export, or arbitrary
  dialog automation. Try the implemented helper for its supported portion, then
  report only the remaining unsupported operation. Do not abandon all verification.
- Unknown dialogs, timeouts, forced exits, or missing prerequisites produce bounded
  failures. Do not recover by grabbing the physical mouse/keyboard, guessing screen
  coordinates, switching desktops, or silently retrying after a possible save.
- Reports use [result.schema.json](result.schema.json). Planning may use `document: null`;
  concrete CAD/native runs include hashes, versions, artifacts, and missing checks.
  A completed scoped report is not a production-release decision.

Implementation references: installed `diptrace_mcp.headless_gui`,
`diptrace_mcp.pcb_native_acceptance`, `diptrace_mcp.cinematic_recording`, and
`diptrace_mcp.server_runtime`; source-checkout `scripts/headless_gui_entry.py`,
`scripts/install_linux.sh`, and `scripts/install_macos.sh`. Prefer the installed
version and actual command schemas over a remembered tool count or old source revision.
