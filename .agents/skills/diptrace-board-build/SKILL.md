---
name: diptrace-board-build
description: >
  Complete headless DipTrace board build pipeline extracted from proven
  builds (attiny85-arduino-clone 3772 LOC + i2c-level-shifter 532 LOC +
  dut-controller-reva). Covers LCSC sourcing → schematic generation →
  visual wiring → nativeize → PCB placement/routing → pours/silk → SVG
  preview → native DRC verification. Use when building any new board.
---

# DipTrace Board Build Pipeline

## The One Rule

`build_schematic_document()` / `build_pcb_document()` produce XML that
DipTrace 5.3 CANNOT parse (silent hang). Every generated file MUST pass
through nativeization before opening in the editor.

## Architecture Overview

```
Phase 0: SOURCE          LCSC/EasyEDA → vendor/*.json → *.elixml
Phase 1: CONNECTIVITY    Builder class → PlacePart + ConnectPins
Phase 2: VISUAL WIRING   Ground symbols, Net Ports, Wires, Labels
Phase 3: NATIVEIZE       Transplant content → native template → opens in DipTrace
Phase 4: PCB SYNC        build_sync_plan → ComponentSyncMapping → placement
Phase 5: ROUTING         Priority batches → plan_pcb_routes → AddTraceOperation
Phase 6: FINISH          Pours + stitching → sanitize pads → silkscreen
Phase 7: VERIFY          ERC/DRC → SVG preview → native gate11
```

## Phase 0: Source Components

### Resolution order (house rule)
1. DipTrace installed catalog (`query_builtin_library_catalog`)
2. LCSC/EasyEDA exact MPN match
3. Custom-drawn only after both documented zero matches

### LCSC fetch pattern
```python
from diptrace_mcp.pipeline import lcsc_fetch
result = lcsc_fetch("ESP32-S3-MINI-1U-N8", "vendor/")
# Returns: code, mpn, package, pins, pads, json_path, datasheet_path
```

Fallback chain for MPN→C-code resolution:
1. DuckDuckGo HTML scrape: `html.duckduckgo.com/html/?q=<MPN>+lcsc`
2. JLCPCB parts API: POST `selectSmtComponentList`
3. Manual web search

### JSON → .elixml conversion rules

EasyEDA geometry:
- Units are 10 mil (0.254 mm); Y grows UP; DipTrace Y grows DOWN
- Symbol pins: `P~show~0~<number>~<x>~<y>~<rotation>~<id>`
- Pin names: scan `^^` sections, find `<value>~start/end~~~#color`
- Body rect: `R~<x>~<y>~...~<w>~<h>` or synthesize from PL/PG bbox
- Footprint pads: `PAD~<shape>~x~y~w~h~layer~net~number~hole_r~points~angle`
  - Shape ∈ {RECT, POLYGON, OVAL, ELLIPSE, CIRCLE}; POLY = use declared w/h
- Silk tracks: `TRACK~<width>~<layer>~<net>~points`

Critical transforms:
- **Pad ordering**: DipTrace sync maps pins↔pads POSITIONALLY. Pattern pads
  MUST be sorted to match symbol pin sequence exactly.
- **Merged pads**: "A1B12" covers two connector legs. Either split into two
  half-width pads OR renumber to integers with alias JSON.
- **Duplicate pad numbers** (ESP32 thermal grid "61"×9): merge into one pad
  with union bounding box.
- **Alphanumeric pad numbers**: DipTrace sync resolves by numeric Id fallback;
  renumber all non-digit pads sequentially in pin order + save alias map.
- **Zero-length pins**: nearest-edge body synthesis can produce length=0;
  clamp to ≥0.5mm.
- **ElectricType**: valid values are Input, Output, Bidirectional, Power,
  Passive. Unknown values may hang Schematic.exe.

## Phase 1: Schematic Connectivity

Use a Builder class pattern (see dut-controller-reva builder):

```python
class Builder:
    def part(self, stem_style, refdes, value, sheet, x, y):
        # First embed includes library_component_xml/pattern_xml/pad_style_xml
        # Subsequent placements reference the emitted style name only
        ...

    def nets(self, table):
        # table: {net_name: [(refdes, pad_number), ...]}
        # Translates pad numbers through alias if needed
        ...
```

Key gotchas:
- `_component_definitions()` renames styles to CompTypeN; track alias mapping
- Pad numbers must be unique per component (sync requirement)
- Assert `assigned ∪ no_connect == all_pins` before writing

## Phase 2: Visual Wiring

Without wires, DipTrace shows floating symbols. Three approaches:

### A. Ground Symbols + Net Ports (attiny85 pattern — BEST quality)

From `layout_and_wire.py`:

1. **`add_ground_symbols(document, groups)`** — places GND port symbols
   near ground pin clusters. Each group: (sheet, ((ref,pin),...), terminal_xy).
   Uses GROUND_LIBRARY_INDEX from installed Net Ports library.
   Sets DNP=Y on symbols so they don't appear in BOM.

2. **`add_named_net_ports(document, labels, specs)`** — places power ports
   (+3V3, VBUS) and named signal ports (Port_In/Port_Out). Labels are
   (net_name, sheet, terminal_xy). Port library index depends on net name
   length: `28 + min(max(len(net),1), 7)` for input, `36 + ...` for output.

3. **`wire(index, net, sheet, start, end, *middle_waypoints)`** — creates
   WireSpec connecting two pins via explicit waypoints. L-shaped paths.

4. **`port(index, net, sheet, key, length=7.62)`** — creates a short stub
   wire from a pin extending outward (length along pin direction), ending
   at a free endpoint where a label is placed.

5. **`append_wires(document, operations)`** — writes Wire elements into
   Nets/Net/Wires with proper Connected1/2, Object1/2, SubObject1/2 attrs.

6. **Quality checks** (assert before writing):
   - `assert_pin_escape(spec, index)` — first segment exits along pin direction
   - `body_intersections(points, sheet, boxes)` — no wire crosses a component body
   - `unrelated_pin_hits(spec, stubs, net_by_pin)` — no wire touches foreign pin
   - `crossing_count(spec, planned)` — no wire crossings on same sheet

7. **`append_overview(document)`** — draws SYSTEM_OVERVIEW sheet with
   functional blocks, cross-sheet signal lines, labels. Documentation only,
   no electrical connectivity.

8. **`annotate_rotated_parts(document)`** — replaces auto-placed RefDes/Value
   markings with manually positioned text shapes for rotated components.

9. **`center_sheet_content(document)`** — computes content bounding box per
   sheet, shifts all elements to center within page bounds minus margins.
   Asserts content fits inside page after centering.

### B. Simple Wire Chaining (my wire_schematic.py)

For large boards where manual wire specification is impractical:
- Compute absolute pin positions from library data (`compute_endpoints()`)
- Greedy nearest-neighbour chaining per net per sheet
- L-shaped paths between consecutive endpoints
- Cross-sheet pins get skipped (caller should add net labels separately)

Generated 92 wires for Rev.A (178 parts, 144 nets).

### C. Net Labels Only (minimal viable)

Place text annotations near pins showing their net name. No wires drawn.
Fastest but least readable.

## Phase 3: Nativeize

```python
from diptrace_mcp.pipeline import nativeize_document
nativeize_document(
    input_path="board.dchxml",
    template_path="proven-native.dchxml",
    output_path="board-native.dchxml",
)
```

The script `nativeize_reva.py` shows the full implementation:
- Clears template Library containers, grafts our PadStyles/Patterns/Components
- Clears Schematic/Components and Nets, grafts ours
- Clones Sheet elements for multi-sheet designs
- Forces Units="mm" on root and both Library levels
- Sets SheetWidth/SheetHeight (A4 landscape = 297×210)

Templates proven to work:
- `i2c-level-shifter-module.dchxml` — schematic (headless-built, opens clean)
- `attiny85-arduino-clone-pcb.dipxml` — PCB (native gate11-saved)

## Phase 4: PCB Sync + Placement

Follow attiny85 `build_pcb.py::build()`:

```python
physical = strip_net_ports(schematic)  # keep only Parts with Pattern refs
board = build_pcb_document(PcbScaffold(width_mm=W, height_mm=H, ...))
sync = build_sync_plan(physical, board, mappings=[ComponentSyncMapping(...)],
                        pattern_documents=[physical])
placed = apply_semantic_operations(board, [sync.operation]).document
```

Key patterns:
- **Pad renumbering**: DipTrace writes multi-pad nets as "6@"; sync requires
  unique numbers. Rename then tie to GND post-sync via direct XML injection.
- **Markings block**: Native Pcb.exe defaults RefDes to SilkAlign="Auto" with
  3mm font that lands on pads. Inject explicit Markings block:
  ```xml
  <Markings>
    <CompRotate>N</CompRotate>
    <FontVector>Y</FontVector><FontSize>1.2</FontSize>
    <RefDesGlobal SilkShow="Show" SilkAlign="Top"/>
  </Markings>
  ```
- **Route keepout**: inject Rectangle shapes with Layer="Route Keepout"
  between critical pins (e.g., switching regulator legs).
- **Manual pre-routes**: place critical traces BEFORE autorouter using
  `AddTraceOperation` with explicit waypoints. These become obstacles that
  constrain subsequent automatic routing.

## Phase 5: Routing

Priority batch ordering (from attiny85):

```python
groups = [
    (["TPS_FB"], ["Top"]),           # regulator feedback
    (["VBUS"], ["Top"]),              # power trunk
    (["USB_D-"], layers),             # diff pairs
    (["USB_D+"], layers),
    (["+3V3"], power_layers),         # rail
    *([net], layers for signal_nets), # digital signals
    (["GND"], bottom_layers),         # ground last
]
```

Router config (attiny85 proven values):
```python
PCBRouterConfig(
    grid_mm=0.125,
    clearance_mm=0.13,
    max_nodes=1_000_000,        # node cap binds before wall clock
    route_time_budget_ms=900_000,  # pure runaway guard (~300s worst case)
    max_vias_per_connection=2,
    via_cost=2.0,
    max_detour=12,
    avoid_component_bodies=False,
    allow_via_in_pad=False,
    max_ripup_attempts=3,
    allow_component_moves=False,
    placement=PCBPlacementV2Config(grid_mm=0.5, search_radius_steps=6),
)
```

**Critical**: node cap must bind before time budget, else machine load
flips results run-to-run. Measure worst-case nodes, set budget accordingly.

For boards >100mm: increase grid to 0.25–0.5mm and budgets proportionally.

## Phase 6: Finishing

### Pad sanitization
EasyEDA copper often exceeds 0.13mm rule at fine pitches. Shrink width to
(min_neighbour_distance − 0.35mm). See `sanitize_pads()` in Rev.A builder.

### Pours + stitching
```python
add_copper_pours(doc, net="GND", layers=("Top","Bottom"),
                  clearance_mm=0.22, board_clearance_mm=0.3,
                  stitch_pitch_mm=4.0, stitch_edge_mm=1.0)
```

Attiny85 final pour clearance was 0.22mm (rule was 0.13 but native raster
needed margin). Stitch pitch 4.0mm for large boards, 2.0mm for small.

### Silkscreen
```python
doc = hide_assembly_markings(doc)
plan = plan_silkscreen(build_snapshot(doc),
                        SilkscreenPlanConfig(clearance=0.15, search_steps=20))
doc = apply_semantic_operations(doc, silk.operations).document
```

Also hide Name/Value markings on ICs (keep RefDes visible only).

## Phase 7: Verification

| Gate | Tool | Pass criteria |
|---|---|---|
| ERC | `run_erc(path=...)` | 0 findings |
| Connectivity | `run_connectivity_check(path=...)` | 0 findings |
| Headless QC | `review_pcb_quality(snapshot)` | hard_error_count == 0 |
| Native roundtrip | `headless_gui roundtrip --editor schematic` | ok=true |
| Native DRC | `diptrace_native_gate11.py` | errors = fab-tolerance only |
| Visual | `render_board_svg(pcb_path)` | inspect manually |

## Debugging patterns

| Symptom | Diagnosis |
|---|---|
| DipTrace hangs on open | Missing standard sections → nativeize |
| Components off-page | Units mismatch → force mm in nativeize |
| Router produces 0 ops | Node budget exhausted → increase budgets |
| Trace violates clearance | Check obstacle identity via exc.object_ids |
| Sync fails "Cannot resolve pad" | Pattern pad order ≠ symbol pin order |
| Duplicate pad number error | Merge thermal grids, renumber shield tabs |
| RawTreeSnapshot.compile mismatch | Capture BEFORE mutation, compile AFTER |
| Wires not visible in schematic | ConnectPins ≠ AddWire; need both |

## Utility function reference

All from `attiny85-arduino-clone/layout_and_wire.py` unless noted:

| Function | Purpose |
|---|---|
| `endpoints(doc)` | Map net→absolute pin positions |
| `endpoint_index(by_net)` | (refdes,pin)→Endpoint lookup |
| `component_boxes(doc)` | refdes→(sheet,x0,y0,x1,y1) |
| `transform_local(part, x, y)` | Rotate local→global coords |
| `pin_point(index, key)` | Absolute position of a pin endpoint |
| `wire(index, ...)` | Create WireSpec between two points |
| `port(index, ...)` | Short stub wire + label point |
| `add_ground_symbols(doc, groups)` | Place GND symbols |
| `add_named_net_ports(doc, labels, specs)` | Place net port symbols |
| `append_wires(doc, ops)` | Write Wire elements to XML |
| `assert_pin_escape(spec, index)` | Validate pin exit direction |
| `body_intersections(pts, sheet, boxes)` | Wire vs body collision check |
| `crossing_count(spec, planned)` | Wire crossing count |
| `append_overview(doc)` | Draw SYSTEM_OVERVIEW blocks |
| `annotate_rotated_parts(doc)` | Reposition rotated component labels |
| `center_sheet_content(doc)` | Center content within page bounds |
| `content_bounds(doc, sheet)` | Content bbox per sheet |
| `clean_visuals(raw_bytes)` | Strip generated ports, reset markings |
| `ensure_overview_sheet(root)` | Create overview sheet if missing |
| `render_board_svg(path)` | SVG Top/Bottom preview (Rev.A) |
| `sanitize_pads()` | Shrink EasyEDA copper widths (Rev.A) |
