# Roadmap and Actual Status

This document separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document, policy and configured adapters allow the feature;
3. **DipTrace verified** — controlled real DipTrace or real-client evidence exists for the exact path.

Implementation never implies universal DipTrace compatibility. Runtime `get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-10

The current source/package version is `0.2.1`. Annotated tag `v0.2.1`, the GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI are already published.

The accepted production-code candidate for the latest manual campaign is:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

That commit includes the post-PR #65/#66 Ponytail pass (PR #68). Later documentation-only commits do not invalidate this production-code identity.

The durable recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md), updated on 2026-08-10. Resume from that checkpoint instead of repeating already accepted gates.

A new product-development track also starts at this checkpoint: **intelligent schematic and PCB design quality**. Formal acceptance remains paused at its existing resume point while the project first proves that it can produce schematics that are not only electrically correct, but compact, readable, intentionally structured and comparable in presentation quality to strong professional reference designs. The schematic track comes first because its geometry is primarily a readability/layout problem; the PCB track follows after the same generate/score/improve architecture is established.

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

This is **8 of 12 blocking manual gates complete**.

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

`codex_real_client_restart = PASS` on the same production candidate.

- Codex Desktop: `26.803.5235.0`;
- DipTrace MCP: `0.2.1`;
- 159 tools available after both restarts;
- `get_capabilities` was identical across restarts;
- new process IDs confirmed actual Codex/MCP restart;
- production code remained unchanged.

## Intentional pause in formal acceptance

The next formal gate remains:

`claude_desktop_real_client_restart`

It is **PENDING** and has not been run.

The formal campaign is intentionally paused before that gate. Before spending more time on client/installer lifecycle checks, the project will validate and improve the core product behavior: can the current MCP author a normal, readable, useful schematic in real DipTrace, and can it evolve from bounded authoring into an intentional schematic-layout engine?

This pause does not cancel or waive the remaining formal gates.

## New development track — intelligent schematic and PCB design

### Product goal

The project should progress from "can safely create/edit EDA objects" to "can make defensible engineering-layout decisions". The target is not blind imitation of one vendor style or rigid enforcement of every possible electronics drafting convention. The target is a schematic/PCB that an experienced engineer can open and understand quickly, with sensible grouping, orientation, flow, density and routing decisions.

Reference schematics and layout examples from component datasheets should be treated as **high-value design motifs**, not absolute coordinate templates. The engine should preserve the intent of a reference design — which parts belong together, relative order, orientation, local signal flow, important adjacency and recognizable topology — while adapting that motif to the rest of the actual project.

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

The same generate -> score -> improve loop should be reusable for PCB work later, where physical/electrical constraints become much stronger.

### Design principles

- Prefer human readability and recognizable functional structure over merely minimizing total geometric wire length.
- Keep functional blocks compact, but penalize needless schematic-area expansion so the result does not become an oversized empty canvas.
- Prefer conventional visual flow where it helps understanding: inputs toward outputs, signal flow predominantly left-to-right, supply hierarchy and returns placed consistently, without treating these conventions as hard laws when they make the actual circuit worse.
- Preserve useful local reference-design structure from datasheets instead of scattering a component's support network across the sheet.
- Allow placement and wire routing to influence each other. Wiring is not a final cosmetic pass if a small component move can remove pathological crossings, detours or unreadable topology.
- Prefer deterministic, explainable scoring first. ML remains optional future work and must not be required for the first useful implementation.
- Do not optimize for "looks standardized" at the expense of engineering clarity. A clean, obvious circuit is more important than ceremonial compliance with drafting conventions that add no value.
- Every automatic edit remains inside the existing preview/SHA/transaction/review safety model.

## Schematic track — start here

### Phase 26 — real-world readability baseline and benchmark fixtures

**Status: active checkpoint / first task.**

PR #66 added deterministic bounded readability routing for newly authored schematic wires. Its automated goals include component avoidance, text/label avoidance, crossing and overlap avoidance, Manhattan routing, self-intersection avoidance and fewer unnecessary bends. The subsequent Ponytail pass may have modified adjacent behavior.

The historical `diptrace_ratline_and_wire_roundtrip` PASS remains valid for its original scope. It proves wire connectivity and native round-trip behavior, but it does **not** prove that higher-level current schematic authoring consistently produces a schematic a human would consider clean and usable.

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

Candidate scoring should include explicit terms for:

- symbol/body overlap;
- text/label clearance zones;
- functional-group cohesion;
- deviation from a trusted reference motif;
- pin-facing / orientation quality;
- estimated future wire length;
- estimated future crossings;
- alignment and grid regularity;
- backward or confusing signal flow;
- whitespace balance / visual density;
- total occupied schematic area;
- unnecessary movement from an already-good existing layout.

The engine should generate multiple bounded candidates where useful rather than pretending one greedy placement is globally optimal.

### Phase 29 — human-readable schematic interconnect router

**Goal:** route wires, labels and buses as a readability problem rather than a shortest-path problem.

Extend the current bounded Manhattan wire routing into a sheet-aware interconnect planner that can:

- minimize wire-symbol and wire-text collisions;
- strongly penalize unnecessary crossings and overlaps;
- minimize bends where that improves readability;
- avoid ambiguous junction presentation;
- keep related parallel signals visually coherent;
- prefer short local wires inside a functional block;
- decide when a named net label is clearer than a long cross-sheet wire;
- support buses/grouped signals where the underlying DipTrace representation is verified;
- preserve obvious input-to-output visual flow;
- expose quality metrics for every routed connection.

Crucially, routing may return a structured placement-feedback request rather than accepting a pathological route. Example: "moving U3 right by one grid region removes four crossings and 80 mm of detour". The router must not mutate placement implicitly; it proposes bounded repairs that the joint optimizer can score.

### Phase 30 — joint schematic layout optimizer

**Goal:** optimize placement and wiring together.

Introduce a bounded co-optimization loop:

1. classify blocks and intent;
2. generate several placement candidates;
3. route or estimate interconnect for each candidate;
4. score the complete schematic;
5. apply local placement feedback for pathological routes;
6. re-route affected nets only;
7. stop on convergence, budget exhaustion or no meaningful score improvement;
8. present the best candidate through the existing guarded plan/preview transaction path.

The score must remain decomposed and explainable. A lower score is meaningful only when its component metrics are disclosed; there should be no opaque "AI quality" number in the deterministic baseline.

### Phase 31 — schematic quality gate and product-level acceptance

**Goal:** prove that the engine produces consistently useful schematics, not just valid XML.

Create a benchmark/acceptance suite containing synthetic, project-owned and legally usable real reference cases. For each case retain the initial state, generated candidate(s), final state and machine-readable metrics.

Quality gates should cover at minimum:

- electrical/connectivity non-regression;
- no new ERC/review regression within supported checks;
- collision/crossing/bend metrics;
- compactness without crowding;
- stable deterministic output for a fixed seed/config;
- reference-motif preservation where applicable;
- real DipTrace open/save/re-export;
- human review of a representative subset.

This phase closes only when the project can take a deliberately ugly but electrically correct schematic and reliably produce a materially cleaner version without routine manual cleanup.

## PCB track — after the schematic architecture is proven

The PCB track reuses the schematic intent/optimizer architecture, but adds physical electrical constraints. It should not start by attempting a full replacement for a mature EDA autorouter.

### Phase 32 — PCB design-intent and net-policy model

Classify functional blocks and nets by engineering importance and derive explicit routing/placement policies: critical length, via penalty, layer preference, return-path sensitivity, current/power role, noise sensitivity, differential relationship and other available constraints. Datasheet/reference-layout motifs should describe important local placement and loop structure without blindly copying board coordinates.

### Phase 33 — global PCB placement optimizer

Extend the existing local/legalizing placer into hierarchical/global placement with functional groups, support-component adjacency, orientation, decoupling, thermal spacing, connector flow and estimated routeability. Placement scoring must include the cost of the routes it is likely to create, not only ratsnest anchor length.

### Phase 34 — routing policy and placement-routing feedback

Use the current local router and optional Freerouting as candidate generators. Add engineering-aware route ordering and scoring so a via, detour or layer transition carries a different cost for USB/RF/clock/power than for low-speed GPIO/LED signals. Allow routing congestion and critical-route failure to feed back into placement.

### Phase 35 — power, ground and via strategy

Add explicit planning for ground stitching, reference-transition vias, thermal vias, via fences where justified, power-via arrays, plane/pour continuity and return-current considerations. Keep current copper-pour/refill limitations explicit until authoritative geometry is available.

### Phase 36 — joint PCB optimizer and benchmark

Combine placement, routing candidates, power/ground strategy, DRC/review, SI/return-path heuristics and manufacturing constraints into the same bounded generate -> score -> improve loop established by the schematic work. External routers remain untrusted candidate generators; the MCP's own structural review and transaction gates remain authoritative for what it can actually prove.

Benchmark against deliberately poor layouts, hand-improved layouts and legally usable reference boards. Do not claim "optimal PCB" or fabrication sign-off; report measurable improvements and remaining unsupported categories.

## Remaining blocking formal acceptance

When the schematic authoring/readability validation and the chosen development checkpoint are intentionally finished or paused, resume formal acceptance in this order:

| Order | Gate | Status |
| --- | --- | --- |
| 1 | `claude_desktop_real_client_restart` | **PENDING** |
| 2 | `windows_clean_install_repair_uninstall` | **PENDING** |
| 3 | `elevated_plugin_install_profile_preservation` | **PENDING** |
| 4 | `custom_state_preservation` | **PENDING** |

Generate the exact evidence worksheet with:

```bash
python scripts/prepare_manual_acceptance.py acceptance \
  --version 0.2.1 \
  --commit <exact-40-character-production-commit>
```

After recording observations and evidence files, validate it with:

```bash
python scripts/prepare_manual_acceptance.py acceptance --check
```

The validator must not call the blocking acceptance complete while a required gate remains pending.

## Claim-specific or optional manual work

These are not core blockers unless the corresponding claim is planned:

- public redownload/install smoke after a future release whose bytes change;
- external legal/Novarm review if a planned claim or distribution activity requires it;
- real openEMS execution if external-solver validation is to be claimed.

## Repository implementation status

The previous repository-only roadmap is implementation-complete, but the new schematic/PCB intelligence track intentionally creates new product-development work. Current implementation already provides the foundation:

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
- manual-acceptance evidence tooling.

The new work should reuse these layers rather than duplicating them. In particular, high-level optimizers should produce typed plans/operations that still pass through the existing guarded transaction and review paths.

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

The acceptance campaign and the new optimizer roadmap do not implicitly add or remove public tools. New optimizer capability should prefer internal domain modules/services and a small deliberate public surface rather than one MCP tool per heuristic.

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
| 25 | manual acceptance paused at 8/12 | Through Codex restart PASS; formal resume point is Claude Desktop |
| 26 | **active checkpoint** | Establish real-world schematic readability baseline and benchmark cases |
| 27 | planned — schematic | Design intent, functional blocks and datasheet/reference motifs |
| 28 | planned — schematic | Hierarchical component placement, orientation, compactness and routeability scoring |
| 29 | planned — schematic | Human-readable wire/label/bus routing with placement feedback |
| 30 | planned — schematic | Joint placement/interconnect optimizer with bounded iterative repair |
| 31 | planned — schematic | Quality benchmark, real-DipTrace acceptance and product-level readability gate |
| 32 | planned — PCB | PCB design-intent and engineering-aware net policy model |
| 33 | planned — PCB | Global/hierarchical PCB placement optimizer |
| 34 | planned — PCB | Engineering-aware routing policy and placement-routing feedback |
| 35 | planned — PCB | Power/ground, stitching and via strategy |
| 36 | planned — PCB | Joint PCB optimizer, review loop and measurable benchmark |

## Permanent limitations and non-claims

- Synthetic scaffolds and generated fixture packs are MCP-generated XML, not DipTrace exports.
- Changing `format_version` is not conversion or compatibility evidence.
- Reference datasheet/reference-board motifs are guidance and provenance-bearing constraints, not proof that the generated design is manufacturer-approved.
- The local router is bounded and is not a full push-and-shove/free-angle/global EDA router.
- Copper-pour, return-path, impedance, thermal, DFM/DFA/DFT and manufacturing reviews retain approximation/skip boundaries.
- Generic fabrication/assembly manifests are not native Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off packages.
- The ngspice adapter runs user-provided netlists; it does not generate a complete simulation netlist from a DipTrace design.
- Native manufacturing generation remains unavailable because no verified DipTrace output API is claimed.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review, production readiness or globally optimal schematic/PCB layout.
