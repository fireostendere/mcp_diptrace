# Roadmap and Actual Status

This document separates three distinct states:

1. **implemented** — production code, typed contracts, and repository tests exist;
2. **runtime available** — the active document, policy, geometry backend, and
   configured adapters allow the feature;
3. **DipTrace verified** — a controlled real DipTrace open/save/re-export or
   live apply/cancel experiment exists for the exact path.

Implementation does not imply universal DipTrace compatibility. Runtime
`get_capabilities` remains authoritative.

## Current checkpoint — 2026-08-07

The current source/package version is `0.2.1`. Version `v0.2.1` is the latest
published development prerelease. The GitHub prerelease assets are published and
the exact tag-bound PyPI Trusted Publishing workflow completed successfully.
Remaining human acceptance work is tracked separately from package publication.

The project has moved beyond a parser prototype. The strongest areas are:

- PCB/schematic/library reading and structured queries;
- guarded semantic writes and transactions;
- engineering review with explicit skipped/partial categories;
- schematic authoring and schematic-to-PCB synchronisation;
- bounded placement, local/multi-net routing, differential-pair workflows, and
  preliminary SI analysis;
- Windows bridge, standalone server, installer, portable bundle, and client
  configurator build pipelines;
- stable MCP, Facade, error, safety, and packaging contracts.

The first service-Facade decomposition pass is complete. The previous monolith
was split into explicit typed domain services while preserving the 159-tool MCP
surface, 157 public Facade signatures, state ownership, and safety boundaries.
Future architecture work is no longer a prerequisite for the 0.2.0 candidate.

## Practical classification

| Area | Status | Main remaining gap |
| --- | --- | --- |
| PCB/schematic read/query | mature beta | broader redistributable current-version fixtures |
| Component/Pattern Library read/validate | mature beta | more current mask/paste/courtyard examples |
| Guarded semantic edits | mature beta | close all trust-invalidation evidence gaps |
| Transactions and rollback | mature beta | more real writer round trips |
| Schematic authoring | beta | live authored-wire and hierarchy evidence |
| Schematic → PCB sync | beta | broader real round trips and trust-path closure |
| Placement | bounded beta | no full global placer/legalizer |
| Local/multi-net routing | bounded beta | no push-and-shove/free-angle/global router |
| Differential-pair/SI | beta | optional external-solver validation |
| Windows installer/portable | candidate-ready in CI | clean-machine and real-client acceptance |
| Native Component/Pattern mutation | blocked | controlled writer semantics and round-trip fixtures |
| Native manufacturing output | outside current core scope | no verified DipTrace output API |
| Pattern recommendation | planned | local dataset, deterministic retrieval, held-out metrics |

## 0.2.1 release and acceptance status

Automated preparation is complete for the current candidate:

- project and Windows assets use version `0.2.1`;
- exact PR #49 head CI run `30940972328` passed;
- exact PR #49 Windows installer run `30940972331` passed;
- installer, portable bundle, standalone server, bridge, and configurator build;
- Linux/macOS/Windows tests, Ruff, strict Mypy, DCO, artifact audit, service
  contract audit, decomposition safety audit, and event-loop audit pass;
- public MCP surface remains 159 tools;
- candidate records and rollback rules are committed.

Remaining human blockers:

1. clean Windows 11 install, repair, and uninstall;
2. current real DipTrace 5 checks across PCB, Schematic, Component, and Pattern;
3. real Codex and Claude Desktop configuration/restart checks;
4. elevated plug-in installation while preserving the original user profile;
5. custom-state preservation acceptance;
6. final frozen asset hashes and public-download verification;
7. any required external legal review.

The candidate remains unsigned and development-stage. Q1 Component Angle
GUI/re-export validation remains `NOT_RUN`.

## Current evidence boundary

Controlled host evidence exists for selected paths:

- DipTrace 5.3.0.2 schematic save/re-export comparison;
- DipTrace 5.2.0.4 Windows ↔ WSL PCB and Schematic apply/cancel/wrong-SHA;
- GUI/save/re-export confirmation for the tested applied cases;
- no host mutation for tested cancel and wrong-SHA cases.

This evidence does not cover every tool, writer, XML object, source variant, or
DipTrace 5.x build.

The capability report also intentionally does not claim complete
trust-invalidation coverage for:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

## Current public contracts

The following baselines must not be weakened:

- 159 MCP tools;
- current complete wire snapshot:
  - 142,746 canonical UTF-8 bytes;
  - SHA-256 `073f53681306fd13c5f3f29d61baed9a83fc9eb5c1ed14883846005a39d812db`;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations;
- stable structured public error envelope;
- project-owned worker-thread boundary for all registered tools;
- exact SHA, policy, backup, atomic-write, session-lease, and trust-authority
  boundaries;
- package-owned authority registry separated from user-controlled evidence.

## Priority A — Finish 0.2.1 acceptance evidence

This is the immediate priority.

Deliverables:

- execute the remaining Windows/DipTrace/client acceptance matrix;
- record dated evidence and exact versions;
- freeze the final release commit;
- regenerate compliance outputs and final assets;
- verify every per-file SHA-256;
- create annotated `v0.2.0` only after the gates pass;
- publish as an explicitly unsigned development/prerelease;
- download public assets and repeat checksum/install/stdio/uninstall smoke tests.

Exit condition: immutable tag, exact asset inventory, final checksums, public
installation evidence, and reconciled README/changelog/citation/release record.

## Priority B — Close compatibility and trust evidence

After the 0.2.1 publication:

1. close trust invalidation for all currently listed write paths;
2. collect a small redistributable current DipTrace fixture pack covering PCB,
   schematic, Component Library, Pattern Library, controlled writer pairs, and a
   real DSN/SES pair;
3. add real DipTrace acceptance for authored wires and generated ratlines;
4. verify mask, paste, courtyard, and `Common` semantics with one-setting-at-a-
   time exports;
5. make the resulting cases executable in CI without DipTrace installed.

Exit condition: every documentation claim can distinguish parser-tested,
operation-tested, DipTrace-exported, and real round-trip-verified behavior.

## Priority C — Native library writers

Only after Priority B supplies controlled evidence:

- create/update patterns;
- create/update components, parts, pins, graphics, and fields;
- attach patterns to components;
- maintain explicit pin-to-pad mapping;
- preserve unknown/unsupported library XML;
- require explicit collision and replacement behavior;
- prove idempotence and real DipTrace open/save/re-export equivalence.

No placeholder tools should be registered before these gates are met.

## Priority D — Human-guided pattern recommendation

The first useful recommendation system should rank existing patterns, not train
a model immediately.

Planned sequence:

1. append-only local feedback records;
2. deterministic package feature extraction;
3. hard compatibility filters;
4. geometry-distance ranking;
5. held-out top-1/top-3 and invalid-pattern rejection metrics;
6. explicit human accept/reject/correction capture;
7. optional fine-tuning only after the retrieval baseline and privacy controls
   are stable.

User projects, datasheets, screenshots, and library XML must never be committed
automatically.

## Priority E — Optional external validation

- capture a real openEMS integration run;
- add more Freerouting DSN/SES fixtures;
- preserve the typed external-process boundary and runtime availability model;
- keep optional solver evidence separate from core parser/write trust.

## Phase summary

| Phase | Status | Result |
| --- | --- | --- |
| 0 | complete | baseline package, capability, SDK, and policy contracts |
| 1 | complete | PCB/schematic/library models and structured queries |
| 2 | complete | normalised geometry, spatial index, previews, GEOS/fallback paths |
| 3 | complete | semantic compiler, transactions, SHA, backup, rollback |
| 4 | complete | component/part/text/rule/test-point writes and library validation |
| 5 | partial | bounded DRC/ERC/review with explicit missing/approximate categories |
| 6 | complete | silkscreen planning and apply |
| 7 | complete | bounded placement planning, scoring, legalisation, apply |
| 8 | complete | trace/via primitives and bounded multi-layer routing |
| 9 | complete | DSN/Freerouting/SES workflow |
| 10 | complete | differential pairs, length/skew, preliminary impedance |
| 11 | partial | return-path, BOM, DFM/DFA/DFT, thermal and assembly heuristics |
| 12 | partial | release manifests and optional openEMS; native library/output writers absent |
| 13 | complete | skills, prompts, CI, benchmarks, truthful capability discovery |
| 14 | complete | synthetic PCB/schematic scaffolding |
| 15 | complete | schematic authoring |
| 16 | complete | panelisation parameters |
| 17 | complete | typed ngspice batch adapter |
| 18 | complete | congestion-aware multi-net routing |
| 19 | complete | additive and guarded exact schematic-to-PCB reconciliation |
| 20 | implementation complete | trust authority, comparison, native Windows CI, cancellation; evidence gaps remain |
| 21 | complete | service-Facade decomposition with explicit domain services and parity checks |
| 22 | candidate complete | Windows installer/portable/configurator release-candidate pipeline |
| 23 | planned | human-guided pattern recommendation |

## Permanent limitations and non-claims

- Synthetic scaffolds are MCP-generated XML based on maintained observations;
  changing `format_version` is not conversion or compatibility evidence.
- The local router is bounded and not equivalent to a full EDA router.
- Copper-pour, return-path, impedance, thermal, DFM/DFA/DFT, and manufacturing
  reviews retain explicit approximation and skip boundaries.
- Generic fabrication/assembly manifests are not native Gerber, NC Drill,
  ODB++, IPC-2581, or assembler sign-off packages.
- The ngspice adapter runs user-provided netlists; it does not generate a full
  simulation netlist from a DipTrace design.
- Native library mutation and native manufacturing generation remain unavailable.
- The project does not claim Novarm/DipTrace endorsement, universal
  compatibility, signed binaries, independent review, or production readiness.
