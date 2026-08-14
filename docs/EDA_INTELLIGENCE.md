# EDA Intelligence — Current Implementation

This is the evergreen cross-domain map for higher-level schematic/PCB intelligence after the post-0.2.1 development work. Historical release and acceptance records remain immutable evidence snapshots and must not be rewritten to inherit later capabilities.

## Safety model

The intelligence modules generate facts, candidates, scores, feedback, or ordinary semantic operations. They do not bypass the existing allowed-root, expected-SHA, policy, preview, transaction, backup/recovery, live-session, or review boundaries.

The public MCP contract was intentionally expanded from 159 to **165 registered tools** to productize a bounded selection of the engines below (see [MCP_TOOLS.md](MCP_TOOLS.md)). All other modules in this document remain internal/package-level unless a public tool is explicitly added and the tools/list snapshot is intentionally updated.

The project-level manual acceptance matrix is also complete for its recorded scope: **all 12 blocking manual gates are PASS across the accepted checkpoints**. That evidence remains bound to those exact checkpoints and is not inherited automatically by later release bytes.

## Schematic pipeline

The current deterministic pipeline is:

1. `schematic_layout.py` — functional blocks, part/net roles, provenance-bearing reference motifs and readability metrics;
2. `schematic_optimizer.py` — bounded placement candidate generation and first-stage interconnect/readability scoring;
3. `schematic_pin_geometry.py` — conservative pin geometry resolution from the embedded Component Library Design Cache;
4. `schematic_wire_planner.py` — bounded non-mutating wire candidate cleanup/scoring with explicit placement feedback;
5. `schematic_joint_optimizer.py` — pin-aware placement + route scoring over sheet-local net groups;
6. `schematic_placement_repair.py` — bounded placement changes driven by route feedback;
7. `schematic_ensemble.py` — deterministic motif + route + congestion ranking across placement candidates;
8. `schematic_atomic_reroute.py` — selective existing-wire replacement for nets touched by moved parts.

### Atomic selective reroute

`plan_atomic_schematic_placement_reroute` removes only explicit wire geometry for affected `(net, sheet)` groups, virtually applies the selected placement, resolves the new endpoints, replans each affected net with the existing bounded wire planner, and fails the whole plan if any affected route cannot be safely rebuilt.

The returned operation order is dependency-safe:

`DeleteWireOperation* -> MoveComponentsOperation* -> AddWireOperation*`

Passing the complete operation list to the existing semantic transaction path gives one preview/SHA/commit boundary for placement and replacement wires. The planner itself is non-mutating. Unwired nets are not turned into page-spanning explicit wires by default, and unaffected existing wire geometry is not rewritten.

Current limitation: affected explicit nets are rebuilt from resolved pin endpoints through deterministic MST edges; arbitrary hand-authored junction topology is not preserved as a visual constraint.

### Motifs and congestion

Builtin motifs are explicitly labelled `source_kind="builtin"` and describe only deterministic readability heuristics inferred from normalized roles. They never masquerade as datasheet/reference-design evidence.

The schematic ensemble adds a bounded congestion estimate using placement-grid occupancy, hotspot cells, local neighboring pressure and sheet span. Route defects remain lexicographically more important than congestion/compactness.

External/project/datasheet motifs can still be supplied explicitly with provenance. Automatic external motif ingestion remains separate work.

### Real-DipTrace schematic quality checkpoint

The initial product-quality campaign in `SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md` is complete. Cases 01–18 exercised real DipTrace authoring/readability, incremental edits, transaction safety, single- and multi-net atomic reroute, obstacle/readability repair, native Save/Close/Reopen/re-export and a repaired 22-part stress schematic.

The final repaired stress case was operator-accepted and all 12 required schematic semantic categories survived native round-trip. PR #90 merged the bounded production fixes while preserving the frozen 159-tool public contract. This is evidence for the tested campaign scope, not a universal DipTrace-layout or global-optimality claim.

Future schematic real-host work is impact-based: rerun only cases plausibly affected by later production changes, or add new cases for genuinely new claims such as hierarchy, external motif ingestion, topology preservation or automatic symbol rotation.

## PCB Generations A-D

The current layers are:

- **Generation A:** `pcb_design_intent.py` and `pcb_placement.py` — roles, blocks, multi-role nets, explicit operator constraints and bounded intent-aware placement;
- **Generation B:** `pcb_physical.py` — exported stackup/reference context, PDN topology proxies, hot-loop candidates, return-path/noise/via-role analysis;
- **Generation C:** `pcb_routing_policy.py` — deterministic net routing policy/order and conservative observed-route checks;
- **Generation D:** `pcb_joint_optimizer.py` — hard-first bounded candidate comparison.

`pcb_candidate_ensemble.py` creates real Generation-A placement candidates under multiple engineering profiles (`balanced`, `critical_nets`, `noise_aware`, `support_compact`) plus the existing-board baseline. Generation B/C facts contribute conservative soft evidence terms, and the existing Generation-D selector chooses the winner with hard safety/mechanical/connectivity/DRC/reference/manufacturing violations lexicographically dominant.

No SI/PI/thermal/EMI proxy is upgraded into field-solver truth. Unknown stackup/current/edge-rate/reference facts remain unknown or penalized as uncertainty. Real-DipTrace/native-router/solver evidence remains claim-specific.

## DSN/SES and XML analysis

`specctra_analysis.py` adds non-mutating pre-import analysis on top of the bounded Specctra path: structural inventory, route net/wire/via/segment counts, total route length/width range, route layer inventory, duplicate SES net detection, unknown target-board nets/layers and semantic import-planner classification into importable/skipped nets.

`xml_analysis.py` provides a deterministic semantic fingerprint/inventory for parsed XML, including unknown elements. Attribute order and outer text whitespace do not change the fingerprint; element order remains significant. A companion delta reports local structural additions/removals and tag/attribute-count changes. This supplements, but does not replace, domain-level connectivity comparison.

## Evidence automation

The existing operator capture pipeline still owns `source -> open/save -> re-export`, hashes, attestations and quarantine/candidate creation.

`evidence_report.py` and `scripts/build_evidence_report.py` can turn a finalized review-only candidate into deterministic JSON/Markdown while rechecking artifact SHA-256 bindings and computing XML semantic fingerprints/deltas.

The report builder cannot grant PASS, provenance trust, fixture trust or release acceptance. Operator claims remain labelled as operator-supplied facts. Trust promotion continues to require a separate reviewed action.

## Component/Pattern mutation API preparation

`library_mutation.py` remains the internal raw-preserving writer core with real-editor evidence for its controlled scope.

`library_mutation_api.py` adds a stable expected-SHA-bound package contract around that core: `LibraryMutationRequest`, in-memory mutation/validation, deterministic result SHA, XML semantic delta/fingerprint, explicit pin/pad mapping errors and `public_registration=False` in the preview.

This is API preparation, not a new public MCP tool. Registering native-library writes publicly remains a deliberate product/API decision and must update the public contract snapshot and claim/evidence documentation.

## Cinematic hardening

Cinematic replay remains a presentation subsystem, not engineering authority.

`cinematic_preflight.py` adds deterministic content identity independent of random session IDs plus bounded checks for cue count, duration/timing consistency, payload bytes, desktop-command count, path points, typed text and hotkey chord size. `cinematic_preflight_cli.py` provides standalone inspection.

The safety boundary is also enforced inside `cinematic_host.py`: `play_manifest()` calls `preflight_cinematic_manifest(manifest)` before any dry-run or real desktop driver action. Exact DipTrace UI macros/calibration remain editor/version/configuration specific. PCB via/layer-transition replay remains fail-closed until staged real-UI macros are validated.

## Documentation drift guard

`scripts/check_documentation_state.py` compares evergreen current-state docs with the implemented module set and frozen public-tools snapshot, checks that cinematic playback still enforces preflight and library mutation remains package-only, and rejects known stale current-state acceptance/reroute/headless-CLI claims. `tests/test_documentation_state.py` executes that contract in the normal CI test matrix.

Historical dated evidence/release records are intentionally excluded from current-state freshness assertions.

## Testing

New regression/property coverage includes:

- selective reroute scope, source immutability and locked-part refusal;
- deterministic schematic motif/congestion ensemble behavior;
- deterministic PCB ensemble generation and Generation-D ranking reuse;
- DSN/SES structure/importability analysis;
- Hypothesis XML fingerprint invariants and unknown-XML mutation detection;
- evidence-report hash/tamper/determinism behavior;
- cinematic preflight budgets/content identity and mandatory playback invocation;
- SHA-bound library mutation preview behavior;
- evergreen documentation-state regression.

Repository CI remains authoritative. The supported-environment combined coverage gate remains 90%; the geometry-enabled Linux-only floor remains 85%.

## What still needs real hardware/software/operator evidence

The completed 18-case schematic campaign and the completed 12-gate manual matrix should not be repeated without an impact- or claim-based reason. Remaining manual/native evidence is claim-specific and currently includes:

- current-candidate PCB whole-board/native refill/plane/via quality acceptance where stronger claims are desired;
- exact UI-profile cinematic replay validation;
- release-specific Windows/client lifecycle retests only when changed production code/artifacts or a new claim make them relevant;
- new schematic claims outside the completed campaign scope, such as hierarchy, topology-preserving reroute or automatic rotation/pin-facing behavior;
- manufacturing output, independent review, regulatory, EMC, PI, thermal or field-solver sign-off.
