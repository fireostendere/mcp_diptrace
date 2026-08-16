# Domain Model

## Purpose

The domain model separates raw DipTrace XML, normalized observable facts, inferred engineering intent, operator-provided constraints and candidate/analysis results. The project deliberately avoids turning an inferred label or missing physical value into an authoritative fact.

## Core layers

```text
raw DipTrace XML
    |
    v
secure parser / format-specific models
    |
    v
normalized PCB / schematic / library models
    |
    +--> observed geometry/connectivity/metadata
    +--> stable IDs and provenance
    |
    v
engineering-intent / analysis layers
    |
    +--> schematic intent + motifs
    +--> PCB Generations A-D
    |
    v
candidate plans / metrics / findings / feedback
    |
    v
typed semantic operations
    |
    v
guarded transaction path
```

## Facts versus inference

Keep three categories explicit:

1. **Observed fact** — directly supported by parsed document/export/evidence;
2. **Inferred intent** — deterministic heuristic/classification with reasons/confidence;
3. **Operator/reference fact** — explicit project/operator input with provenance.

A component name may suggest a role. It does not prove a datasheet, current, edge rate, impedance, thermal limit or manufacturing capability. Those values remain unknown unless supplied by appropriate evidence.

## Stable identities

Normalized objects use stable/canonical IDs where possible so plans, findings, transactions and evidence can refer to the same object without depending on transient list position.

Stable identity is especially important for:

- components/parts;
- nets;
- traces/vias/wires;
- library components/patterns/pins;
- findings and candidate plans;
- live-session/transaction records.

## Schematic domain layer

The normalized schematic model provides parts, sheets, pins/connectivity, wires, labels/text and embedded Design Cache data used by the higher layout engine.

The schematic intelligence layer adds:

- coarse part roles;
- coarse net roles;
- deterministic functional blocks;
- principal/support relationships when uniquely supported;
- reference motifs with provenance/confidence;
- readability metrics;
- placement candidates;
- route metrics/placement feedback;
- resolved/unresolved pin-geometry evidence;
- joint route/placement scores;
- bounded repair candidates.

Reference motifs encode relative intent such as near/left/right/above/below/same-row/same-column. They do not copy absolute datasheet page coordinates or silently claim that a component name proves a particular reference circuit.

Unresolved or ambiguous Design Cache/library pin matches remain explicit rather than being guessed.

## PCB Generation A domain layer

`pcb_design_intent.py` adds higher engineering semantics above raw PCB connectivity:

- component roles;
- deterministic functional blocks;
- multi-role net classifications;
- criticality and noise emission/sensitivity intent;
- optional physical/electrical constraints;
- conservative power/ground topology intent;
- provenance/reasons/confidence and explicit overrides.

This layer is the semantic foundation, not the complete PCB engine.

## PCB Generation B domain layer

`pcb_physical.py` augments intent with bounded physical context derived from available evidence:

- exported stackup/reference candidates;
- PDN source/load/decoupling relationships;
- regulator hot-loop candidates;
- return-path observations;
- timing-gated aggressor/victim risk context;
- semantic via roles.

Missing current/current density/voltage drop/via capacity or authoritative refill geometry remain unknown. Generation B does not convert local heuristics into field-solver or PI/EMC proof.

## PCB Generation C domain layer

`pcb_routing_policy.py` represents route policy and observed-route engineering constraints:

- deterministic priority/order;
- spacing preferences/requirements;
- preferred/forbidden layers;
- via budgets/penalties;
- impedance/tolerance;
- maximum length/skew;
- reference requirements;
- stub sensitivity;
- shielding preference;
- copper/topology intent;
- bounded placement feedback.

When width/timing/impedance/reference data are absent, the model preserves that absence rather than synthesizing constants.

## PCB Generation D domain layer

`pcb_joint_optimizer.py` represents bounded whole-board candidates and decomposed score dimensions.

Hard dimensions include safety, mechanical, connectivity, DRC, reference-path and manufacturing constraints. They are lexicographically dominant over soft placement/routing/via/SI/PI/return-path/EMI-risk/thermal-risk/manufacturing metrics.

A candidate may carry plan/evidence references. Selection does not directly mutate the document.

## Placement model

Two placement levels coexist intentionally:

- low-level placement/legalization models handle geometry, outline, keepouts, overlap and ordinary candidate legality;
- higher-level schematic/PCB intelligence models add functional/electrical/readability scoring and bounded feedback.

The higher layer does not replace the low-level legality authority. See [PLACEMENT_ENGINE.md](PLACEMENT_ENGINE.md).

## Semantic operations

Write intent is represented by typed semantic operations instead of arbitrary XML string patches. Operations are validated/compiled through the guarded execution path and remain subject to preview/expected-SHA/policy/backup/transaction rules.

Internal optimizers should produce operations, operation plans or candidate references rather than writing XML directly.

## Library mutation model

The repository contains an internal raw-preserving Component/Pattern Library mutation core. Its purpose is to preserve unknown/unmodeled XML while making bounded known semantic changes.

Controlled real-editor round-trip evidence exists for the internal core. Public native-library write registration is a separate product/API decision and should not be inferred from the domain implementation.

## Cinematic presentation model

The cinematic subsystem uses presentation-specific models such as timeline events, desktop steps, UI profiles and affine coordinate transforms. These models describe visible replay, not authoritative engineering state.

A `DipTraceUIProfile` is editor/version specific and carries explicit action macros plus a calibrated mapping from design coordinates to normalized client coordinates. It is intentionally separate from normalized engineering models so UI pixels/gestures cannot become hidden engineering facts.

## Evidence and provenance

Analysis/findings/candidates should disclose enough provenance to answer:

- which document/candidate identity was analysed;
- which facts were observed versus inferred;
- which optional/operator constraints were used;
- which approximation/evidence boundary applies;
- whether the result was synthetic, analytic, runtime-observed or real-DipTrace verified.

User-controlled files/sidecars cannot mint package-owned high trust.

## Current limitations

- arbitrary datasheet/reference-design interpretation is not part of the
  deterministic core; validated SHA-bound structured rule-pack ingestion is;
- schematic rotation/pin-facing semantics are not universally trusted without real-host evidence;
- selective atomic affected-wire replacement conservatively reuses one nearby
  intentional junction when bounded, but does not reconstruct arbitrary
  hand-authored multi-junction topology;
- PCB Generations B-D remain bounded analysis/selection layers, not field/PI/EMC/thermal/native manufacturing authorities;
- authoritative poured-copper/refill semantics remain a native-host evidence boundary;
- cinematic replay models cannot be used as proof that a semantic edit succeeded.
