# Technical Debt Register

This register separates maintainability debt from evidence debt so release decisions do not conflate missing code with missing real-system proof.

## Architecture guardrails

The post-0.2.1 maintainability cleanup is complete. The following are continuing constraints, not open refactor tasks:

- keep `diptrace_mcp.server` as a compatibility facade while implementation remains split into input/boundary and runtime modules;
- keep adapter parsing helpers and record/query builders in explicit modules rather than rebuilding `adapters.py` as a monolith;
- keep `DipTraceService` focused on orchestration; stateful store construction belongs to `services.container`;
- coverage floors for high-risk modules are ratchets and must not be lowered merely to make CI pass;
- packaged skill scripts remain generated copies of canonical scripts and must pass the synchronization gate;
- release/version-bearing metadata must agree with `release.json`;
- preserve the published MCP/Facade/error/safety contracts unless a deliberate versioned change is reviewed.

## Repository implementation debt

There is no known generic repository-only roadmap blocker that should be implemented merely to advance the remaining formal acceptance matrix.

The previously open code-side items have implementation/tests, including trust-path coverage, deterministic fixture generation, raw-preserving library mutation, pattern recommendation, DFM/DFA/DFT checks and manual-acceptance tooling.

However, real product validation can still expose focused implementation defects. A reproducible schematic authoring/readability failure found in the next validation campaign becomes a concrete implementation task even though the generic roadmap is otherwise repository-complete.

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

Four blocking formal gates remain:

- `claude_desktop_real_client_restart`;
- `windows_clean_install_repair_uninstall`;
- `elevated_plugin_install_profile_preservation`;
- `custom_state_preservation`.

The formal campaign is intentionally paused before Claude Desktop while core schematic authoring quality is validated more deeply.

Claim-specific optional evidence remains external legal/Novarm review when required, a real openEMS integration run only when solver validation is claimed, and public-redownload smoke when a future release changes published bytes.

## Immediate product-validation debt — schematic authoring/readability

PR #66 added deterministic bounded wire-quality routing for newly authored schematic wires. Automated tests cover component-region avoidance, schematic text avoidance, crossing avoidance, collinear overlap avoidance, Manhattan paths and bounded deterministic search.

That automated coverage and the historical authored-wire round-trip PASS do not prove that the current post-Ponytail system can author a complete schematic that is clean and understandable to a human.

Before resuming the remaining client/Windows lifecycle gates, validate representative small real schematics in DipTrace. At minimum include:

- resistor divider;
- LED + resistor;
- simple RC/divider + capacitor;
- collision-prone placement;
- RefDes/Value/net-label-near-wire cases;
- a small multi-net circuit authored from a clean starting point.

Review both semantics and presentation:

- correct component/pin/net connectivity;
- sensible placement/orientation;
- readable wire geometry;
- no unrelated symbol crossings;
- no unnecessary wire-wire crossings or collinear overlaps;
- no wires covering RefDes, Value or net labels;
- clear junction intent;
- no unreasonable detours/bends;
- native DipTrace save/reopen/re-export preservation;
- whether routine manual cleanup is unnecessary for a normal result.

This is a stronger product-quality validation, not a rewrite of the historical `diptrace_ratline_and_wire_roundtrip` gate. Any failure should get its own focused reproducer and regression test.

## Evidence discipline

Use `scripts/prepare_manual_acceptance.py` for the canonical manual-only matrix. Historical FAIL attempts remain immutable; repairs get fresh retest attempts.

Documentation-only commits after the accepted production candidate do not create production-code drift. If relevant production code changes, explicitly identify the new candidate and rerun only the evidence plausibly affected by that change.
