# EDA Intelligence — Current Implementation

This is the evergreen cross-domain map for the higher-level schematic/PCB intelligence.
Historical release and acceptance records remain immutable evidence snapshots and do not
inherit later capabilities automatically.

## Safety model

The intelligence modules generate facts, candidates, scores, feedback or ordinary semantic
operations. They do not bypass allowed-root, expected-SHA, policy, preview, transaction,
backup/recovery, live-session or review boundaries.

The public MCP surface remains **167 registered tools**. New roadmap modules in this document
are package-level unless explicitly productized and added to the frozen public contract.

**All 12 blocking manual gates are PASS across the accepted checkpoints.** The Claude
Desktop restart was completed later than the historical `0bb09b4...` checkpoint: it is
PASS on a separate machine that had Claude Desktop and DipTrace MCP but **did not have
Codex installed**. Therefore it is independent client/host evidence, not a same-host
Codex-vs-Claude comparison. The older Claude waiver remains only as historical chronology
for the earlier checkpoint.

## Schematic pipeline

The current deterministic pipeline includes:

1. `schematic_layout.py` — functional blocks, part/net roles, provenance-bearing motifs and
   readability metrics;
2. `schematic_optimizer.py` — bounded placement candidates and first-stage scoring;
3. `schematic_pin_geometry.py` — conservative Design Cache pin geometry;
4. `schematic_wire_planner.py` — bounded non-mutating wire planning and quality feedback;
5. `schematic_joint_optimizer.py` — pin-aware placement/route scoring;
6. `schematic_placement_repair.py` — bounded repair driven by route feedback;
7. `schematic_ensemble.py` — deterministic motif/route/congestion ranking and iterative
   objective history;
8. `schematic_topology.py` — literal existing-wire graph recovery;
9. `schematic_rotation.py` — confidence-gated cardinal rotation candidates;
10. `schematic_atomic_reroute.py` — atomic affected-net delete/rotate-or-move/rebuild.

### Atomic selective reroute

The atomic planner removes only affected explicit sheet-local wire geometry, proves the
source topology before mutation, applies the selected placement/rotation virtually,
resolves replacement endpoints and rebuilds the affected groups.

For proven connected acyclic existing-wire graphs, all intentional junctions on affected
pin-to-pin paths are preserved. Cyclic, free-leaf, incomplete or ambiguous hand-authored
topology fails closed instead of being silently flattened or converted to an unrelated MST.

The dependency-safe batch is:

`DeleteWireOperation* -> RotateComponentsOperation*/MoveComponentsOperation* -> AddWireOperation*`

The complete batch uses the existing semantic transaction path for one
preview/SHA/commit/rollback boundary. Unaffected explicit geometry is not rewritten and
unwired nets are not silently converted to page-spanning explicit wires.

### Rotation authority

Cardinal 0/90/180/270 candidates are produced only for unlocked parts with complete
high-confidence pin geometry. Source pin geometry and post-rotation geometry are kept
separate so rotated endpoints cannot become circular evidence for the original topology.
Automatic rotation remains disabled by default and requires focused M2 real-host evidence
before a symbol/editor family is enabled or claimed.

### Motifs and sourced rules

Builtin motifs remain deterministic heuristics and never masquerade as datasheet or
reference-design evidence.

`reference_rules.py` validates source-bound engineering rule packs. Claim-eligible facts
must carry source SHA-256, revision, exact locator, units/limit semantics, conditions and
applicability. Missing or ambiguous provenance remains explicit; model memory is not a
source.

## Reviewer evaluation

`advanced_review.py` now includes a provider-neutral reviewer evaluation contract for
versioned PCB/schematic cases and replayed structured responses. Scoring keeps deterministic
hard-rule adjudication authoritative and reports hard-defect recall, false alarms,
hallucinated facts, source mistakes, connectivity regressions and ranking stability.

Ground-truth cases marked `pending_m11` cannot be treated as approved evaluation truth.
M11 remains the human trust/promotion gate.

## PCB Generations A-D

The PCB layers remain:

- **Generation A:** engineering intent and bounded placement;
- **Generation B:** stackup/reference/PDN/return-path/noise context;
- **Generation C:** routing policy and observed-route checks;
- **Generation D:** hard-first bounded candidate comparison.

`pcb_candidate_ensemble.py` generates bounded in-memory alternatives for Generation-D
selection. `pcb_physics_knowledge.py` and `pcb_quality.py` add deterministic source-linked
qualitative review and explicit unknown physical facts. `pcb_whole_board.py` composes
placement, routing, outline, copper and silkscreen stages.

The whole-board path now has a guarded package-level preview/apply contract bound to source
SHA, candidate SHA and deterministic plan identity. Apply rechecks stale input, hard review
findings and post-write identity and uses the existing backup/rollback safety boundary.
Authoritative DipTrace refill/native DRC remains unresolved until M1 evidence is collected
for the exact candidate/claim.

## Quantitative engineering estimates

`physics_estimates.py` provides bounded explicit-input analytical helpers for trace/via DC
resistance, voltage drop, aggregate loss and first-order thermal estimates. Results record
exact inputs, method/source identity, assumptions, limitations and sensitivity. Missing
geometry/material/current/source facts remain `unknown`; typical values are never inserted
silently.

M3 governs source applicability and M8 governs physical correlation/sign-off. Calculator
output is not SI/PI/thermal/EMC proof.

## DSN/SES and XML analysis

`specctra_analysis.py` provides bounded non-mutating DSN/SES structure/importability
analysis. `xml_analysis.py` provides deterministic semantic fingerprints and structural
deltas including unknown XML. Neither grants compatibility or mutates a project by itself.

## Evidence automation

`capture_diptrace_evidence.py` remains the trust-neutral source/open-save/re-export capture
boundary. `evidence_report.py` produces deterministic per-candidate reports and rechecks
artifact hashes.

`evidence_campaign.py` aggregates multiple candidate reports, exact-hash media/frame
metrics, exported geometry/manufacturing deltas, explicitly untrusted AI visual findings and
promotion/rejection requests under a deterministic campaign identity. It cannot grant PASS,
provenance trust, fixture trust, native refill authority or registry promotion. Those remain
separate human decisions under M11 and the relevant claim gate.

## Component/Pattern mutation

`library_mutation.py` remains the internal raw-preserving writer core.
`library_mutation_api.py` provides an expected-SHA package-level preview contract and remains
`public_registration=False`. A public native-library write tool still requires an explicit
M12 product/API decision and intentional frozen-contract update.

## Cinematic and hidden GUI

Cinematic replay remains presentation automation rather than engineering authority.
`cinematic_preflight.py` enforces deterministic preflight before replay; calibrated UI
profiles, visible/hidden capture and the hidden Win32 desktop helper remain separate
presentation infrastructure. Exact editor/version/profile gestures remain
configuration-specific evidence and unverified via/layer-transition gestures fail closed.

## Documentation drift guard

`scripts/check_documentation_state.py` and `tests/test_documentation_state.py` protect
current-state claims against known stale public-tool, reroute, cinematic, headless and
acceptance wording. Historical dated evidence/release records remain excluded from evergreen
freshness assertions.

## Testing and evidence boundaries

Repository tests cover the automated roadmap layers, including transport responsiveness,
guarded whole-board planning, reviewer evaluation, source-bound rules, topology preservation,
rotation gating, quantitative estimates and evidence campaigns. CI remains authoritative for
repository behavior.

The initial 18-case real-DipTrace schematic campaign remains PASS for its recorded scope. New
topology-preserving reroute and automatic rotation claims do **not** inherit that evidence;
focused M2 validation is still required before enabling or claiming them.

Remaining real-host/human evidence is claim-specific, including stronger whole-board
refill/DRC claims (M1), engineering-source applicability (M3), physical correlation/sign-off
(M8), evidence promotion (M11) and new public/default product decisions (M12).
