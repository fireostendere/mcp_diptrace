# PCB Design Engine

## Scope

The PCB design engine turns normalized board connectivity plus explicit engineering facts into deterministic, explainable placement/routing policy. It is intentionally layered above the existing XML adapters, local placement legalizer, router, review engine and guarded semantic transaction path.

The goal is not to claim globally optimal PCB layout or replace a mature field solver/autorouter. The goal is to make defensible engineering decisions, expose the assumptions behind them, and improve a board through a bounded generate -> score -> improve loop.

No Generation A capability expands the public MCP `tools/list` contract. The current 159-tool surface stays frozen while the internal EDA architecture is proven.

## Architecture

```text
schematic / PCB connectivity
        +
operator / project constraints
        |
        v
PCB design intent
        |
        +--> component roles / functional blocks
        +--> net roles / electrical criticality
        +--> power / ground strategy intent
        |
        v
intent-aware placement
        |
        v
routing policy / stackup / SI / PI / EMI   (later generations)
        |
        v
joint score and bounded repair
        |
        v
guarded semantic plan -> preview -> SHA-bound apply -> review
```

Physical facts are never invented to make the model look complete. Unknown edge rate, current, impedance, stackup or datasheet facts remain unknown until they are supplied or supported by authoritative project data.

## Generation A — PCB understands electronics

**Status: implemented internally; automated regression/CI required before the generation is accepted.**

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

This prevents the common but unsafe rule "analog + digital means split the ground plane" from entering the engine as a default. Generation B will add physical return-path/PDN reasoning before topology intent becomes copper implementation.

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

The v2 score exposes separate terms for:

- existing geometry/ratsnest legality score;
- functional-block cohesion;
- support-to-anchor adjacency;
- critical-net connection distance;
- intent-level aggressor/victim proximity.

The noise term is only a deterministic placement proxy. Frequency overlap, coupling geometry, field behavior and actual EMC risk belong to Generation B/C and are not claimed here.

## Generation B — PCB understands fields and current paths

**Status: planned.**

Generation B deepens the intent model with physical/electrical analysis.

### Stackup and reference structure

- choose/validate signal and reference layer relationships;
- expose whether a route can maintain a continuous reference;
- combine manufacturer/project stackup facts with the existing impedance estimator;
- keep analytic estimate, manufacturer geometry and external field-solver evidence at distinct trust levels.

### Power integrity / PDN

For each rail model:

- source and loads;
- expected steady/transient current when known;
- bulk and local decoupling intent;
- trace/pour/plane distribution choices;
- voltage-drop/current-density bottlenecks;
- power/ground via requirements;
- regulator hot-loop topology.

Decoupling becomes a pad/current-loop problem rather than only a component-distance proxy.

### Return-path strategy

Extend the current heuristic return-path analyzer into explicit route/reference reasoning:

- continuous reference below signal segments;
- plane gaps/splits and return detours;
- layer transitions and nearby return vias;
- Kelvin/sense return separation;
- current-domain boundaries without automatically splitting ground.

### Noise compatibility

Replace distance-only placement risk with bounded aggressor/victim analysis using known edge/frequency, geometry and reference structure. Unknown physics remains disclosed rather than guessed.

### Via intelligence

Distinguish engineering roles:

- signal via;
- power via;
- ground-stitching via;
- return-transition via;
- differential transition pair;
- thermal via;
- via fence where justified.

The existing via geometry/span validator remains the low-level authority.

## Generation C — PCB routes intentionally

**Status: planned.**

### Routing policy compiler

Translate net intent into concrete router policy: priority, width/clearance, preferred layers, via budget/penalty, target impedance, pair/skew rules, reference requirement and spacing/shielding constraints.

### Route ordering

Route topology-critical nets first rather than XML order. Typical ordering is switching/RF/timing/high-speed/precision analog before ordinary controls and indicators, but the actual order derives from criticality/constraints rather than a fixed protocol list.

### SI-aware routing and crosstalk

Add post-candidate checks for:

- impedance continuity;
- differential symmetry/skew;
- stubs;
- parallel-coupling exposure;
- plane/reference discontinuity;
- layer-transition return path.

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

Generation A automated coverage includes:

- component/net role inference;
- support-to-functional-anchor grouping;
- explicit electrical overrides and unknown-value preservation;
- continuous-ground default and non-automatic star grounding;
- switch/sense/shield topology distinctions;
- exported differential-pair evidence;
- decomposed placement scoring;
- intent-aware support placement;
- hard-geometry non-regression;
- deterministic component-budget refusal.

Future generations must add small engineering trap fixtures rather than relying on one large demo board. A real-DipTrace acceptance fixture is required before claims about poured copper, plane behavior, via structures or native round-trip semantics are promoted beyond the existing evidence boundary.

## Non-claims

Generation A does **not** claim:

- field-solver accuracy;
- PDN/PI sign-off;
- EMC compliance;
- automatic proof that a plane, star point or Kelvin connection is electrically optimal;
- authoritative copper refill geometry;
- thermodynamic/CFD analysis;
- fabrication or assembly sign-off;
- globally optimal placement.

It provides the deterministic engineering-intent and placement foundation on which those deeper analyses can be built.