# Cinematic Demo Mode

## Status

Cinematic mode is implemented as an optional deterministic presentation layer for DipTrace MCP workflows. It can replay already-planned engineering actions through the Windows DipTrace UI and capture video/GIF output.

It is not engineering authority:

- normal planners decide what should happen;
- semantic operations/XML bridge/transactions remain authoritative for edits;
- cinematic mode decides how to show an already-planned action;
- replay is not proof of semantic acceptance without separate real-host evidence.

Cinematic does not change the public MCP contract, which currently registers **165 tools**.

## Modules

- `cinematic.py` — deterministic timeline and pacing presets;
- `cinematic_cli.py` — timeline capture/compile and ffmpeg helper;
- `cinematic_host.py` — Windows replay host and dry-run driver;
- `cinematic_preflight.py` — deterministic manifest content identity and safety budgets;
- `cinematic_preflight_cli.py` — standalone preflight inspection;
- `cinematic_recording.py` — visible-window recording plus hidden-desktop cinematic orchestration;
- `diptrace_ui.py` — UI profile model and design-to-client affine calibration;
- `diptrace_profile_cli.py` — template/probe/calibrate/action/validate CLI;
- `diptrace_cinematic_semantic.py` — semantic Schematic/PCB replay adapters;
- `diptrace_window.py` — Windows target-window/client geometry handling.

## Supported semantic replay

Schematic:

- semantic part placement;
- planner-selected wire vertices.

PCB:

- Generation-A placement proposals;
- simple same-layer trace vertices.

PCB trace replay fails closed for via/layer transitions until explicit staged real-UI macros are validated.

## UI profiles and calibration

PCB and Schematic use separate version/editor-specific profiles. A profile stores editor/version identity, target window-title substring, explicit verified action macros and an affine design-coordinate -> normalized client-coordinate transform. No guessed toolbar coordinates or shortcuts are installed by default.

```bash
python -m diptrace_mcp.diptrace_profile_cli template \
  --editor schematic --version 5.3 --output schematic-5.3.json
python -m diptrace_mcp.diptrace_profile_cli probe --window "DipTrace"
python -m diptrace_mcp.diptrace_profile_cli calibrate \
  schematic-5.3.json anchors.json
python -m diptrace_mcp.diptrace_profile_cli validate schematic-5.3.json
```

At least three non-collinear anchors are required; four or more are recommended so residual error can expose a bad fit. Calibration fails closed when residual limits are exceeded.

## Timeline capture

```bash
python -m diptrace_mcp.cinematic_cli init demo.jsonl \
  --title "PCB routing demo" --preset cinematic --domain pcb
python -m diptrace_mcp.cinematic_cli event demo.jsonl route_trace --target CLK
python -m diptrace_mcp.cinematic_cli compile demo.jsonl --output demo.cinematic.json
```

Payload persistence is disabled by default.

## Manifest preflight

Standalone inspection remains useful:

```bash
python -m diptrace_mcp.cinematic_preflight_cli demo.cinematic.json
```

The same validation is enforced before any dry-run, visible replay, or hidden capture action. A caller cannot bypass the manifest safety boundary by invoking the Python playback API directly.

Preflight checks:

- exact `diptrace-cinematic-v1` format;
- cue array/count and index consistency;
- monotonic/non-overlapping start/end/settle timing;
- declared duration against final cue timing;
- bounded settle gaps;
- per-cue serialized payload bytes;
- desktop command count;
- click-path point count;
- typed-text size;
- maximum hotkey chord length.

It also emits a deterministic `content_sha256`. Random/session metadata such as `session_id` is excluded from that identity, while title/timing/cues/payloads remain significant.

The desktop command parser/driver retains its own per-command validation. Manifest preflight is an additional whole-manifest guard, not a replacement for normalized-coordinate, button, click-count, pause, hotkey or text validation.

## Dry-run and visible playback

Both commands automatically preflight the manifest:

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --dry-run
python -m diptrace_mcp.cinematic_host demo.cinematic.json --window "DipTrace"
```

Running the standalone preflight CLI first is optional when an operator wants the content fingerprint/summary before playback.

Exact action macros/calibration remain editor/version/configuration specific. Dry-run/preflight do not prove that a real UI profile is correct.

## Visible recording

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 \
  --window-title "DipTrace" --fps 60
python -m diptrace_mcp.cinematic_cli ffmpeg raw-demo.mp4 demo --preset cinematic
```

The visible recorder resolves a title substring to a real HWND and uses Windows ffmpeg `gdigrab`.

## Hidden Win32 desktop capture

The packaged headless helper can run DipTrace, deterministic replay, and ffmpeg on the same separate hidden `WinSta0` desktop. The operator's normal input desktop remains available while the recording is produced.

```powershell
& "<install-root>\app\tools\diptrace_mcp_headless_gui\diptrace_mcp_headless_gui.exe" `
  cinematic capture `
  --diptrace-root "C:\Program Files\DipTrace" `
  --editor pcb `
  --project "C:\work\board.dip" `
  --manifest "C:\work\demo.cinematic.json" `
  --video "C:\work\demo.mp4" `
  --gif "C:\work\demo.gif"
```

The hidden capture path is deliberately different from the visible cinematic driver:

1. validate the DipTrace installation/project and mandatory cinematic preflight before launching the host;
2. create a random hidden Win32 desktop under `WinSta0`;
3. launch the worker and DipTrace explicitly on that desktop;
4. launch ffmpeg `gdigrab` on the same desktop and capture that desktop rather than the operator's `Default` desktop;
5. replay normalized commands with bounded `SendMessageTimeoutW` window messages;
6. close/terminate bounded child processes and return structured evidence including manifest/video/GIF SHA-256 values, PIDs, desktop, window-station and session identity.

Hidden replay never calls global `SetCursorPos`, `mouse_event`, `keybd_event`, `SendInput` or `SwitchDesktop`. It therefore does not steal the operator's physical cursor or keyboard.

For safety, hidden replay currently accepts normalized click/path commands, text via window messages and message-safe single keys. Modifier/multi-key hotkeys such as `Ctrl+...` deliberately fail closed; configure an equivalent calibrated click path or another verified message-safe macro instead. Visible cinematic playback retains its existing profile semantics.

`ffmpeg` must be available on `PATH` for recording/GIF conversion. The helper does not upload frames or send screenshots to a model; MP4/GIF generation is local.

## Safety/evidence boundary

- compute engineering decisions before polished replay where possible;
- UI profiles require explicit calibration/action macros;
- no guessed pixels/shortcuts by default;
- manifest-level and command-level actions are bounded;
- mandatory preflight executes before playback driver actions;
- dry-run remains available before visible cursor movement;
- payload recording is off by default;
- hidden replay does not synthesize global physical input;
- cinematic replay cannot grant engineering acceptance evidence;
- normal preview/expected-SHA/transaction/review paths remain authoritative.

## Current acceptance boundary

Implemented and regression-tested:

- deterministic timeline/presets;
- capture/compile;
- visible Windows cursor/click/hotkey/text/path host;
- profile persistence/readiness and affine calibration;
- semantic schematic part/wire replay;
- PCB placement and same-layer trace replay;
- content fingerprint and mandatory manifest safety preflight;
- visible HWND recording and MP4/GIF helper commands;
- hidden `WinSta0` cinematic orchestration with DipTrace and ffmpeg on the same desktop;
- bounded hidden message replay that does not use global physical-input APIs;
- packaged-helper startup smoke for the cinematic subcommand.

Still requires real-client evidence:

- verified macros for the exact DipTrace PCB/Schematic configuration used for a recording;
- end-to-end calibration against the real open document;
- one real Windows/DipTrace proof that `gdigrab` records the intended hidden desktop on the supported host configuration;
- staged via/layer-transition and other unverified editor gestures.
