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
- For PCB and schematic recordings, show components and connections appearing
  one at a time in a plausible human construction order.
- Frame recordings from the design boundary: for PCBs, use the purple board
  outline, fit the whole board with about 10% margin, keep the framing stable,
  and exclude editor controls. Apply the equivalent boundary-fit rule to
  schematic recordings.
- After a visual PCB change, regenerate and inspect the PCB, MP4, and GIF. Check
  the final frame as well as the staged sequence.
