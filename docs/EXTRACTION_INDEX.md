# Extraction index: what was taken from where → where it lives now

This file maps every reusable pattern from the two proven builds.

## From attiny85-arduino-clone (3772 LOC)

| Source file | Pattern | Destination | Lines |
|---|---|---|---|
| layout_and_wire.py: compute_endpoints, compute_body_boxes | Pin geometry | `schematic_wiring.py` | 50 |
| layout_and_wire.py: add_ground_symbols | GND symbols | `schematic_wiring.py` + SKILL §2A | — |
| layout_and_wire.py: add_named_net_ports, attach_named_ports | Net ports | `schematic_wiring.py` + SKILL §2A | — |
| layout_and_wire.py: wire(), port(), append_wires() | Wire routing | `schematic_wiring.py` (WireSpec, SchematicWireBuilder.wire) | 35 |
| layout_and_wire.py: append_overview, append_graphic, append_text | Overview sheet | SKILL §2A | — |
| layout_and_wire.py: annotate_rotated_parts | RefDes labels for rotated parts | SKILL §2A | — |
| layout_and_wire.py: center_sheet_content, content_bounds | Sheet layout | SKILL §2A | — |
| layout_and_wire.py: pin_stubs, body_intersections, crossing_count | Wire quality checks | SKILL §2A | — |
| build_connectivity.py: NETS dict → ConnectPinsOperation | Declarative netlist | `schematic_wiring.py::SchematicWireBuilder` + SKILL §1 | — |
| build_pcb.py: strip_schematic_to_physical | Strip net ports for sync | `pcb_build_kit.py` | 18 |
| build_pcb.py: _renumber_j1_shield_pads / _tie_j1_shield_to_gnd | Pad renumber pattern | `pcb_build_kit.py` | 12 |
| build_pcb.py: make_intent / _intent() | PCBIntentOverrides | `pcb_build_kit.py` | 18 |
| build_pcb.py: inject_route_keepout | Keepout shapes | `pcb_build_kit.py` | 12 |
| build_pcb.py: inject_markings_preset | Silk markings fix | `pcb_build_kit.py` | 18 |
| build_pcb.py: dump_stage | ATTINY_STAGE_DIR | `pcb_build_kit.py` | 5 |
| build_pcb.py: placement_from_dict | POS→sync mapping | `pcb_build_kit.py` | 5 |
| build_pcb.py: router_config / priority batches (groups) | Routing | SKILL §5 | — |
| build_pcb.py: headless QC gate | `review_pcb_quality` | SKILL §7 | — |
| build_pcb.py: Native refill/DRC (gate11) | `diptrace_native_gate11.py` | SKILL §7 | — |
| set_bom_fields.py: SetComponentPropertiesOperation | BOM fields | `provenance.py` | 20 |
| convert_lcsc_*.py: EasyEDA JSON → elixml | Component sourcing | `pipeline.py::lcsc_fetch` | 80 |
| PCB_BUILD.md: gate table (monotonic) | Build handoff | SKILL §7 | — |
| COMPONENT_PROVENANCE.md: resolution order | Provenance | `provenance.py` | — |
| rules/*.md: per-IC datasheet rules | Layout constraints | SKILL gotchas | — |

## From i2c-level-shifter (532 LOC)

| Source file | Pattern | Destination |
|---|---|---|
| build_i2c_level_shifter_pcb.py: _compact_standard_header | Footprint modification via RawTreeSnapshot | `pcb_build_kit.py` note |
| build_i2c_level_shifter_pcb.py: _placement_stage | Progressive stage rendering | `pcb_build_kit.py::dump_stage` |
| build_i2c_level_shifter_pcb.py: _physical_schematic variant | Strip to physical | `pcb_build_kit.py` |
| build_i2c_level_shifter_pcb.py: compact single-script build | One-shot pipeline | SKILL intro |
| Native template pattern | Generate→transplant | `pipeline.py::nativeize_document` |
| SVG preview pattern | Quick check w/o GUI | `pipeline.py::render_board_svg` |

## From dut-controller-reva (this session)

| Pattern | Destination |
|---|---|
| Pad order + alphanumeric renumber + EPAD merge | `lcsc_library.py` |
| Pad width sanitizer | `pcb_build_kit.py` sanitize note |
| Connection-budget chunking (64-link router bound) | `scripts/build_dut_controller_reva_pcb.py::route_rest` |
| 3 new MCP tools | `pipeline.py` + `server_runtime.py` (170 tools) |

## What stays project-specific (intentionally NOT extracted)

- Exact POSITIONS dict per board (board dimensions drive this)
- WireSpec waypoint coordinates (functional layout drives this)
- Component spec (which MPNs for this board's function)
- Net topology (which pins form which nets for this circuit)

These are specified declaratively per board via a board-spec JSON (see templates/).

