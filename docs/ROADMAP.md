# Roadmap and Actual Status

This roadmap separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document/policy/configuration permits the feature;
3. **DipTrace verified** — controlled real DipTrace/client evidence exists for the exact path and candidate.

Implementation never implies universal DipTrace compatibility. Historical evidence stays bound to the production identity that was actually tested.

## Current checkpoint — 2026-08-17

The current source/package version is `0.4.0`. Version `v0.4.0` is the current published
unsigned development release. Its annotated tag targets
`b4c0132283ff16a0bca81567df6704d1f6a73c7f`; the GitHub release and
`diptrace-mcp==0.4.0` PyPI package are public immutable identities.

The exact pre-release cross-platform candidate
`72750d195e204cf0c11c04d71364055ca7634c6b` passed the Windows, Linux, macOS,
PyPI-validation, MCPB/registry-preparation and repository-CI gates before the
release/tag sequence. Preparation-only MCPB evidence did not publish a v0.4.0
MCPB asset.

Current `main` may contain post-release documentation/release-pipeline hardening
that is intentionally not part of the immutable `v0.4.0` bytes. Historical
release and acceptance evidence stays bound to the identity actually tested.

The schematic-quality production fixes were merged by PR #90. The production merge identity is:

`main@6bfb656008e27f07e665a9b63540d6dc4a5174b6`

Documentation-only commits after that merge do not change the production-code identity of the closed schematic-quality campaign.

The historical formal manual-acceptance checkpoint remains:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

The durable recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md). Completed real-host/client PASS evidence is not silently transferred to later code.

The detailed schematic product-quality campaign is in [SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md](SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md). Cases 01–18 are complete; future reruns are impact-based or tied to new claims rather than a replay of the whole campaign.

Current cross-domain implementation detail is in [EDA_INTELLIGENCE.md](EDA_INTELLIGENCE.md).

## Completed manual gates on the accepted historical checkpoint

PASS:

- PCB open/save/re-export round-trip;
- schematic open/save/re-export round-trip;
- Component Library writer save/reopen/re-export;
- Pattern Library writer save/reopen/re-export;
- generated PCB ratlines and authored schematic wires;
- MASK / PASTE / COURTYARD / COMMON semantics;
- Q1 Component Angle GUI/re-export;
- real Codex Desktop restart/configuration/`get_capabilities`.

The canonical matrix therefore has 8 of 12 blocking manual gates PASS at that historical checkpoint.

Later operator-confirmed evidence from a separate machine completed `claude_desktop_real_client_restart` and `custom_state_preservation`. Together with `windows_clean_install_repair_uninstall`, including a from-zero run on a separate new Windows machine, and `elevated_plugin_install_profile_preservation` on exact candidate `9af6da2`, all 12 blocking gates are PASS across the accepted checkpoints.

# Schematic track

Detailed implementation: [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## Phase 26 — real-world readability baseline

**Status: complete for the initial real-DipTrace product-quality campaign.**

The historical wire-only acceptance was strengthened by an 18-case real-host campaign covering authored schematics, visual readability, incremental editing, transaction-failure safety, native round-trip and representative stress composition. Failed/invalid intermediate attempts remain retained as evidence rather than being erased by later repairs.

## Phase 27 — design intent and reference motifs

**Status: implemented, including bounded external rule-pack ingestion.**

Implemented:

- conservative part/net roles and functional blocks;
- provenance-bearing project/datasheet/reference/builtin motif model;
- deterministic builtin readability motifs that are explicitly labelled as heuristics rather than external evidence;
- strict SHA-bound project/datasheet/reference rule packs with per-source and
  per-rule provenance plus redistribution metadata.

Arbitrary PDF interpretation remains reviewer work: the deterministic engine
accepts only validated structured facts and never treats filenames or model
memory as provenance.

## Phase 28 — placement engine v2

**Status: bounded global strategy implemented for current scope.**

Implemented:

- hierarchical block/anchor/support placement;
- configurable grid/row packing and locked-part preservation;
- bounded deterministic candidate generation;
- readability/interconnect/movement scoring;
- ordinary `MoveComponentsOperation` output.

Cardinal rotation/pin-facing candidate generation is implemented as a confidence-gated package layer and remains disabled by default until focused real-host M2 evidence exists for the exact symbol/editor path. Broader externally sourced motif generation remains review-driven.

## Phase 29 — human-readable interconnect planning

**Status: bounded implementation complete for current scope.**

Implemented:

- non-mutating route evaluation/cleanup;
- obstacle/crossing/overlap/self-intersection/diagonal/bend/length/detour metrics;
- explicit placement feedback;
- conservative Design Cache pin geometry;
- configurable ground/power policy;
- deterministic motif + route + placement-grid congestion ensemble ranking;
- sheet-level net priorities and explicit wire/net-label/bus/power-symbol
  strategy, including indexed sibling groups suitable for buses.

Full global Steiner-tree/junction optimisation remains outside the bounded
planner.

## Phase 30 — joint placement/routing + existing-wire transaction

**Status: major functional gap closed; bounded implementation complete for current scope.**

Implemented:

- pin-aware route scoring for hypothetical placement candidates;
- bounded route-feedback-driven placement repair;
- rigid block/local repair policy and strict translation/candidate budgets;
- source-document immutability during planning;
- **selective reroute of explicit affected `(net, sheet)` groups when moved parts touch existing wires**;
- **one dependency-safe semantic batch combining wire deletion, component movement and replacement wire authoring**;
- fail-closed refusal if any affected endpoint/route cannot be rebuilt;
- fail-closed rejection of stale/geometrically inconsistent Wire segment references;
- no rewriting of unaffected explicit wire geometry;
- bounded multi-iteration repair of top candidates with objective history and a
  strict-improvement stopping rule;
- literal reconstruction of unambiguous connected acyclic existing-wire graphs, preserving every proven junction on affected pin-to-pin paths;
- fail-closed refusal of cyclic, free-leaf, incomplete or ambiguous hand-authored branched topology instead of silently rewriting it;
- confidence-gated cardinal symbol rotation can be composed into the same delete -> rotate/move -> rebuild semantic batch, but remains disabled by default pending M2 native evidence;
- no automatic page-spanning explicit wiring of previously unwired nets by default.

Current boundary: ordinary affected endpoint selection remains bounded and deterministic, but branched existing nets are no longer flattened merely because they contain multiple intentional junctions. The planner preserves all proven junctions on an unambiguous connected acyclic literal wire graph. Cyclic, free-leaf, incomplete and ambiguous topology fails closed. Global Steiner-tree optimization is still intentionally outside the bounded planner.

## Phase 31 — schematic quality gate

**Status: PASS / closed for the initial 18-case campaign.**

Cases 01–18 in `SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md` are complete. The campaign found and repaired real quality/semantic issues, retained failed and invalid attempts, validated single- and multi-net atomic reroute, checked incremental edits and transaction failure behavior, reused representative native evidence where impact analysis allowed it, and closed on a repaired 22-part stress schematic.

The final representative schematic was operator-accepted and survived real DipTrace Save/Close/Reopen/re-export with all 12 required schematic semantic categories preserved. PR #90 merged the bounded fixes without expanding the public MCP contract.

This gate is not a universal claim. Topology-preserving reroute and confidence-gated rotation planning now exist at package level, but their new claim scope is not inherited from the historical 18-case campaign. Hierarchy, automatic enabling of symbol rotation/pin-facing, broader datasheet/reference ingestion, or materially changed production code requires focused new evidence.

# PCB track — Generations A-D

Detailed implementation: [PCB_DESIGN_ENGINE.md](PCB_DESIGN_ENGINE.md).

## Generation A — electronics intent and placement

**Status: implemented.**

`pcb_design_intent.py` and `pcb_placement.py` provide component/net roles, blocks, explicit constraints, conservative power/ground topology intent and bounded deterministic placement candidates.

## Generation B — physical context

**Status: bounded implementation complete.**

`pcb_physical.py` provides exported stackup/reference candidates, conservative PDN topology, hot-loop/return-path/noise context and semantic via roles while preserving unknown current/current-density/voltage-drop/via-capacity facts.

## Generation C — intentional routing

**Status: bounded implementation complete.**

`pcb_routing_policy.py` compiles deterministic routing policy/order and evaluates supplied route observations without inventing missing width, impedance, timing or crosstalk limits.

Native copper refill remains a real-host evidence boundary.

## Generation D — whole-board selection

**Status: selector + candidate-specific physical review + bounded whole-board pipeline implemented.**

`pcb_joint_optimizer.py` retains lexicographically dominant hard safety/mechanical/connectivity/DRC/reference/manufacturing dimensions over decomposed soft placement/routing/via/SI/PI/return/EMI/thermal/manufacturing metrics.

`pcb_candidate_ensemble.py` now feeds that selector real bounded Generation-A placement plans under disclosed profiles:

- `balanced`;
- `critical_nets`;
- `noise_aware`;
- `support_compact`;
- unchanged `existing_board` baseline.

Generation B/C facts contribute conservative proxy/uncertainty terms only. No invented autorouter traces or solver facts are introduced.

`pcb_quality.py` evaluates each hypothetically applied candidate rather than
reusing baseline geometry. Its hard findings feed Generation D; compactness,
centering, symmetry, hot-loop/decoupling span, plane continuity, GND
stitching/thermals and silkscreen clearance remain separately explainable.

`pcb_whole_board.py` composes the existing stages into one non-committing plan:
candidate selection -> routing -> compact rectangular outline -> two-layer GND
pours/stitching -> silkscreen -> final review. Stage operation kinds are kept so
the existing cinematic path can replay them one at a time.

### Real-DipTrace product acceptance

**Status: pending for stronger whole-board quality claims.**

The synthetic engineering-trap catalog remains useful regression coverage but is not native-DipTrace proof. Real acceptance should use generate -> open -> refill where needed -> DRC/review -> save/reopen/re-export -> compare.

The narrower repository I²C demo path is operator-accepted as of 2026-08-16:
the compact 25×12 mm PCB, matching schematic and board-framed GIF/MP4 outputs
were inspected in the current DipTrace configuration. The current generator
also includes compact 2.54 mm headers, two explicit GND-pour boundaries,
four-spoke thermal intent and 17 distributed GND stitching vias. This does not
close the broader authoritative-refill/plane/via or manufacturing acceptance
boundary above.

# Quantitative engineering-estimate track

**Status: bounded package-level implementation.**

`physics_estimates.py` provides explicit-input analytical trace/via DC resistance,
voltage-drop, aggregate-loss and first-order thermal estimates. Missing material,
geometry, current or source facts remain `unknown`; no typical value is substituted.
Each estimate records the exact inputs, method identity, source revision/SHA/locator,
assumptions, sensitivity terms and limitations. These calculations are engineering
assistance only: M3 governs source applicability and M8 governs any physical
measurement/correlation claim.

# DSN/SES and XML analysis track

**Status: implemented bounded analysis layer.**

`specctra_analysis.py` adds structural/token/depth inventory plus route statistics and non-mutating import compatibility classification for SES results. Unknown target nets/layers and skipped imports are explicit before mutation.

`xml_analysis.py` adds deterministic semantic fingerprints/inventories and structural deltas for all parsed XML, including unknown elements. Attribute order is normalized; child order remains significant.

Hypothesis/property tests cover fingerprint determinism, attribute-order invariance and unknown-XML change detection.

Further work should focus on additional real router dialect fixtures and claim-specific round-trip evidence, not broadening the parser by guessing unsupported syntax.

# Evidence automation track

**Status: capture + deterministic report pipeline implemented.**

Existing `capture_diptrace_evidence.py` owns source/open-save/re-export capture, hashes, quarantine, operator attestations and review-only candidate generation.

`evidence_report.py` + `scripts/build_evidence_report.py` now:

- recheck candidate artifact SHA bindings;
- compute XML semantic fingerprints/deltas;
- compute domain counts and connectivity fingerprints/deltas;
- emit deterministic JSON/Markdown;
- surface missing/tampered artifacts and review blockers;
- never grant PASS/provenance/fixture/release trust automatically.

`evidence_campaign.py` now aggregates multiple candidate reports, exact-hash media/frame metrics, exported geometry/manufacturing deltas, explicitly untrusted visual-review findings and promotion/rejection requests into one deterministic campaign identity. It never grants PASS, native-refill authority or trust; promotion remains the separate human M11 decision.

# Component/Pattern mutation API track

**Status: internal writer proven for its historical scope; stable package-level preview API prepared; public MCP registration intentionally pending.**

`library_mutation_api.py` provides an expected-SHA-bound request/preview layer over the raw-preserving mutation core with semantic delta/fingerprint and explicit mapping errors.

It remains `public_registration=false`. A public write tool must be an explicit product/API decision with public-contract snapshot, policy, documentation and current-candidate real-editor evidence review.

# Cinematic presentation track

**Status: implemented presentation subsystem + bounded whole-manifest preflight; repository examples accepted, additional-client UI acceptance remains scoped.**

Implemented:

- deterministic timeline/presets and JSONL capture/compile;
- Windows cursor/click/hotkey/text/path replay and dry-run;
- PCB/Schematic UI profiles and affine calibration;
- semantic schematic/PCB replay for supported primitives;
- HWND recording and MP4/GIF helpers;
- isolated hidden-window `PrintWindow`/`WM_PRINT` capture with local ffmpeg MP4/GIF output;
- `cinematic_preflight.py` deterministic content hash and finite cue/timing/payload/desktop-action budgets;
- mandatory `cinematic_host.play_manifest()` preflight before dry-run or real desktop driver actions.

Still pending real acceptance:

- repeat action-macro/calibration evidence for additional
  editor/version/configuration combinations beyond the accepted repository
  examples;
- staged via/layer-transition replay and other unverified editor gestures.

# Headless native GUI track

**Status: Windows isolation primitive and packaged helper implemented; real DipTrace actions remain exact-host evidence.**

`headless_gui.py` creates an isolated Win32 desktop inside the current interactive session, launches a worker and DipTrace there, and performs only bounded automation. It never switches the user's input desktop and has no physical mouse/keyboard fallback. The current native action is open -> Save -> close for PCB/Schematic/Component/Pattern editors; `cinematic_recording.py` reuses the isolation primitive for presentation-only hidden MP4/GIF capture.

Source checkouts invoke it with `py -m diptrace_mcp.headless_gui`; Windows packaged builds include `diptrace_mcp_headless_gui.exe` under the helper tools directory. Hosted CI verifies desktop isolation and packaging without claiming licensed DipTrace UI compatibility. See [HEADLESS_GUI.md](HEADLESS_GUI.md).

# Documentation/CI drift protection

**Status: implemented.**

`scripts/check_documentation_state.py` verifies the frozen public-tool count, current EDA module representation, semantic current-state markers, the mandatory cinematic preflight boundary, package-only library mutation registration, completed 12/12 acceptance wording, current selective-reroute claims and the headless source command contract. `tests/test_documentation_state.py` runs the checker through the normal CI test matrix.

Historical dated release/acceptance/audit records remain excluded from current-state freshness assertions.

# Public contracts

- 167 registered MCP tools (165 existing tools plus the read-only built-in-library bridge);
- stable structured error envelope;
- server-owned worker-thread boundary;
- SHA/policy/backup/atomic-write/session-lease/trust/transaction boundaries.

Higher-level EDA modules should continue to prefer typed package internals and a small deliberate public surface.

# Next project sequence

1. Keep the completed schematic cases 01–18 closed unless an impact-based production change requires a focused rerun.
2. Keep the completed 12-gate manual matrix closed unless an impact-based production change requires a focused rerun.
3. Gather real-DipTrace native refill/DRC evidence for the new whole-board PCB
   pipeline when stronger PCB claims are the active product priority.
4. Treat cinematic exact-UI acceptance, headless native-action expansion and any future public library-write API as separate claim/product tracks.

# Phase summary

| Area | Current status |
| --- | --- |
| manual acceptance | all 12 blocking gates PASS across the accepted checkpoints |
| schematic intent/motifs | implemented + builtin heuristics + SHA-bound external rule packs |
| schematic placement | bounded implementation + confidence-gated rotation candidates; automatic rotation remains M2-gated |
| schematic route/joint repair | bounded iterative implementation with objective history and junction reuse; public repair/reroute plan tools shipped |
| schematic selective atomic reroute | placement/rotation batch implemented with multi-junction topology preservation for proven acyclic graphs; rotation remains M2-gated |
| schematic product quality | **PASS for initial 18-case real-DipTrace campaign; future work impact/claim-based** |
| PCB Generation A | implemented |
| PCB Generation B | implemented/bounded |
| PCB Generation C | implemented/bounded |
| PCB Generation D | candidate-specific physical review + bounded whole-board plan implemented; read-only `compare_pcb_placement_candidates` tool shipped |
| PCB product quality | compact two-layer example and cinematic output operator-accepted for v0.3.0; stronger native-refill/manufacturing claims remain open |
| DSN/SES analysis | bounded structural/importability analysis implemented |
| XML semantic analysis | fingerprint/delta + property tests implemented |
| bounded physics estimates | explicit-input trace/via resistance, voltage drop, loss budget and first-order thermal; M3/M8 claim gates retained |
| evidence reports | deterministic candidate + campaign aggregation with hash-bound media/deltas and no automatic trust |
| library mutation public API | package-level request/preview prepared; public MCP registration pending |
| cinematic | presentation + mandatory preflight + hidden MP4/GIF capture implemented; exact UI acceptance remains configuration-specific |
| headless GUI | hidden Win32 desktop helper implemented with selectable `hidden`/`native` open -> Save -> close plus isolated cinematic capture; real DipTrace actions remain claim-specific evidence |
| documentation drift | evergreen code/docs guard implemented and CI-tested |

# Permanent limitations / non-claims

- Synthetic fixtures and benchmark catalogs are not DipTrace exports unless explicitly recorded as such.
- Changing `format_version` is not conversion evidence.
- Builtin motifs are labelled heuristics, not manufacturer/reference-design approval.
- Local routing/placement search is bounded, not a globally optimal EDA solver.
- PCB analytic layers are not field-solver, PI, thermal or EMC proof.
- Native manufacturing generation is unavailable.
- Cinematic replay is presentation automation, not engineering acceptance evidence.
- Evidence reports do not grant trust/PASS.
- The completed schematic campaign proves only its recorded scope and does not imply arbitrary hierarchy/topology/global-optimality support.
- The project does not claim Novarm/DipTrace endorsement, universal DipTrace or MCP-client compatibility, signed binaries, independent review, production readiness or globally optimal schematic/PCB layout.
