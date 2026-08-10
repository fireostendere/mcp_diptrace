# Roadmap and Actual Status

This document separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document, policy and configured adapters allow the feature;
3. **DipTrace verified** — controlled real DipTrace or real-client evidence exists for the exact path.

Implementation never implies universal DipTrace compatibility. Runtime `get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-10

The current source/package version is `0.2.1`. Annotated tag `v0.2.1`, the GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI are already published.

The production-code candidate accepted through the latest completed manual gates is:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

That commit includes the post-PR #65/#66 Ponytail pass (PR #68). Later development may move `main`; completed evidence remains bound to the candidate on which it was captured unless a later gate explicitly adopts a new production identity.

The durable recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md), updated on 2026-08-10. Resume from that checkpoint instead of repeating already accepted gates.

A new product-development track also starts at this checkpoint: **intelligent schematic and PCB design quality**. Formal lifecycle acceptance is paused while the project proves that it can make defensible EDA decisions rather than only safe XML edits. The schematic and PCB engines share the same internal generate -> score -> improve architecture. Schematic readability remains its own acceptance track; PCB Generation A now establishes the electrical-intent and placement foundation in parallel without expanding the public MCP surface.

## Completed real-host / real-client acceptance

The following blocking manual gates are complete:

- current PCB open/save/re-export round-trip;
- current schematic open/save/re-export round-trip;
- real Component Library writer `.eli` save/reopen/re-export with semantic preservation and writer idempotence;
- real Pattern Library writer `.lib` save/reopen/re-export with semantic preservation and writer idempotence;
- generated PCB ratlines and authored schematic wires;
- complete MASK / PASTE / COURTYARD / COMMON semantics gate;
- Q1 Component Angle GUI/re-export;
- real Codex Desktop configuration/restart/`get_capabilities`.

The canonical matrix therefore has **8 of 12 blocking manual gates PASS**.

`claude_desktop_real_client_restart` is **WAIVED for the current project campaign**. It was not run and is not PASS. The project accepts the residual client-specific interoperability risk because the real Codex gate already demonstrated stdio MCP startup, actual process restart, tool exposure and stable `get_capabilities` behavior. No direct Claude Desktop validation is claimed.

The canonical repository manual-acceptance validator still treats Claude Desktop as required and does not encode this project-level waiver. It may continue to report the canonical matrix as incomplete; do not weaken the validator or fabricate a PASS merely to remove that warning.

### Mask / paste / courtyard / Common

`diptrace_mask_paste_courtyard_common_semantics = PASS` on the accepted production candidate.

- MASK — PASS;
- PASTE — PASS;
- COURTYARD — PASS after the historical parser defect was repaired by PR #65;
- COMMON — PASS, with native Common represented by omission and explicit override represented distinctly without invented numeric defaults.

The historical COURTYARD FAIL remains immutable evidence and is not a restart point.

### Q1 Component Angle

`diptrace_q1_component_angle = PASS` with DipTrace PCB Layout 5.3.0.3.

Observed real-host behavior:

- 90° -> `Angle="1.5708"`;
- 180° -> `Angle="3.1416"`;
- 270° -> `Angle="4.7124"`;
- entered 360° normalizes to GUI 0°, with canonical zero export allowed to omit `Angle`;
- `Change Side` from Top 90° produced Bottom `Angle="4.7124"`, `Flip="Y"` and reader `mirrored=true`;
- coordinates, pattern, connectivity and other non-orientation properties were preserved;
- native open/save/re-export completed without repair/error.

The private/manual campaign PASS is distinct from any future source-controlled public evidence promotion. Do not silently change the public warning/evidence contract without a separate reviewed code change.

### Codex real-client restart

`codex_real_client_restart = PASS` on the same accepted production candidate.

- Codex Desktop: `26.803.5235.0`;
- DipTrace MCP: `0.2.1`;
- 159 tools available after both restarts;
- `get_capabilities` was identical across restarts;
- new process IDs confirmed actual Codex/MCP restart;
- production code remained unchanged.

## Intentional pause in formal lifecycle acceptance

The next project-required lifecycle gate, when formal acceptance resumes, is:

`windows_clean_install_repair_uninstall`

The Claude Desktop gate is skipped by explicit project waiver, not by inference and not as PASS.

Before spending more time on installer/profile lifecycle checks, the project is validating and improving the core product behavior: can the system create useful schematics and make explainable PCB design decisions while retaining the existing safety/trust boundaries?

## New development track — intelligent schematic and PCB design

### Product goal

The project should progress from "can safely create/edit EDA objects" to "can make defensible engineering-layout decisions". The target is not blind imitation of one vendor style or rigid enforcement of every possible electronics drafting convention. The target is a schematic/PCB that an experienced engineer can open and understand quickly, with sensible grouping, orientation, flow, density, electrical constraints and routing decisions.

Reference schematics and layout examples from component datasheets should be treated as **high-value design motifs**, not absolute coordinate templates. The engine should preserve the intent of a reference design — which parts belong together, relative order, orientation, local signal/current flow, important adjacency and recognizable topology — while adapting that motif to the rest of the actual project.

The long-term architecture is deliberately staged:

```text
reference / datasheet intent
          +
project connectivity and constraints
          |
          v
candidate placement
          |
          v
candidate interconnect routing
          |
          v
quality scoring
          |
          +----> placement feedback / local repair
          |
          v
transaction preview -> guarded apply -> review
```

For PCB work, the same loop gains physical/electrical sub-scores for stackup/reference structure, PDN/current paths, controlled impedance, vias, crosstalk, EMI risk, thermal behavior and manufacturing constraints.

### Shared design principles

- Prefer deterministic, explainable scoring first. ML remains optional future work.
- Keep observed document facts separate from inferred engineering intent and operator-supplied facts.
- Missing current, edge rate, impedance, stackup or datasheet facts remain explicit unknowns rather than guessed constants.
- Allow placement and routing to influence each other; routing may propose bounded placement repair instead of accepting a pathological result.
- Hard DRC/mechanical/safety violations cannot be compensated by a better cosmetic or wire-length score.
- Preserve useful reference-design structure from datasheets without copying absolute coordinates blindly.
- Every automatic edit remains inside the existing preview/SHA/transaction/review safety model.
- Internal optimizer development does not automatically create new MCP tools; the current public tool surface stays stable unless a separate API decision is made.

## Schematic track

### Phase 26 — real-world readability baseline and benchmark fixtures

**Status: active checkpoint.**

PR #66 added deterministic bounded readability routing for newly authored schematic wires. Its automated goals include component avoidance, text/label avoidance, crossing and overlap avoidance, Manhattan routing, self-intersection avoidance and fewer unnecessary bends. The subsequent Ponytail pass and later development may have modified adjacent behavior.

The historical `diptrace_ratline_and_wire_roundtrip` PASS remains valid for its original scope. It proves wire connectivity and native round-trip behavior, but it does **not** prove that higher-level current schematic authoring consistently produces a schematic a human would consider clean and usable.

Before the first Phase 26 real-world experiment, record the actual local production candidate. Do not assume that the historical `0bb09b4...` identity is still the code being tested if later production changes are present.

Build small real circuits from clean starting points and preserve them as regression/quality cases where licensing and provenance allow. Suggested cases:

- resistor divider;
- LED + resistor;
- divider + capacitor / simple RC network;
- LDO or small DC/DC support network;
- MCU power/decoupling fragment;
- a deliberately collision-prone layout;
- RefDes/Value/net-label-near-wire cases;
- at least one small multi-block, multi-net schematic.

Validate and begin measuring:

- correct components, pins, values and net connectivity;
- sensible component placement and orientation;
- readable wire paths;
- no wires through unrelated symbols;
- no unnecessary crossings or collinear overlaps;
- no wire covering RefDes, Value or net labels;
- obvious junction intent;
- no extreme detours or needless bends;
- occupied sheet area / bounding-box compactness;
- functional-group compactness;
- rough left-to-right signal-flow consistency;
- native open/save/reopen/re-export preservation;
- whether the schematic is useful without routine manual cleanup.

A reproducible quality problem found here becomes a focused regression case and input to the next phases. Historical PASS evidence is not rewritten.

### Phase 27 — schematic intent and reference-motif model

**Goal:** represent why parts belong together before trying to place them.

Add an internal schematic design-intent layer that can describe:

- functional blocks and sub-blocks;
- main component versus support components;
- pin/net roles when they can be resolved safely;
- repeated channels;
- signal direction hints;
- power-tree relationships;
- local adjacency preferences;
- preferred symbol orientation / pin-facing relationships;
- hard versus soft layout constraints;
- provenance and confidence for every inferred/reference-derived constraint.

Add a reference-motif representation for datasheet/reference circuits. A motif should record relative topology and presentation intent rather than absolute page coordinates. Example concepts include "input capacitor beside VIN/GND", "feedback divider grouped at FB", "crystal network beside oscillator pins" and "connector -> protection -> interface/MCU".

Initial implementation should support project/operator-supplied structured motifs and deterministic built-in heuristics. Automated datasheet ingestion/search can be added later; the layout engine must not depend on online retrieval to work.

### Phase 28 — schematic placement engine v2

**Goal:** place whole functional structures, not isolated symbols.

Build a hierarchical placer:

1. place/pack functional blocks;
2. place the principal component inside each block;
3. place its reference/support motif relative to it;
4. orient symbols to expose connected pins toward the intended local flow;
5. pack remaining components while respecting text and wiring corridors;
6. globally compact the result without collapsing readability.

Candidate scoring should include explicit terms for symbol/body overlap, text/label clearance, functional-group cohesion, motif deviation, pin-facing/orientation quality, future wire length/crossings, grid regularity, signal-flow direction, visual density, total occupied area and unnecessary movement.

The engine should generate multiple bounded candidates where useful rather than pretending one greedy placement is globally optimal.

### Phase 29 — human-readable schematic interconnect router

**Goal:** route wires, labels and buses as a readability problem rather than a shortest-path problem.

Extend bounded Manhattan routing to minimize symbol/text collisions, crossings, overlaps and unnecessary bends; keep parallel related signals coherent; prefer short local wires; decide when labels/buses are clearer; preserve obvious signal flow; and disclose per-route quality metrics.

Routing may return a structured placement-feedback request rather than accepting a pathological route. The router must not mutate placement implicitly; it proposes bounded repairs that the joint optimizer can score.

### Phase 30 — joint schematic layout optimizer

**Goal:** optimize placement and wiring together.

Introduce a bounded co-optimization loop: classify intent, generate placement candidates, route/estimate each, score the complete schematic, apply bounded placement feedback, reroute affected nets only, stop on convergence/budget exhaustion, then present the best candidate through the existing guarded plan/preview path.

### Phase 31 — schematic quality gate and product-level acceptance

**Goal:** prove consistent usefulness, not only valid XML.

Create benchmark/acceptance cases retaining initial state, candidate(s), final state and machine-readable metrics. Gate connectivity/ERC non-regression, collision/crossing/bend metrics, compactness, determinism, reference-motif preservation, real DipTrace open/save/re-export and human review of a representative subset.

This phase closes only when a deliberately ugly but electrically correct schematic is reliably made materially cleaner without routine manual cleanup.

## PCB track — electrical-intent to whole-board optimization

The detailed design document is [`PCB_DESIGN_ENGINE.md`](PCB_DESIGN_ENGINE.md). The PCB track deliberately sits above existing parsers, placement legalizer, router, impedance/return-path helpers and guarded transaction path rather than replacing them.

### Generation A — PCB understands electronics

#### Phase 32 — PCB design intent, net intelligence and electrical criticality

**Status: implemented internally; acceptance requires green repository CI.**

Build a typed engineering graph above raw connectivity:

- component roles such as controller, power converter, connector, interface, sensor, timing, protection and support;
- deterministic functional blocks with principal anchors and support members;
- multi-role net classification: ground/shield, power/high-current, switch node, clock, differential, reset/control/digital, analog/precision/reference/feedback/current-sense and RF;
- explicit criticality, noise-emission/noise-sensitivity and via-penalty intent;
- optional physical constraints for edge rate, frequency, current, impedance/tolerance, length/skew, via count, layers, spacing, reference and stubs;
- explicit confidence/reasons and operator overrides for facts XML cannot prove.

Missing physical values remain unknown. Exported differential-pair data may raise confidence/constraints; naming heuristics may classify intent but may not invent electrical numbers.

Power/ground topology policy begins here but remains intent, not copper implementation:

- ordinary ground -> continuous reference plane preferred;
- chassis/shield -> distinct return domain;
- switching node -> local copper minimized;
- sense nets -> Kelvin candidate;
- power rail -> local plane/pour candidate;
- star grounding is never inferred automatically and requires explicit project/operator intent.

This prevents the unsafe shortcut "analog + digital => split ground" from becoming an automatic rule.

#### Phase 33 — intent-aware PCB placement v2

**Status: implemented internally; acceptance requires green repository CI.**

Keep the existing `placement.py` as the low-level geometry/legalization authority and add a higher board-level placer that:

1. fixes locked and mechanically anchored components;
2. handles principal functional anchors before support parts;
3. pulls support components toward resolved anchors;
4. derives desired regions from critical connectivity;
5. generates bounded deterministic board candidates;
6. rejects candidates that increase overlap/outline/keepout penalties;
7. scores geometry, block cohesion, support adjacency, critical connection distance and intent-level aggressor/victim proximity separately;
8. emits normal semantic move operations rather than writing XML directly.

Generation A intentionally preserves side/rotation and uses proximity/noise proxies. Pad-level current loops, reference planes, crosstalk fields and thermal spreading belong to Generation B.

### Generation B — PCB understands fields and current paths

#### Phase 34 — stackup, PDN, return-path and via intelligence

**Status: planned.**

Add physical decision layers before serious routing:

- stackup/reference-layer relationships and manufacturable controlled-impedance geometry;
- distinct trust levels for analytic impedance estimates, manufacturer geometry and external field-solver evidence;
- PDN graph per rail: source, loads, steady/transient current when known, bulk/local decoupling, distribution and voltage-drop/current bottlenecks;
- decoupling and switching-regulator hot-loop geometry using pad/current paths rather than only component distance;
- return-path analysis across continuous reference copper, plane gaps/splits and layer transitions;
- power/ground stitching, signal-return vias and current-carrying via requirements;
- via roles: signal, power, ground stitching, return transition, differential transition, thermal and justified via fence.

The existing via span/geometry validator, impedance estimator and return-path analyzer remain lower-level inputs. Unknown authoritative pour/refill geometry stays explicit until verified.

#### Phase 35 — noise compatibility, impedance and electrical placement refinement

**Status: planned.**

Replace distance-only noise proxies with bounded aggressor/victim analysis using known edge/frequency, parallel exposure, layer/reference structure and separation. Refine placement scoring with:

- decoupling loop area;
- switching hot-loop/switch-node area;
- analog/RF/clock separation;
- impedance-compatible routing corridors;
- reference-plane availability;
- expected via transitions;
- connector/interface flow;
- thermal clustering/spreading heuristics;
- high-current path geometry.

The engine still reports risk indicators, not EMC/PI sign-off.

### Generation C — PCB routes intentionally

#### Phase 36 — routing policy compiler and route ordering

**Status: planned.**

Compile net intent into concrete router policy rather than making the router guess: priority, width/clearance, preferred/forbidden layers, via budget/penalty, target impedance, pair/skew constraints, continuous-reference requirement, spacing, shielding and stub policy.

Route topology-critical nets before ordinary control/indicator nets. Ordering derives from criticality and explicit constraints rather than XML order or a hard-coded protocol list.

#### Phase 37 — SI-aware routing, copper strategy and placement feedback

**Status: planned.**

Extend candidate routing/review to include:

- impedance continuity and differential symmetry/skew;
- stub and excessive-via penalties;
- parallel coupling/crosstalk exposure;
- reference-plane continuity and return-via proximity across layer changes;
- current-aware power routing;
- trace vs local copper vs plane/pour planning;
- ground stitching and local shielding where justified;
- authoritative refill/island/cutout/thermal-relief handling only after DipTrace geometry/evidence is sufficient.

Routing may produce bounded placement repairs: move/rotate a part, open a corridor, remove several vias or restore a valid reference path. The joint optimizer decides whether the repair wins globally.

### Generation D — optimize the whole board

#### Phase 38 — joint multi-objective PCB optimizer

**Status: planned.**

Combine placement, routing, SI, PI, return-path, EMI-risk, thermal and manufacturing/assembly/test constraints into one bounded generate -> score -> improve loop.

The complete score remains decomposed. Hard DRC/mechanical/safety violations are lexicographically dominant and cannot be traded away for lower wire length, prettier geometry or fewer vias.

External routers/solvers remain candidate/evidence generators; they do not bypass MCP trust, transaction or review boundaries.

#### Phase 39 — PCB benchmark and real-DipTrace product acceptance

**Status: planned.**

Create small engineering-trap benchmark families rather than one giant demo board:

- MCU + decoupling + crystal;
- LDO and buck/boost regulator;
- ADC/sensor and mixed analog/digital;
- current shunt / precision sense;
- USB/high-speed differential;
- Ethernet/CAN/other interface blocks;
- RF module + antenna/matching;
- higher-current power distribution;
- multilayer controlled-impedance examples.

For each retain deliberately poor, acceptable/reference and generated candidates where provenance permits. Measure hard-rule non-regression plus electrical/routeability/SI/PI/EMI-risk/thermal/manufacturing score components.

Real-DipTrace acceptance for affected primitives must use generate -> open -> refill where required -> DRC/review -> save -> reopen -> re-export -> compare. Claims about poured copper, plane behavior, via structures or native semantics may not be promoted from synthetic parser round-trips alone.

## Remaining formal lifecycle acceptance

When the chosen product-development checkpoint is intentionally finished or paused, resume project-required formal acceptance in this order:

| Order | Gate | Status |
| --- | --- | --- |
| — | `claude_desktop_real_client_restart` | **WAIVED — not PASS; no direct Claude evidence** |
| 1 | `windows_clean_install_repair_uninstall` | **PENDING** |
| 2 | `elevated_plugin_install_profile_preservation` | **PENDING** |
| 3 | `custom_state_preservation` | **PENDING** |

Generate the canonical evidence worksheet with:

```bash
python scripts/prepare_manual_acceptance.py acceptance \
  --version 0.2.1 \
  --commit <exact-40-character-production-commit>
```

After recording observations and evidence files, validate it with:

```bash
python scripts/prepare_manual_acceptance.py acceptance --check
```

The canonical validator does not currently encode the Claude waiver and therefore must not call the full canonical matrix complete while that required gate remains pending internally. The project-level waiver is documented separately rather than disguised as PASS.

## Claim-specific or optional manual work

These are not core blockers unless the corresponding claim is planned:

- public redownload/install smoke after a future release whose bytes change;
- external legal/Novarm review if a planned claim or distribution activity requires it;
- real openEMS execution if external-solver validation is to be claimed.

## Repository implementation status

The previous repository-only roadmap is implementation-complete, but the schematic/PCB intelligence track intentionally creates new product-development work. Current implementation already provides the foundation:

- PCB, schematic and library parsing/querying;
- guarded semantic transactions, rollback, SHA/policy/backup/atomic-write boundaries;
- schematic authoring and schematic-to-PCB reconciliation;
- bounded placement/routing, DSN/SES, differential-pair and preliminary SI workflows;
- Windows bridge/installer/portable/configurator build pipelines;
- explicit trust-path regression coverage;
- deterministic synthetic PCB, schematic, Component Library, Pattern Library and DSN/SES fixture generation;
- raw-preserving Component/Pattern Library mutation core;
- deterministic pattern-recommendation baseline;
- bounded DFM/DFA/DFT release-readiness checks;
- manual-acceptance evidence tooling;
- internal PCB Generation A design-intent/net-intelligence model;
- internal intent-aware PCB placement v2 layered over the existing legalizer.

The new work should reuse these layers rather than duplicating them. High-level optimizers produce typed plans/operations that still pass through the existing guarded transaction and review paths.

## Native library mutation status

The internal raw-preserving Component/Pattern mutation core has real Component Editor and Pattern Editor round-trip evidence.

This does not silently expand the public MCP contract. Public registration of native library write tools remains a separate API/product decision.

## Ratline and authored-wire status

The historical `diptrace_ratline_and_wire_roundtrip` gate is PASS. PCB ratline serialization/collision defects were repaired through PRs #63/#64, and schematic authored-wire connectivity survived native save/reopen/re-export.

PR #66 later added stronger readability routing for newly authored schematic wires. Because that behavior is broader than the historical gate, it now forms the baseline for Phase 26 rather than forcing a rerun of the historical gate.

## Current public contracts

The maintained public baseline remains:

- 159 registered MCP tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations;
- stable structured public error envelope;
- project-owned worker-thread boundary for registered tools;
- exact SHA, policy, backup, atomic-write, session-lease and trust-authority boundaries.

The optimizer roadmap does not implicitly add or remove public tools. New optimizer capability should prefer internal EDA modules/services and a small deliberate public surface rather than one MCP tool per heuristic.

## Phase summary

| Phase | Status | Result |
| --- | --- | --- |
| 0–4 | complete | package/contracts, parsing/models, geometry, transactions and semantic writes |
| 5 | bounded complete | deterministic DRC/ERC/review categories with explicit limits |
| 6–10 | complete | silkscreen, placement, routing, DSN/SES, differential-pair/length/preliminary impedance |
| 11 | bounded complete | return-path, BOM, DFM/DFA/DFT, thermal and assembly heuristics |
| 12 | implementation complete | release manifests/adapters; external solver/native manufacturing sign-off remain external |
| 13–19 | complete | skills/CI, scaffolding, schematic authoring, panelisation, ngspice, multi-net routing and sync |
| 20 | repository complete | trust authority/comparison/cancellation plus regression coverage |
| 21 | complete | service-Facade decomposition and parity guardrails |
| 22 | candidate complete | Windows installer/portable/configurator pipeline; clean-machine acceptance remains manual |
| 23 | baseline complete | deterministic pattern recommendation and privacy-bounded feedback/evaluation |
| 24 | host-verified internal core | Component/Pattern mutation core has real editor evidence; public registration is deferred |
| 25 | manual acceptance paused | 8 canonical PASS gates; Claude WAIVED for current campaign; resume point is Windows lifecycle |
| 26 | active checkpoint — schematic | real-world readability baseline and benchmark cases |
| 27 | planned — schematic | design intent, functional blocks and reference motifs |
| 28 | planned — schematic | hierarchical placement/orientation/compactness/routeability |
| 29 | planned — schematic | human-readable interconnect routing with placement feedback |
| 30 | planned — schematic | joint placement/interconnect optimizer |
| 31 | planned — schematic | quality benchmark and real-DipTrace readability acceptance |
| 32 | **implemented — PCB Generation A** | PCB design intent, net intelligence, criticality and conservative power/ground policy; CI gate required before acceptance |
| 33 | **implemented — PCB Generation A** | intent-aware PCB placement v2 over existing legality/scoring; CI gate required before acceptance |
| 34 | planned — PCB Generation B | stackup, PDN, return-path and via intelligence |
| 35 | planned — PCB Generation B | noise compatibility, impedance/reference and placement refinement |
| 36 | planned — PCB Generation C | routing-policy compiler and engineering-aware route ordering |
| 37 | planned — PCB Generation C | SI-aware routing, copper/plane/pour strategy and placement feedback |
| 38 | planned — PCB Generation D | joint multi-objective whole-board optimizer |
| 39 | planned — PCB Generation D | engineering benchmark suite and real-DipTrace product acceptance |

## Permanent limitations and non-claims

- Synthetic scaffolds and generated fixture packs are MCP-generated XML, not DipTrace exports.
- Changing `format_version` is not conversion or compatibility evidence.
- Reference datasheet/reference-board motifs are guidance and provenance-bearing constraints, not proof that the generated design is manufacturer-approved.
- The local router is bounded and is not a full push-and-shove/free-angle/global EDA router.
- PCB Generation A intent/noise/thermal/current-return values are deterministic policy/proxies, not field, PI, thermal or EMC simulation results.
- Copper-pour, return-path, impedance, thermal, DFM/DFA/DFT and manufacturing reviews retain approximation/skip boundaries.
- Generic fabrication/assembly manifests are not native Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off packages.
- The ngspice adapter runs user-provided netlists; it does not generate a complete simulation netlist from a DipTrace design.
- Native manufacturing generation remains unavailable because no verified DipTrace output API is claimed.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review, production readiness, direct Claude Desktop validation or globally optimal schematic/PCB layout.
