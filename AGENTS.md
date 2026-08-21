# Repository instructions

## User-taught PCB house rules

Apply these defaults to PCB generation and demonstration media unless the user
explicitly requests otherwise. Datasheets, electrical safety, DRC, mechanical
constraints, and manufacturability take precedence.

- For standard 2.54 mm connectors, choose the simplest, smallest practical
  footprint by default.
- Keep boards compact. Derive the outline from component courtyards plus a sane
  manufacturing margin, remove unused space, center the layout, and preserve
  visual symmetry when it does not harm placement or routing. A connector's
  occupied dimension may define the corresponding board dimension.
- On ordinary two-layer boards, route signals and positive power on Top. Keep
  Bottom as an effectively continuous GND plane; also pour GND on Top. Break
  the Bottom plane only when a necessary via or physical constraint requires it.
- Stitch Top and Bottom GND generously across every free region, not merely one
  edge. On small boards, start around a 2 mm grid, obey clearances, and verify
  coverage in every part of the board instead of relying only on the via count.
- Connect soldered connector GND pads to pours with a four-spoke cross thermal
  relief so they remain easy to solder.
- Keep silkscreen readable, close to its associated component, and visually
  aligned. It must not enter another component's mounting/courtyard space or
  overlap pads, holes, or vias. Silkscreen may cross copper traces because the
  traces remain under solder mask.
- Demo media is opt-in. Do not create recordings, MP4, GIF, or staged screenshot
  sequences during ordinary engineering work unless the user explicitly asks
  for a demo, capture, or evidence package.
- When PCB or schematic recordings are explicitly requested, show components
  and connections appearing one at a time in a plausible human construction
  order.
- Frame requested recordings from the design boundary: for PCBs, use the purple
  board outline, fit the whole board with about 10% margin, keep the framing
  stable, and exclude editor controls. Apply the equivalent boundary-fit rule
  to schematic recordings.
- After a visual PCB change, regenerate and inspect MP4/GIF only when that demo
  media was explicitly requested. Check the final frame as well as the staged
  sequence.

## Component-library lookup order

For every schematic component, use this mandatory order and record the lookup
result before placing or creating anything:

1. Search the installed DipTrace component libraries and use the matching
   built-in component, including its native symbol, pin mapping, and attached
   pattern.
2. If DipTrace has no matching component, search LCSC/JLCPCB by exact MPN and
   use the available catalog component/library data.
3. Draw a custom component only after both searches have documented zero exact
   matches. Validate its pinout and footprint against the manufacturer
   datasheet before use.

Never substitute a hand-drawn generic symbol when an exact DipTrace or LCSC
component exists. Apply the same lookup order to connectors and passives where
catalog parts are required for the deliverable.

## Schematic wiring rules

- Lay out every sheet for human reading, not for an autorouter score: functional
  flow goes left-to-right, positive rails stay above the signal path, and GND
  symbols sit below the components they return.
- Put external connectors and other signal or power sources on the left and
  receiving functional blocks on the right. On hierarchy/overview blocks, put
  input ports on the left edge and output ports on the right edge.
- Keep every sheet centered inside its real DipTrace page bounds. Treat
  `XPos`/`YPos` as viewport state, not page coordinates; derive the usable area
  from `SheetWidth`/`SheetHeight` and the four margins, then verify that all
  components, wires, symbols, labels, and annotations remain inside it.
- Place each support component beside the IC pin it serves. Move components to
  make a connection short and obvious before adding bends or a long detour.
- Keep local wires short, orthogonal, and inside their functional block. Never
  use a sheet-edge or perimeter loop to avoid a crossing; rearrange the block
  instead.
- Avoid wire crossings. If two connections compete for the same space, change
  component placement first. A formally valid but visually ambiguous route is
  not acceptable.
- Prefer visible orthogonal wires for connections within a sheet. Every
  cross-sheet/global connection must terminate in a native DipTrace Net Port
  component on each participating sheet. Root `Text`/net-label shapes are
  annotations only and must never be used as electrical connectivity.
- Use exact installed native power Net Port symbols for positive rails (for
  example `+3V3` and a VCC-style symbol named `VBUS`) and the native GND symbol
  for ground. Hide the GND name marking when the symbol alone is unambiguous
  and the text would add rotated clutter.
- Treat an auto-generated net name matching `Net <number>` as a hard failure:
  repair the native Net Port connectivity and confirm the intended name
  survives a native DipTrace open/save/re-export.
- From every IC pin, run a clear straight segment outward before the first bend.
  Never turn immediately beside a pin row or route along neighboring pin stubs.
- Never route a wire through any component body, including the source or
  destination component, and never cross an unrelated component pin or pin
  stub.
- Keep reference designators, values, net names, sheet names, and port labels
  horizontal, upright, unobstructed, and close to what they describe. Rotate the
  component or counter-rotate its markings when needed.
- Orient or mirror connectors so their wire-facing pins point into the sheet or
  functional block while preserving a readable top-to-bottom pin order.
- For a multi-sheet design, add a top-level overview sheet with one block per
  functional sheet and visible orthogonal connections labelled with the key
  cross-sheet nets. Keep this overview documentary: do not duplicate circuitry
  or create unintended electrical connectivity or BOM entries.
