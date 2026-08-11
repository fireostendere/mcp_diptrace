# Cinematic Demo Mode

## Status

Cinematic mode is implemented on `main` as an optional deterministic presentation layer for DipTrace MCP workflows. It can replay already-planned engineering actions through the visible Windows DipTrace UI and capture video/GIF output.

It is not engineering authority:

- normal planners decide what should happen;
- semantic operations/XML bridge/transactions remain authoritative for edits;
- cinematic mode decides how to show an already-planned action visibly;
- visible replay is not proof of semantic acceptance without separate real-host evidence.

The public MCP contract remains unchanged at 159 tools.

## Modules

- `cinematic.py` — deterministic timeline and pacing presets;
- `cinematic_cli.py` — timeline capture/compile and ffmpeg helper;
- `cinematic_host.py` — Windows replay host and dry-run driver;
- `cinematic_preflight.py` — deterministic manifest content identity and safety budgets;
- `cinematic_preflight_cli.py` — standalone preflight command;
- `cinematic_recording.py` — ffmpeg/Windows recording helper;
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

PCB and Schematic use separate version/editor-specific profiles. A profile stores:

- editor/version identity;
- target window-title substring;
- explicit verified action macros;
- an affine design-coordinate -> normalized client-coordinate transform.

No guessed toolbar coordinates or shortcuts are installed by default.

Create/probe/calibrate/validate a profile:

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

Before desktop playback, validate the compiled manifest:

```bash
python -m diptrace_mcp.cinematic_preflight_cli demo.cinematic.json
```

The preflight checks:

- exact `diptrace-cinematic-v1` format;
- cue array/count consistency;
- cue index sequence;
- monotonic/non-overlapping start/end/settle timing;
- declared duration against actual final cue timing;
- bounded settle gaps;
- per-cue serialized payload bytes;
- total desktop command count;
- total click-path point count;
- total typed-text size;
- maximum hotkey chord length.

It also emits a deterministic `content_sha256`. Random/session metadata such as `session_id` is excluded from that identity, while title/timing/cues/payloads remain significant. This makes two equivalent compiled demonstrations comparable without pretending that two recording sessions are the same session.

The default budgets are intentionally generous enough for normal demos but finite. A caller can use `CinematicSafetyBudget` for a stricter controlled environment.

The existing desktop parsers/drivers retain their own per-command bounds (normalized coordinates, supported mouse buttons, click count, pause, hotkeys/text behavior). Preflight is an additional whole-manifest guard, not a replacement for those command-level checks.

## Dry-run and real playback

Run preflight first, then dry-run:

```bash
python -m diptrace_mcp.cinematic_preflight_cli demo.cinematic.json
python -m diptrace_mcp.cinematic_host demo.cinematic.json --dry-run
```

Real Windows replay:

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --window "DipTrace"
```

Exact action macros/calibration remain editor/version/configuration specific. Dry-run/preflight do not prove that a real UI profile is correct.

## Recording

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 \
  --window-title "DipTrace" --fps 60

python -m diptrace_mcp.cinematic_cli ffmpeg raw-demo.mp4 demo --preset cinematic
```

The recorder resolves a title substring to a real HWND and uses Windows ffmpeg `gdigrab`.

## Safety/evidence boundary

- compute engineering decisions before polished replay where possible;
- UI profiles require explicit calibration/action macros;
- no guessed pixels/shortcuts by default;
- manifest-level and command-level actions are bounded;
- dry-run is available before cursor movement;
- payload recording is off by default;
- cinematic replay cannot grant engineering acceptance evidence;
- normal preview/expected-SHA/transaction/review paths remain authoritative.

## Current acceptance boundary

Implemented and regression-tested:

- deterministic timeline/presets;
- capture/compile;
- Windows cursor/click/hotkey/text/path host;
- profile persistence/readiness and affine calibration;
- semantic schematic part/wire replay;
- PCB placement and same-layer trace replay;
- content fingerprint and manifest safety preflight;
- HWND recording and MP4/GIF helper commands.

Still requires real-client evidence:

- verified macros for the exact DipTrace PCB/Schematic configuration used for a recording;
- end-to-end calibration against the real open document;
- staged via/layer-transition and other unverified editor gestures.
