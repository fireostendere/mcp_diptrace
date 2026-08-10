# Placement Engine

## Two placement layers

The project now has two deliberately different PCB placement layers.

`placement.py` remains the bounded low-level legalizer used by the existing public MCP workflow. `pcb_placement.py` is the Generation A internal intent-aware placer. The higher layer reuses the lower layer's normalized geometry and scoring instead of duplicating outline, keepout or overlap rules.

No Generation A change expands the frozen public MCP `tools/list` contract.

## Local legalizer — existing public workflow

Phase 7 provides a deterministic incremental/local placer. Every write plan requires an explicit selector, source SHA, preview, and semantic transaction. A single plan is limited to 50 components, 512 base grid positions per component, and 30 seconds.

Legality checks include:

- containment within the board outline and an optional region;
- same-side component spacing;
- placement keepouts;
- preservation of locked objects.

Candidate bounds retain the normalized footprint's offset from its component anchor. Moves translate that bound, and rotation candidates rotate it about the real anchor instead of re-centering the bound on the anchor.

The score reports separate weighted contributions for overlap, containment, keepout, ratsnest wire length, movement, rotation, and side changes, together with raw overlap area, wire length, and movement. Ratsnest distance is currently measured between component anchors.

The existing public workflow remains:

1. call `analyze_placement`;
2. call `generate_placement_candidates` or `score_placement`;
3. call `plan_component_placement` or `legalize_component_placement`;
4. review unresolved items, score and preview resources;
5. call `apply_component_placement_plan(dry_run=true)`;
6. commit against the source SHA, run review and roll back on regression.

Before storing a public plan, the MCP server applies its operations in memory and compares placement DRC errors before and after. A plan that introduces new errors is rejected with `drc_regression`.

## PCB placement v2 — Generation A internal engine

Generation A adds `pcb_placement.py` above the local legalizer. It consumes `PCBDesignIntent` from `pcb_design_intent.py` and treats placement as an electrical-structure problem rather than only a ratsnest problem.

The deterministic order is:

1. keep locked and mechanically anchored components fixed;
2. place/consider principal functional anchors before support members;
3. pull support components toward their resolved anchor;
4. derive other desired positions from critical connected nets;
5. generate a bounded candidate set around the desired region;
6. reject candidates that increase hard overlap/containment/keepout penalties;
7. choose only a candidate that improves the complete decomposed score;
8. emit ordinary `MoveComponentsOperation` objects.

The v2 score contains separate terms for:

- the existing placement geometry/ratsnest score;
- functional-block cohesion;
- support-to-anchor adjacency;
- critical-net connection distance;
- intent-level aggressor/victim proximity.

The planner preserves existing side and rotation in Generation A. That keeps the first electrical-placement implementation narrow and makes the existing semantic move path the only mutation primitive required.

## Engineering intent boundary

Generation A placement uses deterministic proxies only. Component role, functional grouping, criticality and noise sensitivity/emission may affect placement, but the engine does not claim field-solver, thermal or PDN accuracy.

Unknown current, edge rate, impedance and datasheet facts remain unknown unless supplied explicitly. Full decoupling loop geometry, power-loop area, stackup/reference-plane scoring, crosstalk and thermal spreading belong to later PCB generations documented in [`PCB_DESIGN_ENGINE.md`](PCB_DESIGN_ENGINE.md).

## Limitations

- The local Phase 7 engine is still greedy/local legalization, not global placement.
- Generation A v2 is board-level and intent-aware but remains a bounded deterministic candidate optimizer, not a proof of global optimum.
- Bounding-box confidence is limited without authoritative footprint body/courtyard geometry.
- V2 preserves component side and rotation.
- Decoupling and power-loop terms are connectivity/proximity proxies until pad-level current paths are modeled.
- Noise separation uses intent risk and distance only; coupling geometry and frequency overlap are deferred.
- Thermal role is modeled as intent but no heat-flow calculation is performed.
- `deterministic_seed` remains part of the local placer contract; the current local algorithm does not use randomness.
