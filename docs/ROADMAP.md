# Roadmap and Actual Status

This document separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document, policy and configured adapters allow the feature;
3. **DipTrace verified** — a controlled real DipTrace open/save/re-export or live host experiment exists for the exact path.

Implementation never implies universal DipTrace compatibility. Runtime `get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-09

The current source/package version is `0.2.1`. Annotated tag `v0.2.1`, the GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI are already published. The post-release architecture cleanup and the repository-only roadmap closure are merged on `main`.

The manual acceptance campaign has now moved substantially beyond the 2026-08-08 checkpoint. The durable recovery record is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md). If a later gate fails or a Work session is interrupted, resume from that checkpoint rather than restarting already accepted gates.

Completed real-host acceptance now includes:

- current PCB open/save/re-export round-trip;
- current schematic open/save/re-export round-trip;
- real Component Library writer `.eli` save/reopen/re-export with semantic preservation and writer idempotence;
- real Pattern Library writer `.lib` save/reopen/re-export with semantic preservation and writer idempotence;
- the full ratline/authored-wire gate: PCB generated ratlines and schematic authored wires;
- MASK semantics;
- PASTE semantics.

The first unfinished semantic gate is now **COURTYARD**. Real DipTrace 5.3.0.3 preserved the one-setting-at-a-time Courtyard change correctly, but `main@4ddea7937661afedf9c195af558680c4705bb368` did not expose `Source/Board/Settings/LineWidth/Courtyard` through the MCP semantic read surfaces. PR #65 adds the targeted typed project-setting read path without adding MCP tools or changing public service signatures. The code-only PR head `936fdf3d5c8378f5f42214813620eab95f3755ca` completed green CI, Windows-installer and PyPI workflow checks before the documentation checkpoint commits.

After PR #65 merges, rerun **COURTYARD only** from a fresh evidence attempt. MASK and PASTE remain PASS and must not be repeated without a specific regression reason. If COURTYARD passes, continue with **COMMON**.

All repository work that can be completed without a real external GUI/host remains implemented on the current development line:

- PCB, schematic and library parsing/querying;
- guarded semantic transactions, rollback, SHA/policy/backup/atomic-write boundaries;
- schematic authoring and schematic-to-PCB reconciliation;
- bounded placement/routing, DSN/SES, differential-pair and preliminary SI workflows;
- Windows bridge/installer/portable/configurator build pipelines;
- explicit trust-path regression coverage for stored-plan apply, SES import, schematic-to-PCB sync and live-session apply;
- deterministic synthetic PCB, schematic, Component Library, Pattern Library and DSN/SES fixture-pack generation with explicit non-claims;
- raw-preserving Component/Pattern Library mutation core with explicit collision/replacement policy, unknown-XML preservation, component/part/pin/field/pattern writes and pin-to-pad validation;
- deterministic human-guided pattern-recommendation baseline with hard compatibility filters, geometry ranking, append-only derived feedback records and held-out top-1/top-3/rejection metrics;
- additional deterministic DFM/DFA/DFT release-readiness checks while preserving explicit manufacturing/sign-off limitations;
- a manual-acceptance evidence harness whose matrix contains only tasks that require a real external system, GUI observation, clean-machine state or human/legal judgement.

The public MCP surface remains unchanged. Real Component Editor and Pattern Editor round-trip evidence now exists for the internal library mutation core, so the previous host-evidence prerequisite has been satisfied. Public registration of native library write tools is nevertheless a separate product/API decision and is not performed implicitly by this acceptance campaign.

## What remains

There is no remaining repository-only development blocker in the current roadmap. The remaining gates require human observation or external systems, except for focused repairs triggered by a genuine manual-acceptance failure.

### Blocking manual acceptance — current order

| Order | Gate | Status | Resume rule |
| --- | --- | --- | --- |
| 1 | `diptrace_mask_paste_courtyard_common_semantics / COURTYARD` | **RETEST REQUIRED after PR #65** | Preserve the historical FAIL; create a fresh targeted attempt after merge. |
| 2 | `diptrace_mask_paste_courtyard_common_semantics / COMMON` | **NOT RUN** | Start only after COURTYARD passes. |
| 3 | Q1 Component Angle GUI/re-export | **NOT RUN** | Run after the mask/paste/courtyard/Common semantic sequence completes. |
| 4 | Real Codex configuration/restart/`get_capabilities` | **PENDING** | Use the applicable server build and record restart plus capability evidence. |
| 5 | Real Claude Desktop configuration/restart/`get_capabilities` | **PENDING** | Same evidence standard as Codex. |
| 6 | Clean Windows install / repair / uninstall | **PENDING** | Use the applicable release bytes; this is a real-machine gate. |
| 7 | Elevated plug-in installation with original profile preservation | **PENDING** | Preserve the original user profile. |
| 8 | Pre-existing custom-state preservation | **PENDING** | Verify install/repair/uninstall does not destroy existing state. |

The following gates are already complete and are not restart points: current PCB round-trip, current schematic round-trip, Component Library writer, Pattern Library writer, generated PCB ratlines, authored schematic wires, MASK and PASTE.

Generate the exact evidence worksheet with:

```bash
python scripts/prepare_manual_acceptance.py acceptance \
  --version 0.2.1 \
  --commit <exact-40-character-commit>
```

After recording observations and evidence files, validate it with:

```bash
python scripts/prepare_manual_acceptance.py acceptance --check
```

The validator refuses to call the blocking acceptance complete while a required manual gate is pending or a claimed PASS lacks referenced evidence.

### Claim-specific or optional manual work

These are not core repository blockers:

- public redownload/install smoke after a future release whose bytes change;
- external legal/Novarm review if a planned claim or distribution activity requires it;
- real openEMS execution if optional external-solver validation is to be claimed.

## Compatibility and trust status

Repository regression coverage exercises the previously untested write families:

- generic stored-plan apply;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply` fail-closed trust behavior.

Stored plans, SES import and schematic-to-PCB synchronization all converge on the guarded semantic transaction commit, which invalidates prior document trust after a successful write. Live apply is SHA-bound to the exact working bytes; replacement of the exchange document cannot retain stale SHA-bound provenance.

The synthetic fixture pack closes CI/parser/writer infrastructure gaps but deliberately carries `synthetic_parser_only` provenance and explicit non-claims for `diptrace_exported`, open/save verification and round-trip verification. Real host acceptance evidence is tracked separately from synthetic fixtures and is summarized in the manual checkpoint document.

## Native library mutation status

Implementation is complete below the public MCP registration boundary:

- create/update patterns;
- create/update components and parts;
- create/update pins, fields and basic graphics;
- attach existing patterns to components;
- explicit pin-to-pad mapping validation;
- explicit `error` / `keep` / `update` collision behavior;
- explicit known-collection replacement flags;
- raw-preserving mutation through `RawTreeSnapshot`, preserving unrelated unknown XML;
- deterministic/idempotence regression tests.

Real editor acceptance is also complete:

- Component Library writer: **PASS** with native `.eli` save/reopen/re-export and second-pass idempotence;
- Pattern Library writer: **PASS** with native `.lib` save/reopen/re-export and second-pass idempotence.

The previous “host evidence missing” blocker is therefore closed. The public 159-tool contract still intentionally does not gain native library write tools in this campaign. Any future public registration requires an explicit API/product decision, documentation and contract review rather than being inferred from the acceptance PASS.

## Ratline and authored-wire status

The combined `diptrace_ratline_and_wire_roundtrip` gate is **PASS** on `main@4ddea7937661afedf9c195af558680c4705bb368`.

PCB Part A originally exposed two real-host issues: missing native-visible ratline serialization and then an avoidable ratline-to-unrelated-pad collision. PR #63 added coherent native ratline serialization; PR #64 added deterministic geometry-aware orientation selection. The final real DipTrace 5.3 retest passed.

Schematic Part B also passed: authored `WIRE_TEST` connectivity and wire endpoint/topology semantics survived native `.dch` save/reopen and final XML re-export. These failures and repairs are historical evidence, not pending work.

## Pattern recommendation status

The non-ML baseline is implemented:

1. deterministic package feature extraction;
2. hard compatibility filters;
3. geometry-distance ranking;
4. deterministic tie-breaking;
5. held-out top-1/top-3 and forbidden-pattern rejection metrics;
6. append-only human accept/reject/correction records containing derived identifiers/hashes rather than project XML or datasheets.

Optional future ML/fine-tuning is product exploration, not a blocker. It must not replace the deterministic baseline or privacy boundary.

## Review / DFM / DFA / DFT status

The registered review system remains deliberately bounded. A deterministic release-readiness supplement additionally checks facts that can be derived from exported XML, including duplicate reference designators, explicit footprint assignment, component values/procurement identity, embedded pattern availability, 3D-model references and explicit testpoint coverage.

Physical thermal performance, probe accessibility, fabrication process limits, assembly sign-off and native manufacturing outputs cannot be proven by repository code alone and therefore remain explicit manual/external boundaries rather than fake automated checks.

## Current public contracts

The following published baselines are intentionally preserved by this development work:

- 159 registered MCP tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations;
- stable structured public error envelope;
- project-owned worker-thread boundary for registered tools;
- exact SHA, policy, backup, atomic-write, session-lease and trust-authority boundaries;
- package-owned trust authority separated from user-controlled evidence.

PR #65 changes existing PCB read results only; it does not add tools or service methods. Native library host verification likewise does not silently expand the public MCP surface.

## Phase summary

| Phase | Status | Result |
| --- | --- | --- |
| 0–4 | complete | package/contracts, parsing/models, geometry, transactions and existing semantic writes |
| 5 | bounded complete | deterministic DRC/ERC/review categories with explicit skipped/approximate boundaries |
| 6–10 | complete | silkscreen, placement, routing, DSN/SES, differential-pair/length/preliminary impedance |
| 11 | bounded complete | return-path, BOM, DFM/DFA/DFT, thermal and assembly heuristics plus release-readiness supplement |
| 12 | implementation complete | release manifests/adapters; real external solver and native manufacturing sign-off remain external |
| 13–19 | complete | skills/CI, scaffolding, schematic authoring, panelisation, ngspice, multi-net routing and sync |
| 20 | repository complete | trust authority/comparison/cancellation plus regression coverage; remaining external acceptance is tracked explicitly |
| 21 | complete | service-Facade decomposition and parity guardrails |
| 22 | candidate complete | Windows installer/portable/configurator pipeline; clean-machine acceptance is manual |
| 23 | baseline complete | deterministic pattern recommendation and privacy-bounded feedback/evaluation |
| 24 | host-verified internal core | raw-preserving Component/Pattern mutation core has real Component/Pattern Editor round-trip evidence; public write registration is a separate deferred API decision |
| 25 | manual acceptance in progress | PCB, schematic, both library writers, ratline/wire, MASK and PASTE are complete; COURTYARD targeted retest is next, then COMMON and remaining client/Windows gates |

## Permanent limitations and non-claims

- Synthetic scaffolds and generated fixture packs are MCP-generated XML, not DipTrace exports.
- Changing `format_version` is not conversion or compatibility evidence.
- The local router is bounded and is not a full push-and-shove/free-angle/global EDA router.
- Copper-pour, return-path, impedance, thermal, DFM/DFA/DFT and manufacturing reviews retain explicit approximation/skip boundaries.
- Generic fabrication/assembly manifests are not native Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off packages.
- The ngspice adapter runs user-provided netlists; it does not generate a complete simulation netlist from a DipTrace design.
- Native manufacturing generation remains unavailable because no verified DipTrace output API is claimed.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review or production readiness.
