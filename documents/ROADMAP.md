# Project Roadmap

## Purpose and audit baseline

This is the forward-looking project roadmap. It was first written after a repository
review on 2026-08-16 and re-based on 2026-11-10 after the server review recorded in
[MCP_REVIEW_2026-11-10.md](../docs/MCP_REVIEW_2026-11-10.md) (`main@3041f00`). It
consolidates the current-state records in
[the maintained roadmap](../docs/ROADMAP.md),
[technical debt](../docs/TECH_DEBT.md),
[open compatibility questions](../docs/OPEN_QUESTIONS.md), and the implementation.
The companion [manual roadmap](MANUAL_ROADMAP.md) owns gates that require a real
operator, licensed software, physical hardware, legal authority, or independent
approval.

The published release is still `v0.4.0` (167 tools). Everything below describes
post-release `main`, whose public surface is 152 tools.

## Decision model

The neural reviewer is important, but it is not the sole safety boundary:

- the model interprets design intent, proposes candidates, and can extract a
  draft of sourced rules;
- deterministic validators enforce path, SHA, policy, transaction, geometry,
  connectivity, and hard-rule boundaries;
- hard violations dominate soft aesthetic scores and cannot be downgraded by a
  model response;
- missing current, voltage, stackup, material, temperature, timing, or source
  data remains `unknown` rather than being invented;
- real DipTrace, fabrication, laboratory, legal, and independent-review claims
  close only through the [manual roadmap](MANUAL_ROADMAP.md).

The project-specific layout and recording rules in [AGENTS.md](../AGENTS.md)
remain acceptance criteria: compact 2.54 mm connectors, sensible symmetry,
compact centered placement, two-layer ground strategy, generous GND stitching,
four-spoke connector thermals, clean silkscreen, staged replay, and
design-boundary framing.

## Closed work that must not return to the backlog

The following capabilities already exist and need regression maintenance, not
another implementation project:

- guarded preview/apply, expected SHA, policy, backup, transaction, and live
  session safety;
- the public surface was consolidated from 167 to 152 tools after `v0.4.0`; the
  schemas are snapshot-guarded but still require client/release regression
  validation when changed;
- schematic intent, bounded placement ensemble, iterative repair, interconnect
  strategy, and atomic affected-net reroute;
- PCB Generations A-D, candidate-specific physical review, compactness,
  centering, symmetry, GND pour/stitching/thermal checks, and silkscreen planning;
- the internal whole-board pipeline in
  [pcb_whole_board.py](../src/diptrace_mcp/pcb_whole_board.py);
- SHA-bound structured engineering-rule ingestion with provenance;
- bounded qualitative physics principles and explicit unknowns;
- XML/connectivity evidence reports, DSN/SES analysis, external solver adapters,
  and internal Component/Pattern mutation;
- board-framed PCB/Schematic GIF and MP4 capture for the accepted examples;
- the historical 12/12 manual matrix and schematic cases 01-18.

Those closed campaigns are rerun only for an impacted path or a new claim, not
as a blanket release ritual.

## Closed: the 2026-08-16 plan (A0-A8)

Every automated item of the first plan is closed; see
[AUTOMATABLE_ROADMAP_CLOSURE.md](../docs/AUTOMATABLE_ROADMAP_CLOSURE.md). The manual
gates they named stay claim-triggered.

| Item | Outcome |
| --- | --- |
| A0 reconcile with `origin/main` | done |
| A1 in-memory MCP transport timeout | resolved; MCP is served by a project-owned protocol server and the transport tests pass |
| A2 whole-board plan behind preview/apply | package-level guarded preview/apply; default enablement waits for M1 |
| A3 reviewer evaluation harness | implemented; label approval is M11 |
| A4 source provenance for rule packs | implemented; each pack needs M3 before it backs a claim |
| A5 topology-preserving reroute | implemented for proven acyclic graphs; M2 per new topology family |
| A6 confidence-gated rotation | implemented, disabled by default; M2 |
| A7 bounded quantitative physics | implemented; M3/M8 for claims |
| A8 evidence campaign aggregation | implemented; promotion stays M11 |

Since then `main` also gained: the consolidated 152-tool surface, DipTrace 5.3.5.1
native profiles next to 5.3.0.3, Linux/macOS host installation, the schematic stage
of the quality gate with per-stage done criteria, design-wide schematic readability
review, and the reviewed fifteen-skill catalog.

## P0 — stop false passes

A check that reports PASS without having checked is worse than a missing check.
These come first and need no public-schema change.

### B1. Real copper connectivity in headless QC and the board gate

Compute per-net connectivity from pads, trace endpoints and vias (union-find), and
count every net with more than one group as unrouted. Disclose nets that rely on a
pour instead of guessing: the i2c board's GND has no traces and is legitimately
pour-connected, so pour-only nets are reported as `native_refill_required`, not as
errors and not as connected. Run `run_checks` in the board stage of
`pcb_quality_gate.py` and block on its errors and skipped checks.

Done when: a board with one trace removed fails QC and the gate; the three
repository boards keep their current verdicts for the right reasons; the pour-only
disclosure is visible in the QC report.

### B2. Validate and correct differential microstrip impedance

Do not ship the reviewer's proposed formula on trust. First pin reference values
from a cited published table or the openEMS adapter for at least the three
reproduced geometries, then correct the odd/even-mode expressions, add the copper
thickness to stripline plane separation, and keep the validity-range warnings.

Done when: the calculator is within a stated tolerance of the pinned references,
and the references, their source and the tolerance are in the tests. M3 owns source
applicability.

### B3-B6. Make skipped geometry visible

- B3: use the pad bounding box as a fallback obstacle, or count the pad as skipped
  and set `partial_skipped`; skip placeholder-box components in overlap/edge checks
  with a reason.
- B4: unrouted nets yield `net_unrouted` / unavailable in length and pair checks;
  `within_tolerance` is `null` without a tolerance.
- B5: add supplier part numbers to the BOM grouping key when the MPN is empty.
- B6: coarsen the stitching sample pitch instead of returning nothing; rotate and
  mirror silkscreen text boxes; reject traces outside the outline.

Done when each has a regression test built from the reproduction in the review.

## P1 — write-path and contract hardening

### B7-B12. Write path

- B7: with `txid` and `dry_run=false`, commit only what was previewed; appending
  requires `dry_run=true`. Remove the silent identical-operation dedupe.
- B10: validate `move_via` / `add_via` with the path validation `_replace_trace`
  already uses.
- B11: `place_part` requires a library definition and a matching pin count.
- B9: resolve nets by name; accept an XML id only in an explicit form.
- B12: decide an age limit for transactions that never reached commit (retention
  keeps non-terminal records on purpose today), then prune them.
- B8: `expected_schematic_sha256` on `sync_schematic_to_pcb` — public-schema change,
  bundle with B13.

### B13-B16. One intentional contract revision

Batch every change that touches the frozen snapshot into a single revision so
clients revalidate once (M5):

- B13: `readOnlyHint` / `destructiveHint` / `openWorldHint` on all tools;
- B8: the schematic SHA input;
- B16: `selector` required where it is required, unknown arguments rejected, `ok`
  on every success envelope, remaining domain error codes mapped;
- B14: a tool → capability-key map and corrected net-class/testpoint capability
  answers.

B15 (per-instance job ownership in a shared state directory, compare-and-set on
cancel) is internal and can land separately.

Also settle the Q1 Component Angle status: either flip
`Q1_COMPONENT_ANGLE_LIVE_VALIDATED` with the accepted evidence or correct the
documents that already say PASS.

## P1 — close the tool gaps the skills work around

The review lists twelve gaps (G1-G12). Each adds public tools, so each needs the M12
decision first. Recommended order, by how often the repository's own board builds
needed the workaround:

1. **G3 + G4 copper pours and free stitching vias** — the internal
   `copper_pours` functions exist; house rules require both on every board.
2. **G6 + G7 + G12 small authoring deletes** — delete part/sheet/net label, board
   text add/delete, `place_builtin_component` inside a transaction. Small, and they
   remove most remaining raw `apply_xml_edits` use.
3. **G9 + G1 gate and native acceptance as jobs** — wrap `pcb_quality_gate` and the
   native acceptance CLIs in the existing job store, so a packaged install without a
   checkout can run the definition of done.
4. **G5 + G8 outline, holes, net classes, pairs, via styles.**
5. **G10 + G11 paginated schematic readers and a public wire planner.**
6. **G2 native manufacturing export** — only after M12 selects it and M6 can follow.

Keep the discovery budget: prefer one tool with a `kind`/`action` input over a tool
per object type, the way `run_review(profile=...)` replaced fourteen tools.

## P2 — triggered work, not speculative commitments

These tasks start only after the named evidence demonstrates a real need:

| Trigger | Minimal implementation | Required manual gate |
| --- | --- | --- |
| Non-rectangular or crowded boards fail current bounding-box compaction | Courtyard/pad/hole/keepout-aware polygon compaction with conservative fallback | M1; M6 only for a fabrication-ready claim |
| Differential-pair cases fail because of escapes, neck-down, or skew | Bounded symmetric escapes, explicit-rule neck-down, and phase tuning through the existing clearance path | M1 for native DRC; M8 only for SI-performance claims |
| Controlled DSN/SES samples expose a dialect gap | Add only the observed grammar/import rule and a byte-bound fixture | M9 |
| A reusable UI profile needs layer changes or vias | Add the exact calibrated gesture and staged cue | M4 |
| A supported native manufacturing workflow is selected | After decision M12, orchestrate the native/external exporter and validate its manifest; do not invent Gerber/NC Drill writers | M6 after implementation |
| Product owner approves public Component/Pattern mutation | Reuse the package API, add the narrow schema/policy/tests, and intentionally update the public snapshot | M12 |
| A current-state document actually drifts from code | Extend the existing drift checker with the smallest stable semantic assertion | None |

Do not pre-emptively build push-and-shove routing, a global optimizer, an OAuth
server, a multi-user trust model, generic fixture apply, dark-theme image
histograms, or a broad library writer. Add one only after a recorded product need
or a reproducible failing case.

## Recommended execution order

1. B1, then B3-B6: the gate must not pass what it did not check.
2. B2 with pinned references.
3. B7, B10, B11, B9, B12, B15: internal write-path fixes.
4. One contract revision for B8, B13, B14, B16; run M5 for the named clients.
5. Tool gaps in the order above, each after its M12 decision; G3/G4 first.
6. Cut the next release once 1-4 are in: `main` already differs from `v0.4.0` by a
   breaking surface change, and the fixes in 1 affect release decisions.
7. A P2 item only when its trigger exists.

## Definition of done for automated roadmap items

An automated item is complete only when:

- its smallest useful public or package-level contract is documented;
- deterministic tests cover success, refusal, stale input, and data-loss paths;
- no model output can bypass hard rules or transaction safety;
- missing physical facts and unsupported host semantics remain explicit;
- generated snapshots, release allowlists, documentation checks, and full CI
  pass at one exact SHA;
- code completion and claim authorization are recorded separately: automated
  work may finish first, while any stronger native, physical, legal, or
  independent-review claim cites its completed gate in
  [MANUAL_ROADMAP.md](MANUAL_ROADMAP.md).

## Permanent non-claims

This roadmap does not promise universal DipTrace compatibility, globally
optimal placement/routing, invented electrical values, vendor endorsement,
solver-grade SI/PI/thermal/EMC proof from heuristics, fabrication or regulatory
sign-off from CI, signed trust without a protected identity, or independent
review without an independent reviewer.
