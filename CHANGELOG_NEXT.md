# Post-0.2.1 development changes

This development record tracks changes merged after the immutable `v0.2.1` release while the next version has not yet been selected. The source/package version remains `0.2.1`; these items are **not** part of the published `v0.2.1` artifacts unless stated otherwise.

## Added

### Schematic intelligence

- deterministic schematic design-intent model with functional blocks and provenance-bearing reference motifs;
- hierarchical schematic placement foundation and bounded multi-candidate placement optimizer;
- non-mutating schematic wire planner with disclosed readability metrics and explicit placement feedback;
- conservative Component Library pin-geometry resolution from the embedded Design Cache;
- pin-aware joint placement/routing scoring for hypothetical candidates;
- bounded non-mutating placement repair driven by route feedback and re-scored by the joint optimizer.

### PCB Generations A-D

- **Generation A:** engineering intent, component roles, functional blocks, multi-role net classification, explicit electrical constraints, conservative power/ground topology intent and intent-aware placement v2;
- **Generation B:** exported stackup/reference context, conservative PDN/source/load/decoupling analysis, regulator hot-loop candidates, return-path integration, timing-gated aggressor/victim triage and semantic via roles;
- **Generation C:** deterministic routing-policy compiler, engineering route ordering, observed-route SI checks, copper/topology strategy and bounded placement feedback;
- **Generation D:** bounded whole-board candidate selector with lexicographically dominant hard constraints, decomposed soft metrics and a synthetic engineering-trap benchmark catalog.

### Product and engineering support

- raw-preserving internal Component/Pattern Library mutation core with controlled real-editor evidence;
- deterministic pattern recommendation and privacy-bounded feedback/evaluation baseline;
- deterministic synthetic acceptance fixture-pack generator;
- write-path trust invalidation regression coverage;
- deterministic DFM/DFA/DFT release-readiness supplement;
- manual-only acceptance evidence generator and validator;
- aggregate supported-environment coverage gate raised to 90% while preserving the 85% geometry-enabled Linux-only floor.

### Cinematic presentation mode

- deterministic cinematic timelines with `cinematic`, `timelapse`, `tutorial` and `gif` pacing presets;
- Windows desktop replay host with bounded cursor/click/hotkey/text/path actions and dry-run support;
- version/editor-specific `DipTraceUIProfile` persistence and readiness validation;
- affine DipTrace design-coordinate to normalized client-coordinate calibration with residual checks;
- normalized live cursor probing for one-shot UI calibration;
- semantic Schematic part/wire replay and PCB Generation A placement replay;
- same-layer PCB trace replay with fail-closed refusal of unsupported via/layer transitions;
- HWND-targeted ffmpeg capture plus MP4/GIF post-processing helpers.

Cinematic replay is deliberately a presentation branch. The XML bridge and normal preview/SHA/transaction/review path remain authoritative for engineering edits and acceptance.

## Changed

- The public MCP contract remains frozen at 159 tools despite the new internal EDA layers.
- The private/manual Q1 Component Angle campaign is now PASS on its accepted production checkpoint; immutable historical release records keep the status that was true when each release was cut.
- `claude_desktop_real_client_restart` is explicitly WAIVED for the current campaign, not marked PASS; the canonical validator remains conservative.
- Documentation now distinguishes current implementation state from immutable release/audit/acceptance snapshots.
- Documentation now describes PCB Generations A-D as implemented internal layers instead of future work.
- Documentation now describes the schematic phases as partially implemented foundations rather than wholly planned work.
- Installation/release documentation now reflects that `v0.2.1` and `diptrace-mcp==0.2.1` are already published.
- Testing documentation now reflects the combined 90% coverage gate and the separate 85% Linux-only floor.

## Remaining boundaries

- selective atomic re-route/replacement of existing schematic wires after placement repair remains future work;
- stronger sheet-level schematic congestion scheduling and automatic motif ingestion remain future work;
- real-DipTrace product acceptance for PCB Generation D remains pending;
- cinematic UI macros and calibration still require real-client verification for the exact DipTrace version/editor configuration;
- staged cinematic playback of vias/layer transitions remains unsupported;
- Windows lifecycle gates remain pending after the current manual-acceptance pause;
- native manufacturing generation, field-solver/PI/EMC/thermal sign-off, universal compatibility, signed-binary trust, independent review and production readiness are not claimed.

This file should be folded into `CHANGELOG.md` when the next version is selected.
