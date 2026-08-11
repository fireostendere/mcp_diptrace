# Roadmap and Actual Status

This roadmap separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document/policy/configuration permits the feature;
3. **DipTrace verified** — controlled real DipTrace/client evidence exists for the exact path and candidate.

Implementation never implies universal DipTrace compatibility. Historical evidence stays bound to the production identity that was actually tested.

## Current checkpoint — 2026-08-11

Source/package version remains `0.2.1`. The immutable `v0.2.1` release and PyPI package are published; post-release development is tracked separately.

The latest accepted manual-production checkpoint remains:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

The durable recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md). Completed real-host/client PASS evidence is not silently transferred to later code.

Current cross-domain implementation detail is in [EDA_INTELLIGENCE.md](EDA_INTELLIGENCE.md).

## Completed manual gates on the accepted checkpoint

PASS:

- PCB open/save/re-export round-trip;
- schematic open/save/re-export round-trip;
- Component Library writer save/reopen/re-export;
- Pattern Library writer save/reopen/re-export;
- generated PCB ratlines and authored schematic wires;
- MASK / PASTE / COURTYARD / COMMON semantics;
- Q1 Component Angle GUI/re-export;
- real Codex Desktop restart/configuration/`get_capabilities`.

The canonical matrix therefore has 8 of 12 blocking manual gates PASS.

`claude_desktop_real_client_restart` is **WAIVED for the current project campaign**, not PASS.

When lifecycle acceptance resumes, the project-required sequence remains:

1. `windows_clean_install_repair_uninstall`;
2. `elevated_plugin_install_profile_preservation`;
3. `custom_state_preservation`.

# Schematic track

Detailed implementation: [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## Phase 26 — real-world readability baseline

**Status: active product checkpoint.**

Repository functionality is substantially stronger than the historical wire-only acceptance. The remaining question is product quality in real DipTrace: whether complete generated/repaired schematics become materially easier to read without routine manual cleanup.

The real-host validation document remains `SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md`.

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
- no rewriting of unaffected explicit wire geometry;
- no automatic page-spanning explicit wiring of previously unwired nets by default.

Current limitation: affected explicit nets are rebuilt from resolved pin endpoints through deterministic MST edges; arbitrary hand-authored junction topology is not preserved as a visual constraint.

Next refinement: optional intentional-junction preservation and bounded iterative generate -> score -> repair -> reroute convergence with objective history/stopping criteria.

## Phase 31 — schematic quality gate

**Status: pending product-level real-DipTrace acceptance.**

Close only when representative ugly-but-electrically-correct schematics are reliably improved without connectivity/ERC regression and without routine manual cleanup, with controlled real-host open/save/re-export evidence for the affected primitives.

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
- `cinematic_preflight.py` deterministic content hash and finite cue/timing/payload/desktop-action budgets.

Still pending real acceptance:

- verified action macros/calibration for the exact editor/version/configuration;
- staged via/layer-transition replay and other unverified editor gestures.

# Documentation/CI drift protection

**Status: in this development pass.**

Evergreen implementation documentation must name current internal architecture rather than inheriting historical snapshots. CI should verify version/tool-count invariants and require the current EDA modules to remain represented in maintained docs. Historical dated release/acceptance/audit records remain excluded from this freshness rule.

# Public contracts

- 159 registered MCP tools;
- stable structured error envelope;
- server-owned worker-thread boundary;
- SHA/policy/backup/atomic-write/session-lease/trust/transaction boundaries.

Higher-level EDA modules should continue to prefer typed package internals and a small deliberate public surface.

# Phase summary

| Area | Current status |
| --- | --- |
| manual acceptance | 8 canonical PASS gates on accepted historical checkpoint; Claude WAIVED; Windows lifecycle next |
| schematic intent/motifs | implemented + builtin heuristic motifs |
| schematic placement | bounded implementation |
| schematic route/joint repair | bounded implementation |
| schematic selective atomic reroute | implemented for affected explicit sheet-local nets |
| schematic product quality | real-DipTrace acceptance pending |
| PCB Generation A | implemented |
| PCB Generation B | implemented/bounded |
| PCB Generation C | implemented/bounded |
| PCB Generation D | selector + real bounded placement candidate ensemble implemented |
| PCB product quality | stronger current-candidate real-DipTrace acceptance pending |
| DSN/SES analysis | bounded structural/importability analysis implemented |
| XML semantic analysis | fingerprint/delta + property tests implemented |
| evidence reports | deterministic review-only report pipeline implemented |
| library mutation public API | package-level request/preview prepared; public MCP registration pending |
| cinematic | presentation + preflight implemented; exact UI acceptance pending |

# Permanent limitations / non-claims

- Synthetic fixtures and benchmark catalogs are not DipTrace exports unless explicitly recorded as such.
- Changing `format_version` is not conversion evidence.
- Builtin motifs are labelled heuristics, not manufacturer/reference-design approval.
- Local routing/placement search is bounded, not a globally optimal EDA solver.
- PCB analytic layers are not field-solver, PI, thermal or EMC proof.
- Native manufacturing generation is unavailable.
- Cinematic replay is presentation automation, not engineering acceptance evidence.
- Evidence reports do not grant trust/PASS.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review, production readiness, direct Claude Desktop validation or globally optimal schematic/PCB layout.
