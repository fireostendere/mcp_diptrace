# Cinematic Demo Mode

## Status

Cinematic mode is implemented on `main` as a deterministic presentation layer for DipTrace MCP workflows. It can replay already-planned engineering actions through the visible DipTrace UI on Windows and capture the result as video or GIF.

It is deliberately separate from engineering decision making and from the authoritative write/evidence path:

- normal planners decide **what** should happen;
- normal semantic operations / XML bridge / transactions remain authoritative for engineering edits;
- cinematic mode decides **how to present** an already-planned action visibly;
- visible replay is not proof that DipTrace semantically accepted an edit unless separate real-host evidence verifies it.

The cinematic implementation does not change the frozen 159-tool MCP public contract.

## Supported scopes

- **Schematic:** semantic part placement and planner wire vertices can be replayed visibly;
- **PCB:** Generation A placement proposals and simple same-layer trace vertices can be replayed visibly;
- **General:** arbitrary MCP/service events can be captured into a deterministic timeline.

## Architecture

```text
MCP / planner
    |
    +--> authoritative engineering preview/apply/validation
    |
    v
semantic operations / placement proposals / route vertices
    |
    v
DipTraceCinematicAdapter
    |
    +--> DipTraceUIProfile
    |       +-- explicit verified UI action macros
    |       +-- design -> normalized client affine transform
    |
    v
cinematic manifest
    |
    v
WindowsDesktopDriver
    |
    v
visible DipTrace UI
    |
    v
ffmpeg gdigrab -> MP4 -> GIF
```

The normal XML bridge is blocking from DipTrace's point of view. Artificial delays inside XML exchange cannot truthfully animate intermediate document states, so visible replay is a separate presentation host.

## Modules

- `cinematic.py` — deterministic timeline, events and pacing presets;
- `cinematic_cli.py` — capture initialization/event append/compile and ffmpeg command generation;
- `cinematic_host.py` — Windows replay host and dry-run driver;
- `cinematic_recording.py` — ffmpeg/Windows recording helper;
- `diptrace_ui.py` — UI profile model and design-to-client affine calibration;
- `diptrace_profile_cli.py` — profile template/probe/calibrate/action/validate CLI;
- `diptrace_cinematic_semantic.py` — semantic Schematic/PCB replay adapters;
- `diptrace_window.py` — Windows window/client geometry targeting.

## Timeline presets

| Preset | Purpose |
| --- | --- |
| `cinematic` | polished default demo |
| `timelapse` | fast progression through many operations |
| `tutorial` | slower explanatory playback |
| `gif` | compact GIF-oriented timing |

## UI profiles

PCB and Schematic use separate profiles because their tools/workflows differ. A profile records:

- editor and DipTrace version identity;
- target window-title substring;
- explicit multi-step action macros such as `place_component`, `route_trace` and `wire`;
- an affine transform from DipTrace design coordinates to normalized window-client coordinates.

A default profile intentionally contains no guessed toolbar pixels or guessed shortcuts. It must be calibrated and supplied with verified actions before real replay.

Python API:

```python
from diptrace_mcp.diptrace_ui import make_diptrace_profile

pcb = make_diptrace_profile("pcb", version="5.3")
schematic = make_diptrace_profile("schematic", version="5.3")
```

## Design coordinates -> client coordinates

`DesignToClientTransform` fits a full 2D affine transform:

```text
client_x = xx * design_x + xy * design_y + x0
client_y = yx * design_x + yy * design_y + y0
```

This can represent scale, offset, inverted Y, different X/Y scales and small skew. Output coordinates are normalized to the target DipTrace client area (`0.0 .. 1.0`) rather than hard-coded to one physical monitor resolution.

At least three non-collinear anchors are required. Four or more are recommended so residual error can reveal a poor calibration. Calibration fails closed when RMS or maximum residual exceeds configured thresholds.

## Practical Windows calibration

Create a profile template:

```bash
python -m diptrace_mcp.diptrace_profile_cli template \
  --editor schematic \
  --version 5.3 \
  --output schematic-5.3.json
```

Probe the current normalized cursor position inside a visible DipTrace window:

```bash
python -m diptrace_mcp.diptrace_profile_cli probe --window "DipTrace"
```

Collect anchors, for example:

```json
[
  {"design": [0.0, 0.0], "client": [0.20, 0.80]},
  {"design": [50.0, 0.0], "client": [0.70, 0.80]},
  {"design": [0.0, 30.0], "client": [0.20, 0.35]},
  {"design": [50.0, 30.0], "client": [0.70, 0.35]}
]
```

Fit/persist the transform:

```bash
python -m diptrace_mcp.diptrace_profile_cli calibrate \
  schematic-5.3.json anchors.json
```

## UI action macros

Actions are ordered desktop steps. They may include normalized positions, click paths, clicks, hotkeys, text and bounded pauses.

Example action file:

```json
[
  {"hotkey": ["ctrl", "p"], "pause_ms": 150},
  {"text": "{component}"},
  {"hotkey": ["enter"]}
]
```

Install and validate:

```bash
python -m diptrace_mcp.diptrace_profile_cli action \
  schematic-5.3.json place_component place-component.json

python -m diptrace_mcp.diptrace_profile_cli validate schematic-5.3.json
```

Schematic requires `place_component` and `wire`. PCB requires `place_component` and `route_trace`.

Template values such as `{component}`, `{refdes}`, `{object_id}` and `{net}` are resolved only at semantic replay time.

## Semantic replay

### Schematic

- `schematic_place_part_payload()` consumes the existing `PlacePartOperation`, maps its design coordinates through the calibrated transform and provides semantic values to the UI macro.
- `schematic_wire_payload()` consumes the existing `AddWireOperation` and converts the planner-selected vertices to a visible multi-point click path.

The visible path therefore follows the planner geometry rather than a second independent routing representation.

### PCB

- `pcb_placement_plan_payloads()` consumes the current Generation A `PCBPlacementV2Plan` and converts each placement proposal into calibrated visible placement coordinates.
- `pcb_trace_payload()` consumes the existing `AddTraceOperation` and converts same-layer trace vertices into a routing click path.

Trace replay fails closed if the operation contains a via transition or layer change. Those cases require explicit staged macros; silently replaying them as a same-layer path would be misleading.

## Capture any MCP/service process

Initialize append-only capture:

```bash
python -m diptrace_mcp.cinematic_cli init demo.jsonl \
  --title "PCB routing demo" \
  --preset cinematic \
  --domain pcb
```

Append events and compile:

```bash
python -m diptrace_mcp.cinematic_cli event demo.jsonl route_trace --target CLK
python -m diptrace_mcp.cinematic_cli compile demo.jsonl --output demo.cinematic.json
```

Payload persistence is disabled by default so a presentation log does not accidentally become a copy of arbitrary MCP arguments. Enable it only when explicitly wanted and appropriate for the data.

## Dry-run and playback

Always validate a manifest/profile without moving the real cursor first:

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --dry-run
```

Real Windows replay:

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --window "DipTrace"
```

The host focuses the target window, executes steps in order, uses eased cursor motion and honors bounded pauses.

## Recording

The recorder uses Windows ffmpeg `gdigrab`. A title substring is resolved to a real HWND so the document filename does not have to be copied into the command exactly.

Window capture:

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 \
  --window-title "DipTrace" \
  --fps 60
```

Whole desktop:

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 --desktop --fps 60
```

Generate final MP4/GIF processing commands:

```bash
python -m diptrace_mcp.cinematic_cli ffmpeg raw-demo.mp4 demo --preset cinematic
```

## Safety and reproducibility

- engineering decisions should be computed before polished replay where possible;
- UI profiles are version/editor/configuration specific;
- no guessed toolbar coordinates are installed by default;
- calibration coordinates/residuals are bounded and fail closed;
- normalized client coordinates outside the permitted viewport are rejected;
- JSONL payload recording is off by default;
- dry-run is available before real desktop actions;
- presentation automation cannot promote itself to engineering acceptance evidence;
- normal preview, expected-SHA, backup, transaction and validation paths remain authoritative.

## Current boundary

Implemented and regression-tested on `main`:

- deterministic timeline and four pacing presets;
- generic workflow capture/compile;
- Windows smooth cursor/click/hotkey/text/path playback;
- multi-step action macros;
- PCB/Schematic profile persistence/readiness;
- affine design-to-client calibration with residual checks;
- normalized live cursor probe;
- semantic Schematic part/wire replay;
- PCB Generation A placement replay;
- same-layer PCB trace replay;
- HWND-based recording target resolution;
- MP4/two-pass GIF command generation;
- dry-run and unit/CI coverage.

Still requires real-client acceptance rather than inference:

- verified action macros for the exact DipTrace 5.3 PCB/Schematic configuration used for recording;
- end-to-end calibration against a real open DipTrace document;
- staged GUI playback for vias/layer transitions and other editor gestures whose exact UI workflow has not yet been verified.
