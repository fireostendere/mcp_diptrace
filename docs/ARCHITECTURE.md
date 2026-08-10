# Architecture

## Scope

DipTrace MCP is intentionally split into four concerns:

1. public MCP transport and stable error/contract handling;
2. application/domain services and guarded engineering operations;
3. internal EDA intelligence that generates/scores proposals without bypassing safety boundaries;
4. optional Windows presentation automation for visible cinematic replay.

The public MCP surface remains stable while the internal EDA layers evolve.

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
    |      +--> schematic layout + co-optimisation
    |      +--> PCB Generations A-D
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

A separate optional branch turns already-planned actions into visible UI replay:

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
WindowsDesktopDriver -> visible DipTrace UI -> ffmpeg capture
```

Cinematic replay is presentation automation. It is not a replacement for the guarded XML engineering path and is not semantic acceptance evidence by itself.

## Public MCP layer

`src/diptrace_mcp/server.py` owns:

- FastMCP tool/resource registration;
- stdio and trusted-loopback HTTP transports;
- conversion of internal exceptions into the stable public error envelope;
- the project-owned worker-thread boundary for synchronous domain work;
- dependency assembly through the stable `DipTraceService` Facade.

Current frozen public contract:

- 159 registered tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations.

`reference/mcp-tools-list.snapshot.json` and CI guard that surface. New internal heuristics do not automatically become new tools.

## Service and trust boundaries

`DipTraceService` remains the stable public Facade. Domain implementations live under `src/diptrace_mcp/services/` and receive narrow typed dependencies rather than the complete Facade.

Shared state is intentionally centralized:

- document loading/gateway;
- normalized model cache;
- record storage;
- transaction storage;
- live-session state;
- policy configuration;
- evidence/trust authority.

Services must not create parallel stores or duplicate safety state.

Persistent writes continue through the existing guarded path:

1. validate/resolve path inside allowed roots;
2. parse bounded XML;
3. bind operation/preview to an exact SHA-256;
4. validate semantic operation and policy impact;
5. back up existing targets where applicable;
6. write via temporary file and atomic replace;
7. preserve transaction/recovery metadata;
8. for live sessions, re-check working/exchange/original identities before apply.

## Normalized domain model

Parsers/adapters convert DipTrace XML into typed normalized PCB, schematic and library models. The normalized layer carries stable IDs, geometry/connectivity facts and provenance without pretending that every XML token has authoritative engineering meaning.

Observed facts, inferred engineering intent and operator-provided facts remain distinct. In particular, missing current, edge rate, impedance, stackup authority and manufacturing limits remain unknown until supplied by trustworthy evidence.

See [Domain Model](DOMAIN_MODEL.md).

## Schematic intelligence

The current schematic architecture is internal and non-public. Its modules are:

- `schematic_layout.py` — design intent, functional blocks, reference motifs, readability metrics and first hierarchical placement plan;
- `schematic_optimizer.py` — bounded multi-candidate placement search and first-stage interconnect estimates;
- `schematic_wire_planner.py` — non-mutating wire candidate evaluation and explicit placement feedback;
- `schematic_pin_geometry.py` — conservative pin geometry resolution from the embedded Design Cache or explicit fallback library;
- `schematic_joint_optimizer.py` — pin-aware hypothetical route scoring across placement candidates;
- `schematic_placement_repair.py` — bounded route-feedback-driven placement repair and re-ranking.

The implementation deliberately remains non-mutating until an ordinary semantic operation plan is selected. Existing-wire schematics are still refused by the placement planners by default because moving symbols without atomically replacing affected wires would degrade the drawing.

The next architectural step is a selective-reroute transaction layer that can compose selected placement moves and affected wire replacements into one guarded transaction. See [Schematic Layout Engine](SCHEMATIC_LAYOUT_ENGINE.md).

## PCB design intelligence — Generations A-D

The PCB design engine is layered above the existing geometry legalizer/router/review path.

### Generation A — intent and placement

- `pcb_design_intent.py` builds engineering roles, functional blocks, multi-role net intent, criticality and explicit physical constraints;
- `pcb_placement.py` performs deterministic intent-aware placement v2 while the existing low-level placement engine remains the legality/geometry authority.

Generation A uses conservative proximity/intent proxies and does not invent field/current/thermal values.

### Generation B — physical context

`pcb_physical.py` adds bounded exported-stackup/reference context, conservative PDN source/load/decoupling analysis, regulator hot-loop candidates, return-path integration, timing-gated aggressor/victim triage and semantic via-role classification.

It consumes available evidence but does not promote approximate analysis into field-solver, PI, EMC or thermal sign-off.

### Generation C — routing policy

`pcb_routing_policy.py` compiles intent into deterministic route order and explicit layer/via/length/skew/impedance/reference/stub/shield constraints. It evaluates supplied route observations and can emit bounded placement feedback for pathological candidates.

Native routing/copper writes still use the existing guarded semantic path. Authoritative pour/refill geometry remains a real-host evidence boundary.

### Generation D — whole-board selection

`pcb_joint_optimizer.py` selects among bounded candidates. Hard safety, mechanical, connectivity, DRC, reference-path and manufacturing dimensions are lexicographically dominant over soft placement/routing/via/SI/PI/return-path/EMI-risk/thermal-risk/manufacturing scores.

The optimizer selects and explains candidates; it does not directly apply them. The accompanying engineering-trap catalog is synthetic-regression evidence only. Real-DipTrace Generation D product acceptance remains pending.

See [PCB Design Engine](PCB_DESIGN_ENGINE.md).

## Low-level placement and routing

The existing low-level placement/routing modules remain important authorities:

- geometry and board-outline/keepout legality;
- bounded component placement and legalization;
- route candidate generation, clearance and via validation;
- differential-pair/length and preliminary impedance/return-path helpers;
- semantic trace/via operations and guarded transactions.

The higher EDA generations compose these primitives; they do not replace or bypass them. See [Placement Engine](PLACEMENT_ENGINE.md), [Routing Engine](ROUTING_ENGINE.md), [Geometry Engine](GEOMETRY_ENGINE.md) and [Transactions](TRANSACTIONS.md).

## Component and Pattern Library mutation

A raw-preserving internal Component/Pattern Library mutation core exists and has controlled real Component Editor / Pattern Editor round-trip evidence. This is an internal capability. It does not automatically create public native-library write tools or broaden the public compatibility claim.

## External adapters

Freerouting, ngspice and openEMS are process adapters with explicit typed boundaries. They run locally through bounded job directories/process controls and cannot bypass project trust, transaction or review policy. Adapter output is evidence/candidate data, not an automatic authority over the document.

## Cinematic presentation layer

The cinematic subsystem lives in:

- `cinematic.py` — deterministic timeline and presets;
- `cinematic_cli.py` — JSONL capture/compile and ffmpeg command generation;
- `cinematic_host.py` — Windows replay host and dry-run driver;
- `cinematic_recording.py` — Windows ffmpeg capture helpers;
- `diptrace_ui.py` — version/editor-specific UI profiles and affine design-to-client calibration;
- `diptrace_profile_cli.py` — profile template/probe/calibrate/action/validate workflows;
- `diptrace_cinematic_semantic.py` — semantic Schematic/PCB replay adapters;
- `diptrace_window.py` — Windows target-window resolution/client geometry.

UI profiles fail closed until calibrated and supplied with the required verified action macros. The coordinate transform maps DipTrace design coordinates to normalized client coordinates rather than fixed monitor pixels.

The subsystem is Windows-specific where it touches the real desktop. Timeline compilation and dry-run logic remain deterministic/testable without moving the cursor.

See [Cinematic Demo Mode](CINEMATIC_DEMO_MODE.md).

## Evidence model

Three states must not be collapsed:

- **implemented** — code and repository regression tests exist;
- **runtime available** — current document/policy/adapters expose the capability;
- **DipTrace verified** — controlled real-host/client evidence exists for the exact path and candidate.

Historical evidence stays bound to the exact commit/release where it was captured. Later `main` development does not inherit it automatically.

## Current architectural limitations

- selective atomic reroute of existing schematic wires after placement repair is not implemented;
- automatic datasheet/reference-motif ingestion is not required by the schematic engine and remains future work;
- real-host validation of all schematic rotation/pin-facing conventions remains incomplete;
- PCB Generation D real-DipTrace product acceptance remains pending;
- cinematic UI macros/calibration are configuration-specific and still require real-client acceptance;
- cinematic PCB replay currently refuses via/layer-transition traces;
- native manufacturing generation and trusted sign-off are outside the current implementation;
- no internal optimizer result is field-solver, PI, EMC, thermal or fabrication authority by itself.
