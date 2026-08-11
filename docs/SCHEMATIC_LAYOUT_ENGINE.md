# Schematic Layout Engine

## Status

The intelligent schematic track is implemented as a bounded deterministic internal pipeline. It does not add public MCP tools by itself and it does not bypass the existing semantic-operation, preview, expected-SHA, transaction or real-DipTrace evidence boundaries.

Current modules:

- `schematic_layout.py` — design intent, functional blocks, provenance-bearing motifs and readability metrics;
- `schematic_optimizer.py` — bounded multi-candidate placement search and first-stage interconnect scoring;
- `schematic_pin_geometry.py` — conservative embedded Design Cache pin resolution;
- `schematic_wire_planner.py` — non-mutating wire candidate scoring and placement feedback;
- `schematic_joint_optimizer.py` — pin-aware hypothetical placement/routing scoring;
- `schematic_placement_repair.py` — bounded placement repair driven by route feedback;
- `schematic_ensemble.py` — motif + route + congestion ranking;
- `schematic_atomic_reroute.py` — selective existing-wire replacement for nets touched by moved parts.

See [EDA_INTELLIGENCE.md](EDA_INTELLIGENCE.md) for the cross-domain implementation map.

## Design intent and motifs

Intent inference uses normalized schematic facts: RefDes/names/values, pin/net connectivity, multipart identity and explicit caller/reference data. It does not infer a datasheet from a part name.

Reference motifs express relative constraints such as `near`, left/right, above/below, same-row and same-column. Every motif retains provenance and confidence.

`schematic_ensemble.py` also derives conservative builtin readability motifs from already-inferred roles. These are explicitly labelled `source_kind="builtin"` and their source identifies them as deterministic heuristics. They are never presented as datasheet/reference-design evidence.

## Placement and first-stage scoring

Placement candidate generation remains bounded and deterministic. Candidates vary functional-block order, support packing and sheet compactness while preserving locked parts and grid policy.

The disclosed first-stage score includes layout/readability terms, estimated future interconnect, connector-flow pressure and movement cost. This score is a candidate heuristic, not a claim of globally optimal placement.

## Pin-aware route scoring

`schematic_pin_geometry.py` resolves pin geometry from the embedded Component Library Design Cache when identity is sufficiently strong. Ambiguity remains unresolved rather than guessed.

`schematic_joint_optimizer.py` virtually moves candidate parts, groups connectivity per `(net, sheet)`, applies explicit ground/power routing policy, decomposes included net groups into deterministic MST endpoint edges and evaluates each edge through the existing bounded wire planner.

Hard route defects are lexicographically more important than the first-stage placement score. Source XML and normalized source objects are not mutated during scoring.

## Placement repair

`schematic_placement_repair.py` translates explicit route feedback into bounded hypothetical moves such as endpoint convergence, row/column alignment and routing-corridor opening. Functional blocks move as rigid groups when appropriate; locked/unresolved groups fail closed.

Every unique repair is rescored. A repair is selected only when its joint rank is strictly better than the original candidate.

## Congestion-aware ensemble

`schematic_ensemble.py` adds a bounded placement-grid congestion model:

- occupied cells;
- hotspot cells;
- maximum cell occupancy;
- local neighboring pressure;
- overall content span.

Route rejection/obstacle/overlap/crossing/self-intersection/diagonal defects remain dominant over congestion and compactness. Congestion is a scheduling/readability proxy, not a physical solver.

## Atomic placement + selective reroute

The previous major gap — moving parts in an already-wired schematic without leaving stale wire geometry — now has an internal transaction planner.

`plan_atomic_schematic_placement_reroute`:

1. compares a selected placement candidate with the current schematic and identifies actually moved parts;
2. identifies explicit sheet-local wire groups whose nets touch those moved parts;
3. refuses locked moved parts, invalid sheet data, excessive scope or unresolved affected endpoints;
4. virtually removes only the affected explicit wire geometry;
5. virtually applies the selected placement;
6. resolves moved pin endpoints and replans every affected group through the existing bounded wire planner;
7. refuses the whole plan if any affected route is rejected;
8. returns one dependency-safe semantic batch:

`DeleteWireOperation* -> MoveComponentsOperation* -> AddWireOperation*`.

The planner itself never writes XML. Applying the whole returned list through the existing semantic-operation transaction service gives one preview/SHA/commit boundary, so placement and replacement wires are all-or-nothing from the caller's transaction perspective.

Unwired nets are not automatically turned into explicit page wires by default. Unaffected wire geometry is not rewritten.

Current limitation: affected explicit nets are rebuilt from resolved pin endpoints using deterministic MST edges. Arbitrary hand-authored junction topology is not preserved as a visual constraint. A future topology-preservation layer may improve that without weakening the current fail-closed boundary.

## Existing direct-planner refusal

The older placement-only planners may still refuse an already-wired schematic when used directly. That behavior remains correct: a placement-only operation cannot safely move symbols while leaving wire geometry behind. Existing-wire support belongs to the atomic selective-reroute planner above.

## Testing and evidence

Repository tests cover deterministic candidate generation/ranking, pin resolution, route scoring, repair budgets, selective reroute scope, locked-part refusal, source immutability and semantic replay.

Those tests prove repository behavior, not visual product quality in a particular DipTrace build. The real-host schematic readability campaign in `SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md` remains the appropriate acceptance path for claims about human-readable output.

## Remaining work

- stronger global/sheet-level congestion scheduling beyond the current bounded placement-grid proxy;
- automatic ingestion of externally sourced/datasheet motifs with explicit provenance and redistribution policy;
- optional preservation/reuse of existing intentional junction topology during affected-net reroute;
- real-host validation before automatic symbol-rotation/pin-facing decisions are enabled by default;
- bounded multi-iteration generate -> score -> repair -> reroute convergence with explicit objective history and stopping criteria.
