# DipTrace MCP Architecture

## Scope

DipTrace MCP is a local MCP server with an optional Windows executable bridge for designs opened in DipTrace. The design separates the MCP boundary, domain services, XML/file safety, persistent state, and external DipTrace/tool processes.

Mutable release/version facts live in project metadata and release records rather than this evergreen architecture document.

## High-level flow

```text
MCP client
    |
    v
server.py / server_runtime.py
    |
    v
DipTraceService (internal composition/orchestration root)
    |
    +--> focused domain services
    +--> policy, stores, cache, document gateway
    |
    v
XML files and shared state
    ^
    |
diptrace_mcp_bridge.exe
    ^
    |
DipTrace executable XML plug-in contract
```

The externally relevant server contract is the MCP surface. `server_runtime.py` defines the concrete tool signatures and registration; `reference/mcp-tools-list.snapshot.json` freezes the complete `tools/list` model in CI.

## Application and domain services

`src/diptrace_mcp/service.py` is an internal application composition root. It owns shared state and the few cross-service operations that need orchestration. Focused behavior lives under `src/diptrace_mcp/services/`.

The composition root does not maintain a second method-for-method API contract. Public MCP wrappers call application methods by name, and simple calls resolve to the service that actually implements them. Internal service ownership and forwarding topology may change while the MCP contract and safety behavior remain stable.

Primary services include:

- `DocumentService`: normalized documents, selectors, connectivity and bounded XML reads;
- `BomService`: BOM and component/library metadata;
- `ReviewService`: review reports and engineering analysis;
- `DiscoveryService`: document/library discovery;
- `ExportService`: bounded export records and artifacts;
- `JobService` / `ExternalJobsService`: jobs and external-tool orchestration;
- `RoutingService`: routing analysis, plans and apply paths;
- `PlacementService`: placement and silkscreen planning/apply paths;
- `SemanticOperationsService` / `SemanticEngineService`: guarded semantic edits and previews;
- `SynchronizationService`: schematic-to-PCB synchronization;
- `XmlWriteService`: guarded raw XML edits and raw previews;
- `ScaffoldingService`: synthetic and seed-based document creation;
- `TransactionService`: preview, commit, rollback and recovery;
- `EvidenceService`: provenance, comparison and fail-closed trust;
- `LiveSessionService`: live-session lifecycle.

`ServiceContext` groups shared typed dependencies. `DocumentGateway` is the path/session-aware loader and target registry. Domain services do not create duplicate stores, caches, sessions, transactions or policies.

See [`SERVICE_DECOMPOSITION.md`](SERVICE_DECOMPOSITION.md) for the intentionally small statement of the internal service-boundary policy.

## Shared state

One server instance owns one instance of each stateful dependency:

```text
DipTraceService
├── Settings / Policy
├── DocumentGateway
├── ModelCache
├── SessionStore
├── TransactionStore
├── PlanStore
├── FindingStore
├── JobStore / ExternalJobManager
├── ExportStore
├── BackupStore
├── RawPreviewStore (lazy)
├── TrustedProvenanceRegistry
└── domain services
```

Persistent records live below the configured state directory. Record stores validate identifiers and confined paths before reading or removing entries. Retention is count-and-age based and protects active, nonterminal, corrupt, redirected or otherwise unverifiable state.

## XML safety boundary

`src/diptrace_mcp/xml_document.py` owns the core file-safety rules:

- bounded document reads;
- root/source-type validation;
- rejection of `DOCTYPE` and `ENTITY` declarations;
- source encoding, BOM and line-ending detection;
- exact match-count guards;
- bounded raw and semantic edits;
- preservation of supported encodings outside targeted regions;
- reparse/semantic checks after modification;
- SHA-256 binding, bounded diffs, backups and atomic replacement.

Unsupported or ambiguous input fails closed. Non-finite numeric values are rejected before entering geometry, rules or comparison logic.

## Normalized models and cache

Adapters and inspectors convert supported PCB, schematic, Component Library and Pattern Library XML into typed domain models. Unknown sections remain available through bounded XML-fragment reads and are preserved by targeted edits.

`ModelCache` keys snapshots by resolved path, source SHA-256 and live-session state. It enforces entry and estimated-byte budgets; an oversized snapshot can be returned to the current caller without being retained.

## Creation and semantic writes

Synthetic scaffolding follows project-owned observations and does not imply compatibility with every DipTrace version. Seed-based creation copies a real user-supplied DipTrace-shaped XML file while preserving unknown content and provenance constraints. Neither path grants high trust automatically.

High-level writes follow the same guarded sequence:

```text
load exact source bytes
  -> validate policy and source SHA
  -> parse typed operations
  -> build modified bytes
  -> reparse and run bounded checks
  -> compute conservative write impact
  -> preview / transaction record
  -> require expected SHA at commit
  -> backup existing bytes
  -> atomic replacement
  -> update provenance/trust state
```

Transactions persist snapshots and metadata for preview, validation, commit, rollback and recovery. Conflict-checked rollback is the only write-impact restoration exemption and still passes the active policy.

## Review, placement and routing

Review services persist structured findings and explicit skipped/partial status instead of converting unavailable geometry or rules into a clean result. The implementation matrix is documented in [`REVIEW_ENGINE.md`](REVIEW_ENGINE.md).

Placement and routing provide bounded helpers such as deterministic silkscreen/placement plans, trace/via primitives, multi-layer 45-degree A*, congestion-aware multi-net routing and differential-pair routing. They are not a full global placer, push-and-shove router or free-angle EDA engine.

## External tools

Freerouting, ngspice and openEMS use server-selected command vectors and a shared bounded runner. Processes start with `shell=false`, run in isolated job directories, continuously drain bounded output tails and share one concurrency budget.

POSIX jobs use process groups for timeout/cancellation cleanup. Windows jobs use Job Objects with kill-on-close semantics and explicit root-process reaping.

## Windows live bridge

`src/diptrace_mcp/bridge.py` is compiled into `diptrace_mcp_bridge.exe`. DipTrace invokes it with a temporary exchange XML path and waits for the process to exit.

The bridge copies the source into session state, records the native exchange path and original SHA-256, and remains active while MCP operations inspect or modify `working.xml`. Applying a session revalidates the working SHA, exchange path, original exchange SHA and write impact before replacement. Cancel exits without replacing the exchange XML.

Windows-origin paths remain in Windows syntax in persisted metadata. A WSL server derives `/mnt/<drive>/...` only in memory. Persisting a translated WSL path into Windows-origin metadata is invalid and fails closed.

The executable plug-in protocol has no explicit DipTrace-host acknowledgement after process exit, so local finalization never claims host confirmation it cannot prove.

## Safety invariants

1. Caller-controlled paths remain inside configured allowed roots.
2. XML root/source type cannot be silently replaced.
3. Raw edits require exact match counts.
4. `dry_run=true` is the default where exposed.
5. Commit/apply requires the caller-observed SHA-256.
6. Existing targets are backed up before replacement.
7. Persistent JSON/XML writes use same-directory temporary files and atomic replacement.
8. Live apply rechecks working SHA, exchange path, original SHA and write impact.
9. Explicit cancel leaves exchange XML unchanged.
10. User-controlled evidence cannot grant package-owned high trust.
11. Streamable HTTP is intended for loopback use; OAuth and multi-user isolation are not implemented.

## Evidence boundary

Controlled live evidence covers selected workflows, not universal DipTrace compatibility. Unresolved evidence gaps remain explicit in capability/status data and `docs/OPEN_QUESTIONS.md`. Trust, provenance and compliance gates are safety properties rather than cleanup targets.

## Packaging boundary

The Python wheel contains the MCP server and packaged skills. Complete Windows live integration additionally requires the bridge and associated configuration/installer assets. Build/release policy is documented in the release and packaging documents rather than duplicated here.
