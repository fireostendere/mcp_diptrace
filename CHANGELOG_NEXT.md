# Unreleased

## Added

- candidate-specific PCB quality review covering compactness, centering,
  symmetry, return planes, GND pours/stitching, thermal-relief intent,
  silkscreen mounting-space clearance, hot-loop span and decoupling span;
- a bounded whole-board PCB pipeline that reuses placement, routing, rectangular
  outline compaction, two-layer GND pours/stitching and silkscreen operations;
- source-linked qualitative PCB physics principles and explicit unknown-fact
  reporting instead of guessed current, impedance, thermal or EMC limits;
- SHA-bound structured engineering-rule packs for project, datasheet and
  reference-design facts, with per-rule provenance and redistribution metadata;
- iterative schematic placement repair with objective history, a global
  interconnect strategy (wire/label/bus/power symbol), and conservative reuse of
  intentional existing junctions;
- evidence-report domain summaries/connectivity fingerprints and deterministic
  design-frame quality assessment for PCB/Schematic recording crops.

## Changed

- PCB ensemble candidates are now reviewed after their hypothetical operations
  are applied in memory, so hard physical/layout findings affect selection;
- PCB placement scoring now includes board compactness, centering, simple
  repeated-pair symmetry and topology-backed high-di/dt-loop span;
- silkscreen labels prefer closer association, normalize unreadable quarter-turn
  text, may cross solder-masked traces, and still avoid foreign mounting areas,
  pads, holes and vias;
- the two public candidate-ranking tools accept optional validated engineering
  rule packs without adding another MCP tool.

# 0.3.0 detailed release changes

This record preserves the detailed changes included in the immutable `v0.3.0`
unsigned development prerelease. New post-release work belongs in a new section
above this release record.

## Added

### Read-only built-in library bridge

- public `query_builtin_library_catalog` browsing/search over DipTrace's immutable installed catalog;
- public `place_builtin_component` for guarded copy-only placement from a returned catalog ID into a schematic Design Cache;
- isolated Component Editor `.eli` to `.elixml` export with source-SHA preservation, cache reuse, unit conversion and real-DipTrace BSS138 open/save validation;
- no public mutation path for native `.eli` or `.lib` files.

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
- deterministic smallest-area preference between otherwise equally compatible
  patterns, making compact standard 2.54 mm connectors the default;
- package-level `copper_pours.py` helper for explicit-net Top/Bottom pour
  boundaries, four-spoke thermal intent and bounded distributed GND stitching;
- silkscreen body avoidance enabled by default, hidden-marking filtering and
  assembly-only label suppression;
- compact symmetric 25×12 mm I²C level-shifter PCB example with 14 traces, two
  GND pours and 14 stitching vias.

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
- isolated hidden-desktop capture of the real DipTrace project window through `PrintWindow`/bounded `WM_PRINT` BGRA frames piped to ffmpeg, with black/title-bar-only rejection;
- repository I²C level-shifter source plus MP4/GIF demonstration with one-at-a-time symbol and net reveal.
- PCB/Schematic design-boundary fitting, purple board-outline detection,
  control-free crop selection, output padding and one-point-at-a-time route
  timing;
- matching PCB source plus board-framed MP4/GIF demonstration.

Cinematic replay is deliberately a presentation path. The XML bridge and normal preview/SHA/transaction/review path remain authoritative for engineering edits and acceptance.

### Headless Windows GUI worker

- isolated Win32-desktop worker for bounded native DipTrace open/save/close work without switching the user's input desktop or synthesizing physical mouse/keyboard input;
- selectable launch mode: `hidden` (separate randomly named `WinSta0` desktop, invisible) is the default, and `native` explicitly targets the verified current `WinSta0` input desktop so the round trip stays visible; native mode rejects elevated callers and validates desktop/window-station/session identity before DipTrace work;
- Windows hidden/native smoke/readiness checks and a frozen packaged helper under `app/tools/diptrace_mcp_headless_gui/`;
- fail-closed automation with no coordinate-input fallback when a native control action cannot be completed safely;
- split Windows packaging boundary: the per-user MCP installer is permanently non-elevated, while a separate self-contained administrator plug-in installer owns only the bridge/settings payload and bounded DipTrace `Plugins\\<module>\\DipTraceMCP` writes.

The headless worker is a host-automation boundary, not a second semantic authoring authority or a process/filesystem/network/token/privilege sandbox. Real DipTrace actions remain claim-specific acceptance evidence.

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

- The public MCP contract was intentionally expanded from the frozen 159 to 165 tools for bounded intelligence engines, then to 167 for the read-only built-in-library bridge; package-level native-library mutation remains intentionally unregistered.
- Existing-wired schematics no longer represent a fundamental placement dead-end: affected explicit wire geometry can now be selectively replanned as one atomic semantic transaction batch. The older conservative placement planners may still refuse existing wires when used directly.
- The initial real-DipTrace schematic quality campaign is complete: cases 01–18 closed with retained failed/invalid attempts, targeted fixes, operator visual review and native Save/Close/Reopen/re-export evidence. PR #90 merged the bounded fixes into `main`.
- PCB Generation D can now compare multiple internally generated bounded placement candidates rather than only caller-supplied synthetic examples.
- DSN/SES results can be structurally and semantically screened before import without mutating the PCB.
- Real-DipTrace capture candidates can be converted into reproducible machine-readable and Markdown evidence reports without rewriting historical evidence or manufacturing trust.
- The private/manual Q1 Component Angle campaign is PASS on its accepted production checkpoint; immutable historical release records keep the status that was true when each release was cut.
- The accepted manual matrix is complete at 12 of 12 blocking gates PASS across its recorded checkpoints. Claude Desktop restart and custom-state preservation are operator-confirmed PASS from a separate machine; their earlier WAIVED/pending states remain historical only.
- Documentation distinguishes current implementation state from immutable release/audit/acceptance snapshots.
- Installation/release documentation identifies the immutable `v0.3.0`
  GitHub/PyPI assets and split Windows packaging without rewriting older releases.
- Testing documentation reflects the combined 90% coverage gate and the separate 85% Linux-only floor.
- The operator accepted the current repository PCB/Schematic designs and both
  GIF/MP4 examples in the current DipTrace configuration on 2026-08-16.

## Fixed

- Wired-schematic repair scoring now models the same world the atomic reroute applies: the joint route scorer removes exactly the affected wire geometry the reroute would replace for a candidate's moved parts (through the same shared affected-group logic) and keeps unaffected nets as obstacles instead of re-scoring their preserved wires as phantom replacement candidates; a clean wired schematic no longer receives spurious repair motion, and unaffected nets' geometry is provably never deleted.
- `plan_schematic_placement_repair` builds its baseline from the document's current placement, so repair-plus-reroute works on already-wired schematics as documented (the previous optimizer candidate generation refused wired documents before the reroute stage ran).
- Operator `moves` are true immutable repair constraints: the engine carries `fixed_part_ids`, proposal generation never moves a fixed part or a group containing one, scoring happens on the constrained geometry, and the service verifies the final coordinates fail-closed instead of silently re-applying them; reported `improved`/score now refer to the actually applied geometry.
- RefDes resolution for `moves` is fail-closed: a RefDes shared by multiple schematic parts (multi-part components) is refused with the bounded list of matching stable IDs, duplicate moves for one part are refused (conflicting or identical), unique RefDes remain case-insensitive and stable object IDs remain the exact selector.
- No-op plan/apply contract is consistent across the stored-plan tools: empty placement/silkscreen/repair plans are stored with `status="noop"` plus `no_changes=true`, and applying one is an idempotent success (`ok=true`, `changed=false`, no transaction, SHA unchanged) instead of raising after looking applicable.
- Schematic placement-repair planning fails closed when the generated operation batch exceeds the 100-operation transaction limit, instead of storing a plan that the paired apply tool could never execute.
- Capability reporting matches runtime availability: `release_readiness` requires a board document, and `schematic_placement_candidate_ranking` is reported unavailable for wired schematics where the underlying scorer refuses to run.
- `recommend_patterns` exposes the typed `PatternRequirement` schema in `tools/list` (pad count, mounting, geometry bounds, pitch, holes, required pad numbers) instead of an opaque object.
- Headless Save targets the project window rather than IME/proxy windows, dispatches the native menu command without physical input, orders `WM_CLOSE` behind Save on the same queue, and fails when normal process exit cannot be observed.
- Hidden recording selects the real project `TForm1`, dismisses the XML-open information dialog through a button message, pads odd H.264 frames, bounds GIF post-processing, and removes stale MP4/GIF outputs before each validated run.

## Remaining boundaries

- atomic selective schematic reroute currently rebuilds affected sheet-local explicit nets from resolved pin endpoints; it does not preserve arbitrary pre-existing manual junction topology as a visual constraint;
- stronger sheet-level/global schematic congestion scheduling and external/reference motif ingestion remain future work;
- the completed 18-case schematic campaign supports its tested scope only; new schematic claims such as hierarchy, topology-preserving reroute or automatic rotation/pin-facing behavior still require claim-specific evidence;
- PCB candidate/whole-board quality remains subject to claim-specific real-DipTrace
  native refill/plane/via acceptance where stronger claims are desired;
- cinematic UI macros and calibration for additional DipTrace
  version/editor configurations require their own real-client verification;
- staged cinematic playback of vias/layer transitions remains unsupported;
- the 12-gate manual matrix is complete for its recorded checkpoints; future Windows/client reruns are impact- or release-claim-based rather than automatically replaying the full matrix;
- the library mutation request/preview contract remains package-level and unregistered in the public MCP tool snapshot;
- native manufacturing generation, field-solver/PI/EMC/thermal sign-off, universal compatibility, signed-binary trust, independent review and production readiness are not claimed.

The concise release summary is in `CHANGELOG.md`; do not rewrite this detailed
published-release record when later development begins.
