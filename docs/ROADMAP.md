# Roadmap and Actual Status

This roadmap separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document/policy/configuration permits the feature;
3. **DipTrace verified** — controlled real DipTrace/client evidence exists for the exact path and candidate.

Implementation never implies universal DipTrace compatibility. Historical evidence stays bound to the production identity that was actually tested.

## Current checkpoint — 2026-08-14

The current source/package version is `0.2.1`. The immutable `v0.2.1` release and PyPI package are published; post-release development is tracked separately.

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

**Status: implemented foundation + bounded builtin motif generation.**

Implemented:

- conservative part/net roles and functional blocks;
- provenance-bearing project/datasheet/reference/builtin motif model;
- deterministic builtin readability motifs that are explicitly labelled as heuristics rather than external evidence.

Still pending: automatic external datasheet/reference-design ingestion with provenance/redistribution controls.

## Phase 28 — placement engine v2

**Status: bounded implementation complete for current scope.**

Implemented:

- hierarchical block/anchor/support placement;
- configurable grid/row packing and locked-part preservation;
- bounded deterministic candidate generation;
- readability/interconnect/movement scoring;
- ordinary `MoveComponentsOperation` output.

Still pending: real-host-backed automatic rotation/pin-facing decisions and broader externally sourced motif generation.

## Phase 29 — human-readable interconnect planning

**Status: bounded implementation complete for current scope.**

Implemented:

- non-mutating route evaluation/cleanup;
- obstacle/crossing/overlap/self-intersection/diagonal/bend/length/detour metrics;
- explicit placement feedback;
- conservative Design Cache pin geometry;
- configurable ground/power policy;
- deterministic motif + route + placement-grid congestion ensemble ranking.

Still pending: stronger global/sheet-level congestion scheduling, same-net junction optimization and automatic label/bus strategy.

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
- no automatic page-spanning explicit wiring of previously unwired nets by default.

Current limitation: affected explicit nets are rebuilt from resolved pin endpoints through deterministic MST edges; arbitrary hand-authored junction topology is not preserved as a visual constraint.

Next refinement: optional intentional-junction preservation and bounded iterative generate -> score -> repair -> reroute convergence with objective history/stopping criteria.

## Phase 31 — schematic quality gate

**Status: PASS / closed for the initial 18-case campaign.**

Cases 01–18 in `SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md` are complete. The campaign found and repaired real quality/semantic issues, retained failed and invalid attempts, validated single- and multi-net atomic reroute, checked incremental edits and transaction failure behavior, reused representative native evidence where impact analysis allowed it, and closed on a repaired 22-part stress schematic.

The final representative schematic was operator-accepted and survived real DipTrace Save/Close/Reopen/re-export with all 12 required schematic semantic categories preserved. PR #90 merged the bounded fixes without expanding the public MCP contract.

This gate is not a universal claim. New capabilities outside the tested scope — hierarchy, automatic symbol rotation/pin-facing, topology-preserving reroute, broader datasheet/reference ingestion, or materially changed production code — require focused new evidence.

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

**Status: selector + internally generated candidate ensemble implemented.**

`pcb_joint_optimizer.py` retains lexicographically dominant hard safety/mechanical/connectivity/DRC/reference/manufacturing dimensions over decomposed soft placement/routing/via/SI/PI/return/EMI/thermal/manufacturing metrics.

`pcb_candidate_ensemble.py` now feeds that selector real bounded Generation-A placement plans under disclosed profiles:

- `balanced`;
- `critical_nets`;
- `noise_aware`;
- `support_compact`;
- unchanged `existing_board` baseline.

Generation B/C facts contribute conservative proxy/uncertainty terms only. No invented autorouter traces or solver facts are introduced.

### Real-DipTrace product acceptance

**Status: pending for stronger whole-board quality claims.**

The synthetic engineering-trap catalog remains useful regression coverage but is not native-DipTrace proof. Real acceptance should use generate -> open -> refill where needed -> DRC/review -> save/reopen/re-export -> compare.

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
- emit deterministic JSON/Markdown;
- surface missing/tampered artifacts and review blockers;
- never grant PASS/provenance/fixture/release trust automatically.

Further automation may aggregate multiple candidate reports into campaign dashboards, but trust promotion must remain a separate reviewed decision.

# Component/Pattern mutation API track

**Status: internal writer proven for its historical scope; stable package-level preview API prepared; public MCP registration intentionally pending.**

`library_mutation_api.py` provides an expected-SHA-bound request/preview layer over the raw-preserving mutation core with semantic delta/fingerprint and explicit mapping errors.

It remains `public_registration=false`. A public write tool must be an explicit product/API decision with public-contract snapshot, policy, documentation and current-candidate real-editor evidence review.

# Cinematic presentation track

**Status: implemented presentation subsystem + bounded whole-manifest preflight; exact-client UI acceptance pending.**

Implemented:

- deterministic timeline/presets and JSONL capture/compile;
- Windows cursor/click/hotkey/text/path replay and dry-run;
- PCB/Schematic UI profiles and affine calibration;
- semantic schematic/PCB replay for supported primitives;
- HWND recording and MP4/GIF helpers;
- `cinematic_preflight.py` deterministic content hash and finite cue/timing/payload/desktop-action budgets;
- mandatory `cinematic_host.play_manifest()` preflight before dry-run or real desktop driver actions.

Still pending real acceptance:

- verified action macros/calibration for the exact editor/version/configuration;
- staged via/layer-transition replay and other unverified editor gestures.

# Headless native GUI track

**Status: Windows isolation primitive and packaged helper implemented; real DipTrace actions remain exact-host evidence.**

`headless_gui.py` creates an isolated Win32 desktop inside the current interactive session, launches a worker and DipTrace there, and performs only bounded automation. It never switches the user's input desktop and has no physical mouse/keyboard fallback. The current native action is open -> Save -> close for PCB/Schematic/Component/Pattern editors.

Source checkouts invoke it with `py -m diptrace_mcp.headless_gui`; Windows packaged builds include `diptrace_mcp_headless_gui.exe` under the helper tools directory. Hosted CI verifies desktop isolation and packaging without claiming licensed DipTrace UI compatibility. See [HEADLESS_GUI.md](HEADLESS_GUI.md).

# Documentation/CI drift protection

**Status: implemented.**

`scripts/check_documentation_state.py` verifies the frozen public-tool count, current EDA module representation, semantic current-state markers, the mandatory cinematic preflight boundary, package-only library mutation registration, completed 12/12 acceptance wording, current selective-reroute claims and the headless source command contract. `tests/test_documentation_state.py` runs the checker through the normal CI test matrix.

Historical dated release/acceptance/audit records remain excluded from current-state freshness assertions.

# Public contracts

- 159 registered MCP tools;
- stable structured error envelope;
- server-owned worker-thread boundary;
- SHA/policy/backup/atomic-write/session-lease/trust/transaction boundaries.

Higher-level EDA modules should continue to prefer typed package internals and a small deliberate public surface.

# Next project sequence

1. Keep the completed schematic cases 01–18 closed unless an impact-based production change requires a focused rerun.
2. Keep the completed 12-gate manual matrix closed unless an impact-based production change requires a focused rerun.
3. Continue PCB whole-board/native quality work when stronger PCB claims are the active product priority.
4. Treat cinematic exact-UI acceptance, headless native-action expansion and any future public library-write API as separate claim/product tracks.

# Phase summary

| Area | Current status |
| --- | --- |
| manual acceptance | all 12 blocking gates PASS across the accepted checkpoints |
| schematic intent/motifs | implemented + builtin heuristic motifs |
| schematic placement | bounded implementation |
| schematic route/joint repair | bounded implementation |
| schematic selective atomic reroute | implemented for affected explicit sheet-local nets |
| schematic product quality | **PASS for initial 18-case real-DipTrace campaign; future work impact/claim-based** |
| PCB Generation A | implemented |
| PCB Generation B | implemented/bounded |
| PCB Generation C | implemented/bounded |
| PCB Generation D | selector + real bounded placement candidate ensemble implemented |
| PCB product quality | stronger current-candidate real-DipTrace acceptance pending |
| DSN/SES analysis | bounded structural/importability analysis implemented |
| XML semantic analysis | fingerprint/delta + property tests implemented |
| evidence reports | deterministic review-only report pipeline implemented |
| library mutation public API | package-level request/preview prepared; public MCP registration pending |
| cinematic | presentation + mandatory preflight implemented; exact UI acceptance pending |
| headless GUI | hidden Win32 desktop helper implemented; real DipTrace native actions remain claim-specific evidence |
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
