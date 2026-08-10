# Schematic Layout Engine

## Status

This document describes the deterministic foundation for the intelligent schematic
layout track in `docs/ROADMAP.md`.

The implementation is internal and does not add public MCP tools or change the published
tools/list contract. It builds on the existing schematic parser, semantic operations,
transaction safety model, and authored-wire quality layer.

The current implementation lives in:

- `src/diptrace_mcp/schematic_layout.py` for design intent, reference motifs,
  deterministic readability metrics, and the first hierarchical placement planner;
- `src/diptrace_mcp/schematic_optimizer.py` for bounded multi-candidate placement search,
  estimated future-interconnect cost, candidate ranking, and safe operation planning;
- `src/diptrace_mcp/schematic_wire_planner.py` for non-mutating route-candidate metrics and
  explicit placement feedback on pathological schematic interconnect;
- `src/diptrace_mcp/schematic_pin_geometry.py` for conservative embedded Design Cache pin
  resolution and pin-facing geometric evidence;
- `src/diptrace_mcp/schematic_joint_optimizer.py` for non-mutating pin-aware routing of
  hypothetical placement candidates and joint route/placement ranking.

## Design intent

The intent layer is deliberately conservative. It uses only facts already available in the
normalized schematic:

- RefDes and component naming conventions;
- part value/name metadata;
- net names;
- pin/net connectivity;
- multipart component identity.

It does not pretend to know a component's datasheet from its name alone.

Parts receive a coarse role such as active device, power-control device, connector,
support component, timing component, protection device, control device, or other. Nets
receive coarse roles such as ground, power, clock, reset, interface, signal, or unknown.

Functional blocks are then seeded by active devices and connectors. Multipart components
with the same RefDes are treated as one anchor group. Support components are assigned to an
anchor only when connectivity gives a unique deterministic result. Ground and power nets
are intentionally weak grouping evidence because they commonly span the whole design.
Ambiguous components remain in generic blocks rather than being guessed into the wrong
functional block.

## Reference motifs

Reference schematics from datasheets should be represented as relative engineering and
presentation constraints rather than absolute page coordinates.

The current motif model supports relations such as:

- near;
- left/right of another element;
- above/below another element;
- same row;
- same column.

A motif has explicit provenance (`datasheet`, `reference_design`, `project`, or `builtin`)
and confidence. A `BoundReferenceMotif` maps semantic motif keys to actual schematic part
IDs. This keeps the layout engine independent of online retrieval and prevents component
names from silently minting fake datasheet knowledge.

Automatic datasheet ingestion is intentionally deferred. The deterministic layout engine
must remain useful with project/operator-supplied motifs and without network access.

## Readability score

`analyze_schematic_layout` produces separate machine-readable metrics rather than one
opaque quality number. Current terms include:

- part overlap count;
- cross-net wire crossing count;
- wire overlap count;
- diagonal segment count;
- bend count;
- total wire length;
- functional-block span;
- occupied sheet area;
- approximate content density;
- reference-motif violations.

The total score is a weighted sum of disclosed terms. Lower is better only under the
reported weights and terms. It is not an engineering certification or an ML-generated
quality judgement.

The first score intentionally does not claim exact symbol/pin graphics. Current schematic
part bounds are conservative proxies. Pin geometry can now be resolved from a compatible
embedded Design Cache, but unresolved or ambiguous parts remain explicit.

## First placement planner

`plan_schematic_placement` is the simple deterministic Phase 28 foundation.

The planner:

1. infers functional blocks;
2. orders block classes deterministically;
3. places anchor parts first;
4. packs support parts near their anchor block;
5. snaps placement to a configurable grid;
6. packs blocks left-to-right with bounded row wrapping;
7. preserves locked parts;
8. emits ordinary `MoveComponentsOperation` objects.

The generated operations therefore still use the existing semantic compiler,
preview/SHA/transaction/review safety path. The layout engine does not write XML directly.

## Bounded multi-candidate optimizer

`schematic_optimizer.py` extends the first planner into a bounded search layer instead of
pretending that one greedy packing is globally optimal.

For an unwired schematic it generates multiple deterministic candidates across bounded
combinations of:

- functional-block ordering strategy;
- local support-component presentation (`support_right`, `support_below`, or balanced);
- target row width / sheet compactness.

Candidate generation is capped by `max_candidates` and deduplicates geometrically identical
layouts. Each candidate is scored with disclosed terms rather than a hidden quality value.
The current optimizer score includes:

- the existing layout/readability score;
- estimated future interconnect length;
- estimated future crossing count;
- connector-flow violations where a connector is placed visually downstream of the block
  it feeds;
- movement from the existing layout.

Future interconnect in this first-stage score remains an estimate. For each net the optimizer
builds a deterministic minimum-spanning connection estimate between placed parts and compares
the two Manhattan L-shape orientations while accumulating estimated crossings. Ground is
excluded from this estimate and power may be down-weighted/configured separately. The joint
route scorer described below can now re-rank those candidates with bounded real wire
candidates before any placement is applied.

The selected candidate is the minimum ranked candidate under the disclosed score and stable
tie-breakers. `plan_optimized_schematic_placement` then emits ordinary
`MoveComponentsOperation` objects for changed, unlocked parts. It does not bypass semantic
operations or the transaction boundary.

The optimizer is deterministic for a fixed snapshot and configuration. Regression tests
cover deterministic candidate IDs/order, bounded candidate count, grid adherence, locked
part preservation, replay of selected operations, and refusal of an already-wired
schematic until joint rerouting is available.

## Existing wire-quality layer

The repository already has a bounded deterministic authored-wire quality layer in
`services/schematic_wire_quality.py`. It can reroute newly authored wires around component
and text obstacles and strongly penalizes crossings and overlaps.

The layout modules do not duplicate that router. The router remains the candidate generator;
the planner and joint optimizer layers measure and judge the resulting routes.

## Non-mutating wire planner and placement feedback

`schematic_wire_planner.py` is the first Phase 29 coupling layer. It does not apply a wire
and does not move a symbol. Instead it:

1. measures the caller-supplied `AddWireOperation`;
2. asks the existing bounded wire cleaner for its deterministic cleaned candidate;
3. measures that candidate with the same obstacle/crossing model;
4. selects the lexicographically non-worse route;
5. checks explicit readability thresholds;
6. returns `placement_feedback` when the selected route remains pathological.

The exposed wire metrics include:

- component/text obstacle hits;
- collinear overlaps with existing wires;
- crossings with existing wires;
- self-intersections;
- diagonal segments;
- bend count;
- routed length;
- direct endpoint distance;
- detour ratio.

Feedback is intentionally advisory. Current repair intents include opening a routing
corridor, moving endpoint blocks closer, or repacking endpoint blocks. Pin endpoints are
resolved back to normalized stable part IDs, including multipart RefDes groups where
applicable, so the later joint optimizer has an explicit target set.

This is the key boundary needed for co-optimization: a router is now allowed to say
"this route is still bad; placement must change" instead of silently accepting a long or
collision-prone wire.

## Component Library pin geometry resolver

Schematic instance XML identifies each part and its Pin indices, while symbol pin geometry
lives in the project's embedded Design Cache Component Library. Component Library XML carries
relative pin X/Y, orientation, electrical type, pin type, multipart ownership and ordered pin
identity. The resolver joins those two typed models without adding a second XML parser.

`resolve_document_schematic_pin_geometry` prefers the schematic's own embedded Design Cache.
A standalone Component Library can be supplied as a fallback only through explicit opt-in;
it is not silently mixed into a project because it may represent a different library
revision.

The lower-level `resolve_schematic_pin_geometry` accepts a normalized schematic snapshot and
a typed `LibraryModel`. A library component may be selected through:

- an explicit caller binding from schematic `ComponentStyle` to library component stable ID;
- a `CompTypeN` index hint, but only when the indexed component also passes structural
  identity checks;
- an exact unique component-name match that passes the same structural checks.

Structural validation includes multipart index, pin count, component name where applicable,
and RefDes prefix when both models provide one. Ambiguous or inconsistent matches remain
unresolved. A `CompTypeN` token is therefore an index hint, not proof of identity.

Within an accepted component part, normalized schematic Pin order is mapped to the existing
ordered `LibraryPin` list. Each resolved result carries:

- local pin position;
- local pin orientation;
- electrical and pin type;
- matched library component/pin IDs;
- match basis and confidence;
- absolute position/orientation when the transform is trustworthy enough to apply.

For unrotated parts, absolute position is the schematic part origin plus the library-relative
pin position. Non-zero schematic part rotation is fail-closed by default: the project still
keeps the live-host angle convention as an evidence boundary, so the resolver reports local
geometry but withholds authoritative absolute geometry. An explicit opt-in mode exists for
experiments and tests, but using it does not promote the angle convention to accepted host
evidence.

This resolver is read-only. It does not rotate symbols, move parts, write XML, search online
libraries, or claim that a matched library revision is identical to the original project
library revision.

## Pin-aware joint placement/routing score

`schematic_joint_optimizer.py` couples bounded placement candidates to the existing wire
planner without applying either placement or routing.

For each hypothetical placement candidate it:

1. deep-copies the normalized schematic snapshot;
2. translates part positions and their conservative bounding boxes to the candidate layout;
3. translates resolved pin offsets with each moved part;
4. marks unresolved pin geometry explicitly and uses the candidate part anchor only as a
   fallback;
5. groups connectivity per net and sheet;
6. applies the shared design-intent net-role policy before creating wire candidates: ground
   nets are excluded by default, power nets are included by default, and both choices are
   explicit configuration;
7. decomposes each included sheet-local net into a deterministic endpoint minimum-spanning
   tree;
8. invokes `plan_schematic_wire_candidate` for each bounded edge;
9. exposes completed prior nets only inside the cloned snapshot so later nets see crossing
   pressure;
10. aggregates real route defects and route length;
11. re-ranks placement candidates with hard route defects ahead of the first-stage placement
    heuristic.

The aggregate metrics disclose rejected routes, obstacle hits, overlaps, crossings,
self-intersections, diagonals, bends, length, detour excess, exact pin endpoints, fallback
anchor endpoints, and the count of sheet-local net groups intentionally skipped by routing
policy. The edge budget is bounded and incomplete evaluation is reported instead of silently
pretending that all included connectivity was scored.

Ground is excluded from wire-MST scoring because global ground connectivity is commonly
represented with power symbols or labels rather than page-spanning authored wires. Setting
`include_ground_nets=True` opts back into explicit ground-wire scoring. Power remains included
by default but can likewise be excluded with `include_power_nets=False`. These switches alter
only scoring policy; they do not author power symbols or labels and they do not change the
logical connectivity model.

The joint rank is intentionally lexicographic. Rejected/colliding/overlapping/crossing routes
are worse before the original placement score is considered; bends and route length are
later tie-breakers. This lets a placement with a slightly worse first-stage Manhattan
estimate win when the actual bounded router shows materially cleaner interconnect.

The virtual routes receive ordinary canonical stable IDs and exist only in the cloned
snapshot. Source XML, source normalized objects and candidate placement data are not mutated.
Same-net MST edges are still locally planned rather than globally junction-optimized, and
text obstacles are not yet moved with placement candidates; both limitations are reported.

Both placement planners still refuse an already-wired schematic by default. Moving symbols
while leaving existing wire geometry behind would make the drawing worse. Existing-wire
support belongs in the later selective-reroute transaction layer, where affected wires can
be replaced atomically with the placement change.

## Next implementation steps

The intended order is:

1. promote per-candidate scoring into bounded sheet-level net ordering and congestion-aware
   route scheduling;
2. turn advisory placement feedback into bounded candidate moves and re-score them through
   the joint route scorer;
3. re-route only affected nets after a placement repair and compose the selected placement +
   wire edits into one guarded transaction plan;
4. add reference-motif-driven placement candidate generation;
5. validate schematic rotation semantics in the real host before enabling automatic
   pin-facing rotation decisions by default;
6. run placement, routing and scoring in a bounded generate -> score -> improve loop;
7. preserve the existing guarded transaction/review path for the selected candidate;
8. expose only a small deliberate public MCP surface after the internal architecture is
   proven.

The quality target is practical: a deliberately ugly but electrically correct schematic
should become materially easier for an engineer to read without routine manual cleanup.