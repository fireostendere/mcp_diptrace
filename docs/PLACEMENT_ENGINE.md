# Placement Engine

## Current architecture

Placement is intentionally split into low-level legality/geometry handling and higher-level engineering/readability intelligence.

```text
normalized document + explicit constraints
        |
        +--> low-level placement/legalization
        |       outline / keepouts / overlap / locked parts / grid
        |
        +--> higher-level intent/readability scoring
                schematic placement optimizer
                PCB Generation A placement v2
                later B-D analysis/joint selection
        |
        v
bounded placement candidate(s)
        |
        v
ordinary semantic move operations / guarded plan
```

The higher-level engines do not bypass the existing semantic-operation, preview, expected-SHA, policy, transaction or review path.

## Low-level placement authority

The existing placement/geometry layer remains responsible for bounded geometric reasoning such as:

- board/sheet bounds where represented;
- keepouts and obstacles;
- locked/fixed objects;
- overlap/collision legality;
- grid snapping and deterministic ordering;
- conservative candidate generation/legalization.

It is deliberately not a full industrial global placer and does not infer missing electrical facts.

## Schematic placement

The schematic layout stack is documented in [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

Current implementation includes:

- functional-block/anchor/support placement;
- configurable grid and bounded row packing;
- locked-part preservation;
- bounded deterministic multi-candidate search;
- readability, movement and estimated-interconnect scoring;
- pin-aware joint routing score of hypothetical candidates;
- route-feedback-driven bounded placement repair;
- selective atomic replacement of affected existing wire geometry when placement moves touch explicit sheet-local nets.

Important boundary: the older placement-only planners may still refuse already-wired schematics because moving symbols while leaving existing wire geometry unchanged would degrade connectivity presentation. The dedicated atomic reroute planner closes that gap for supported cases by composing affected-wire deletion, component movement and replacement-wire authoring into one dependency-safe semantic batch. It fails closed when affected endpoints or replacement routes cannot be rebuilt safely and does not rewrite unaffected explicit wire geometry.

Automatic pin-facing rotation also remains conservative until the relevant real-host angle/rotation semantics are sufficiently verified.

## PCB Generation A placement v2

`pcb_placement.py` is the higher PCB placement layer added by Generation A. It uses engineering intent from `pcb_design_intent.py` while retaining the existing low-level legality engine.

Generation A placement can:

1. keep locked/mechanically anchored components fixed;
2. handle principal functional anchors before support components;
3. pull support components toward resolved anchors;
4. derive desired regions from critical connectivity;
5. generate bounded deterministic board candidates;
6. reject candidates that worsen hard overlap/outline/keepout penalties;
7. score functional-block cohesion, support adjacency, critical connection distance and intent-level noise proximity separately;
8. emit ordinary semantic move operations rather than editing XML directly.

Generation A preserves unknown physical values and uses bounded proximity/intent proxies where exact physics are unavailable.

Repository PCB generators additionally prefer compact outlines derived from
occupied component geometry, center the finished layout and preserve visual
symmetry when doing so does not worsen electrical/mechanical legality. Standard
2.54 mm connectors use the smallest equally compatible pattern by default.
These are deterministic soft preferences; locked locations, courtyards, edge
clearance, routing and explicit constraints remain dominant.

## PCB Generations B-D interaction

The old statement that stackup, PDN, routing policy and whole-board optimisation are merely future placement work is no longer correct. They exist as sibling/later internal layers:

- **Generation B (`pcb_physical.py`)** adds stackup/reference, PDN/current-path, return-path, timing-gated noise and via context;
- **Generation C (`pcb_routing_policy.py`)** adds engineering-aware route policy, observed-route checks and bounded placement feedback;
- **Generation D (`pcb_joint_optimizer.py`)** compares bounded whole-board candidates with hard safety/mechanical/connectivity/DRC/reference/manufacturing dimensions dominant over soft placement/routing/SI/PI/thermal/etc. scores.

Those layers do not turn placement into a field solver. They refine or select candidates while preserving explicit evidence/unknown boundaries.

## Placement scoring rules

Scores should remain decomposed and explainable. Typical categories include:

- hard geometry/legal violations;
- movement from current placement;
- functional-group cohesion;
- support-to-anchor adjacency;
- critical connection distance;
- readability/flow terms for schematic;
- routeability/route quality evidence;
- aggressor/victim proximity when supported by intent/evidence;
- reference-path/manufacturing dimensions at later PCB generations.

Hard safety/legal violations cannot be compensated by a better cosmetic soft score.

## Determinism and bounds

Placement search must have explicit deterministic tie-breakers and resource bounds:

- maximum candidate count;
- grid/translation bounds;
- stable object ordering;
- stable candidate IDs/order;
- finite-score validation;
- no hidden random global optimization.

A bounded candidate search may fail to find the global optimum. The project reports that limitation instead of claiming global placement optimality.

## Evidence boundaries

Repository tests can establish deterministic candidate behaviour on fixtures. Real-DipTrace evidence is still required for claims involving native semantics, rotation conventions, refill/copper effects or product-level usefulness.

The Generation D benchmark catalog is synthetic-regression-only until the documented real-DipTrace acceptance path is completed.

## Current limitations

- no globally optimal placer claim;
- atomic affected-net reroute is implemented, but arbitrary hand-authored junction topology is not preserved as a visual constraint when an affected explicit net is rebuilt;
- schematic automatic rotation/pin-facing is evidence-limited;
- Generation A proximity/noise/thermal/current-return terms are not field/thermal/PI simulation;
- Generations B-D are bounded evidence-aware layers, not manufacturing/EMC sign-off;
- authoritative poured-copper/refill behavior is outside the low-level placer and remains a native-host evidence boundary.
