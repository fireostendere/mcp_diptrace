---
name: diptrace-board-build
description: >
  Complete headless DipTrace board build pipeline: LCSC sourcing → schematic
  generation → visual wiring → nativeize → PCB placement/routing → pours/silk
  → SVG preview → native verification. Extracted from proven builds
  (attiny85-arduino-clone, i2c-level-shifter-module, dut-controller-reva).
  Use when building any new board through the DipTrace MCP server.
---

# DipTrace Board Build Pipeline

End-to-end workflow for generating a board entirely through code and opening
the result in real DipTrace without hangs.

## Critical rule: never open bare scaffold XML in DipTrace

`build_schematic_document()` / `build_pcb_document()` produce minimal XML that
DipTrace 5.3 cannot parse (hangs silently). Every generated document MUST pass
through `pipeline_nativeize_document()` before opening in the editor.

## Pipeline stages (ordered)

### Stage 0: Source components

```bash
# For each unique part, resolve MPN → LCSC code → download geometry
python -m diptrace_mcp.pipeline lcsc_fetch "ESP32-S3-MINI-1U-N8" vendor/
```

Or via MCP tool: `pipeline_source_component(mpn_or_code="...", output_dir="vendor/")`

Store results in `vendor/<code>.json` + `vendor/<code>.pdf`.
Record every part in `COMPONENT_PROVENANCE.md` (see attiny85 example).

Convert JSON → `.elixml` using `scripts/lcsc_library.py` patterns:
- Parse `result.dataStr.shape` for symbol pins (P~show~0~<num>~<x>~<y>)
- Parse `result.packageDetail.dataStr.shape` for footprint pads (PAD~...)
- Units are 1/100 inch → multiply by 0.254mm; Y-axis flips
- Handle merged pads ("A1B12") by splitting or aliasing
- Merge duplicate pad numbers (thermal grids) into union bbox
- Order pattern pads to match symbol pin order (positional mapping!)
- Renumber alphanumeric pads to sequential integers + write alias JSON

### Stage 1: Schematic connectivity

Create a builder that:
1. Loads .elixml files via `_component_definitions(source_doc, target_doc, row)`
2. Places parts via `PlacePartOperation` (first embed = include library XML)
3. Connects pins via `ConnectPinsOperation(net=name, pins=[PinEndpoint(...)])`
4. Asserts full pin coverage: assigned ∪ no_connect == all pins

**Gotcha**: Pin indices in ConnectPinsOperation refer to position in the Part's
Pins list, NOT the PadId attribute. The converter must emit pins and pads in
matching order.

See `scripts/build_dut_controller_reva.py` Builder class for reference.

### Stage 2: Visual wiring ← THIS IS WHAT MAKES IT READABLE

Without wires, the schematic shows floating symbols. Three approaches:

**A. Ground symbols + Net Ports (attiny85 pattern):**
- Place GND symbols near ground pin clusters
- Place power port symbols (+3V3, VBUS etc.) near rail pins
- Place named net port symbols (Port_In/Port_Out) for signals
- Draw short stub wires from pins to their nearest symbol
- All handled by `add_ground_symbols()`, `add_named_net_ports()`,
  `attach_named_ports()` in layout_and_wire.py

**B. Net Labels (simplest):**
- For each connected pin, compute absolute position from component X/Y +
  pin offset within symbol + rotation
- Place `AddNetLabelOperation(net=name, x=pin_x+offset, y=pin_y+offset)`
- Multiple pins with same label are visually identified as connected
- Faster than A but less pretty

**C. Full wire routing (attiny85 approach):**
- Compute endpoint positions from library pin data (see `endpoints()` in
  layout_and_wire.py lines 196–237)
- Generate L-shaped wire paths avoiding component bodies
- Add via `AddWireOperation(net, sheet, points, start, end)` +
  `append_wires()` which writes Wire elements into the XML
- Most readable but requires manual coordinate specification per wire

For Rev.A-scale boards (178+ parts), use approach A or B.
For small boards (<20 parts), approach C gives textbook-quality output.

### Stage 3: Nativeize

```python
from diptrace_mcp.pipeline import nativeize_document
nativeize_document(
    input_path="my-board.dchxml",
    template_path="i2c-level-shifter-module.dchxml",  # or any native-saved file
    output_path="my-board-native.dchxml",
)
```

The template contributes ALL standard sections the DipTrace 5.3 loader needs:
Settings, Categories, Simulator, ERC templates, Sheet BorderZones,
ProjectLibs, DesignCache. Our content is grafted into these containers.

**CRITICAL**: Template must use the SAME UNITS as your content. If template is
inch and your coordinates are mm, everything will be 25× off-page. The
`nativeize_document()` function forces mm on both sides.

Sheet dimensions: set `SheetWidth`/`SheetHeight` on each Sheet element
(A4 landscape = 297×210 mm).

### Stage 4: Verify schematic opens

```bash
# Via Windows interop (WSL):
cmd.exe /c ".local\rt.bat schematic <abs_path> 60"
# Expected: {"ok": true, "sha256_after": "..."}
```

Or run ERC via the MCP: `run_erc(path="my-board-native.dchxml")`.

### Stage 5: PCB build

Follow attiny85's `build_pcb.py::build()` pattern:

1. Load nativeized schematic → strip net ports → physical only
2. Create PCB scaffold (`build_pcb_document`)
3. Sync via `build_sync_plan(physical, board, mappings=[ComponentSyncMapping(...)])
   - Each mapping: refdes, pattern_style, x, y, side
   - Pattern styles come from schematic Library PatternStyle names
4. Rotate components (`RotateComponentsOperation`)
5. Route nets in priority batches:
   - USB diff pairs first (width 0.25, clearance 0.18)
   - Power trunks (width 0.6, Top layer preferred)
   - Analog (I²C, ADC) next
   - Digital catch-all last
6. Sanitize pad widths (--sanitize-pads)
7. GND pours + stitching (`add_copper_pours`, stitch_pitch=4.0, clr=0.22)
8. Silkscreen (`hide_assembly_markings` + `plan_silkscreen`)
9. Headless QC (`review_pcb_quality`) — target hard_error_count == 0

**Router budgets**: max_nodes must bind before wall-clock. Use
max_nodes=1M, route_time_budget_ms=900K (measured ~300s worst case).
Grid 0.125mm for fine boards; 0.5mm for large boards.

**Pad sanitization**: EasyEDA copper often exceeds DipTrace's 0.13mm rule at
fine pitches (MSOP/TSSOP). Shrink width to (min_neighbour_distance − 0.35mm).

### Stage 6: Preview + native verify

```bash
# SVG preview (no DipTrace needed)
python scripts/render_board_svg.py

# Native DRC (requires Windows/Wine DipTrace)
py -3 scripts/diptrace_native_gate11.py --diptrace-root ... --project ... --output ...
```

Gate criteria: DRC errors should be manufacturing-tolerance items only,
not design errors.

## File naming convention

```
<project>.dchxml              ← generated schematic (synthetic)
<project>-native.dchxml      ← transplanted, opens in DipTrace
<project>-pcb.dipxml         ← placed+routed board
<project>-native.dipxml      ← transplanted board
vendor/                       ← LCSC JSONs + PDFs + .elixml libs
rules/                        ← datasheet design rules per IC
PCB_BUILD.md                  ← gate table handoff
COMPONENT_PROVENANCE.md       ← part sourcing evidence
```

## Gotchas (learned the hard way)

| Gotcha | Fix |
|---|---|
| Scaffold XML hangs DipTrace | ALWAYS nativeize after generation |
| Template inch + content mm = 25× offset | Force Units="mm" in nativeize |
| Alphanumeric pad numbers hang sync | Renumber sequentially + alias JSON |
| Duplicate pad numbers (EPAD grid) | Merge into single pad with union bbox |
| Pattern pad order ≠ pin order | Sort pattern pads to match pin sequence |
| Router time budget binds first | Set node cap > wall clock estimate |
| EasyEDA copper exceeds DRC rule | Sanitize pad widths post-sync |
| Pours exceed 2048 stitch candidates | Increase stitch_pitch_mm |
| RawTreeSnapshot.compile rejects mutations | Capture BEFORE mutation, compile AFTER |
| Component Id collisions in sync | Ensure unique Ids across all embedded libraries |
