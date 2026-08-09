# Roadmap and Actual Status

This document separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document, policy and configured adapters allow the feature;
3. **DipTrace verified** — controlled real DipTrace or real-client evidence exists for the exact path.

Implementation never implies universal DipTrace compatibility. Runtime `get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-10

The current source/package version is `0.2.1`. Annotated tag `v0.2.1`, the GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI are already published.

The accepted production-code candidate for the latest manual campaign is:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

That commit includes the post-PR #65/#66 Ponytail pass (PR #68). Later documentation-only commits do not invalidate this production-code identity.

The durable recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md), updated on 2026-08-10. Resume from that checkpoint instead of repeating already accepted gates.

## Completed real-host / real-client acceptance

The following blocking manual gates are complete:

- current PCB open/save/re-export round-trip;
- current schematic open/save/re-export round-trip;
- real Component Library writer `.eli` save/reopen/re-export with semantic preservation and writer idempotence;
- real Pattern Library writer `.lib` save/reopen/re-export with semantic preservation and writer idempotence;
- generated PCB ratlines and authored schematic wires;
- complete MASK / PASTE / COURTYARD / COMMON semantics gate;
- Q1 Component Angle GUI/re-export;
- real Codex Desktop configuration/restart/`get_capabilities`.

This is **8 of 12 blocking manual gates complete**.

### Mask / paste / courtyard / Common

`diptrace_mask_paste_courtyard_common_semantics = PASS` on the accepted production candidate.

- MASK — PASS;
- PASTE — PASS;
- COURTYARD — PASS after the historical parser defect was repaired by PR #65;
- COMMON — PASS, with native Common represented by omission and explicit override represented distinctly without invented numeric defaults.

The historical COURTYARD FAIL remains immutable evidence and is not a restart point.

### Q1 Component Angle

`diptrace_q1_component_angle = PASS` with DipTrace PCB Layout 5.3.0.3.

Observed real-host behavior:

- 90° -> `Angle="1.5708"`;
- 180° -> `Angle="3.1416"`;
- 270° -> `Angle="4.7124"`;
- entered 360° normalizes to GUI 0°, with canonical zero export allowed to omit `Angle`;
- `Change Side` from Top 90° produced Bottom `Angle="4.7124"`, `Flip="Y"` and reader `mirrored=true`;
- coordinates, pattern, connectivity and other non-orientation properties were preserved;
- native open/save/re-export completed without repair/error.

The private/manual campaign PASS is distinct from any future source-controlled public evidence promotion. Do not silently change the public warning/evidence contract without a separate reviewed code change.

### Codex real-client restart

`codex_real_client_restart = PASS` on the same production candidate.

- Codex Desktop: `26.803.5235.0`;
- DipTrace MCP: `0.2.1`;
- 159 tools available after both restarts;
- `get_capabilities` was identical across restarts;
- new process IDs confirmed actual Codex/MCP restart;
- production code remained unchanged.

## Intentional pause in formal acceptance

The next formal gate remains:

`claude_desktop_real_client_restart`

It is **PENDING** and has not been run.

The formal campaign is intentionally paused before that gate. Before spending more time on client/installer lifecycle checks, the project will validate the core product behavior more aggressively: can the current MCP author a normal, readable, useful schematic in real DipTrace?

This pause does not cancel or waive the remaining formal gates.

## Immediate priority — real-world schematic authoring/readability

PR #66 added deterministic bounded readability routing for newly authored schematic wires. Its automated goals include component avoidance, text/label avoidance, crossing and overlap avoidance, Manhattan routing, self-intersection avoidance and fewer unnecessary bends. The subsequent Ponytail pass may have modified adjacent behavior.

The historical `diptrace_ratline_and_wire_roundtrip` PASS remains valid for its original scope. It proves wire connectivity and native round-trip behavior, but it does **not** prove that higher-level current schematic authoring consistently produces a schematic a human would consider clean and usable.

The next validation campaign should therefore build small real circuits from a clean starting point and inspect the actual authored result in DipTrace. Suggested cases:

- resistor divider;
- LED + resistor;
- divider + capacitor / simple RC network;
- a deliberately collision-prone layout;
- RefDes/Value/net-label-near-wire cases;
- at least one small multi-net schematic.

Validate:

- correct components, pins, values and net connectivity;
- sensible component placement and orientation;
- readable wire paths;
- no wires through unrelated symbols;
- no unnecessary crossings or collinear overlaps;
- no wire covering RefDes, Value or net labels;
- obvious junction intent;
- no extreme detours or needless bends;
- native open/save/reopen/re-export preservation;
- whether the schematic is useful without routine manual cleanup.

A reproducible quality problem found here should become a focused regression case and, if necessary, a separate repair. This stronger product-quality validation must not rewrite historical PASS evidence.

## Remaining blocking formal acceptance

When the schematic authoring/readability validation is intentionally finished or paused, resume formal acceptance in this order:

| Order | Gate | Status |
| --- | --- | --- |
| 1 | `claude_desktop_real_client_restart` | **PENDING** |
| 2 | `windows_clean_install_repair_uninstall` | **PENDING** |
| 3 | `elevated_plugin_install_profile_preservation` | **PENDING** |
| 4 | `custom_state_preservation` | **PENDING** |

Generate the exact evidence worksheet with:

```bash
python scripts/prepare_manual_acceptance.py acceptance \
  --version 0.2.1 \
  --commit <exact-40-character-production-commit>
```

After recording observations and evidence files, validate it with:

```bash
python scripts/prepare_manual_acceptance.py acceptance --check
```

The validator must not call the blocking acceptance complete while a required gate remains pending.

## Claim-specific or optional manual work

These are not core blockers unless the corresponding claim is planned:

- public redownload/install smoke after a future release whose bytes change;
- external legal/Novarm review if a planned claim or distribution activity requires it;
- real openEMS execution if external-solver validation is to be claimed.

## Repository implementation status

There is no known repository-only implementation blocker that should be completed merely to advance the formal matrix. Current implementation includes:

- PCB, schematic and library parsing/querying;
- guarded semantic transactions, rollback, SHA/policy/backup/atomic-write boundaries;
- schematic authoring and schematic-to-PCB reconciliation;
- bounded placement/routing, DSN/SES, differential-pair and preliminary SI workflows;
- Windows bridge/installer/portable/configurator build pipelines;
- explicit trust-path regression coverage;
- deterministic synthetic PCB, schematic, Component Library, Pattern Library and DSN/SES fixture generation;
- raw-preserving Component/Pattern Library mutation core;
- deterministic pattern-recommendation baseline;
- bounded DFM/DFA/DFT release-readiness checks;
- manual-acceptance evidence tooling.

If real schematic authoring exposes a product defect, that defect becomes the next focused repository task even though the generic repository roadmap was previously implementation-complete.

## Native library mutation status

The internal raw-preserving Component/Pattern mutation core has real Component Editor and Pattern Editor round-trip evidence.

This does not silently expand the public MCP contract. Public registration of native library write tools remains a separate API/product decision.

## Ratline and authored-wire status

The historical `diptrace_ratline_and_wire_roundtrip` gate is PASS. PCB ratline serialization/collision defects were repaired through PRs #63/#64, and schematic authored-wire connectivity survived native save/reopen/re-export.

PR #66 later added stronger readability routing for newly authored schematic wires. Because that behavior is broader than the historical gate, it now has a separate real-world readability validation priority rather than forcing a rerun of the historical gate.

## Current public contracts

The maintained public baseline remains:

- 159 registered MCP tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations;
- stable structured public error envelope;
- project-owned worker-thread boundary for registered tools;
- exact SHA, policy, backup, atomic-write, session-lease and trust-authority boundaries.

The acceptance campaign does not implicitly add or remove public tools.

## Phase summary

| Phase | Status | Result |
| --- | --- | --- |
| 0–4 | complete | package/contracts, parsing/models, geometry, transactions and semantic writes |
| 5 | bounded complete | deterministic DRC/ERC/review categories with explicit limits |
| 6–10 | complete | silkscreen, placement, routing, DSN/SES, differential-pair/length/preliminary impedance |
| 11 | bounded complete | return-path, BOM, DFM/DFA/DFT, thermal and assembly heuristics |
| 12 | implementation complete | release manifests/adapters; external solver/native manufacturing sign-off remain external |
| 13–19 | complete | skills/CI, scaffolding, schematic authoring, panelisation, ngspice, multi-net routing and sync |
| 20 | repository complete | trust authority/comparison/cancellation plus regression coverage |
| 21 | complete | service-Facade decomposition and parity guardrails |
| 22 | candidate complete | Windows installer/portable/configurator pipeline; clean-machine acceptance remains manual |
| 23 | baseline complete | deterministic pattern recommendation and privacy-bounded feedback/evaluation |
| 24 | host-verified internal core | Component/Pattern mutation core has real editor evidence; public registration is deferred |
| 25 | manual acceptance paused at 8/12 | Through Codex restart PASS; formal resume point is Claude Desktop |
| 26 | validation priority | Real-world schematic authoring/readability on the accepted post-Ponytail production candidate |

## Permanent limitations and non-claims

- Synthetic scaffolds and generated fixture packs are MCP-generated XML, not DipTrace exports.
- Changing `format_version` is not conversion or compatibility evidence.
- The local router is bounded and is not a full push-and-shove/free-angle/global EDA router.
- Copper-pour, return-path, impedance, thermal, DFM/DFA/DFT and manufacturing reviews retain approximation/skip boundaries.
- Generic fabrication/assembly manifests are not native Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off packages.
- The ngspice adapter runs user-provided netlists; it does not generate a complete simulation netlist from a DipTrace design.
- Native manufacturing generation remains unavailable because no verified DipTrace output API is claimed.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review or production readiness.
