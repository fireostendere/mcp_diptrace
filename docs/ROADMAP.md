# Roadmap and Actual Status

This roadmap separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document, policy and configured adapters allow the feature;
3. **DipTrace verified** — controlled real DipTrace/client evidence exists for the exact path and candidate.

Implementation never implies universal DipTrace compatibility. Runtime `get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-11

The source/package version is `0.2.1`. Annotated tag `v0.2.1`, the GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI are published.

The latest accepted manual-production checkpoint remains:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

That identity is preserved because manual evidence is commit-bound. Later development on `main` — schematic intelligence, 90% aggregate coverage, PCB Generations A-D and cinematic replay — is implemented/tested repository work but does not silently inherit the earlier real-host/client evidence.

The durable manual recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md), updated on 2026-08-10.

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

The canonical matrix therefore has **8 of 12 blocking manual gates PASS**.

`claude_desktop_real_client_restart` is **WAIVED for the current project campaign**. It was not run and is not PASS. The repository validator intentionally remains stricter and may continue to report the canonical matrix incomplete.

When formal lifecycle acceptance resumes, the next project-required gate is:

`windows_clean_install_repair_uninstall`

followed by:

1. `elevated_plugin_install_profile_preservation`;
2. `custom_state_preservation`.

## Product-development priority

Formal lifecycle acceptance is intentionally paused while the project improves the core engineering product: useful schematic layout and explainable PCB design decisions under the existing trust/write boundaries.

The shared optimization pattern is:

```text
observed project facts + explicit constraints + optional reference intent
                              |
                              v
                       bounded candidates
                              |
                              v
                    measure / score / explain
                              |
                       bounded feedback
                              |
                              v
          guarded semantic plan -> preview -> apply -> review
```

Unknown current, edge rate, impedance, authoritative stackup, manufacturing capability and similar physical facts remain explicit unknowns rather than guessed constants.

# Schematic track

Detailed implementation documentation: [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## Phase 26 — real-world readability baseline

**Status: active product checkpoint.**

The repository has deterministic authored-wire quality handling, but the product-level question remains whether complete real schematics become materially easier to read without routine cleanup.

Representative acceptance cases should cover small RC/divider/LED circuits, regulator support networks, MCU power/decoupling, collision-prone layouts and at least one multi-block schematic. Measure connectivity/ERC preservation, symbol/text/wire collisions, crossings, overlaps, bends, detour, block cohesion, compactness, signal flow and native open/save/re-export behavior.

## Phase 27 — design intent and reference motifs

**Status: foundation implemented.**

`schematic_layout.py` now provides deterministic design intent, coarse part/net roles, functional blocks and provenance-bearing reference motifs (`datasheet`, `reference_design`, `project`, `builtin`) expressed as relative presentation constraints rather than copied absolute coordinates.

Still pending: automated datasheet/reference-design ingestion. The engine intentionally works without online retrieval.

## Phase 28 — schematic placement engine v2

**Status: bounded implementation.**

Implemented:

- hierarchical block/anchor/support placement;
- configurable grid and bounded row packing;
- locked-part preservation;
- multiple deterministic candidates with bounded search;
- first-stage readability/interconnect/movement scoring;
- ordinary `MoveComponentsOperation` output through the existing semantic path.

Still pending: fully validated automatic rotation/pin-facing decisions for real DipTrace rotation semantics and broader motif-driven candidate generation.

## Phase 29 — human-readable interconnect planning

**Status: bounded implementation.**

Implemented:

- non-mutating route-candidate evaluation;
- obstacle/crossing/overlap/self-intersection/diagonal/bend/length/detour metrics;
- explicit placement feedback for pathological routes;
- conservative Design Cache pin-geometry resolution;
- configurable ground/power routing policy for joint scoring.

Still pending: stronger sheet-level congestion scheduling, global same-net junction optimisation and automatic label/bus strategy.

## Phase 30 — joint schematic layout optimizer

**Status: partial implementation.**

Implemented:

- pin-aware route scoring for hypothetical placement candidates;
- deterministic bounded edge budgets;
- joint lexicographic ranking of placement plus route quality;
- bounded route-feedback-driven placement repair;
- rigid block moves where appropriate, local same-block repair where appropriate;
- strict candidate/translation bounds and source-document immutability.

Still pending:

- selective reroute of only affected existing nets;
- one atomic guarded plan combining selected placement moves and wire replacement;
- fuller iterative generate -> score -> repair -> reroute loop with objective history/stopping criteria.

## Phase 31 — schematic quality gate

**Status: pending product-level acceptance.**

Close only when representative ugly-but-electrically-correct schematics are reliably improved without routine manual cleanup and without connectivity/ERC regression, with controlled real-DipTrace open/save/re-export evidence for the affected primitives.

# PCB track — Generations A-D

Detailed implementation documentation: [PCB_DESIGN_ENGINE.md](PCB_DESIGN_ENGINE.md).

## Generation A — electronics intent and placement

### Phase 32 — design intent / net intelligence

**Status: complete internal implementation (PR #81).**

`pcb_design_intent.py` provides component roles, functional blocks, multi-role net classification, criticality/noise intent, explicit physical constraints and conservative power/ground topology intent. Naming heuristics may classify intent but do not invent physical numbers.

### Phase 33 — intent-aware placement v2

**Status: complete internal implementation (PR #81).**

`pcb_placement.py` builds bounded deterministic board candidates above the existing low-level legality/geometry engine. It preserves locked/mechanically anchored components and scores functional cohesion, support adjacency, critical connection distance and intent-level aggressor/victim proximity separately.

## Generation B — physical context

### Phase 34 — stackup / PDN / return path / vias

**Status: complete bounded implementation (PR #83).**

`pcb_physical.py` reuses exported stackup/reference data, conservative PDN source/load/decoupling analysis, hot-loop candidates, return-path analysis and semantic via roles. Unknown current/current density/voltage drop/via capacity remain unknown.

### Phase 35 — noise compatibility and physical refinement

**Status: bounded complete (PR #83).**

Timing-gated aggressor/victim analysis uses explicit edge-rate/frequency evidence plus normalized geometry/reference context. It is risk triage, not EMC/PI sign-off.

## Generation C — intentional routing

### Phase 36 — routing policy compiler

**Status: complete internal implementation (PR #84).**

`pcb_routing_policy.py` compiles intent into deterministic routing priority/order and explicit spacing, preferred/forbidden layers, via budgets/penalties, impedance/tolerance, max length/skew, reference, stub and shielding preferences.

### Phase 37 — SI-aware route observation / copper strategy / feedback

**Status: bounded complete (PR #84).**

The layer evaluates supplied route observations for length, vias, forbidden layers, reference continuity, impedance, skew and stubs; reports parallel exposure without inventing a universal crosstalk threshold; preserves copper topology intent; and can emit bounded endpoint-placement feedback.

Native routing and poured-copper edits remain in the guarded semantic path. Authoritative refill geometry is still a real-host boundary.

## Generation D — whole-board selection

### Phase 38 — joint multi-objective optimizer

**Status: complete internal implementation (PR #86).**

`pcb_joint_optimizer.py` applies lexicographically dominant hard safety/mechanical/connectivity/DRC/reference/manufacturing dimensions over decomposed soft placement/routing/via/SI/PI/return-path/EMI-risk/thermal-risk/manufacturing metrics. It selects candidates; it does not apply edits directly.

### Phase 39 — benchmark and real-DipTrace product acceptance

**Status: synthetic benchmark catalog complete; real-DipTrace product acceptance pending.**

The catalog covers MCU/decoupling/crystal, regulators, mixed signal, precision current sense, high-speed differential, Ethernet/CAN, RF, high-current power and multilayer controlled-impedance traps. These cases are regression fixtures, not native-DipTrace proof.

Real acceptance must use the affected generate -> open -> refill where required -> DRC/review -> save -> reopen -> re-export -> compare path.

# Cinematic presentation track

**Status: implemented on `main`; real-client calibration/acceptance pending.**

The cinematic subsystem is not a new engineering authority. It converts already-planned semantic actions/placement proposals/route vertices into deterministic visible playback for demos/video/GIF capture.

Implemented:

- deterministic timeline/pacing presets;
- generic JSONL workflow capture and deterministic manifest compilation;
- Windows cursor/click/hotkey/text/path replay plus dry-run;
- PCB/Schematic version-specific UI profiles;
- affine design-coordinate -> normalized-client-coordinate calibration with residual checks;
- semantic Schematic part/wire and PCB placement/same-layer trace replay;
- HWND-targeted ffmpeg recording and MP4/GIF command generation.

Pending real acceptance:

- verified UI action macros for the exact DipTrace 5.3 editor configuration used for recording;
- end-to-end calibration against a real document;
- explicit staged playback for via/layer transitions and other not-yet-verified UI gestures.

See [CINEMATIC_DEMO_MODE.md](CINEMATIC_DEMO_MODE.md).

# Current public contracts

- 159 MCP tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations;
- stable structured error envelope;
- server-owned worker-thread boundary;
- SHA/policy/backup/atomic-write/session-lease/trust/transaction boundaries.

Internal EDA development should continue to prefer typed modules/services and a small deliberate public surface rather than one MCP tool per heuristic.

# Phase summary

| Phase | Current status |
| --- | --- |
| 0–24 | repository implementation complete/bounded as documented in specialist docs; native/real-host claims remain evidence-scoped |
| 25 | manual acceptance paused at 8 canonical PASS gates; Claude restart WAIVED; Windows lifecycle next |
| 26 | active schematic product-quality checkpoint |
| 27 | schematic intent/motif foundation implemented |
| 28 | bounded schematic placement v2 implemented |
| 29 | bounded schematic wire planning + pin geometry implemented |
| 30 | joint scoring + bounded placement repair partially implemented; selective reroute transaction pending |
| 31 | schematic product-level real-DipTrace quality acceptance pending |
| 32–33 | PCB Generation A complete internal implementation |
| 34–35 | PCB Generation B complete/bounded internal implementation |
| 36–37 | PCB Generation C complete/bounded internal implementation |
| 38 | PCB Generation D joint selector complete internal implementation |
| 39 | Generation D synthetic benchmark complete; real-DipTrace product acceptance pending |
| cinematic | deterministic presentation subsystem implemented; real UI calibration/action acceptance pending |

# Permanent limitations and non-claims

- Synthetic fixtures and benchmark catalogs are not DipTrace exports unless explicitly recorded as such.
- Changing `format_version` is not conversion or compatibility evidence.
- Reference motifs are provenance-bearing guidance, not manufacturer approval.
- The local router is bounded, not a full push-and-shove/free-angle/global EDA router.
- PCB analytic layers do not become field-solver, PI, thermal or EMC proof.
- Native manufacturing generation is unavailable.
- The ngspice adapter runs provided netlists; it is not a complete schematic-to-SPICE compiler.
- Cinematic replay is presentation automation, not proof that DipTrace semantically accepted an edit.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review, production readiness, direct Claude Desktop validation or globally optimal schematic/PCB layout.
