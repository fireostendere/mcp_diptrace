---
name: pcb-design-workflow
description: RAG-backed. Take a DipTrace board through requirements, source evidence, schematic, PCB, production handoff, bring-up, and revisions using existing project skills and explicit build gates. Use for a full design cycle, a new board specification, or resuming a PCB build; «полный цикл платы», «ТЗ на плату», «продолжи разработку». Use when the user says “Take this board through the complete design and production cycle.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# PCB design workflow

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Carry evidence from MIT/theory, board-design guides and DipTrace courses through
architecture, schematic, placement/routing, production and test; consult it at each decision stage.

Coordinate the requested lifecycle stages; read each linked skill only when its stage
is needed. Current user instructions and the project's `AGENTS.md`, when present,
determine scope, engineering evidence, house rules, and acceptance. A request to prepare a
production package authorizes local preparation, not ordering, payment, or publication.

## Establish or resume the project

- Resolve the project directory, schematic/PCB paths, revision, assembly variant,
  requested endpoint, and available hardware. Reuse the existing naming and reports.
- For an existing design, use
  [pcb-project-intake](../pcb-project-intake/SKILL.md) to inventory exact
  document identities. Read its specification, rules, and `PCB_BUILD.md`.
- For a new design, create a concise `PROJECT_SPEC.md`: purpose, interfaces and pinout,
  input ranges and protection, rail/load/startup budget, exact critical variants,
  enclosure/connector datums, dimensions, environment, fab/assembly process, quantity,
  programming/test access, and measurable acceptance criteria. Record unknowns rather
  than inventing electrical or mechanical requirements. Ask only about choices that
  change the design; continue independent work.
- Sketch functional blocks and power domains. Bind every consequential requirement to
  its source and a verification method. Mark estimates and proposed choices explicitly.
- Assemble and maintain the RAG engineering brief from theory, board practice, DipTrace
  courses and project lessons. Proactively surface coupled risks and alternatives;
  carry the context from schematic to layout, production and bring-up without waiting
  for another expert-role prompt. Preserve useful decisions in the existing project journal.
- Before resuming an existing PCB handoff, run the quality gate below. A failure returns
  work to the owning stage. A new specification without a board is not a passed PCB gate.

## Stage routing

| Requested outcome | Skill to read |
|---|---|
| Datasheet, package, pinout, layout and revision evidence | [diptrace-datasheet-rules](../diptrace-datasheet-rules/SKILL.md) |
| BOM, catalog parts, availability and substitutions | [diptrace-bom-sourcing](../diptrace-bom-sourcing/SKILL.md) |
| Library pin/pad validation | [library-quality-audit](../library-quality-audit/SKILL.md) |
| Architecture and schematic construction | [schematic-engineer](../schematic-engineer/SKILL.md), then [schematic style](../schematic-engineer/references/schematic-style.md) |
| Schematic ERC and connectivity review | [schematic-erc-review](../schematic-erc-review/SKILL.md) |
| Mechanics, critical placement, stackup, routing, silk | [PCB implementation](references/board-layout.md) |
| Ground system and stitching | [Ground and finish](references/board-layout.md#ground-and-finish) |
| Constrained routing and SI when relevant | [critical-net-router](../critical-net-router/SKILL.md), [signal-integrity-review](../signal-integrity-review/SKILL.md) |
| Physical test access | [testpoint-planner](../testpoint-planner/SKILL.md) |
| DFM/DFA/DFT and release review | [release-gate](../release-gate/SKILL.md) |
| Native DipTrace verification | [diptrace-evidence-capture](../diptrace-evidence-capture/SKILL.md) |
| Fabrication/assembly files and production handoff | [diptrace-production-pack](../diptrace-production-pack/SKILL.md) |
| First article, programming, measurements, production tests | [diptrace-board-bringup](../diptrace-board-bringup/SKILL.md) |
| ECO, revision comparison, regression and re-release | [diptrace-revision-review](../diptrace-revision-review/SKILL.md) |

## PCB gates and checkpoint

Maintain `PCB_BUILD.md` using the
[handoff template](references/pcb-build-template.md). Keep this order:

1. Electrical checks.
2. Official source evidence.
3. Footprint and pin-map validation.
4. Mechanics and connector datums.
5. Datasheet-driven critical placement.
6. Two-layer-first stackup.
7. Critical then remaining routing.
8. Zero ratlines.
9. Top/Bottom GND pours and distributed stitching.
10. Silkscreen.
11. Headless QC.
12. Native DipTrace refill, connectivity, and DRC.
13. Media and release inspection.

These are acceptance gates, not permission to defer evidence until after dependent
design decisions. A failed gate invalidates downstream evidence affected by the defect.
Never mark a later gate PASS over an unresolved earlier gate. A narrower task stops
at its requested endpoint without claiming the remaining gates passed.

Record input/output hashes, evidence paths, last passing gate, current failure,
intentional datasheet deviations and consequences, exact executable resume command,
and last checkpoint commit. Make narrow checkpoint commits after evidence/footprints,
placement/routing, and native acceptance/media. Preserve unrelated changes. When Git
writes are unavailable, record exact intended files and commit commands without
claiming a commit exists.

From the source repository root (this project-specific checker is not shipped in the
wheel):

```bash
PYTHONPATH=src .venv/bin/python scripts/pcb_quality_gate.py <project-dir>
```

If several revisions coexist, supply explicit absolute `--board` and `--schematic`
paths. Non-zero is BLOCKED. Exit zero checks hash/order consistency and headless QC;
pending manual gates still need evidence. The checker contains a thermal-via exception
for a historical board, so independently enforce the current no-via-in-pad rule.
If only the wheel is installed, record the missing checkout/checker and perform the
available MCP checks; do not claim the repository handoff gate passed.

Inspect the chosen builder before executing it. The current
`scripts/build_generic_board.py` invokes DUT Rev.A
scripts and tolerates some stage failures; it is not a safe universal dispatcher for a
new board. Reuse a fitting maintained builder or guarded MCP operations with explicit
project targets. Historical recipe numbers are examples, not current design rules:
never shrink verified pads or merge thermal-pad geometry to suppress errors; route
constrained differential pairs as pairs; permit via-in-pad only with the explicitly
requested compatible filled/capped process. Native DRC failures remain failures.

## Finish the requested endpoint

Return actual artifact paths, revision and hashes, passed/failed/missing gates, and
the exact next action when blocked. Regenerate and inspect PCB/MP4/GIF after a visual
PCB change as required by AGENTS.md, including staged sequence and final frame.
A consistent checkpoint, a native-accepted PCB, a production package, and a tested
physical board are separate results; report only those supported by evidence.

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
