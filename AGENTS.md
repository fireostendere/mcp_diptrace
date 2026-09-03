# Repository instructions

## Knowledge / RAG usage policy

The current DipTrace project and explicit user instructions are the primary
source of truth for the current editing task.

Use Knowledge MCP / RAG only when external or previously recorded knowledge is
actually required to decide WHAT the design should contain, HOW something
should work, or WHICH engineering rule/recommendation applies.

Use RAG when:

- engineering knowledge is missing or uncertain;
- a datasheet, application note, standard, reference design, or project
  specification is needed;
- component-specific requirements are unknown;
- the task asks WHY or HOW something should be implemented;
- current project state is insufficient to make a technically correct decision.

Do NOT query RAG when the task can be completed from:

1. the user's current explicit instruction, and
2. the current DipTrace project/editor state.

In particular, do NOT query RAG for:

- visual rearrangement;
- moving existing blocks/components;
- alignment, spacing, grouping, or cosmetic cleanup;
- changing the visual composition of a sheet;
- hiding/removing already-understood documentary connections;
- operations whose desired result is fully specified by the user;
- verification that can be performed directly through DipTrace MCP.

Examples:

`How should USB D+/D- be routed?` → RAG is appropriate.

`What are the layout requirements for TPS62130?` → RAG is appropriate.

`Which logical interfaces should this system overview contain?` → RAG may be
appropriate if the current project/specification does not answer it.

`Move these blocks so the sheet looks cleaner.` → Do NOT use RAG.

`Remove the power lines and leave only the logic lines.` → Do NOT use RAG when
the existing lines can already be identified from the current schematic.

`Move R15 2 mm to the right.` → Do NOT use RAG.

When the user gives an explicit instruction that conflicts with older project
documentation retrieved from RAG, do not silently override the user with the
older document. Treat the user's current instruction as the desired edit unless
doing so would create a technical/safety contradiction that must be surfaced.

Before calling `knowledge_search`, ask internally: "Is there a material fact I
do not know that is required to perform this task?" If no, do not call RAG.

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
