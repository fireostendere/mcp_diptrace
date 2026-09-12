# Readable DipTrace schematic construction

Project instructions and electrical correctness take precedence. These drawing rules
are adapted from the project's DipTrace schematic-style skill and packaged here so
the schematic workflow also works outside a source checkout.

## Parts and layout

- Search exact installed MPNs with `query_builtin_library_catalog`, then verified
  catalog data; custom drawing follows documented misses. Reuse verified native
  symbols, electrical pin types, mappings, and attached patterns.
- Flow left to right; place support networks beside the IC pins they serve. Orient
  connectors toward the circuit while preserving understandable physical pin order.
- Use native positive-rail symbols above the signal path and local GND symbols below.
  Text annotations do not replace power ports. Net Ports stay out of the physical BOM.
- Keep references, values, labels, and notes horizontal, readable and near their object.
  Counter-rotate markings when the component orientation would make them unreadable.
- Align peer blocks consistently; use a compact topology that follows actual interfaces.
  Apply the accumulated design/DipTrace course context while preserving the requested
  visual scope; retrieve further examples when they help the task.

## Wiring and connectivity

- Logical `connect_pins` and graphical `add_wire` are distinct operations. Check the
  actual connectivity graph and native view; a populated netlist is not visible wiring.
- Escape straight from a pin before a bend. Prefer short orthogonal paths; do not cross
  bodies, foreign pins/stubs, labels, or unrelated wires. Move parts when that removes
  unnecessary detours. Distinguish crossing lines from connected junctions.
- Put a native Net Port with the intended name and real pin connection on each sheet
  participating in a global connection. Set the component Name, not only pin text.
  Explicitly selected Connect Nets by Name can also work, but verify its native result.
- Check every pin's intended net or NC state, hierarchy scope, and multi-part identity.
  Investigate unintended generated net names rather than cosmetically renaming them.
- Documentary lines must end on visible blocks/ports/junctions. A documentary
  `Shape Type="Line"` has exactly two endpoints; represent bends as multiple segments.

## Page and overview

Schematic page coordinates are centered at the origin. Viewport XPos/YPos do not move
the design. With the page's own margins, the usable bounds are:

```text
min_x = -SheetWidth / 2 + LeftMargin
max_x =  SheetWidth / 2 - RightMargin
min_y = -SheetHeight / 2 + BottomMargin
max_y =  SheetHeight / 2 - TopMargin
```

Fit all components, wires, power ports, markings, and notes inside those bounds.
For multi-sheet designs, make a top-level functional overview with one block per
sheet and clear labeled logical interfaces. Documentary blocks add no electrical
connections or physical BOM entries. Include power distribution only when it is the
point of the overview or the user asks for it.

## Supported editing and verification

Use `add_sheet`, `place_builtin_component`/`place_part`, `connect_pins`, `add_wire`,
`add_net_label`, `set_pin_no_connect`, `set_component_fields`, and `rename_net` as
advertised. For placement/wiring repair, inspect
`rank_schematic_placement_candidates` and `plan_schematic_placement_repair`, then
apply the stored plan through `apply_schematic_placement_repair_plan` with normal
preview/hash/post-checks. Already-wired ranking requires the advertised explicit
allow-existing-wires options; it is not itself a mutation or automatic repair.

Inspect geometry, pin escape, page containment, readability, and connectivity after
each bounded batch. Before scaling a new pattern to many sheets, verify one sheet
through the [native runtime](../../shared/runtime.md). Known Shift Origin handling
belongs to the bounded native worker; unknown dialogs are not coordinate-click targets.
Record schematic media when requested; follow current project media rules for PCB work.
