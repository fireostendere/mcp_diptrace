# Placement Engine

## Implemented

Phase 7 provides a deterministic incremental/local placer. Every write plan requires an
explicit selector, source SHA, preview, and semantic transaction. A single plan is
limited to 50 components, 512 base grid positions per component, and 30 seconds.

Legality checks include:

- containment within the board outline and an optional region;
- same-side component spacing;
- placement keepouts;
- preservation of locked objects.

The score reports separate weighted contributions for overlap, containment, keepout,
ratsnest wire length, movement, rotation, and side changes, together with raw overlap
area, wire length, and movement. Ratsnest distance is currently measured between
component anchors.

## Workflow

1. Call `analyze_placement`.
2. Call `generate_placement_candidates` or use `score_placement` for model-generated alternatives.
3. Call `plan_component_placement` or `legalize_component_placement`.
4. Review unresolved items, the score, and plan preview resources.
5. Call `apply_component_placement_plan(dry_run=true)`.
6. Commit against the source SHA, then run a review; roll back if the result regresses.

Before storing a plan, the MCP server applies its operations in memory and compares the
number of placement DRC errors before and after. A plan that introduces new errors is
rejected with `drc_regression`.

## Limitations

- This is greedy/local legalization, not global placement.
- Bounding-box confidence is limited without footprint body or courtyard geometry.
- There are no terms for functional groups, thermal clustering, decoupling, accessibility,
  or routing channels. Those decisions remain with the model until verified data is available.
- `deterministic_seed` remains part of the contract; the current algorithm does not use randomness.
