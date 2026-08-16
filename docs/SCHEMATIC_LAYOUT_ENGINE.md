# Schematic Layout Engine

## Status

The schematic intelligence track is a bounded deterministic pipeline behind the existing
semantic-operation, preview, expected-SHA, transaction and real-DipTrace evidence
boundaries. Public placement/repair tools remain intentionally narrow; the newer topology
and rotation helpers are package-level and do not expand the 167-tool MCP contract.

Current modules:

- `schematic_layout.py` — design intent, functional blocks, provenance-bearing motifs and
  readability metrics;
- `schematic_optimizer.py` — bounded placement candidates and first-stage interconnect
  scoring;
- `schematic_pin_geometry.py` — conservative embedded Design Cache pin resolution;
- `schematic_wire_planner.py` — non-mutating wire candidates and route-quality feedback;
- `schematic_joint_optimizer.py` — pin-aware placement/routing scoring;
- `schematic_placement_repair.py` — bounded route-feedback-driven placement repair;
- `schematic_ensemble.py` — motif, route, congestion and iterative objective-history
  ranking;
- `schematic_topology.py` — literal existing-wire graph recovery and validation;
- `schematic_rotation.py` — confidence-gated cardinal rotation candidates;
- `schematic_atomic_reroute.py` — atomic placement/rotation plus affected-net rebuild.

See [EDA_INTELLIGENCE.md](EDA_INTELLIGENCE.md) for the cross-domain map.

## Design intent and motifs

Intent inference uses normalized schematic facts: RefDes/names/values, pin/net
connectivity, multipart identity and explicit caller/reference data. It does not infer a
datasheet from a part name.

Reference motifs express relative constraints such as `near`, left/right, above/below,
same-row and same-column. Every motif retains provenance and confidence.

`reference_rules.py` accepts strict source-bound engineering-rule packs. Engineering facts
must retain source SHA-256, revision and locator metadata before they can become
claim-eligible. Missing or ambiguous provenance remains explicit and cannot be supplied
from model memory.

Builtin readability motifs remain deterministic heuristics and are never presented as
manufacturer/reference-design approval.

## Placement, pin geometry and route scoring

Placement search remains bounded and deterministic. Locked parts, operator-fixed moves
and unresolved geometry remain fail-closed constraints.

Pin geometry is resolved from the embedded Component Library Design Cache only when
identity is sufficiently strong. Missing or ambiguous pin ownership is not guessed.

Route defects are lexicographically more important than aesthetic placement scores.
Source XML and normalized source objects are not mutated during candidate scoring.

## Confidence-gated rotation

`schematic_rotation.py` generates 0/90/180/270-degree candidates only when the target part
is unlocked and the complete pin geometry reaches the configured confidence threshold.
Orientation contributes to pin-facing and route/readability scoring.

The engine deliberately separates source pin geometry from post-rotation geometry:
source geometry is used to prove the existing hand-authored topology, while rotated
geometry is used only to construct replacement endpoints. This prevents a rotation
candidate from retroactively becoming evidence for the topology it is about to change.

Automatic rotation remains disabled by default. Enabling a symbol/editor family or making
an exact DipTrace rotation/pin-facing claim still requires the focused M2 real-host gate.

## Topology-preserving atomic reroute

`schematic_topology.py` reconstructs the literal existing wire graph for each affected
sheet-local net before mutation. A graph is eligible for topology-preserving reroute only
when it is connected, acyclic and unambiguous and all relevant pin/junction ownership is
resolved.

For eligible branched nets, every proven junction on the affected pin-to-pin paths is
preserved. The planner no longer flattens a valid multi-junction tree merely because it
contains more than one intentional junction.

The planner fails closed for:

- cyclic existing-wire graphs;
- unexplained free-leaf branches;
- incomplete pin/junction ownership;
- ambiguous topology;
- locked affected parts;
- excessive bounded scope or other hard transaction preconditions.

`plan_atomic_schematic_placement_reroute` composes one dependency-safe semantic batch:

`DeleteWireOperation* -> RotateComponentsOperation*/MoveComponentsOperation* -> AddWireOperation*`

Only actually affected explicit wire geometry is removed. Unaffected explicit geometry is
preserved and remains an obstacle during replanning. Unwired nets are not silently turned
into page-spanning explicit wires.

The planner itself never writes XML. Applying the complete operation list through the
existing transaction layer provides one preview/SHA/commit/rollback boundary, so delete,
rotate/move and rebuild are all-or-nothing.

Readability defects may remain as explicit quality feedback when connectivity can still be
rebuilt safely; destructive replacement is refused when connectivity/topology evidence is
not sufficient.

## Placement repair and ensemble

`schematic_placement_repair.py` translates route feedback into bounded hypothetical moves.
Functional blocks can move as rigid groups; locked/unresolved groups remain immutable.
A repair is selected only when its joint rank strictly improves.

`schematic_ensemble.py` combines motif, route and bounded grid-congestion signals, records
objective history and stops when no strict improvement is available or the configured
iteration limit is reached. It also returns explicit wire/label/bus/power-symbol strategy
without silently mutating connectivity.

## Existing direct-planner refusal

Older placement-only planners may still refuse already-wired schematics. That remains
correct: placement-only mutation cannot safely leave stale wire geometry behind. Existing
wire support belongs to the atomic selective-reroute path.

## Testing and real-host evidence

Repository tests cover:

- deterministic candidate generation/ranking and pin resolution;
- source immutability and affected-net scope;
- multi-junction tree preservation;
- cycle/free-leaf/ambiguous-topology refusal;
- locked and unresolved-part refusal;
- confidence-gated cardinal rotation and stale-candidate refusal;
- atomic `delete -> rotate/move -> rebuild` ordering;
- rollback/transaction invariants and explicit route-quality feedback.

The initial real-DipTrace authoring/readability campaign (cases 01–18) remains PASS for its
recorded scope. It must not be reinterpreted as evidence for the newly added topology and
rotation claim scope. M2 is required before enabling or claiming those newer families in a
real DipTrace host.

## Remaining work

The intentionally unimplemented work is broader optimization, not transactional safety:

- global same-net Steiner-tree optimization beyond preservation of proven literal acyclic
  topology;
- broader global/sheet-level optimization when measured benchmarks show the bounded local
  search is the limiting factor;
- arbitrary document/application-note extraction beyond the strict source-bound rule-pack
  workflow;
- automatic symbol rotation/pin-facing enabling for symbol/editor families that have not
  passed focused M2 evidence;
- broader real-project tuning without hiding objective terms.
