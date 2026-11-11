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
post-release `main`, whose public surface is 159 tools.

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

Since then `main` also gained: the consolidated tool surface (167 to 152, now 159), DipTrace 5.3.5.1
native profiles next to 5.3.0.3, Linux/macOS host installation, the schematic stage
of the quality gate with per-stage done criteria, design-wide schematic readability
review, and the reviewed fifteen-skill catalog.

## Closed: the 2026-11-10 review items

| Item | Outcome |
| --- | --- |
| B1 copper connectivity | board gate computes it; pour-only joins disclosed for native refill |
| B2 differential microstrip | corrected to the air-impedance/modal-permittivity structure; reference geometries pinned; not field-solver validated |
| B3-B5 | missing geometry disclosed; unrouted nets have no length; BOM grouping keeps supplier codes apart |
| B6 | stitching coverage on large boards and traces outside the outline fixed; silkscreen box rotation open |
| B7, B10-B12, B15 | previewed-only commits, via-move validation, library-checked `place_part`, expiring abandoned previews, per-server job ownership |
| B8, B13, B16 | one contract revision: schematic SHA for sync, annotations, strict arguments, uniform envelope |
| G1 native checks | `run_native_check` job around the existing helpers (source installs only) |
| G3, G4 pours and stitching | `add_copper_pours`, `delete_copper_pours` |
| G5 outline | `set_board_outline` (straight edges; holes and cutouts open) |
| G6 schematic deletes | `delete_parts`, `delete_net_labels` (sheet and PCB component deletes open) |
| G9 quality gate | `run_quality_gate`; the gate ships in the package |
| G10 schematic readers | covered by paged `query_objects` (parts, pins, wires, nets) |
| G12 | `place_builtin_component` accepts `txid` |

## P0 — evidence for what was just added

New write tools change native documents, and nothing here has been opened in DipTrace:

- **M1** for `add_copper_pours` / `delete_copper_pours` / `set_board_outline`:
  generate, open, refill, DRC, save, re-export, compare. The pour writer is the one the
  operator-accepted I2C board used, but the tool path is new.
- **M2** for `delete_parts` and `delete_net_labels` on a real schematic round-trip.
- **`run_native_check`** has been exercised only up to "the helper starts and its exit
  code is recorded"; run each of its four checks on a host with a reviewed DipTrace
  build. Packaged (frozen) servers refuse it: decide whether to ship the helpers as
  executables.
- **M5** for the contract revision with the named clients: unknown arguments are now
  refused, `selector` is required on write tools, sync commits need the schematic SHA.
- **B2** against a field solver (the openEMS adapter) before any impedance claim.

## P1 — remaining review items

- **B14**: publish a tool → capability-key map and give the pipeline tools a key.
- **B9**: accept an XML id for a net only in an explicit form.
- **B6**: rotate and mirror silkscreen text boxes; needs a board with rotated and
  bottom-side text as a fixture.
- Run `run_checks` in the board gate once its overlap/edge findings on the accepted
  ATtiny board are triaged.
- Settle the Q1 Component Angle status (flag vs documents).
- Triage `unresolved_endpoint_owner` on the ATtiny schematic (net items naming absent
  part ids).

## P1 — tool gaps that still need a native reference

No repository board contains these objects, so there is no native XML to model them
on. Each needs one DipTrace-authored sample (M10) before a writer is added:

| Gap | Missing |
| --- | --- |
| G5 | mounting holes, cutouts, keepout authoring, outline arcs |
| G7 | board text add/delete/set content |
| G8 | create/delete net class, differential pair and via style; write DRC rules/stackup |
| G6 | delete sheet (sheet renumbering), remove a PCB component with its traces |
| G11 | public wire planner for `add_wire` (the internal planner exists) |
| G2 | native Gerber/NC Drill/pick-and-place as a tool (`native_cad` API exists; needs M12 then M6) |

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

1. M1/M2 evidence for the new write tools and one real run of each native check.
2. M5 for the contract revision, then cut the next release: `main` now differs from
   `v0.4.0` by two breaking surface changes.
3. B14, B9, the gate's `run_checks` triage.
4. One native sample per remaining gap, then its writer.
5. A P2 item only when its trigger exists.

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
