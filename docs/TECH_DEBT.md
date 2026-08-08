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

No current roadmap item is blocked on repository-only implementation.

The previously open code-side items now have implementation/tests:

- explicit trust-path regression coverage for stored-plan apply, SES import, schematic-to-PCB sync and live apply fail-closed behavior;
- deterministic synthetic PCB/Schematic/Component Library/Pattern Library/DSN/SES fixture generation and validation;
- raw-preserving native Component/Pattern mutation primitives with explicit collision/replacement policy and pin-to-pad validation;
- deterministic pattern recommendation with hard filters, geometry ranking, append-only derived feedback and held-out metrics;
- additional deterministic DFM/DFA/DFT release-readiness checks;
- manual-only acceptance pack generation and evidence validation.

Native library mutation intentionally remains below the public MCP write-tool boundary until real DipTrace Component/Pattern Editor round-trip evidence exists. That is an evidence gate, not missing writer-core implementation.

## Manual evidence debt

The remaining debt cannot be closed by repository code alone:

- clean Windows 11 install/repair/uninstall observation;
- current real DipTrace PCB and Schematic open/save/re-export acceptance;
- current real Component Library and Pattern Library writer round trips;
- authored-wire and generated-ratline GUI/save/re-export evidence;
- mask/paste/courtyard/`Common` controlled exports;
- Q1 Component Angle GUI/re-export evidence;
- real Codex and Claude Desktop configuration/restart acceptance;
- elevated plug-in install and user-profile preservation;
- custom-state preservation across install/repair/uninstall.

Claim-specific optional evidence remains external legal/Novarm review if required, a real openEMS integration run if solver validation is claimed, and public-redownload smoke when a future release changes published bytes.

Use `scripts/prepare_manual_acceptance.py` to generate the canonical manual-only checklist and to reject unsupported PASS claims without referenced evidence.
