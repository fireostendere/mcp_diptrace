# Roadmap and Actual Status

This document separates three states:

1. **implemented** — production code and repository tests exist;
2. **runtime available** — the active document, policy and configured adapters allow the feature;
3. **DipTrace verified** — a controlled real DipTrace open/save/re-export or live host experiment exists for the exact path.

Implementation never implies universal DipTrace compatibility. Runtime `get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-08

The current source/package version is `0.2.1`. Annotated tag `v0.2.1`, the GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI are already published. The post-release architecture cleanup is merged on `main`.

All repository work that can be completed without a real external GUI/host has now been implemented on the current development line:

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

The public MCP surface remains unchanged while unverified native library writers stay below the public tool boundary. They must not be registered as production MCP write tools until real DipTrace library round-trip evidence exists.

## What remains

There is no remaining repository-only development blocker in the current roadmap. The remaining gates require human observation or external systems.

### Blocking manual acceptance

1. **Clean Windows 11 install / repair / uninstall** using the exact release bytes.
2. **Current real DipTrace PCB round-trip**: open, inspect, save and re-export representative MCP-modified PCB XML.
3. **Current real DipTrace Schematic round-trip** including authored wires.
4. **Current real Component Library writer round-trip** including parts, pins, fields, pattern attachment and explicit pin-to-pad mapping.
5. **Current real Pattern Library writer round-trip** including pads and graphics.
6. **Generated ratline and authored-wire GUI verification** followed by save/re-export comparison.
7. **Mask, paste, courtyard and `Common` semantics** using one-setting-at-a-time real DipTrace exports.
8. **Q1 Component Angle GUI/re-export validation**, which remains `NOT_RUN` until performed in DipTrace.
9. **Real Codex configuration/restart/get_capabilities** using the release server.
10. **Real Claude Desktop configuration/restart/get_capabilities** using the release server.
11. **Elevated plug-in installation with original user-profile preservation**.
12. **Pre-existing custom-state preservation** across install/repair/uninstall.

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

Repository regression coverage now exercises the previously untested write families:

- generic stored-plan apply;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply` fail-closed trust behavior.

Stored plans, SES import and schematic-to-PCB synchronization all converge on the guarded semantic transaction commit, which invalidates prior document trust after a successful write. Live apply is SHA-bound to the exact working bytes; replacement of the exchange document cannot retain stale SHA-bound provenance.

This closes the **repository-test gap**, not the **DipTrace-host evidence gap**. Real host acceptance remains manual and is listed above.

The synthetic fixture pack closes CI/parser/writer infrastructure gaps but deliberately carries `synthetic_parser_only` provenance and explicit non-claims for `diptrace_exported`, open/save verification and round-trip verification.

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

The only remaining gate is real Component Editor / Pattern Editor open-save-re-export evidence. Public native library write tools remain intentionally unregistered until that evidence exists.

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

New unverified library mutation and recommendation code does not silently expand the MCP surface.

## Phase summary

| Phase | Status | Result |
| --- | --- | --- |
| 0–4 | complete | package/contracts, parsing/models, geometry, transactions and existing semantic writes |
| 5 | bounded complete | deterministic DRC/ERC/review categories with explicit skipped/approximate boundaries |
| 6–10 | complete | silkscreen, placement, routing, DSN/SES, differential-pair/length/preliminary impedance |
| 11 | bounded complete | return-path, BOM, DFM/DFA/DFT, thermal and assembly heuristics plus release-readiness supplement |
| 12 | implementation complete | release manifests/adapters; real external solver and native manufacturing sign-off remain external |
| 13–19 | complete | skills/CI, scaffolding, schematic authoring, panelisation, ngspice, multi-net routing and sync |
| 20 | repository complete | trust authority/comparison/cancellation plus regression coverage; real host evidence is manual |
| 21 | complete | service-Facade decomposition and parity guardrails |
| 22 | candidate complete | Windows installer/portable/configurator pipeline; clean-machine acceptance is manual |
| 23 | baseline complete | deterministic pattern recommendation and privacy-bounded feedback/evaluation |
| 24 | implementation complete, host-gated | raw-preserving native Component/Pattern mutation core; public write registration waits for real DipTrace evidence |

## Permanent limitations and non-claims

- Synthetic scaffolds and generated fixture packs are MCP-generated XML, not DipTrace exports.
- Changing `format_version` is not conversion or compatibility evidence.
- The local router is bounded and is not a full push-and-shove/free-angle/global EDA router.
- Copper-pour, return-path, impedance, thermal, DFM/DFA/DFT and manufacturing reviews retain explicit approximation/skip boundaries.
- Generic fabrication/assembly manifests are not native Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off packages.
- The ngspice adapter runs user-provided netlists; it does not generate a complete simulation netlist from a DipTrace design.
- Native manufacturing generation remains unavailable because no verified DipTrace output API is claimed.
- The project does not claim Novarm/DipTrace endorsement, universal compatibility, signed binaries, independent review or production readiness.
