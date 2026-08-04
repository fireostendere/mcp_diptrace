# `DipTraceService` decomposition map

Status: phase-one inventory prepared from `main` at
`1e1e8b7402533297795207ce2452b85eaea2e36c` (2026-08-04). This document is an
implementation map, not a claim that the monolith has already been fully
refactored.

## Baseline

| Metric | Value |
| --- | --- |
| `service.py` lines | 7,849 |
| `service.py` bytes | 311,147 |
| `DipTraceService` methods (including private helpers and `__init__`) | 197 |
| Registered MCP tools | 159 |
| Python | 3.12.3 |
| MCP SDK | 1.29.0 |
| Full baseline tests | 1,062 passed, 4 skipped |

The baseline suite passed on the exact base above. The four skips are native
Windows/PowerShell cases. Any baseline command that exercises AnyIO threads
must run outside the restricted execution namespace; a minimal
`anyio.to_thread.run_sync` reproducer otherwise hangs in that namespace.

## Dependency ownership

The current server instance owns one instance of every stateful store. Domain
services must receive those exact instances and must never construct stores or
caches themselves.

```text
DipTraceService (public MCP Facade; top-level assembly)
├── Settings
├── Policy
├── SessionStore ─────────────── live-session state and working XML
├── TransactionStore ─────────── transaction state, snapshots, backups, previews
├── PlanStore ────────────────── placement/silkscreen plans
├── FindingStore ─────────────── review reports and findings
├── JobStore ─────────────────── external-job state
├── ExportStore ──────────────── export metadata and artifacts
├── BackupStore ──────────────── write backups
├── ExternalJobManager ───────── process adapters over JobStore
├── ModelCache ───────────────── normalized document snapshots
├── RawPreviewStore (lazy) ───── bounded raw XML preview state
├── TrustedProvenanceRegistry ── package-owned trust authority
├── DocumentGateway ───────────── one target registry and document loader
└── domain services
    ├── DocumentService (phase one)
    ├── BomService (phase one)
    └── ReviewService (phase one)
```

`ServiceContext` is intentionally narrow. Phase one shares `Settings`,
`Policy`, `ModelCache`, `TransactionStore`, `SessionStore`, and `FindingStore`.
The gateway owns the single mutable document-target registry. The Facade keeps
the existing attribute names (`settings`, `policy`, `models`, `transactions`,
`sessions`, and so on) for compatibility while passing those same objects to
the services.

### Shared mutable state

* `SessionStore`, `TransactionStore`, `PlanStore`, `FindingStore`, `JobStore`,
  `ExportStore`, and `BackupStore` persist records under the one configured
  state directory and have their own synchronization/retention rules.
* `ExternalJobManager` shares `JobStore` and controls the configured external
  process budget; it is not recreated by a domain call.
* `ModelCache` is the sole normalized-snapshot cache. A service may read it,
  but may not replace it or maintain a second cache.
* `DocumentGateway.targets` is the sole document-id-to-target map for a server
  instance. It preserves the current `load()` registration behavior.
* `RawPreviewStore` is created only on first raw-preview access, as before.
* `_workflow_prompt_names` is assembled by the concrete server and is not
  domain state. The embedded provenance registry is package-owned authority,
  not workspace state.

### Boundary decisions

* `DocumentGateway` is neutral infrastructure for path resolution, live-session
  target resolution, loading, and document-id lookup. It does not perform
  trust authorization, writes, transactions, or response conversion.
* `DocumentService` owns read-only normalized document models, object queries,
  inspector read models, connectivity, XML fragments, and document resources.
* `BomService` owns library metadata reads and BOM extraction/review/query
  logic. Export artifact creation remains in the Facade for a later exports
  phase because it mutates the export store.
* `ReviewService` owns registered read-only review execution and finding reads.
  Review execution still persists its report in the shared `FindingStore`; this
  existing state side effect is explicitly retained.
* Trust/evidence resolution, transactions, semantic writes, routing, external
  jobs, placement plans, testpoint writes, and live-session lifecycle remain
  in the Facade for later phases because their safety boundaries cross several
  stores or depend on SHA/lease/atomic-write ordering.

## Complete method inventory

The columns use the following compact dependency notation: `S` Settings, `P`
Policy, `MC` ModelCache, `SS` SessionStore, `TS` TransactionStore, `PS`
PlanStore, `FS` FindingStore, `JS` JobStore, `ES` ExportStore, `BS`
BackupStore, `EJM` ExternalJobManager, `TPR` TrustedProvenanceRegistry, `GW`
DocumentGateway, and `RF` pure domain algorithms. `R` means read-only with
respect to design bytes (a report/store write is called out in side effects),
`M` means mutating, and `I` means internal/lifecycle. “Caller” names the MCP
tool where one exists; otherwise it names the internal caller or `—`.

| Method | Lines | Status | MCP tool/caller | R/M | Stores/dependencies | Private helpers | Document types | Side effects | Exceptions | Tx/SHA | Live session | External process | Thread-safety | Proposed target | Phase | Risk |
| --- | ---: | --- | --- | :---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `__init__` | 1098–1127 | internal | server construction | I | S, P, all stores, MC, TPR | — | all | assembles one instance of each dependency | configuration/store errors | — | creates session manager | no | instance-owned state | Facade assembly | 1 | low |
| `raw_previews` | 1130–1138 | internal | raw preview methods | I | S, raw-preview store | — | XML | lazy store creation | filesystem errors | — | no | no | lazy initialization | Shared infrastructure | 1 | low |
| `set_workflow_prompt_names` | 1140–1143 | internal | server prompt registration | M | — | — | — | replaces prompt-name tuple | `—` | — | no | no | server startup only | Facade assembly | later | low |
| `_load_seed_provenance` | 1145–1158 | internal | evidence/create paths | I | TPR, S | — | seed files | reads sidecar | document/evidence errors | SHA read | no | no | read-only | EvidenceService | 3 | medium |
| `_load_and_validate_evidence_manifest` | 1160–1341 | internal | evidence paths | R | S, TPR | `_fail_closed_trust`, path helpers | PCB/schematic | reads and validates manifest | evidence/document errors | SHA-bound | no | no | read-only | EvidenceService | 3 | high |
| `_load_and_authorize_trusted_registry_evidence` | 1343–1377 | internal | trust resolver | R | TPR, S | manifest helpers | PCB/schematic | authorization read | registry/evidence errors | SHA-bound | no | no | read-only | EvidenceService | 3 | high |
| `_write_provenance_sidecar` | 1379–1386 | internal | write/trust paths | M | S | atomic helper | all | writes provenance metadata | filesystem/edit errors | SHA-bound | maybe | no | serialized file write | EvidenceService | 3 | high |
| `resolve_effective_document_trust` | 1388–1518 | internal | document_info/writes | R | S, TPR | evidence helpers | PCB/schematic/library | fail-closed trust read | evidence/document errors | SHA-bound | maybe | no | read-only | EvidenceService | 3 | high |
| `invalidate_document_trust_after_write` | 1520–1538 | internal | semantic/raw writes | M | S, TPR | `_invalidated_document_provenance`, sidecar write | all | downgrades trust and writes sidecar | edit/filesystem errors | SHA-bound | maybe | no | serialized write | EvidenceService | 3 | high |
| `_invalidated_document_provenance` | 1540–1563 | internal | trust invalidation | I | TPR, S | `_load_seed_provenance` | all | builds provenance only | evidence errors | SHA input | no | no | read-only | EvidenceService | 3 | medium |
| `resolve_target` | 1565–1586 | internal | `load` | R | S, SS | — | all/live | resolves allowed or live path | object/session/path errors | — | yes | no | SS synchronized | DocumentGateway | 1 | medium |
| `load` | 1588–1592 | internal | all document methods | R | S, SS, MC/GW | `resolve_target` | all | registers target in map | object/document errors | source SHA read | yes | no | cache shared | DocumentGateway | 1 | medium |
| `_load_overwrite_target` | 1594–1626 | internal | creation writers | R | S | SHA helpers | all | reads overwrite candidate | edit/confirmation/SHA errors | required SHA | maybe | no | read-only | Transaction/write core | 3 | high |
| `_require_current_target_sha256` | 1629–1647 | internal | write paths | R | filesystem | — | all | reads current bytes | edit/SHA errors | critical SHA gate | maybe | no | race-sensitive | Transaction/write core | 3 | high |
| `_require_target_still_absent` | 1650–1659 | internal | creation writers | R | filesystem | — | all | checks absence | edit errors | target race | no | no | race-sensitive | Transaction/write core | 3 | high |
| `_read_optional_transaction_file` | 1662–1681 | internal | transaction recovery | R | TS | — | XML/sidecar | reads transaction file | transaction conflict | SHA computed | no | no | TS synchronized | TransactionService | 3 | high |
| `_require_optional_transaction_file_unchanged` | 1684–1707 | internal | transaction recovery | R | TS | previous helper | XML/sidecar | verifies bytes unchanged | transaction conflict | SHA-bound | no | no | race-sensitive | TransactionService | 3 | high |
| `_compensate_transaction_file` | 1710–1773 | internal | transaction recovery | M | TS | optional-file helpers | XML/sidecar | conditional restore/delete | transaction conflict/filesystem | SHA-bound | no | no | race-sensitive | TransactionService | 3 | critical |
| `_load_transaction_backup_bytes` | 1775–1808 | internal | rollback | R | TS | SHA helper | XML | reads and verifies backup | transaction conflict | backup SHA | maybe | no | TS synchronized | TransactionService | 3 | critical |
| `load_document_id` | 1810–1826 | internal | resource methods | R | GW, S | — | all | reads registered target | document errors | current SHA read | yes | no | target-map read | DocumentGateway | 1 | medium |
| `status` | 1828–1847 | public | `diptrace_status` | R | S, SS, MC, `get_capabilities` | — | all/live | reads status/capabilities | session/document errors | — | yes | adapter probes only | store reads | Facade | later | medium |
| `get_capabilities` | 1849–1892 | public | `get_capabilities` | R | S, P, SS, TPR | `_add_runtime_capabilities` | all | probes availability | capability/config errors | — | yes | probes external tools | read-only | Facade | later | medium |
| `trusted_provenance_registry_report` | 1894–1897 | public/internal | capability/trust callers | R | TPR | — | all | none | registry errors | — | no | no | read-only | EvidenceService | 3 | low |
| `_add_runtime_capabilities` | 1899–1953 | internal | `get_capabilities` | R | S, P, SS | — | all | probes configured adapters | capability errors | — | yes | adapter probes | read-only | Facade | later | medium |
| `document_info` | 1955–1970 | public | `get_document_info` | R | GW, MC, trust state | `load`, trust resolver, `_read_success` | all | none | document/trust errors | source SHA | yes | no | cache synchronized | DocumentService (trust callback) | 1 | medium |
| `board_model` | 1972–2107 | public | `get_board_model` | R | GW, MC | `_validate_page`, `_bounded_board_item`, `_read_success` | PCB | none; bounded response | document/validation errors | source SHA | yes | no | MC synchronized | DocumentService | 1 | low |
| `schematic_model` | 2109–2121 | public | `get_schematic_model` | R | GW, MC | `_read_success` | schematic | none | document errors | source SHA | yes | no | MC synchronized | DocumentService | 1 | low |
| `library_model` | 2123–2131 | public | `get_library_model` | R | GW, MC, RF | `_read_success` | component/pattern library | none | document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `scan_component_libraries` | 2133–2136 | public | `scan_component_libraries` | R | S | `_scan_libraries`, `scan_documents` | component library | reads directory | path/document errors | — | no | no | read-only | DiscoveryService | 3 | medium |
| `scan_pattern_libraries` | 2138–2141 | public | `scan_pattern_libraries` | R | S | `_scan_libraries`, `scan_documents` | pattern library | reads directory | path/document errors | — | no | no | read-only | DiscoveryService | 3 | medium |
| `query_library_items` | 2143–2164 | public | `query_library_items` | R | GW, MC, RF | `_validate_page`, `_read_success` | component/pattern library | none | document/library/validation errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `get_library_component` | 2166–2172 | public | `get_library_component` | R | GW, MC, RF | `_get_library_item` | component library | none | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `get_library_pattern` | 2174–2180 | public | `get_library_pattern` | R | GW, MC, RF | `_get_library_item` | pattern library | none | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `validate_library_component` | 2182–2188 | public | `validate_library_component` | R | GW, MC, RF | `_validate_library_item` | component library | none | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `validate_library_pattern` | 2190–2196 | public | `validate_library_pattern` | R | GW, MC, RF | `_validate_library_item` | pattern library | none | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `validate_pin_pad_mapping` | 2198–2215 | public | `validate_pin_pad_mapping` | R | GW, MC, RF | `_validate_library_item` | component library | filters findings | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `get_bom` | 2217–2239 | public | `get_bom` | R | GW, MC, RF | `_read_success` | PCB/schematic | none | document/BOM errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `export_bom` | 2241–2255 | public | `export_bom` | R* | GW, MC, ES | export helpers | PCB/schematic | writes export record/artifacts | document/export/filesystem | source SHA | yes | no | ES synchronized | ExportService | 3 | medium |
| `export_fabrication_outputs` | 2257–2274 | public | `export_fabrication_outputs` | R* | ES, GW, MC | `_export_release_manifest` | PCB | writes manifest artifacts | capability/document/export | source SHA | yes | no | ES synchronized | ExportService | 3 | medium |
| `export_assembly_outputs` | 2276–2293 | public | `export_assembly_outputs` | R* | ES, GW, MC | `_export_release_manifest` | PCB | writes manifest artifacts | capability/document/export | source SHA | yes | no | ES synchronized | ExportService | 3 | medium |
| `_export_release_manifest` | 2295–2315 | internal | export methods | M | ES, GW, MC | `_read_success` | PCB | persists export manifest | document/export/filesystem | source SHA | yes | no | ES synchronized | ExportService | 3 | medium |
| `review_bom` | 2317–2323 | public | `review_bom` | R | GW, MC, RF | `_read_success` | PCB/schematic | none | document/BOM errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `compare_bom_to_design` | 2325–2336 | public | `compare_bom_to_design` | R | GW, MC, RF | `_read_success` | PCB/schematic | none | document/BOM/validation | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `find_missing_component_fields` | 2338–2368 | public | `find_missing_component_fields` | R | GW, MC, RF | `_read_success` | PCB/schematic | none | document/validation | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `group_bom` | 2370–2376 | public | `group_bom` | R | BomService | `get_bom` | PCB/schematic | none | document/BOM errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `detect_duplicate_bom_items` | 2378–2386 | public | `detect_duplicate_bom_items` | R | BomService | `get_bom` | PCB/schematic | none | document/BOM errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `validate_mpn_consistency` | 2388–2396 | public | `validate_mpn_consistency` | R | BomService | `review_bom` | PCB/schematic | none | document/BOM errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `validate_value_pattern_consistency` | 2398–2406 | public | `validate_value_pattern_consistency` | R | BomService | `review_bom` | PCB/schematic | none | document/BOM errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `compare_schematic_to_pcb` | 2408–2421 | public | `compare_schematic_to_pcb` | R | GW, MC, RF | `_read_success` | schematic + PCB | none | document/compare errors | source SHA | yes | no | MC synchronized | ReviewService | 2 | low |
| `sync_schematic_to_pcb` | 2423–2473 | public | `sync_schematic_to_pcb` | M | GW, MC, TS, SS | `load`, semantic/write helpers | schematic + PCB | plans/applies component changes | sync/SHA/transaction errors | expected SHA/tx | yes | no | locks and stores | SynchronizationService | 3 | high |
| `query_objects` | 2475–2495 | public | `query_objects` | R | GW, MC, RF | `_read_success` | all normalized docs | none | validation/document errors | source SHA | yes | no | MC synchronized | DocumentService | 1 | low |
| `get_object` | 2497–2507 | public | `get_object` | R | GW, MC, RF | `_read_success` | all normalized docs | none | object/document errors | source SHA | yes | no | MC synchronized | DocumentService | 1 | low |
| `get_connectivity_graph` | 2509–2518 | public | `get_connectivity_graph` | R | GW, MC, RF | `_read_success` | PCB/schematic | none | document/connectivity errors | source SHA | yes | no | MC synchronized | DocumentService | 1 | low |
| `document_resource` | 2520–2541 | public | MCP resource reader | R | GW, MC, RF | `load_document_id` | all | none | document/resource errors | source SHA | yes | no | MC synchronized | DocumentService | 1 | low |
| `transaction_summary_resource` | 2543–2548 | public/internal | MCP resource reader | R | TS | transaction summary helper | transaction | none | transaction errors | tx id/SHA fields | no | no | TS synchronized | TransactionService | 3 | medium |
| `raw_preview_diff_resource` | 2550–2551 | public/internal | MCP resource reader | R | raw-preview store | `raw_previews` | XML | none | preview/store errors | preview SHA | no | no | store synchronized | XMLPreviewService | 3 | medium |
| `summarize` | 2553–2555 | public | `summarize_design` | R | GW, RF | `load` | all | none | document errors | source SHA | yes | no | read-only | DocumentService | 1 | low |
| `components` | 2557–2569 | public | `list_components` | R | GW, RF | `_validate_page`, `load` | PCB/schematic | none | document/validation | source SHA | yes | no | read-only | DocumentService | 1 | low |
| `component` | 2571–2578 | public | `get_component` | R | GW, RF | `load` | PCB/schematic | none | document/object errors | source SHA | yes | no | read-only | DocumentService | 1 | low |
| `nets` | 2580–2600 | public | `list_nets` | R | GW, RF | `_validate_page`, `load` | PCB/schematic | none | document/validation | source SHA | yes | no | read-only | DocumentService | 1 | low |
| `rules` | 2602–2607 | public | `get_design_rules` | R | GW, RF | `load` | PCB | none | document errors | source SHA | yes | no | read-only | DocumentService | 1 | low |
| `read_xml` | 2609–2633 | public | `read_xml_fragment` | R | GW | `load` | XML | bounded fragment read | document/validation errors | source SHA | yes | no | read-only | DocumentService | 1 | low |
| `apply_edits` | 2635–2778 | public | `apply_xml_edits` | M | GW, TS, SS, BS, TPR | write/SHA helpers | all XML | guarded XML write/preview | edit/SHA/policy errors | critical expected SHA | yes | no | serialized write | SemanticWriteService | 3 | critical |
| `create_document` | 2780–2874 | public | document creation tools | M | GW, TS, BS, TPR | overwrite/SHA/trust helpers | PCB/schematic | creates/replaces XML | creation/SHA/trust errors | overwrite SHA | yes | no | atomic write | ScaffoldingService | 3 | high |
| `create_document_from_seed` | 2876–3060 | public | `create_document_from_seed` | M | GW, TS, BS, TPR | evidence/SHA helpers | all | creates from seed | creation/evidence/SHA errors | seed/target SHA | yes | no | atomic write | ScaffoldingService | 3 | critical |
| `begin_transaction` | 3062–3118 | public | `begin_transaction` | M | GW, TS, SS, BS | write/SHA helpers | all | creates transaction record/snapshot | transaction/SHA errors | captures source SHA | yes | no | no process | TransactionService | 3 | critical |
| `stage_operations` | 3120–3158 | public | `stage_operations` | M | TS, GW | operation parsers | all | persists staged operations | transaction/validation | tx source SHA | maybe | no | TS synchronized | TransactionService | 3 | critical |
| `preview_transaction` | 3160–3249 | public | `preview_transaction` | R* | TS, MC, GW | preview/transaction helpers | all | persists preview resources | transaction/document errors | tx/source SHA | maybe | no | TS/MC synchronized | TransactionService | 3 | high |
| `validate_transaction` | 3251–3252 | public | `validate_transaction` | R* | TS, GW | transaction helpers | all | persists validation state | transaction/validation | tx/source SHA | maybe | no | TS synchronized | TransactionService | 3 | high |
| `commit_transaction` | 3254–3528 | public | `commit_transaction` | M | TS, SS, BS, TPR | all write/SHA helpers | all | atomic/guarded commit | transaction/SHA/policy | critical expected SHA | yes | no | locks/atomic write | TransactionService | 3 | critical |
| `_synthetic_rollback_provenance_bytes` | 3531–3542 | internal | rollback | I | TPR | — | all | builds bytes only | provenance errors | SHA input | no | no | read-only | TransactionService | 3 | high |
| `_prepare_rollback_provenance_bytes` | 3544–3586 | internal | rollback | I | TPR, S | provenance helpers | all | reads/builds sidecar | trust errors | SHA input | no | no | read-only | TransactionService | 3 | high |
| `_transaction_file_sha256` | 3589–3593 | internal | rollback | R | filesystem | — | XML/sidecar | reads file SHA | OSError | SHA computation | no | no | read-only | TransactionService | 3 | medium |
| `_compensate_rollback_files` | 3595–3654 | internal | rollback | M | TS, BS | transaction file helpers | XML/sidecar | conditionally restores files | transaction/filesystem | SHA-bound | maybe | no | race-sensitive | TransactionService | 3 | critical |
| `rollback_transaction` | 3656–3842 | public | `rollback_transaction` | M | TS, SS, BS, TPR | rollback helpers | all | restores source/sidecar | transaction/SHA/policy | critical SHA | yes | no | locks/atomic write | TransactionService | 3 | critical |
| `list_transactions` | 3844–3850 | public | `list_transactions` | R | TS | transaction summary helper | all | retention read/prune | transaction errors | tx SHA fields | no | no | TS synchronized | TransactionService | 3 | low |
| `_evaluate_roundtrip_evidence` | 3852–4003 | internal | evidence tools | R | S, TPR | semantic comparison helpers | all supported | reads evidence | evidence/validation errors | SHA-bound | no | no | read-only | EvidenceService | 3 | high |
| `_semantic_evidence_record` | 4006–4029 | internal | evidence tools | I | — | — | all | builds model only | validation errors | SHA data | no | no | read-only | EvidenceService | 3 | medium |
| `_require_evidence_evaluation_unchanged` | 4031–4089 | internal | record evidence | R | filesystem | evidence helpers | all | rechecks evidence bytes | evidence conflict | SHA-bound | no | no | race-sensitive | EvidenceService | 3 | critical |
| `_evidence_manifest_path` | 4092–4093 | internal | evidence tools | I | — | — | all | path calculation only | — | — | no | no | read-only | EvidenceService | 3 | low |
| `_evidence_sidecar_path` | 4096–4097 | internal | evidence tools | I | — | — | all | path calculation only | — | — | no | no | read-only | EvidenceService | 3 | low |
| `_require_evidence_output_paths_safe` | 4100–4123 | internal | record evidence | R | S | path helpers | all | validates output destinations | path/evidence errors | — | no | no | race-sensitive | EvidenceService | 3 | high |
| `_roundtrip_evidence_response` | 4125–4186 | internal | evidence tools | I | — | bounded response helpers | all | builds bounded result | validation errors | SHA metadata | no | no | read-only | EvidenceService | 3 | medium |
| `validate_roundtrip_evidence` | 4188–4210 | public | `validate_roundtrip_evidence` | R | S, TPR | evidence helpers | all supported | no design write | evidence/validation | source/evidence SHA | no | no | read-only | EvidenceService | 3 | medium |
| `record_roundtrip_evidence` | 4212–4299 | public | `record_roundtrip_evidence` | M* | S, TPR | evidence helpers | all supported | writes manifest/sidecar metadata | evidence/path/filesystem | SHA-bound | no | no | atomic metadata write | EvidenceService | 3 | high |
| `move_components` | 4301–4326 | public | `move_components` | M | TS, SS, GW | semantic write helpers | PCB/schematic | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_component_value` | 4328–4338 | public | `set_component_value` | M | TS, SS, GW | semantic write helpers | PCB/schematic | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `rotate_components` | 4340–4361 | public | `rotate_components` | M | TS, SS, GW | semantic write helpers | PCB/schematic | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_component_side` | 4363–4376 | public | `set_component_side` | M | TS, SS, GW | semantic write helpers | PCB | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_component_lock` | 4378–4390 | public | `set_component_lock` | M | TS, SS, GW | semantic write helpers | PCB/schematic | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_component_properties` | 4392–4416 | public | `set_component_properties` | M | TS, SS, GW | semantic write helpers | PCB/schematic | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_component_pattern` | 4418–4436 | public | `set_component_pattern` | M | TS, SS, GW | semantic write helpers | PCB/schematic | component write/preview | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `align_components` | 4438–4505 | public | `align_components` | M | MC, TS, SS | placement/semantic helpers | PCB | component write/preview | placement/SHA/policy | expected SHA | yes | no | guarded write | PlacementService | 3 | high |
| `distribute_components` | 4507–4598 | public | `distribute_components` | M | MC, TS, SS | placement/semantic helpers | PCB | component write/preview | placement/SHA/policy | expected SHA | yes | no | guarded write | PlacementService | 3 | high |
| `group_components` | 4600–4618 | public | `group_components` | M | TS, SS, GW | semantic write helpers | PCB | component group write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `ungroup_components` | 4620–4638 | public | `ungroup_components` | M | TS, SS, GW | semantic write helpers | PCB | component group write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `list_board_texts` | 4640–4652 | public | `list_board_texts` | R | GW, MC | query helpers | PCB | none | document errors | source SHA | yes | no | MC synchronized | TextService | 3 | low |
| `move_board_texts` | 4654–4678 | public | `move_board_texts` | M | TS, SS, GW | semantic write helpers | PCB | text write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `rotate_board_texts` | 4680–4699 | public | `rotate_board_texts` | M | TS, SS, GW | semantic write helpers | PCB | text write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_text_visibility` | 4701–4718 | public | `set_text_visibility` | M | TS, SS, GW | semantic write helpers | PCB | text write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_text_style` | 4720–4746 | public | `set_text_style` | M | TS, SS, GW | semantic write helpers | PCB | text write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_pin_no_connect` | 4748–4760 | public | `set_pin_no_connect` | M | TS, SS, GW | semantic write helpers | schematic | pin write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `rename_net` | 4762–4774 | public | `rename_net` | M | TS, SS, GW | semantic write helpers | PCB/schematic | net write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `add_sheet` | 4776–4786 | public | `add_sheet` | M | TS, SS, GW | semantic write helpers | schematic | sheet write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `place_part` | 4788–4828 | public | `place_part` | M | TS, SS, GW | semantic write helpers | schematic | part write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `connect_pins` | 4830–4843 | public | `connect_pins` | M | TS, SS, GW | semantic write helpers | schematic | connectivity write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `disconnect_pins` | 4845–4854 | public | `disconnect_pins` | M | TS, SS, GW | semantic write helpers | schematic | connectivity write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `add_wire` | 4856–4879 | public | `add_wire` | M | TS, SS, GW | semantic write helpers | schematic | wire write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `delete_wire` | 4881–4890 | public | `delete_wire` | M | TS, SS, GW | semantic write helpers | schematic | wire delete | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `add_net_label` | 4892–4915 | public | `add_net_label` | M | TS, SS, GW | semantic write helpers | schematic | label write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `set_panelization` | 4917–4926 | public | `set_panelization` | M | TS, SS, GW | semantic write helpers | PCB | panelization write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `clear_panelization` | 4928–4936 | public | `clear_panelization` | M | TS, SS, GW | semantic write helpers | PCB | panelization write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `update_net_class_rules` | 4938–4976 | public | `update_net_class_rules` | M | TS, SS, GW | semantic write helpers | PCB | rules write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `assign_nets_to_class` | 4978–4990 | public | `assign_nets_to_class` | M | TS, SS, GW | semantic write helpers | PCB | net-class write | edit/policy/SHA | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | high |
| `list_testpoints` | 4992–5016 | public | `list_testpoints` | R | GW, MC | query helpers | PCB | none | document/validation | source SHA | yes | no | MC synchronized | TestpointService | 3 | low |
| `find_testpoint_candidates` | 5018–5129 | public | `find_testpoint_candidates` | R | GW, MC, RF | query/geometry helpers | PCB | none | document/geometry | source SHA | yes | no | MC synchronized | TestpointService | 3 | medium |
| `add_testpoints` | 5131–5142 | public | `add_testpoints` | M | TS, SS, GW | semantic write helpers | PCB | testpoint write | edit/policy/SHA | expected SHA | yes | no | guarded write | TestpointService | 3 | high |
| `move_testpoints` | 5144–5170 | public | `move_testpoints` | M | TS, SS, GW | semantic write helpers | PCB | testpoint write | edit/policy/SHA | expected SHA | yes | no | guarded write | TestpointService | 3 | high |
| `remove_testpoints` | 5172–5184 | public | `remove_testpoints` | M | TS, SS, GW | semantic write helpers | PCB | testpoint delete | edit/policy/SHA | expected SHA | yes | no | guarded write | TestpointService | 3 | high |
| `review_testpoint_coverage` | 5186–5215 | public | `review_testpoint_coverage` | R | GW, MC, RF | query helpers | PCB | none | document/validation | source SHA | yes | no | MC synchronized | ReviewService (later) | 2 | medium |
| `add_trace` | 5217–5243 | public | `add_trace` | M | TS, SS, GW | routing/write helpers | PCB | trace write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `replace_trace` | 5245–5267 | public | `replace_trace` | M | TS, SS, GW | routing/write helpers | PCB | trace replace | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `delete_trace` | 5269–5285 | public | `delete_trace` | M | TS, SS, GW | routing/write helpers | PCB | trace delete | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `set_trace_width` | 5287–5305 | public | `set_trace_width` | M | TS, SS, GW | routing/write helpers | PCB | trace write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `add_via` | 5307–5331 | public | `add_via` | M | TS, SS, GW | routing/write helpers | PCB | via write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `move_via` | 5333–5355 | public | `move_via` | M | TS, SS, GW | routing/write helpers | PCB | via write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `delete_via` | 5357–5367 | public | `delete_via` | M | TS, SS, GW | routing/write helpers | PCB | via delete | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `set_via_style` | 5369–5382 | public | `set_via_style` | M | TS, SS, GW | routing/write helpers | PCB | via style write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `list_unrouted_connections` | 5384–5442 | public | `list_unrouted_connections` | R | GW, MC, RF | routing helpers | PCB | none | document/routing errors | source SHA | yes | no | MC synchronized | RoutingAnalysisService | 2 | medium |
| `get_route_details` | 5444–5513 | public | `get_route_details` | R | GW, MC, RF | routing helpers | PCB | none | document/routing errors | source SHA | yes | no | MC synchronized | RoutingAnalysisService | 2 | medium |
| `get_stackup` | 5515–5530 | public | `get_stackup` | R | GW, MC | `_read_success` | PCB | none | document errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | low |
| `measure_net_lengths` | 5532–5563 | public | `measure_net_lengths` | R | GW, MC, RF | `_read_success` | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `analyze_length_group` | 5565–5593 | public | `analyze_length_group` | R | GW, MC, RF | `_read_success` | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `list_differential_pairs` | 5595–5616 | public | `list_differential_pairs` | R | GW, MC, RF | `_read_success` | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `get_differential_pair` | 5618–5622 | public | `get_differential_pair` | R | GW, MC, RF | pair resolver | PCB | none | document/object errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `analyze_differential_pair` | 5624–5635 | public | `analyze_differential_pair` | R | GW, MC, RF | pair resolver | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `analyze_differential_pairs` | 5637–5664 | public | `analyze_differential_pairs` | R | GW, MC, RF | pair resolver | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `validate_differential_pair` | 5666–5681 | public | `validate_differential_pair` | R | GW, MC, RF | pair resolver | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `calculate_impedance` | 5683–5722 | public | `calculate_impedance` | R | S, RF | impedance helpers | PCB | none | validation/capability errors | — | no | no | read-only | SignalIntegrityService | 2 | low |
| `suggest_trace_geometry_for_impedance` | 5724–5755 | public | `suggest_trace_geometry_for_impedance` | R | S, RF | impedance helpers | PCB | none | validation/capability errors | — | no | no | read-only | SignalIntegrityService | 2 | low |
| `analyze_stackup_for_impedance` | 5757–5768 | public | `analyze_stackup_for_impedance` | R | GW, MC, RF | `_read_success` | PCB | none | document/impedance errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | low |
| `validate_impedance_constraints` | 5770–5892 | public | `validate_impedance_constraints` | R | GW, MC, RF | impedance helpers | PCB | none | document/impedance errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `analyze_controlled_impedance_nets` | 5894–5900 | public | `analyze_controlled_impedance_nets` | R | GW, MC, RF | impedance helpers | PCB | none | document/impedance errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `list_copper_pours` | 5902–5926 | public | `list_copper_pours` | R | GW, MC | query helpers | PCB | none | document errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `analyze_plane_continuity` | 5928–5936 | public | `analyze_plane_continuity` | R | GW, MC, RF | return-path helpers | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `analyze_return_path` | 5938–5960 | public | `analyze_return_path` | R | GW, MC, RF | return-path helpers | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | SignalIntegrityService | 2 | medium |
| `route_connection` | 5962–6030 | public | `route_connection` | M | GW, MC, TS, SS | routing/write helpers | PCB | route write/transaction | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `route_net` | 6032–6115 | public | `route_net` | M | GW, MC, TS, SS | routing/write helpers | PCB | route write/transaction | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `route_diff_pair` | 6117–6178 | public | `route_diff_pair` | M | GW, MC, TS, SS | routing/write helpers | PCB | paired route write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `plan_diff_pair_route` | 6180–6266 | public | `plan_diff_pair_route` | R* | GW, MC, PS, RF | routing/plan helpers | PCB | persists route plan | plan/SHA errors | source SHA | yes | no | no | RoutingPlanningService | 3 | high |
| `plan_route_nets` | 6268–6406 | public | `plan_route_nets` | R* | GW, MC, PS, RF | `_unrouted_pairs` | PCB | persists route plan | routing/plan errors | source SHA | yes | no | no | RoutingPlanningService | 3 | high |
| `apply_route_plan` | 6408–6428 | public | `apply_route_plan` | M | PS, TS, SS, GW | semantic/write helpers | PCB | applies stored routes | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `export_autorouter_dsn` | 6430–6468 | public | `export_autorouter_dsn` | R* | GW, MC, ES | specctra/export helpers | PCB | writes DSN export | document/export errors | source SHA | yes | no | no | ExternalAdaptersService | 3 | high |
| `run_external_autorouter` | 6470–6521 | public | `run_external_autorouter` | M* | EJM, JS, S, GW | external job helpers | PCB | starts external job | external process/job errors | source SHA | maybe | yes | job manager synchronized | ExternalJobService | 3 | critical |
| `inspect_autorouter_result` | 6523–6610 | public | `inspect_autorouter_result` | R | S, GW | specctra helpers | PCB/SES | reads external artifact | external/document errors | source SHA | no | no | read-only | ExternalAdaptersService | 3 | high |
| `import_autorouter_ses` | 6612–6626 | public | `import_autorouter_ses` | M | GW, TS, SS | specctra/semantic helpers | PCB/SES | imports route operations | parse/SHA/transaction errors | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `route_connections` | 6628–6680 | public | `route_connections` | M | GW, MC, TS, SS | routing helpers | PCB | multi-net route write | routing/SHA/policy | expected SHA | yes | no | guarded write | RoutingService | 3 | critical |
| `analyze_routing_congestion` | 6682–6741 | public | `analyze_routing_congestion` | R | GW, MC, RF | routing helpers | PCB | none | document/routing errors | source SHA | yes | no | MC synchronized | RoutingAnalysisService | 2 | medium |
| `run_ngspice_simulation` | 6743–6792 | public | `run_ngspice_simulation` | M* | EJM, JS, S, GW | external job helpers | PCB | creates job and process | external job errors | source SHA | maybe | yes | job manager synchronized | ExternalJobService | 3 | high |
| `run_openems_stripline_analysis` | 6794–6853 | public | `run_openems_stripline_analysis` | M* | EJM, JS, S, GW | external job helpers | PCB | creates job and process | external job errors | source SHA | maybe | yes | job manager synchronized | ExternalJobService | 3 | high |
| `get_job_status` | 6855–6866 | public | `get_job_status` | R | JS, EJM | job helpers | external result | reads job | job errors | job/SHA metadata | no | maybe | JS synchronized | ExternalJobService | 3 | medium |
| `get_job_result` | 6868–6885 | public | `get_job_result` | R | JS, EJM | job helpers | external result | reads bounded result | job/errors | job/SHA metadata | no | maybe | JS synchronized | ExternalJobService | 3 | medium |
| `cancel_job` | 6887–6889 | public | `cancel_job` | M | JS, EJM | — | external result | cancels process/job | job/external errors | job id | no | yes | job manager synchronized | ExternalJobService | 3 | high |
| `list_jobs` | 6891–6908 | public | `list_jobs` | R | JS | job helpers | external result | reads job records | job errors | job metadata | no | no | JS synchronized | ExternalJobService | 3 | low |
| `list_exports` | 6910–6924 | public | `list_exports` | R | ES | export helpers | exports | reads export records | export errors | export SHA metadata | no | no | ES synchronized | ExportService | 3 | low |
| `export_resource` | 6926–6927 | public/internal | MCP resource reader | R | ES | — | exports | reads artifact | export errors | export SHA | no | no | ES synchronized | ExportService | 3 | medium |
| `job_resource` | 6929–6955 | public/internal | MCP resource reader | R | JS | job helpers | external result | reads resource | job errors | job SHA | no | maybe | JS synchronized | ExternalJobService | 3 | medium |
| `_unrouted_pairs` | 6958–6988 | internal | route planning | I | MC, RF | — | PCB | computes pairs only | routing/document errors | source SHA | yes | no | read-only | RoutingService | 3 | medium |
| `plan_silkscreen` | 6990–7059 | public | `plan_silkscreen` | R* | GW, MC, PS, RF | placement helpers | PCB | persists plan | plan/document errors | source SHA | yes | no | PS synchronized | PlacementService | 3 | high |
| `analyze_placement` | 7061–7081 | public | `analyze_placement` | R | GW, MC, RF | placement helpers | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | PlacementService | 2 | medium |
| `generate_placement_candidates` | 7083–7101 | public | `generate_placement_candidates` | R | GW, MC, RF | placement helpers | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | PlacementService | 2 | medium |
| `score_placement` | 7103–7125 | public | `score_placement` | R | GW, MC, RF | placement helpers | PCB | none | document/geometry errors | source SHA | yes | no | MC synchronized | PlacementService | 2 | medium |
| `plan_component_placement` | 7127–7207 | public | `plan_component_placement` | R* | GW, MC, PS, RF | placement helpers | PCB | persists plan | plan/document errors | source SHA | yes | no | PS synchronized | PlacementService | 3 | high |
| `apply_component_placement_plan` | 7209–7223 | public | `apply_component_placement_plan` | M | PS, TS, SS, GW | `_apply_stored_plan` | PCB | applies stored placement | placement/SHA/policy | expected SHA | yes | no | guarded write | PlacementService | 3 | critical |
| `apply_silkscreen_plan` | 7225–7239 | public | `apply_silkscreen_plan` | M | PS, TS, SS, GW | `_apply_stored_plan` | PCB | applies stored text changes | placement/SHA/policy | expected SHA | yes | no | guarded write | PlacementService | 3 | critical |
| `_apply_stored_plan` | 7241–7298 | internal | placement apply | M | PS, TS, SS, GW | semantic/write helpers | PCB | guarded plan application | plan/SHA/transaction | expected SHA | yes | no | guarded write | PlacementService | 3 | critical |
| `_placement_config` | 7301–7305 | internal | placement methods | I | — | — | PCB | config parse only | validation errors | — | no | no | read-only | PlacementService | 2 | low |
| `plan_resource` | 7307–7329 | public/internal | MCP resource reader | R | PS | — | PCB | reads plan artifact | plan errors | plan SHA | no | no | PS synchronized | PlacementService | 3 | medium |
| `run_review` | 7331–7405 | public | `run_board_review`, `run_schematic_review`, review tools | R* | GW, MC, FS, RF | `_read_success` | PCB/schematic | persists review report | review/document errors | source SHA | yes | no | MC/FS synchronized | ReviewService | 1 | low |
| `get_findings` | 7407–7413 | public | review findings tools | R | FS | — | PCB/schematic | reads report | finding errors | stored source SHA | no | no | FS synchronized | ReviewService | 1 | low |
| `get_finding` | 7415–7416 | public | review findings tools | R | FS | — | PCB/schematic | reads finding | finding errors | stored source SHA | no | no | FS synchronized | ReviewService | 1 | low |
| `review_resource` | 7418–7420 | public/internal | MCP resource reader | R | FS | — | PCB/schematic | reads report resource | finding errors | stored source SHA | no | no | FS synchronized | ReviewService | 1 | low |
| `findings_resource` | 7422–7427 | public/internal | MCP resource reader | R | FS | — | PCB/schematic | reads report resources | finding errors | stored source SHA | no | no | FS synchronized | ReviewService | 1 | low |
| `finish_live_session` | 7429–7437 | public | `finish_live_session` | M | SS, TS, BS, TPR | live/transaction helpers | live all | applies/cancels bridge request | session/SHA/transaction | live expected SHA | yes | no | session lease | LiveSessionService | 3 | critical |
| `abandon_live_session` | 7439–7455 | public | `abandon_live_session` | M | SS | live helpers | live all | terminally abandons session | session errors | live state SHA | yes | no | session synchronized | LiveSessionService | 3 | critical |
| `scan_documents` | 7457–7498 | public | `scan_diptrace_documents` | R | S | `_read_source_header`, `_session_id_from_working` | all supported | reads directory and bounded metadata | path/filesystem errors | source SHA per item | maybe | no | read-only | DiscoveryService | 3 | medium |
| `_scan_libraries` | 7500–7522 | internal | library scan tools | R | S | `scan_documents` | libraries | reads directory | path/filesystem errors | source SHA per item | no | no | read-only | DiscoveryService | 3 | medium |
| `_get_library_item` | 7524–7542 | internal | library metadata tools | R | GW, MC, RF | `_read_success` | libraries | none | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `_validate_library_item` | 7544–7581 | internal | library validation tools | R | GW, MC, RF | `_read_success` | libraries | none | scope/document/library errors | source SHA | yes | no | MC synchronized | BomService | 1 | low |
| `_run_semantic_write` | 7583–7591 | internal | semantic operation wrappers | M | TS, SS, GW | `_run_semantic_operations` | all | guarded write/preview | edit/SHA/policy | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | critical |
| `_run_semantic_operations` | 7593–7698 | internal | semantic operation wrappers | M | TS, SS, GW, BS | write helpers | all | applies/preview semantic operations | edit/SHA/transaction | expected SHA | yes | no | guarded write | SemanticWriteService | 3 | critical |
| `_preview_semantic_operations` | 7700–7782 | internal | transaction/semantic preview | R* | TS, GW, MC | preview helpers | all | persists preview artifacts | edit/transaction errors | source SHA | yes | no | serialized store write | SemanticWriteService | 3 | high |
| `_load_snapshot_record` | 7784–7796 | internal | transaction paths | R | TS, MC | — | all | reads transaction snapshot | transaction/SHA errors | validates snapshot SHA | maybe | no | TS/MC synchronized | TransactionService | 3 | high |
| `_session_id_from_working` | 7798–7799 | internal | discovery | R | SS | — | live paths | session lookup only | session errors | — | yes | no | SS synchronized | DiscoveryService | 3 | low |
| `_read_source_header` | 7801–7822 | internal | discovery | R | filesystem | — | all candidates | reads bounded header | OSError | — | no | no | read-only | DiscoveryService | 3 | low |
| `_read_success` | 7825–7842 | internal | read-only methods | I | — | — | all | pure envelope construction | — | copies SHA metadata | no | no | pure | Shared response helper | 1 | low |
| `_validate_page` | 7845–7849 | internal | paged read methods | I | — | — | all | pure argument validation | document errors | — | no | no | pure | Shared response helper | 1 | low |

## Extraction roadmap

### Phase one (this pull request)

1. Introduce `ServiceContext` and `DocumentGateway` without changing store
   ownership or the MCP registration path.
2. Extract `DocumentService`: `board_model`, `schematic_model`, object/query
   and inspector read models, connectivity, document resources, and XML
   fragment reads.
3. Extract `BomService`: library model/query/validation and BOM
   extraction/review/consistency operations. Export artifact methods remain in
   the Facade.
4. Extract `ReviewService`: `run_review`, finding reads, and finding resource
   rendering. Its existing `FindingStore` report persistence remains intact.

These methods are synchronous domain code. The existing server-owned wrapper
continues to apply `anyio.to_thread.run_sync` to all 159 registered tools.

### Later phases

* Phase two: pure signal-integrity/impedance and read-only placement/routing
  analysis, after characterization/parity coverage is expanded.
* Phase three: discovery, exports, external adapters/jobs, and plan stores,
  keeping artifact and process ownership explicit.
* Phase four: semantic writes and testpoint/component operation wrappers only
  after their transaction, policy, and SHA gates have narrow interfaces.
* Phase five: transaction recovery, evidence/trust authorization, document
  creation, and live sessions last. These remain coupled to atomic writes,
  concurrent state, and fail-closed safety contracts.

## Phase-one parity matrix

| Domain | Methods | Existing characterization/fixture coverage | New Facade/direct-service parity coverage | Side-effect check |
| --- | --- | --- | --- | --- |
| Documents | `board_model`, `schematic_model`, `query_objects`, `get_object`, `get_connectivity_graph`, `document_resource`, `summarize`, `components`, `component`, `nets`, `rules`, `read_xml` | `tests/test_service.py`, `tests/test_inspector.py`, `tests/test_bounded_payloads.py`, `tests/test_connectivity.py`, fixture XML under `tests/fixtures` | `tests/test_service_facade_contract.py` compares complete payloads for representative PCB, schematic, and paged model calls | model-cache entry identity and state-record counts unchanged |
| BOM/library | `library_model`, library query/get/validate methods, `get_bom`, `review_bom`, `compare_bom_to_design`, `find_missing_component_fields`, `group_bom`, duplicate/consistency methods | `tests/test_advanced_review.py`, `tests/test_library_adapters.py`, `tests/test_bom.py` | `tests/test_service_facade_contract.py` compares complete payloads and typed exceptions | transaction/session/finding record counts unchanged for read-only calls |
| Review | `run_review`, `get_findings`, `get_finding`, `review_resource`, `findings_resource` | `tests/test_review.py`, `tests/test_advanced_review.py` | `tests/test_service_facade_contract.py` compares report/finding/resource payloads; report persistence is asserted explicitly | review report creation remains the existing documented side effect |

