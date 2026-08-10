# Cinematic demo mode

Cinematic mode is a deterministic presentation layer for DipTrace MCP workflows. It can replay already-planned engineering actions through the visible DipTrace UI and capture the result as video or GIF.

The presentation path is deliberately separate from engineering decision making. The normal planners decide what should happen; the cinematic layer converts those decisions into paced, reproducible GUI actions.

## Supported scopes

- **Schematic** — semantic part placement and planner wire vertices can be replayed visibly.
- **PCB** — PCB Generation A placement proposals and simple same-layer trace vertices can be replayed visibly.
- **General** — arbitrary MCP/service events can be captured into a deterministic timeline.

## Architecture

```text
MCP / planner
    |
    +--> normal engineering apply/validation
    |
    v
semantic operations / placement proposals / route vertices
    |
    v
DipTraceCinematicAdapter
    |
    +--> DipTraceUIProfile
    |       +-- verified UI action macros
    |       +-- design -> client affine transform
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

The current XML bridge remains authoritative for transactional engineering edits. DipTrace invokes that bridge as a blocking plug-in process, so inserting delays into the XML exchange cannot truthfully animate intermediate document states. GUI replay is therefore a separate presentation host.

## Timeline presets

Four deterministic pacing presets are available:

| Preset | Purpose |
| --- | --- |
| `cinematic` | polished default demo |
| `timelapse` | fast progression through many operations |
| `tutorial` | slower explanatory playback |
| `gif` | compact GIF-oriented timing |

## DipTrace UI profiles

A UI profile is explicit about the editor and DipTrace version. PCB and Schematic use separate profiles because their tools and workflows differ.

```python
from diptrace_mcp.diptrace_ui import make_diptrace_profile

pcb = make_diptrace_profile("pcb", version="5.3")
schematic = make_diptrace_profile("schematic", version="5.3")
```

A profile contains:

- a DipTrace version identifier;
- the target window-title substring;
- verified multi-step UI macros such as `place_component`, `route_trace`, and `wire`;
- an affine transform from DipTrace design coordinates to normalized client coordinates.

No guessed toolbar pixels or guessed shortcuts are installed by `make_diptrace_profile`. A profile becomes ready only after calibration and its required UI actions are configured.

## Design coordinates to client coordinates

`DesignToClientTransform` fits a full 2D affine transform:

```text
client_x = xx * design_x + xy * design_y + x0
client_y = yx * design_x + yy * design_y + y0
```

This handles normal scale/offset mapping, inverted Y axes, different X/Y scales, and small skew. Coordinates emitted to desktop playback are normalized to the target window client area (`0.0 .. 1.0`), not tied to one physical monitor resolution.

At least three non-collinear anchors are required. Four or more anchors are recommended because residual error can then detect a poor calibration instead of merely fitting three exact points. Calibration fails closed when RMS or maximum residual exceeds the configured thresholds.

## Practical calibration on Windows

Create an empty profile:

```bash
python -m diptrace_mcp.diptrace_profile_cli template \
  --editor schematic \
  --version 5.3 \
  --output schematic-5.3.json
```

Move the cursor to a known visible design point in DipTrace and probe the current normalized client position:

```bash
python -m diptrace_mcp.diptrace_profile_cli probe \
  --window "DipTrace"
```

The command returns a value such as:

```json
{"client": [0.4123, 0.6331]}
```

Collect three or more anchors in `anchors.json`:

```json
[
  {"design": [0.0, 0.0], "client": [0.20, 0.80]},
  {"design": [50.0, 0.0], "client": [0.70, 0.80]},
  {"design": [0.0, 30.0], "client": [0.20, 0.35]},
  {"design": [50.0, 30.0], "client": [0.70, 0.35]}
]
```

Fit and persist the transform:

```bash
python -m diptrace_mcp.diptrace_profile_cli calibrate \
  schematic-5.3.json anchors.json
```

The output includes anchor count, RMS residual, and maximum residual.

## UI action macros

UI actions are stored as ordered desktop steps. They may contain normalized cursor positions, click paths, clicks, hotkeys, text, and bounded pauses.

Example action file:

```json
[
  {"hotkey": ["ctrl", "p"], "pause_ms": 150},
  {"text": "{component}"},
  {"hotkey": ["enter"]}
]
```

Install it into a profile:

```bash
python -m diptrace_mcp.diptrace_profile_cli action \
  schematic-5.3.json place_component place-component.json
```

Template fields such as `{component}`, `{refdes}`, `{object_id}`, and `{net}` are preserved in the profile and rendered only when the corresponding semantic action is replayed.

Validate readiness:

```bash
python -m diptrace_mcp.diptrace_profile_cli validate schematic-5.3.json
```

Schematic requires `place_component` and `wire`. PCB requires `place_component` and `route_trace`.

## Schematic semantic replay

`schematic_place_part_payload()` accepts the existing `PlacePartOperation`. It maps the operation's design `x/y` through the calibrated profile and supplies semantic values such as component style and reference designator to the UI macro.

`schematic_wire_payload()` accepts the existing `AddWireOperation`. The exact vertices selected by the schematic wire planner are converted into a visible multi-point click path, so the demo follows planner geometry instead of a second independent routing representation.

## PCB semantic replay

`pcb_placement_plan_payloads()` accepts the current PCB Generation A `PCBPlacementV2Plan`. Each `PlacementProposal` is translated into a visible component placement at the proposal's design `x/y` coordinate using the same calibrated transform.

`pcb_trace_payload()` accepts the existing `AddTraceOperation` and converts same-layer trace vertices into a visible routing click path.

Trace playback currently fails closed when an operation contains a via transition or a layer change. Those routes need an explicit staged macro so the player can visibly place the via/change layer rather than silently replaying the wrong geometry.

## Multi-step desktop playback

One cinematic event can contain multiple GUI steps:

```json
{
  "desktop": {
    "window_title_contains": "DipTrace",
    "steps": [
      {"hotkey": ["w"]},
      {
        "path": [[0.20, 0.40], [0.42, 0.40], [0.42, 0.68]],
        "click": "left"
      },
      {"hotkey": ["esc"]}
    ]
  }
}
```

The Windows host focuses the target window, executes each step in order, uses eased cursor motion, and supports bounded per-step pauses. A dry-run driver expands the same commands without touching the desktop.

## Capture any MCP or service process

Initialize an append-only capture:

```bash
python -m diptrace_mcp.cinematic_cli init demo.jsonl \
  --title "PCB routing demo" \
  --preset cinematic \
  --domain pcb
```

Append events and compile a deterministic manifest:

```bash
python -m diptrace_mcp.cinematic_cli event demo.jsonl route_trace --target CLK
python -m diptrace_mcp.cinematic_cli compile demo.jsonl --output demo.cinematic.json
```

Payload persistence is disabled by default so a presentation log does not accidentally become a copy of arbitrary MCP arguments. It is an explicit opt-in at capture creation.

## Desktop dry-run and playback

Validate without moving the real cursor:

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --dry-run
```

Replay against the Windows host:

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --window "DipTrace"
```

## Video and GIF recording

The recorder uses Windows `ffmpeg` `gdigrab`. Real window capture resolves a title substring to a Windows HWND first, then captures the handle. This avoids requiring the exact full DipTrace window title when it also contains a document filename.

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 \
  --window-title "DipTrace" \
  --fps 60
```

The whole desktop is optional:

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 --desktop --fps 60
```

Generate final MP4 and two-pass palette GIF commands:

```bash
python -m diptrace_mcp.cinematic_cli ffmpeg raw-demo.mp4 demo --preset cinematic
```

## Safety and reproducibility

- Engineering decisions are computed before polished playback where possible.
- UI profiles are version/editor specific and must be calibrated rather than guessed.
- Coordinates outside the calibrated client viewport fail closed.
- Calibration residuals are bounded.
- JSONL payload recording is off by default.
- Desktop playback is presentation automation, not proof that DipTrace semantically accepted an edit.
- Normal XML preview, expected-SHA, backup, transaction, and validation paths remain authoritative.

## Current boundary

Implemented in the cinematic branch:

- deterministic timeline and four pacing presets;
- generic workflow capture;
- Windows smooth cursor/click/hotkey/text/path playback;
- multi-step desktop macros;
- DipTrace PCB/Schematic UI profile model;
- profile persistence and readiness validation;
- affine design-to-client calibration with residual checks;
- live normalized cursor probe for calibration;
- semantic Schematic part placement and wire replay;
- PCB Generation A placement proposal replay;
- same-layer PCB trace replay;
- HWND-based DipTrace window capture;
- MP4 and two-pass GIF post-processing;
- dry-run validation and unit/CI coverage.

Still requires real-client acceptance rather than inference:

- verified action macros for the exact DipTrace 5.3 PCB/Schematic UI configuration used for recording;
- end-to-end calibration against a real open DipTrace document;
- staged GUI playback for vias/layer transitions and any editor action whose exact UI gesture has not yet been verified.
