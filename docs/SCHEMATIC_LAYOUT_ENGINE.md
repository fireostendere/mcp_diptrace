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
  estimated future-interconnect cost, candidate ranking, and safe operation planning.

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
part bounds are conservative proxies, and exact pin coordinates are not normalized yet.
This limitation is reported instead of being hidden behind guessed geometry.

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

Future interconnect is deliberately an estimate, not fake detailed routing. For each net the
optimizer builds a deterministic minimum-spanning connection estimate between placed parts
and compares the two Manhattan L-shape orientations while accumulating estimated crossings.
Ground is excluded from this estimate and power may be down-weighted/configured separately.
This makes placement route-aware before the full sheet router is coupled to it.

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

The layout modules do not duplicate that router. The next routing phase should expose and
extend it into a sheet-level candidate planner whose metrics can feed back into placement.

Both placement planners currently refuse an already-wired schematic by default. Moving
symbols while leaving wire geometry behind would make the drawing worse. Existing-wire
support belongs in the joint placement/routing optimizer, where affected wires can be
rerouted atomically.

Rotation is also preserved. Exact schematic pin geometry is required before automatic
orientation can be scored reliably enough to justify rotating user-visible symbols.

## Next implementation steps

The intended order is:

1. expose the current authored-wire cleaner as a non-mutating route-candidate/metrics API;
2. let placement candidates be scored with real bounded route candidates, not only the
   Manhattan estimate;
3. allow routing to return bounded placement-feedback proposals when a small move removes
   pathological crossings or detours;
4. re-route only affected nets after a placement repair;
5. add reference-motif-driven placement candidate generation;
6. normalize or otherwise obtain trustworthy symbol/pin geometry where DipTrace evidence
   permits orientation scoring;
7. run placement, routing and scoring in a bounded generate -> score -> improve loop;
8. preserve the existing guarded transaction/review path for the selected candidate;
9. expose only a small deliberate public MCP surface after the internal architecture is
   proven.

The quality target is practical: a deliberately ugly but electrically correct schematic
should become materially easier for an engineer to read without routine manual cleanup.
