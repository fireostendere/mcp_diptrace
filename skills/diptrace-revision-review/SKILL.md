---
name: diptrace-revision-review
description: RAG-backed. Compare DipTrace hardware revisions, trace electrical/BOM/layout changes, and prepare an ECO with affected verification and release artifacts. Use for netlist diffs, substitutions, rework reconciliation, design regressions, or a new board revision; «сравни ревизии», «ECO платы». Use when the user says “Compare these DipTrace revisions and prepare an ECO.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# DipTrace revision review and ECO

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Carry the RAG engineering context across revisions to explain changes, identify
coupled consequences, compare alternatives and choose meaningful regression checks.

A comparison is read-only for CAD. An explicit change request permits only that
change; it does not authorize overwriting an old release or ordering replacement boards.

## Compare exact revisions

1. Resolve old/new schematic and PCB paths, BOM variants, release manifests, rules,
   and relevant firmware versions. Hash each source and preserve immutable baselines.
   Do not infer the baseline from filenames or modification dates alone.
2. Discover MCP capabilities and read models/connectivity for each document with
   explicit paths. Compare components by stable identity and RefDes, checking
   manufacturer/MPN, value, fitted/DNP state, pattern, pin numbers, and pin-to-pad map.
3. Compare nets as endpoint sets: schematic `(sheet, RefDes, pin)` and PCB
   `(RefDes, pad)`. Report renamed nets separately from changed membership.
   Handle explicit hierarchy/ports, multi-part symbols, and duplicated names; do not
   conflate an unchanged display name with unchanged connectivity.
4. Use `compare_schematic_to_pcb` for each matched schematic/PCB revision pair.
   It compares schematic to PCB, not two arbitrary revisions. For revision diffs,
   compare exported models with existing repository helpers or ordinary JSON/set
   operations; never invent a revision-diff MCP tool.
5. Compare board outline, holes/datums, side/position/orientation, footprints, stackup,
   netclass/clearance/width constraints, traces/vias, pours/keepouts, testpoints, and
   silk as applicable. Disclose unmodeled fields and native-format limits. A text
   XML diff alone is not an electrical or mechanical comparison.
6. Recheck source hashes after the read. Identify intended edits, incidental changes,
   unexplained differences, and evidence gaps with exact affected objects.

## When implementing an authorized ECO

- Record the reason, old/new parts or connections, affected units/revisions, and
  acceptance criteria in `ECO.md` or the project's existing change log.
- Revalidate substitutions through
  [diptrace-bom-sourcing](../diptrace-bom-sourcing/SKILL.md) and
  [diptrace-datasheet-rules](../diptrace-datasheet-rules/SKILL.md).
- Use guarded semantic edits with preview, validation, expected SHA, and post-checks.
  Schematic-to-PCB synchronization is additive by default; inspect every removal or
  reconnection. Enable exact reconciliation only when it matches the authorized ECO
  and the preview accounts for every affected component, endpoint, and route.
- Never silently unlock, delete, or overwrite unrelated objects, user edits, or a
  released manufacturing package. Record physical rework against the affected units.

## Revalidate and release

Write a compact change table with object, before, after, reason, consequence, and
verification result. Return to the earliest affected gate in
[pcb-design-workflow](../pcb-design-workflow/SKILL.md) and invalidate dependent passes,
hashes, native acceptance, media, and production files. A visual-only change still
requires affected geometry/silk checks and the repository media inspection.

Update `PCB_BUILD.md`, run its quality gate for an existing board, and record the
checkpoint/resume command. For production scope, regenerate a distinct package through
[diptrace-production-pack](../diptrace-production-pack/SKILL.md); for assembled hardware,
define regression/rework tests through
[diptrace-board-bringup](../diptrace-board-bringup/SKILL.md).

Deliver the comparison/ECO and passed/failed/unavailable verification. Do not call a
revision equivalent or ready for release while required mappings or deltas are unresolved.

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
