# Architecture

## Scope

DipTrace MCP is intentionally split into four concerns:

1. public MCP transport and stable error/contract handling;
2. application/domain services and guarded engineering operations;
3. internal EDA intelligence that generates/scores proposals without bypassing safety boundaries;
4. optional Windows presentation automation for visible replay or isolated hidden capture.

The public MCP surface currently registers **165 tools**; it was intentionally expanded from the earlier frozen 159 to expose bounded EDA intelligence engines as products.

## End-to-end structure

```text
MCP client
    |
    | stdio / trusted loopback Streamable HTTP
    v
src/diptrace_mcp/server.py
    |  FastMCP registration
    |  public error envelope
    |  server-owned AnyIO worker-thread boundary
    v
DipTraceService Facade
    |
    +--> typed services under src/diptrace_mcp/services/
    +--> shared context / stores / policy / cache / gateway
    +--> internal EDA modules
    |      +--> schematic layout / route / selective reroute ensemble
    |      +--> PCB Generations A-D candidate ensemble
    |      +--> DSN/SES and XML semantic analysis
    v
typed semantic operations
    |
    v
preview / expected SHA / policy / transaction / review
    |
    v
secure XML read/write + live-session state
    ^
    |
Windows bridge
    ^
    |
DipTrace
```

A separate optional branch turns already-planned actions into UI replay and recording:

```text
planned semantic action / placement proposal / route vertices
    |
    v
DipTraceCinematicAdapter
    |
    v
calibrated DipTraceUIProfile
    |
    v
cinematic manifest
    |
    v
mandatory cinematic preflight
    |
    v
WindowsDesktopDriver -> visible DipTrace UI -> gdigrab
                         or
HiddenMessageDesktopDriver -> hidden DipTrace window -> PrintWindow/WM_PRINT -> ffmpeg
```

Cinematic replay is presentation automation. It is not a replacement for the guarded XML engineering path and is not semantic acceptance evidence by itself.

## Public MCP layer

`src/diptrace_mcp/server.py` owns FastMCP registration, stdio/trusted-loopback HTTP transport, the stable error envelope, worker-thread offload and dependency assembly through `DipTraceService`.

Current public contract:

- 165 registered tools.

`reference/mcp-tools-list.snapshot.json` and CI guard that surface. New internal heuristics and package-level APIs do not automatically become new tools; public registration is an intentional contract decision.

## Service and trust boundaries

`DipTraceService` remains the stable public Facade. Domain implementations live under `src/diptrace_mcp/services/` and receive narrow typed dependencies rather than the complete Facade.

Shared state remains centralized: document loading/gateway, normalized-model cache, records, transactions, live sessions, policy and evidence/trust authority. Services must not create parallel stores or duplicate safety state.

Persistent writes continue through the guarded path:

1. resolve an allowed-root path;
2. parse bounded XML;
3. bind preview/operation to exact SHA-256;
4. validate semantic operation and policy impact;
5. create backup/recovery state where applicable;
6. use temporary-file + atomic replacement;
7. preserve transaction/recovery metadata;
8. for live sessions, re-check working/exchange/original identities before apply.

## Normalized domain model

Adapters convert DipTrace XML into typed PCB, schematic and library models with stable IDs, geometry/connectivity facts and provenance. Observed facts, inferred engineering intent and operator-supplied facts remain distinct. Missing current, edge rate, impedance, stackup authority or manufacturing limits stay unknown instead of becoming guessed constants.

See [Domain Model](DOMAIN_MODEL.md).

## Schematic intelligence

The schematic intelligence architecture is internal and deterministic:

- `schematic_layout.py` — design intent, functional blocks, reference motifs and readability metrics;
- `schematic_optimizer.py` — bounded placement candidates and first-stage interconnect estimates;
- `schematic_wire_planner.py` — wire-candidate quality and explicit placement feedback;
- `schematic_pin_geometry.py` — conservative Design Cache pin geometry;
- `schematic_joint_optimizer.py` — pin-aware hypothetical route scoring;
- `schematic_placement_repair.py` — bounded route-feedback-driven placement repair;
- `schematic_atomic_reroute.py` — selective affected-net wire replacement composed with placement moves as one semantic-operation batch;
- `schematic_ensemble.py` — deterministic builtin readability motifs, congestion pressure and route-aware candidate ranking.

`schematic_atomic_reroute.py` closes the former existing-wire gap. It detects only sheet-local explicit wire groups touched by moved parts, fails closed when affected endpoints/routes cannot be rebuilt safely, and returns `delete wire -> move part -> add replacement wire` operations. Atomicity is supplied by the existing semantic transaction path when that complete operation list is previewed/committed together.

The layer remains bounded rather than globally optimal. Global same-net junction optimisation, richer sheet-level scheduling, broader motif ingestion and the full iterative objective-history loop remain future improvement areas.

See [Schematic Layout Engine](SCHEMATIC_LAYOUT_ENGINE.md).

## PCB design intelligence — Generations A-D

The PCB design engine remains layered above geometry/legalisation/routing/review primitives.

- Generation A: `pcb_design_intent.py` + `pcb_placement.py` provide engineering intent and bounded intent-aware placement.
- Generation B: `pcb_physical.py` adds exported-stackup/reference context, conservative PDN/return-path/noise/via-role analysis.
- Generation C: `pcb_routing_policy.py` compiles deterministic routing policy and evaluates supplied route observations.
- Generation D: `pcb_joint_optimizer.py` applies lexicographically dominant hard-rule selection over decomposed soft scores.
- `pcb_candidate_ensemble.py` now generates multiple real bounded Generation-A placement candidates under different engineering profiles, carries conservative B/C evidence terms and lets the existing Generation-D selector choose hard-first. The existing board is retained as an optional baseline candidate.

No Generation B/C/D proxy becomes field-solver, PI, EMC, thermal or manufacturing authority. Real-DipTrace product acceptance for the affected primitives remains a separate evidence boundary.

See [PCB Design Engine](PCB_DESIGN_ENGINE.md).

## Exchange and semantic XML analysis

`specctra_analysis.py` adds bounded DSN/SES inspection around the existing Specctra import/export path. It reports structure, route geometry, unknown nets/layers and which SES routes are importable or skipped before mutation.

`xml_analysis.py` provides deterministic semantic XML fingerprints and structural deltas. Attribute ordering is normalized, element ordering remains significant, and unknown XML contributes to the fingerprint even when the normalized model does not interpret it.

These analyzers are review/evidence tools; they do not grant compatibility or mutate documents by themselves.

## Component and Pattern Library mutation

`library_mutation.py` remains the raw-preserving internal Component/Pattern writer core with controlled real-editor evidence.

`library_mutation_api.py` adds a stable expected-SHA package-level request/preview contract around that core. It is intentionally **not registered as a public MCP tool** (`public_registration=False`), so this work does not expand the current 165-tool contract. A future MCP registration requires an intentional API/product decision, snapshot update and claim-specific acceptance rather than happening incidentally.

## Evidence pipeline

The operator capture boundary remains trust-neutral. `capture_diptrace_evidence.py` records source/open-save/re-export artifacts and operator claims without granting trust.

`evidence_report.py` and `scripts/build_evidence_report.py` now turn a finalized candidate into deterministic JSON/Markdown review output. They re-check artifact SHA bindings and add `xml_analysis.py` fingerprints/deltas, but cannot grant PASS, provenance trust, fixture trust or release acceptance.

## External adapters

Freerouting, ngspice and openEMS remain typed bounded process adapters. Adapter output is candidate/evidence data and cannot bypass trust, transaction or review policy.

## Cinematic presentation layer

The cinematic subsystem includes:

- `cinematic.py` — deterministic timeline/presets;
- `cinematic_cli.py` — capture/compile and ffmpeg command generation;
- `cinematic_preflight.py` — content identity plus timing/payload/desktop-action safety budgets;
- `cinematic_preflight_cli.py` — standalone preflight inspection;
- `cinematic_host.py` — Windows replay/dry-run host; `play_manifest()` always invokes preflight before any driver action;
- `cinematic_recording.py` — visible `gdigrab` plus isolated hidden-window BGRA/ffmpeg capture;
- `diptrace_ui.py` / `diptrace_profile_cli.py` — version/editor-specific profile calibration and action macros;
- `diptrace_cinematic_semantic.py` — semantic schematic/PCB replay adapters;
- `diptrace_window.py` — target-window/client geometry.

UI profiles still fail closed until calibrated and populated with verified macros for the exact client configuration. Same-layer PCB trace replay is supported; via/layer-transition GUI playback remains fail-closed until verified staged actions exist.

See [Cinematic Demo Mode](CINEMATIC_DEMO_MODE.md).

## Documentation state as a contract

`scripts/check_documentation_state.py` compares evergreen documentation with implemented modules and the frozen public-tools snapshot. `tests/test_documentation_state.py` runs this guard in the normal CI test matrix. It checks current-state docs only; immutable historical release/audit/acceptance records remain historical evidence and are not rewritten to match current code.

## Evidence model

Three states remain distinct:

- **implemented** — code and repository regression tests exist;
- **runtime available** — current document/policy/adapters expose the capability;
- **DipTrace verified** — controlled real-host/client evidence exists for the exact path and candidate.

Historical evidence stays bound to the exact commit/release where it was captured. Later development does not inherit it automatically.

## Current architectural limitations

- automatic datasheet/reference-design ingestion remains bounded/future work rather than a source of invented engineering truth;
- global same-net schematic junction optimisation and the fuller iterative objective-history loop remain incomplete;
- real-host validation of all schematic rotation/pin-facing conventions remains incomplete;
- PCB Generation D real-DipTrace product acceptance remains pending;
- cinematic UI macros/calibration remain configuration-specific and require real-client acceptance;
- cinematic PCB replay still refuses unverified via/layer-transition gestures;
- native manufacturing generation and trusted fabrication/sign-off remain outside the implementation;
- no internal optimizer result is field-solver, PI, EMC, thermal or fabrication authority by itself.
