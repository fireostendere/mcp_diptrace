# PCB Design Engine

## Scope

The PCB design engine turns normalized board connectivity plus explicit engineering facts into deterministic, explainable placement/routing policy. It is intentionally layered above the existing XML adapters, local placement legalizer, router, review engine and guarded semantic transaction path.

The goal is not to claim globally optimal PCB layout or replace a mature field solver/autorouter. The goal is to make defensible engineering decisions, expose the assumptions behind them, and improve a board through a bounded generate -> score -> improve loop.

PCB-generation capabilities remain internal while the architecture is proven. The current 159-tool public MCP `tools/list` contract stays frozen; generations do not add one MCP tool per heuristic.

## Architecture

```text
schematic / PCB connectivity
        +
operator / project constraints
        |
        v
PCB design intent                         Generation A
        |
        +--> component roles / functional blocks
        +--> net roles / electrical criticality
        +--> power / ground strategy intent
        |
        v
intent-aware placement                    Generation A
        |
        v
physical context / stackup / PDN / return Generation B
        |
        v
routing policy / SI / copper decisions    Generation C
        |
        v
joint score and bounded repair             Generation D
        |
        v
guarded semantic plan -> preview -> SHA-bound apply -> review
```

Physical facts are never invented to make the model look complete. Unknown edge rate, current, impedance, stackup or datasheet facts remain unknown until they are supplied or supported by authoritative project data.

## Generation A — PCB understands electronics

**Status: implemented, regression-tested and merged to `main` in PR #81.**

Generation A establishes the engineering-intent layer that must exist before a global placer can make useful decisions.

### Design intent

`pcb_design_intent.py` builds a typed engineering view of the board:

- component roles: controller, power converter, connector, interface, sensor, timing, protection, support and mechanical anchor;
- deterministic functional blocks with principal anchors and support members;
- explicit confidence/reasons for inferred roles;
- operator overrides for facts that cannot be recovered safely from XML/naming;
- noise-emission/noise-sensitivity placement intent;
- thermal role metadata used as intent only, not as a temperature prediction;
- deterministic placement priority.

Automatic classification is conservative. It uses exported connectivity, RefDes/name/value metadata and the normalized differential-pair model. An override that does not resolve uniquely becomes a warning instead of being guessed.

### Net intelligence and criticality

Nets may carry multiple roles because real electrical behavior is not a single enum. Generation A recognizes, where evidence exists:

- ground and chassis/shield domains;
- ordinary power and explicit high-current power;
- switching nodes;
- clock/timing nets;
- exported or strongly named differential nets;
- reset/control/digital nets;
- analog, precision-reference, feedback and current-sense nets;
- RF/antenna-like nets.

Each net receives a decomposed electrical intent record containing:

- component membership;
- criticality;
- noise emission and sensitivity;
- via penalty;
- whether a continuous reference is expected;
- optional edge rate, frequency, current, target impedance/tolerance, max length/skew, via limit, layer preferences, reference net, spacing and stub/shielding constraints.

Only supplied/exported values populate physical constraints. Criticality may become more conservative when explicit edge rate/current/length/impedance data is available, but the engine does not manufacture missing electrical values.

### Power and ground strategy

Generation A models topology intent without pretending to perform full PI/return-current simulation.

The deterministic defaults are deliberately conservative:

- ordinary ground -> `continuous_plane_preferred`;
- chassis/shield -> separate `chassis_or_shield` domain;
- switch node -> `local_copper_minimized`;
- current/sense naming -> `kelvin_candidate`;
- power rail -> `local_plane_or_pour_candidate`;
- star grounding -> **never inferred automatically**; it requires explicit project/operator intent.

This prevents the common but unsafe rule "analog + digital means split the ground plane" from entering the engine as a default.

### Placement v2

`pcb_placement.py` sits above the existing `placement.py` local legalizer/scorer. The original engine remains the source of hard placement legality for outline, keepout and overlap behavior.

Generation A placement:

1. fixes locked/mechanically anchored components;
2. identifies functional anchors before support members;
3. derives desired regions from support relationships and critical connectivity;
4. generates deterministic bounded board-level candidates around those targets;
5. refuses candidates that increase hard geometry penalties;
6. scores candidates using a decomposed objective;
7. emits ordinary `MoveComponentsOperation` objects rather than writing XML directly.

The v2 score exposes separate terms for existing geometry/ratsnest legality, functional-block cohesion, support-to-anchor adjacency, critical-net connection distance and intent-level aggressor/victim proximity.

The Generation A noise term remains only a placement proxy. Generation B adds timing-gated physical-context triage without claiming EMC sign-off.

## Generation B — PCB understands fields and current paths

**Status: implemented internally on `pcb_physical.py`; CI/PR acceptance is the gate before merge.**

Generation B consumes the Generation A intent plus existing normalized stackup, geometry, via and return-path evidence. It is non-mutating and emits analysis only.

### Stackup and reference structure

`analyze_pcb_physics()` reuses the existing stackup/impedance analysis and exposes typed microstrip/stripline reference candidates with:

- signal layer and adjacent reference layer(s);
- exported dielectric/copper geometry when available;
- reference-plane confidence from the normalized stackup;
- explicit `exported_stackup` evidence provenance;
- `preliminary_only=True` for analytic candidates.

Analytic geometry is deliberately not promoted to manufacturer-verified or external field-solver evidence.

### Power integrity / PDN

For each identified power rail Generation B records:

- power-converter source candidates only when topology/intent supports them;
- remaining connected load candidates;
- capacitor members as conservative decoupling candidates;
- explicit rail current when supplied;
- inherited trace/local-copper/pour strategy intent;
- whether meaningful power-via capacity validation is required.

Current density and voltage drop remain `unknown` until both current and sufficient copper geometry/material/current-path evidence exist. Numeric via current capacity is not guessed.

Switching-node nets connected to a power converter produce regulator hot-loop **candidates**. They do not become proven current loops until pad-level source/load/return direction is available.

### Return-path strategy

Generation B integrates the existing `analyze_return_path()` engine for nets that require a continuous reference or have precision/sense semantics. The existing analyzer remains authoritative for its bounded observations:

- adjacent-reference resolution from physical stack order;
- missing reference copper;
- possible split crossings;
- layer transitions without normalized return-via evidence;
- disclosed skipped checks where the export is insufficient.

Ground remains continuous by default; mixed analog/digital naming does not create an automatic split.

### Noise compatibility

Distance-only placement risk is no longer sufficient for physical triage. Generation B creates aggressor/victim pairs only when the aggressor has explicit edge-rate or frequency evidence. The bounded score combines:

- known timing evidence;
- Generation A emission/sensitivity/criticality;
- actual component-centroid separation from normalized geometry.

It does **not** assert trace parallelism, spectral overlap, field coupling or EMC compliance. Those require route observations or stronger solvers/evidence.

### Via intelligence

Normalized vias receive semantic roles only when evidence supports them:

- signal via;
- power via;
- ground-stitching via;
- reference-sensitive return-transition candidate;
- differential transition member;
- thermal via only from explicit normalized thermal metadata.

A via fence is not inferred merely from proximity. The existing via geometry/span validator remains the low-level authority, and semantic roles never imply numeric current capacity.

## Generation C — PCB routes intentionally

**Status: planned.**

### Routing policy compiler

Translate net intent into concrete router policy: priority, width/clearance, preferred layers, via budget/penalty, target impedance, pair/skew rules, reference requirement and spacing/shielding constraints.

### Route ordering

Route topology-critical nets first rather than XML order. Typical ordering is switching/RF/timing/high-speed/precision analog before ordinary controls and indicators, but the actual order derives from criticality/constraints rather than a fixed protocol list.

### SI-aware routing and crosstalk

Add post-candidate checks for impedance continuity, differential symmetry/skew, stubs, parallel-coupling exposure, plane/reference discontinuity and layer-transition return path.

### Copper / plane / pour planner

Choose trace versus local copper versus plane/pour from known current/return/thermal constraints. Add refill/island/cutout/thermal-relief validation only after authoritative DipTrace geometry/evidence exists.

### Placement feedback

Routing may return bounded placement repairs instead of accepting pathological routes, for example a small move/rotation that removes several vias or restores a valid reference path. The router proposes; the joint optimizer decides.

## Generation D — whole-board optimization

**Status: planned.**

Combine placement, routing, SI, PI, return-path, EMI-risk, thermal, DFM/DFA/DFT and manufacturing constraints into one bounded multi-objective loop.

Hard violations are lexicographically dominant and cannot be traded away for a prettier score. A candidate with new DRC/mechanical/safety violations loses regardless of wire length or visual compactness.

The complete score remains decomposed. There is no opaque "AI board quality" value without component metrics.

Generation D also adds benchmark families for MCU/decoupling, regulators, ADC/mixed signal, USB/high-speed differential, Ethernet/CAN, RF/antenna and higher-current power designs, followed by controlled DipTrace open/save/re-export acceptance.

## Testing and acceptance

Generation A automated coverage includes component/net role inference, functional grouping, explicit electrical overrides, unknown-value preservation, ground topology safety, differential-pair evidence, decomposed placement scoring, intent-aware placement and hard-geometry/budget refusal.

Generation B automated coverage adds:

- exported stackup/reference candidates without solver-trust promotion;
- unknown-current/source preservation in PDN analysis;
- explicit operator current/converter facts;
- reference-sensitive return-path targeting;
- timing-gated noise analysis;
- bounded via semantic-role classification;
- rejection of invalid return-via search radius.

Each later generation must add small engineering trap fixtures rather than relying on one large demo board. A real-DipTrace acceptance fixture is required before claims about poured copper, plane behavior, via structures or native round-trip semantics are promoted beyond the existing evidence boundary.

## Non-claims

The PCB design engine does **not** currently claim:

- field-solver accuracy;
- PDN/PI sign-off;
- EMC compliance;
- automatic proof that a plane, star point or Kelvin connection is electrically optimal;
- authoritative copper refill geometry;
- thermodynamic/CFD analysis;
- fabrication or assembly sign-off;
- globally optimal placement/routing.

Generations A and B provide the deterministic intent, placement and physical-context foundation on which routing policy and whole-board optimization can be built.