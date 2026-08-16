# Architecture

## Scope

DipTrace MCP is split into four concerns:

1. public MCP transport and stable error/contract handling;
2. application/domain services and guarded engineering operations;
3. internal EDA intelligence that generates, scores and reviews proposals without
   bypassing safety boundaries;
4. optional Windows presentation automation for visible replay or isolated hidden capture.

The public MCP surface currently registers **167 tools**. Roadmap A1-A8 additions are
package-level unless explicitly productized; they do not silently expand that public
surface.

## End-to-end structure

```text
MCP client
    |
    | stdio / trusted loopback Streamable HTTP
    v
FastMCP server
    |
    | public error envelope + worker-thread boundary
    v
DipTraceService facade
    |
    +--> typed domain services
    +--> shared context / stores / policy / cache / gateway
    +--> internal EDA intelligence
    |      +--> schematic placement / topology / rotation / atomic reroute
    |      +--> PCB Generations A-D / whole-board planning
    |      +--> reviewer evaluation / physics estimates / evidence campaigns
    |      +--> DSN/SES and semantic XML analysis
    v
typed semantic operations / guarded plans
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

A separate presentation-only branch turns already-planned actions into calibrated DipTrace
UI replay and MP4/GIF capture. It is not a second semantic write authority.

## Public MCP layer

`server.py` owns FastMCP registration, local stdio/trusted-loopback HTTP transport, the
stable error envelope and server-owned worker-thread offload. The frozen
`reference/mcp-tools-list.snapshot.json` plus CI guard the 167-tool contract.

The transport responsiveness regression exercises repeated in-memory `tools/list`,
`summarize_design` calls and teardown under the existing five-second read budget. The old
audit-venv timeout was not reproduced in the declared development environment, so the
project did not mask it by simply increasing timeouts.

## Service and trust boundaries

`DipTraceService` remains the public facade. Shared document loading, normalized-model
cache, records, transactions, live sessions, policy and trust authority stay centralized.
Services must not create parallel safety state.

Persistent writes continue through the guarded path:

1. resolve an allowed-root path;
2. parse bounded XML;
3. bind preview/operation to exact SHA-256;
4. validate semantic operation and policy impact;
5. create backup/recovery state where applicable;
6. use temporary-file plus atomic replacement;
7. preserve transaction/recovery metadata;
8. re-check working/exchange/original identities for live apply;
9. verify post-write identity and roll back on bounded apply failure.

## Schematic intelligence

The schematic pipeline is deterministic and bounded:

- `schematic_layout.py` — design intent and readability motifs;
- `schematic_optimizer.py` — bounded placement candidates;
- `schematic_pin_geometry.py` — conservative pin geometry;
- `schematic_wire_planner.py` — wire quality and placement feedback;
- `schematic_joint_optimizer.py` — pin-aware route scoring;
- `schematic_placement_repair.py` — bounded repair;
- `schematic_ensemble.py` — motif/route/congestion ranking and objective history;
- `schematic_topology.py` — literal existing-wire graph proof;
- `schematic_rotation.py` — confidence-gated cardinal rotation candidates;
- `schematic_atomic_reroute.py` — selective atomic replacement.

For proven connected acyclic existing-wire graphs, all relevant intentional junctions are
preserved. Cyclic, free-leaf, incomplete or ambiguous topology fails closed. Rotation uses
source geometry to prove existing topology and post-rotation geometry only to build new
endpoints.

The semantic batch is dependency-safe:

`delete affected wires -> rotate/move affected parts -> rebuild affected wires`

Atomicity comes from the existing transaction path when the complete batch is
previewed/committed together. Automatic rotation remains M2-gated for real-host claims.

## PCB intelligence

The PCB engine remains layered:

- Generation A — engineering intent and bounded placement;
- Generation B — stackup/reference/PDN/return-path/noise context;
- Generation C — routing policy and observed-route checks;
- Generation D — hard-first candidate selection.

`pcb_quality.py` and `pcb_physics_knowledge.py` add deterministic qualitative review and
explicit unknown physical facts. `pcb_whole_board.py` composes placement, routing, compact
outline, copper and silkscreen stages.

The whole-board path now exposes a guarded package-level plan/apply contract bound to exact
source SHA, candidate SHA and deterministic plan identity. It reuses the transaction,
backup and rollback boundaries and blocks stale input or hard review failure. DipTrace
native refill and native DRC remain external authority and require M1 for stronger claims.

## Reviewer evaluation and source-backed rules

`advanced_review.py` contains the provider-neutral reviewer evaluation contract. Model
responses are adjudicated against deterministic hard rules and approved ground truth;
`pending_m11` cases cannot be silently promoted to evaluation truth.

`reference_rules.py` accepts source-bound rule packs. Claim-eligible engineering facts
require source SHA-256, revision, locator, units/limit semantics, conditions and
applicability. Missing evidence remains explicit rather than being filled from model memory.

## Quantitative estimates

`physics_estimates.py` provides bounded explicit-input trace/via DC resistance,
voltage-drop, aggregate-loss and first-order thermal calculations. Results retain exact
inputs, source/method identity, assumptions, limitations and sensitivity. Missing physical
facts remain `unknown`. M3 controls source applicability and M8 controls physical
correlation/sign-off.

## Evidence pipeline

The capture boundary remains trust-neutral. `evidence_report.py` builds deterministic
per-candidate reports, while `evidence_campaign.py` aggregates exact-hash reports,
media/frame metrics, exported deltas, explicitly untrusted AI visual findings and
promotion/rejection requests.

No evidence code path can grant PASS, provenance trust, fixture trust, native-refill
authority or independent review. Promotion remains a separate M11 decision.

## Component and Pattern Library mutation

The installed DipTrace catalog is queried read-only. Internal raw-preserving Component and
Pattern mutation remains below the public write-tool boundary.
`library_mutation_api.py` stays package-level with `public_registration=False`; any public
native-library write path requires an explicit M12 decision and public-contract update.

## External adapters

Freerouting, ngspice and openEMS remain typed bounded process adapters. Their output is
candidate/evidence data and cannot bypass trust, transaction or review policy.

## Cinematic and hidden GUI

The presentation subsystem includes deterministic preflight, calibrated UI profiles,
visible replay, hidden Win32 desktop isolation and MP4/GIF capture. It never switches the
operator's input desktop and has no physical mouse/keyboard fallback in the hidden path.
Exact UI gestures remain editor/version/profile-specific evidence.

## Evidence model

Three states remain distinct:

- **implemented** — code and repository tests exist;
- **runtime available** — the active document/policy/adapters expose the capability;
- **DipTrace verified** — controlled real-host/client evidence exists for that exact path.

The project-level blocking manual matrix is **12/12 PASS across accepted checkpoints**.
The Claude Desktop restart PASS was collected later on a separate machine that did not have
Codex installed; it is independent Claude client evidence, not same-host comparative
client evidence. Historical checkpoint wording remains historical.

## Current architectural limitations

- global placement/routing/Steiner optimization remains intentionally bounded and
  trigger-based rather than a claim of global optimality;
- automatic schematic rotation/pin-facing remains M2-gated by symbol/editor family;
- authoritative PCB refill/native DRC and stronger whole-board claims remain M1-gated;
- engineering-source applicability and physical correlation remain M3/M8-gated;
- evidence promotion and public/default product decisions remain M11/M12-gated;
- cinematic UI macros remain configuration-specific;
- native manufacturing generation, fabrication sign-off, SI/PI/thermal/EMC authority and
  independent/legal release authority remain outside automated repository proof.


## Cross-platform GUI host backends

The semantic MCP/service layer remains platform-neutral and keeps the frozen 167-tool
contract. Host GUI actions reuse one packaged Win32 automation core through three
bounded deployment backends:

- Windows: native/hidden Win32 desktop worker;
- Linux: Wine on a private Xvfb display, with the helper using the native Wine
  desktop inside that isolated X server;
- macOS: the Wine prefix bundled by DipTrace.app, with the helper using a private
  hidden Win32 desktop; Apple Silicon runs the official x86-64 bundle via Rosetta.

All backends share the existing MCP/bridge state boundary and do not turn GUI
automation into a second semantic authoring authority.
