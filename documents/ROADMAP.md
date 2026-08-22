# Project Roadmap

## Purpose and audit baseline

This is the forward-looking project roadmap after a repository review on
2026-08-16. It consolidates the current-state records in
[the maintained roadmap](../docs/ROADMAP.md),
[technical debt](../docs/TECH_DEBT.md),
[open compatibility questions](../docs/OPEN_QUESTIONS.md), and the implementation.
The companion [manual roadmap](MANUAL_ROADMAP.md) owns gates that require a real
operator, licensed software, physical hardware, legal authority, or independent
approval.

The reviewed local checkout was
`codex/pcb-physics-reviewer@9733902397698fbe5f11fb3ed112070b9cacbcbd`.
It was one commit ahead of and six commits behind its remote branch. The same
feature had already reached
`origin/main@1a5522537967b57b3401bc4cefdc73c6049b4b6b`, together with follow-up
schema-budget, snapshot, release-allowlist, and regression-test fixes. No merge,
commit, tag, release, or push was performed during this audit.

That mainline commit is post-`v0.3.0` unreleased development. The published
`v0.3.0` artifacts do not contain or inherit the physics-aware changes.

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
- the 167-tool count is retained; the current schemas are snapshot-guarded but
  still require client/release regression validation when changed;
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

## Local workspace prerequisite — not project backlog

### A0. Reconcile the local feature history with `origin/main`

This applies to the reviewed checkout only; the fixes are already merged on
`origin/main`. The local commit has two known release/contract failures:

- the public MCP discovery payload grows by about 26.65% against a 15% budget;
- the release allowlist omits six new source/test files.

The fixes already exist on `origin/main`; they should be reused rather than
reimplemented.

Done when:

- new work starts from, or is cleanly reconciled with, the merged mainline;
- MCP discovery growth is at or below the configured budget;
- the generated snapshot check and release artifact audit pass after
  reconciliation;
- the full Linux, macOS, Windows, static, coverage, packaging, and contract jobs
  are green at one exact SHA.

## P0 — restore deterministic MCP transport validation

### A1. Reproduce and resolve the in-memory MCP call timeout

The audit reproduced a five-second timeout in
`test_mcp_protocol_lists_and_calls_tools` while calling `summarize_design`, both
on the local tree and on an isolated `origin/main` archive. A direct service call
finished in about 23 ms, so the observed delay is in the MCP transport/runtime
path rather than design summarization itself. The combined transport/event-loop
run also failed to terminate normally after its first failure.

This is still a diagnosis item: the audit virtual environment uses an older
pytest than the declared dev range, although its Python and MCP runtime versions
are supported. Do not label the source broken until the declared environment is
reproduced.

Done when:

- a clean environment satisfying `pyproject.toml` reproduces the test at least
  twice, or records the old virtual environment as the cause;
- list, call, cancellation, timeout, and session teardown are profiled
  separately;
- any source fix is placed at the shared runtime/offload boundary rather than in
  `summarize_design` alone;
- the existing server and event-loop responsiveness tests finish without
  timeout, leaked task, or teardown hang on every supported CI environment;
- the timeout is not merely increased unless measured latency justifies a new
  explicit budget.

## P0 — make the completed PCB pipeline safely usable

### A2. Put whole-board optimization behind the existing guarded plan/apply path

The internal optimizer already composes placement, routing, compact outline,
two-layer GND pours, stitching, silkscreen, and final review. The missing product
step is a safe authoring entry point; the algorithms themselves should not be
duplicated.

Implementation boundary:

- convert the internal result into an expected-SHA-bound plan with a stable
  stage list, preview, semantic/connectivity delta, warnings, assumptions, and
  final `PCBQualityReview`;
- keep source bytes immutable until the existing transaction layer commits;
- fail closed on stale SHA, stage failure, hard review findings, or rollback
  failure; mark authoritative refill as unresolved/native-required instead of
  pretending that boundary geometry is final copper;
- reuse an existing public authoring contract if it can carry this plan. Add a
  new MCP tool only after proving that the existing surface cannot express it.

Code-complete when:

- preview and commit produce the same planned result identity;
- fault-injection tests cover every stage and rollback;
- unchanged/unsupported boards produce an explicit refusal or no-op;
- package-level experimental preview remains possible without a native claim.

Manual gate M1 is required before enabling whole-board mutation by default or
publishing a real-DipTrace quality/refill claim; it does not block the code from
being implemented and tested.

## P1 — measure and improve the reviewer

### A3. Add a provider-neutral reviewer evaluation harness

The largest model-dependent risk is not lack of another heuristic; it is lack of
measured reviewer quality. Build the smallest fixed evaluation loop around the
existing schematic/PCB trap catalogs and hard-first selectors.

Deliverables:

- versioned, sanitized PCB and schematic cases with known hard defects,
  acceptable alternatives, explicit unknowns, and human-reviewed labels;
- one structured reviewer response schema;
- generation followed by deterministic adjudication; add a separate critic pass
  only if the evaluation shows a measurable benefit worth its cost, and never
  allow it to waive a deterministic hard violation;
- metrics for missed hard defects, false alarms, invented facts, rule-source
  mistakes, connectivity regressions, and candidate-ranking stability;
- a compact regression report by model/provider/prompt/rule-pack version.

Done when the corpus, scoring, and replay of stored responses are reproducible
offline, every output is bound to its inputs, hard-failure recall and
hallucination rates are visible, and a model upgrade can be compared before it
becomes the default. M11 owns ground-truth label approval; M12 owns promotion of
a model/prompt/rule-pack version to the default.

### A4. Harden source provenance and extract into the existing rule-pack

The repository already validates structured packs; it does not yet provide a
source-to-pack workflow for explicitly supported document and section types.
The three built-in qualitative PCB principles currently link source documents
but do not carry the same exact revision/SHA/page-locator metadata as a rule
pack. Fix that first, then add bounded extraction without weakening the existing
trust model.

Code-complete when:

- every proposed fact carries source SHA-256, document revision, page/table or
  figure locator, units, limit type, conditions, and applicability;
- built-in qualitative principles use the same exact provenance discipline or
  are represented through the existing pack;
- conflicting, ambiguous, unitless, or unsupported facts fail closed;
- adversarial fixtures catch wrong citations, unit conversion mistakes, and
  model-memory substitutions;
- non-redistributable source bytes are not placed in the repository.

M3 approves technical applicability and rights before a pack can affect an
engineering claim; that approval is separate from implementation completion.

### A5. Preserve proven schematic topology during reroute

Current affected-net repair can conservatively reuse one nearby degree-three
junction; otherwise it rebuilds bounded MST edges. Extend it only far enough to
preserve topology that is actually present and unambiguous.

Code-complete when:

- the original sheet-local net graph and all proven branch/junction nodes are
  extracted before planning;
- Y, T, and multi-junction fixtures retain their topology and unaffected
  geometry;
- ambiguous or incomplete graphs produce a structured refusal instead of an
  MST rewrite;
- atomic reroute and rollback invariants remain unchanged;
- arbitrary hand-authored topology outside the proven graph remains refused.

M2 is required before enabling or claiming support for each changed topology
family.

### A6. Add confidence-gated schematic rotation and pin-facing candidates

Rotation operations and bounded pin geometry exist, but automatic optimizer
rotation is intentionally disabled until host semantics and geometry confidence
are sufficient.

Code-complete when:

- only unlocked parts with adequate pin-geometry confidence receive
  0/90/180/270-degree candidates;
- orientation participates in route/readability scoring and any affected wiring
  is rebuilt atomically;
- ambiguous symbols keep their source angle.

M2 is required before enabling a symbol family or making an exact DipTrace
rotation/pin-facing claim.

### A7. Inventory, validate, and extend quantitative physics from sourced inputs

Start with a gap inventory of existing impedance, resistance, PDN, thermal, and
external-adapter helpers so nothing is duplicated. Then extend only the missing
bounded calculations for which all required values are known. Likely useful
scope includes trace/via DC resistance, voltage-drop/current budgets, simple
loss budgets, and disclosed first-order thermal estimates.

Code-complete when:

- formulas, validity ranges, units, assumptions, and source references are
  versioned;
- every result records its exact inputs and sensitivity;
- incomplete inputs remain `unknown` and no typical value is silently supplied;
- analytical estimates remain separate from ngspice/openEMS results;
- deterministic tests cover limits and unit conversions.

M3 owns source applicability and M8 owns physical correlation/sign-off; neither
is implied by the calculator implementation.

### A8. Deepen evidence comparison without granting automatic PASS

Extend the existing per-candidate evidence report only where it reduces manual
review effort.

Useful next increments:

- campaign-level JSON/Markdown aggregation;
- exported-geometry and exported-manufacturing deltas in addition to
  domain/connectivity deltas; do not present them as authoritative native refill;
- hash-bound screenshots and frame metrics;
- untrusted AI visual findings with links to the exact image and rule;
- promotion/rejection records in the existing evidence/provenance registry.

Done when tampered or missing inputs are obvious, repeated reports are
deterministic, and no code path can promote provenance, fixture trust, or PASS
without the separate human decision in M11.

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

1. Reconcile this checkout under A0 and establish one green exact SHA.
2. Reproduce and close A1 before treating local or CI transport results as
   authoritative.
3. Implement A2 and run one exact-candidate M1 smoke before default/public
   mutation or native-quality claims.
4. Implement A3 and approve its ground-truth labels under M11; promote a new
   default model/prompt only through M12.
5. Implement A4, then run M3 on each rule pack or built-in principle intended
   for engineering use.
6. Implement A5/A6 only for measured failures, then run the matching focused M2
   cases before enabling or claiming that scope.
7. Inventory and implement the justified portion of A7; use M8 only for the
   corresponding physical-performance claim.
8. Add A8 or a P2 item only when its trigger exists.

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
