# Post-0.2.1 development changes

This development record tracks changes merged after the immutable `v0.2.1` release while the next version has not yet been selected. The source/package version remains `0.2.1`; these items are **not** part of the published `v0.2.1` artifacts unless stated otherwise.

## Added

### Schematic intelligence

- deterministic schematic design-intent model with functional blocks and provenance-bearing reference motifs;
- hierarchical schematic placement foundation and bounded multi-candidate placement optimizer;
- non-mutating schematic wire planner with disclosed readability metrics and explicit placement feedback;
- conservative Component Library pin-geometry resolution from the embedded Design Cache;
- pin-aware joint placement/routing scoring for hypothetical candidates;
- bounded non-mutating placement repair driven by route feedback and re-scored by the joint optimizer;
- **atomic selective schematic reroute planner** that identifies only explicit sheet-local nets touched by moved parts, fails closed on unresolved endpoints/routes, and emits one dependency-safe `delete_wire -> move_components -> add_wire` semantic batch for the existing guarded transaction path;
- deterministic schematic ensemble ranking that combines builtin-but-explicitly-labelled readability motifs, pin-aware route quality and bounded placement-grid congestion pressure;
- fail-closed validation for stale/geometrically inconsistent Wire segment references while preserving valid middle-of-segment joins;
- real-DipTrace schematic authoring/readability campaign coverage for cases 01–18, including incremental editing, failed-operation safety, single- and multi-net atomic reroute, obstacle/readability repair and a repaired 22-part stress schematic;
- public MCP tools `rank_schematic_placement_candidates`, `plan_schematic_placement_repair` and `apply_schematic_placement_repair_plan` productizing ensemble ranking and the repair-plus-atomic-reroute pipeline through the stored-plan preview/expected-SHA/transaction path.

### PCB Generations A-D

- **Generation A:** engineering intent, component roles, functional blocks, multi-role net classification, explicit electrical constraints, conservative power/ground topology intent and intent-aware placement v2;
- **Generation B:** exported stackup/reference context, conservative PDN/source/load/decoupling analysis, regulator hot-loop candidates, return-path integration, timing-gated aggressor/victim triage and semantic via roles;
- **Generation C:** deterministic routing-policy compiler, engineering route ordering, observed-route SI checks, copper/topology strategy and bounded placement feedback;
- **Generation D:** bounded whole-board candidate selector with lexicographically dominant hard constraints, decomposed soft metrics and a synthetic engineering-trap benchmark catalog;
- bounded A-D candidate ensemble generation using multiple real Generation-A placement profiles (`balanced`, `critical_nets`, `noise_aware`, `support_compact`) plus the existing-board baseline, with B/C conservative evidence proxies and the existing hard-first Generation-D selector;
- public MCP tool `compare_pcb_placement_candidates` exposing that ensemble as a read-only comparison.

### DSN/SES and XML analysis

- bounded Specctra structure inventory for DSN/SES-style S-expressions with scope histogram, token/depth limits and exact root validation;
- non-mutating SES compatibility analysis with route length/width/layer statistics, duplicate-net detection, unknown target nets/layers and the existing semantic import planner's importable/skipped classification;
- deterministic XML semantic inventory/fingerprint and structural delta analysis that ignores XML attribute order while preserving element order and unknown XML;
- Hypothesis/property regression coverage for fingerprint invariants and unknown-XML mutation detection.

### Evidence and acceptance automation

- deterministic evidence-report builder and CLI for finalized operator capture candidates;
- evidence reports re-check quarantined artifact SHA-256 bindings, compute XML semantic fingerprints/deltas, render JSON/Markdown, reproduce operator claims/checklists as such, and **never** grant provenance trust, fixture trust, release acceptance or PASS automatically.

### Component/Pattern Library API preparation

- stable package-level `LibraryMutationRequest` / preview contract over the existing raw-preserving mutation core;
- required expected-SHA binding, deterministic semantic delta/inventory output and explicit pin/pad mapping validation;
- the contract is intentionally **not** registered as a public MCP tool yet; public registration remains a separate API/product and contract-snapshot decision.

### Cinematic presentation mode

- deterministic cinematic timelines with `cinematic`, `timelapse`, `tutorial` and `gif` pacing presets;
- Windows desktop replay host with bounded cursor/click/hotkey/text/path actions and dry-run support;
- version/editor-specific `DipTraceUIProfile` persistence and readiness validation;
- affine DipTrace design-coordinate to normalized client-coordinate calibration with residual checks;
- normalized live cursor probing for one-shot UI calibration;
- semantic Schematic part/wire replay and PCB Generation A placement replay;
- same-layer PCB trace replay with fail-closed refusal of unsupported via/layer transitions;
- HWND-targeted ffmpeg capture plus MP4/GIF post-processing helpers;
- cinematic manifest preflight with deterministic content fingerprint, timing consistency checks and explicit cue/payload/desktop-command/path/text/hotkey safety budgets.

Cinematic replay is deliberately a presentation path. The XML bridge and normal preview/SHA/transaction/review path remain authoritative for engineering edits and acceptance.

### Headless Windows GUI worker

- isolated Win32-desktop worker for bounded native DipTrace open/save/close work without switching the user's input desktop or synthesizing physical mouse/keyboard input;
- Windows smoke/readiness checks and a frozen packaged helper under `app/tools/diptrace_mcp_headless_gui/`;
- fail-closed automation with no coordinate-input fallback when a native control action cannot be completed safely.

The headless worker is a host-automation boundary, not a second semantic authoring authority. Real DipTrace actions remain claim-specific acceptance evidence.

### Product and engineering support

- raw-preserving internal Component/Pattern Library mutation core with controlled real-editor evidence;
- deterministic pattern recommendation and privacy-bounded feedback/evaluation baseline;
- deterministic synthetic acceptance fixture-pack generator;
- write-path trust invalidation regression coverage;
- deterministic DFM/DFA/DFT release-readiness supplement;
- manual-only acceptance evidence generator and validator;
- aggregate supported-environment coverage gate raised to 90% while preserving the 85% geometry-enabled Linux-only floor;
- public MCP tools `recommend_patterns` (deterministic pattern-library recommendation without model calls) and `analyze_release_readiness` (bounded DFM/DFA/DFT findings from exported XML).

## Changed

- The public MCP contract was intentionally expanded from the frozen 159 to 165 tools to productize bounded intelligence engines; package-level library mutation registration remains intentionally unregistered and the contract snapshot/regeneration gate was updated in the same change.
- Existing-wired schematics no longer represent a fundamental placement dead-end: affected explicit wire geometry can now be selectively replanned as one atomic semantic transaction batch. The older conservative placement planners may still refuse existing wires when used directly.
- The initial real-DipTrace schematic quality campaign is complete: cases 01–18 closed with retained failed/invalid attempts, targeted fixes, operator visual review and native Save/Close/Reopen/re-export evidence. PR #90 merged the bounded fixes into `main`.
- PCB Generation D can now compare multiple internally generated bounded placement candidates rather than only caller-supplied synthetic examples.
- DSN/SES results can be structurally and semantically screened before import without mutating the PCB.
- Real-DipTrace capture candidates can be converted into reproducible machine-readable and Markdown evidence reports without rewriting historical evidence or manufacturing trust.
- The private/manual Q1 Component Angle campaign is PASS on its accepted production checkpoint; immutable historical release records keep the status that was true when each release was cut.
- The accepted manual matrix is complete at 12 of 12 blocking gates PASS across its recorded checkpoints. Claude Desktop restart and custom-state preservation are operator-confirmed PASS from a separate machine; their earlier WAIVED/pending states remain historical only.
- Documentation distinguishes current implementation state from immutable release/audit/acceptance snapshots.
- Installation/release documentation reflects that `v0.2.1` and `diptrace-mcp==0.2.1` are already published.
- Testing documentation reflects the combined 90% coverage gate and the separate 85% Linux-only floor.

## Fixed

- `plan_schematic_placement_repair` no longer plans from optimizer-regenerated layouts; the baseline is built from the document's current placement and the joint route scorer runs with existing wires allowed, so repair-plus-reroute now works on already-wired schematics as documented.
- Operator `moves` passed to `plan_schematic_placement_repair` are fixed constraints: they apply on top of the current placement and are re-enforced after repair, so requested coordinates survive planning exactly; regression covers the committed geometry.
- Schematic placement-repair planning now fails closed when the generated operation batch exceeds the 100-operation transaction limit, instead of storing a plan that the paired apply tool could never execute.
- Capability reporting no longer overstates availability: `release_readiness` requires a board document, and `schematic_placement_candidate_ranking` is reported unavailable for wired schematics where the underlying scorer refuses to run.
- `recommend_patterns` exposes the typed `PatternRequirement` schema in `tools/list` (pad count, mounting, geometry bounds, pitch, holes, required pad numbers) instead of an opaque object.

## Remaining boundaries

- atomic selective schematic reroute currently rebuilds affected sheet-local explicit nets from resolved pin endpoints; it does not preserve arbitrary pre-existing manual junction topology as a visual constraint;
- stronger sheet-level/global schematic congestion scheduling and external/reference motif ingestion remain future work;
- the completed 18-case schematic campaign supports its tested scope only; new schematic claims such as hierarchy, topology-preserving reroute or automatic rotation/pin-facing behavior still require claim-specific evidence;
- PCB candidate/whole-board quality remains subject to current-candidate real-DipTrace/native refill/plane/via acceptance where stronger claims are desired;
- cinematic UI macros and calibration still require real-client verification for the exact DipTrace version/editor configuration;
- staged cinematic playback of vias/layer transitions remains unsupported;
- the 12-gate manual matrix is complete for its recorded checkpoints; future Windows/client reruns are impact- or release-claim-based rather than automatically replaying the full matrix;
- the library mutation request/preview contract remains package-level and unregistered in the public MCP tool snapshot;
- native manufacturing generation, field-solver/PI/EMC/thermal sign-off, universal compatibility, signed-binary trust, independent review and production readiness are not claimed.

This file should be folded into `CHANGELOG.md` when the next version is selected.
