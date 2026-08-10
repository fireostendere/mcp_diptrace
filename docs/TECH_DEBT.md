# Technical Debt Register

This register separates maintainability debt from evidence debt so release decisions do not conflate missing code with missing real-system proof.

## Architecture guardrails

The post-0.2.1 maintainability cleanup is complete. The following are continuing constraints, not open refactor tasks:

- keep `diptrace_mcp.server` as a compatibility facade while implementation remains split into input/boundary and runtime modules;
- keep adapter parsing helpers and record/query builders in explicit modules rather than rebuilding `adapters.py` as a monolith;
- keep `DipTraceService` focused on orchestration; stateful store construction belongs to `services.container`;
- keep intelligent schematic/PCB decision logic behind the MCP/application boundary rather than adding one public tool per heuristic;
- keep normalized XML facts separate from inferred engineering intent and operator-supplied constraints;
- require intelligent EDA modules to emit typed semantic operations and reuse the existing preview/SHA/transaction/review path instead of writing XML directly;
- keep unknown physical/electrical facts unknown rather than filling missing current, edge-rate, impedance, stackup or thermal data with invented defaults;
- coverage floors for high-risk modules are ratchets and must not be lowered merely to make CI pass;
- packaged skill scripts remain generated copies of canonical scripts and must pass the synchronization gate;
- release/version-bearing metadata must agree with `release.json`;
- preserve the published MCP/Facade/error/safety contracts unless a deliberate versioned change is reviewed.

## Repository implementation debt

There is no known generic repository-only blocker that should be implemented merely to advance the remaining formal acceptance matrix.

The previously open code-side items have implementation/tests, including trust-path coverage, deterministic fixture generation, raw-preserving library mutation, pattern recommendation, DFM/DFA/DFT checks and manual-acceptance tooling.

The intelligent design roadmap intentionally creates new product work rather than generic cleanup. PCB Generation A now provides the internal design-intent/net-intelligence layer and intent-aware placement v2. Its documented limitations — pad-level current loops, stackup/reference structure, PDN, crosstalk/field behavior, via roles, copper planning, thermal modeling and joint placement/routing optimization — are scoped Generation B-D work, not hidden defects in Generation A.

Real product validation can still expose focused implementation defects. A reproducible schematic or PCB design-quality failure becomes a concrete implementation task even when the corresponding architectural phase is otherwise repository-complete.

## Completed manual evidence

The current development-line campaign has accepted the following blocking gates:

- current real DipTrace PCB open/save/re-export;
- current real DipTrace Schematic open/save/re-export;
- Component Library writer round-trip;
- Pattern Library writer round-trip;
- authored schematic wires and generated PCB ratlines;
- complete mask/paste/courtyard/`Common` semantics;
- Q1 Component Angle GUI/re-export;
- real Codex Desktop configuration/restart/`get_capabilities`.

The accepted production-code identity through those gates is
`0bb09b4b3af40a5a3d1a875fab885430a2d251ba`.

## Remaining formal manual evidence debt

The project has explicitly waived `claude_desktop_real_client_restart` for the current campaign. This is not PASS evidence: Claude Desktop was not independently configured/restarted, and no Claude-specific runtime evidence exists. The waiver is a project-level risk acceptance based on successful real Codex stdio MCP restart evidence and does not change the conservative canonical manual-acceptance validator.

Three project-required lifecycle gates remain:

- `windows_clean_install_repair_uninstall`;
- `elevated_plugin_install_profile_preservation`;
- `custom_state_preservation`.

The formal lifecycle campaign is intentionally paused before those Windows/profile gates while core schematic/PCB design quality is developed and validated more deeply.

Claim-specific optional evidence remains external legal/Novarm review when required, a real openEMS integration run only when solver validation is claimed, and public-redownload smoke when a future release changes published bytes.

## Immediate product-validation debt — schematic authoring/readability

PR #66 added deterministic bounded wire-quality routing for newly authored schematic wires. Automated tests cover component-region avoidance, schematic text avoidance, crossing avoidance, collinear overlap avoidance, Manhattan paths and bounded deterministic search.

That automated coverage and the historical authored-wire round-trip PASS do not prove that the current system can author a complete schematic that is clean and understandable to a human.

Before promoting schematic readability claims, validate representative small real schematics in DipTrace. At minimum include:

- resistor divider;
- LED + resistor;
- simple RC/divider + capacitor;
- collision-prone placement;
- RefDes/Value/net-label-near-wire cases;
- a small multi-net circuit authored from a clean starting point.

Review both semantics and presentation: connectivity, placement/orientation, wire geometry, crossings/overlaps, text collisions, junction intent, detours/bends, native save/reopen/re-export and whether routine cleanup is unnecessary.

This is a stronger product-quality validation, not a rewrite of the historical `diptrace_ratline_and_wire_roundtrip` gate. Any failure should get its own focused reproducer and regression test.

## PCB Generation A evidence boundary

Generation A repository tests can prove deterministic intent classification, explicit-unknown handling, conservative power/ground policy, decomposed placement scoring and placement hard-geometry non-regression. They do **not** create real-DipTrace or electrical-performance evidence.

Before later generations promote claims about actual copper/current behavior, controlled evidence must cover the affected native representations. In particular:

- ground/power strategy is intent only; it does not prove a plane, pour or star topology is electrically optimal;
- copper-pour boundaries are not authoritative refill/island/thermal-relief geometry;
- noise separation is a placement-risk proxy, not crosstalk or EMC simulation;
- thermal roles are metadata/placement intent, not heat-flow analysis;
- analytic impedance helpers remain bounded estimates rather than fabrication-controlled impedance certification;
- Generation A does not require new real-DipTrace evidence because it introduces no new public mutation primitive and emits the already-guarded semantic move operation.

Generation B-D acceptance must add targeted real-DipTrace fixtures before authoritative plane/pour/via or product-level PCB claims are promoted.

## Evidence discipline

Use `scripts/prepare_manual_acceptance.py` for the canonical manual-only matrix. Historical FAIL attempts remain immutable; repairs get fresh retest attempts.

A project-level waiver must not be rewritten as PASS merely to satisfy the canonical matrix. The validator may continue to report incomplete while Claude remains unrun; that is an explicit known difference between the canonical matrix and the current project campaign.

Documentation-only commits after an accepted production candidate do not create production-code drift. If relevant production code changes, explicitly identify the new candidate and rerun only the evidence plausibly affected by that change.
