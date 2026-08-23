# Repository instructions

## User-taught PCB house rules

Apply these defaults to PCB generation and demonstration media unless the user
explicitly requests otherwise. Datasheets, electrical safety, DRC, mechanical
constraints, and manufacturability take precedence.

- For standard 2.54 mm connectors, choose the simplest, smallest practical
  footprint by default.
- Before placing any physical part, verify its exact manufacturer package and
  land pattern against the official datasheet. For ICs, also extract the current
  layout guidelines/example and check the datasheet revision history. Treat the
  vendor layout topology as the default constraint; document every intentional
  deviation and its consequence. Missing evidence blocks the PCB build.
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
- Disable via-in-pad by default. Escape each transition beyond the pad copper
  edge plus applicable clearance before placing the via. Allow via-in-pad only
  when the user explicitly requests a compatible filled/capped fabrication
  process.
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

## PCB build order and handoff

Use this gate order without skipping: electrical checks; official source
evidence; footprint/pin-map validation; mechanics and connector datums;
datasheet-driven critical placement; two-layer-first stackup; critical then
remaining routing; zero ratlines; Top/Bottom GND pours and distributed
stitching; silkscreen; headless QC; native DipTrace refill/DRC; media and
release inspection. A failed gate returns to the stage that owns the defect.

Maintain a project `PCB_BUILD.md` containing input/output SHAs, the last passing
gate, current failure evidence, intentional datasheet deviations, exact resume
command, and the last checkpoint commit. Make narrow commits after evidence and
footprints, after placement/routing, and after native acceptance/media. If Git
write access is unavailable, record the exact intended files and commit command
instead of claiming that a checkpoint exists.

Verify the handoff mechanically before resuming or handing off:
`PYTHONPATH=src .venv/bin/python scripts/pcb_quality_gate.py <project-dir>`
checks gate-table ordering, recorded SHAs against the files on disk, and the
headless QC (`hard_error_count == 0`); non-zero exit means BLOCKED.
