# MCP Tools

## Public contract

DipTrace MCP currently exposes **159 registered MCP tools**. The complete public `tools/list` response is generated and frozen in:

`reference/mcp-tools-list.snapshot.json`

CI regenerates that snapshot through the public in-memory MCP transport and fails if the public contract changes unexpectedly. Runtime `get_capabilities` reports what the active installation, document, policy and adapters allow; it is keyed by capability, not by tool name, and has known disagreements with tool behaviour ([TECH_DEBT.md](TECH_DEBT.md), B14), so also handle the error envelope.

`DipTraceService` is the Facade behind every tool. It resolves public methods on its
typed domain services (`src/diptrace_mcp/services/`) by attribute delegation, so there is
no separate hand-maintained delegation list to keep in step.

Internal EDA modules added after `v0.2.1` intentionally do **not** create one public MCP tool per heuristic.

## Capability groups

The exact names and schemas are in the generated snapshot. Conceptually the public tools cover:

- document discovery/open/read/query;
- PCB, schematic, Component Library and Pattern Library inspection, including
  read-only installed-catalog search and guarded schematic placement;
- connectivity, BOM, component/library metadata;
- offline review profiles (`run_review`) and comparison — not native DRC/ERC;
- placement, silkscreen and bounded routing workflows;
- trace, via, text, component and NetClass semantic edits;
- schematic authoring and synchronization;
- transactions, preview/commit, backup/recovery;
- live-session apply/cancel controls;
- evidence/provenance/trust handling;
- bounded external jobs/adapters;
- release/readiness and other project-owned analysis helpers.

Use MCP introspection rather than copying a manually maintained 159-item list into application code or documentation.

### Consolidated tools (post-`v0.4.0`)

Clients written against the 167-tool `v0.4.0` contract map removed names as follows:

| Removed tool | Use instead |
| --- | --- |
| `run_drc`, `run_erc`, `run_connectivity_check`, `run_board_review`, `run_schematic_review`, `run_manufacturing_review`, `run_manufacturing_geometry_check`, `run_assembly_review`, `run_testability_review`, `run_bom_review`, `run_thermal_review`, `run_silkscreen_check`, `check_silkscreen`, `run_component_clearance_check` | `run_review(profile=...)` |
| `analyze_controlled_impedance` | `validate_impedance_constraints` |
| `legalize_component_placement` | `plan_component_placement` |
| `set_component_fields` | `set_component_properties` |
| `set_diff_pair_rules`, `set_length_constraints` | `update_net_class_rules` |
| `unlock_components` | `lock_components(locked=false)` |

`run_review` profiles: `board_review`, `schematic_review`, `schematic_readability`,
`drc_basic`, `erc_basic`, `connectivity`, `component_clearance`, `silkscreen`,
`manufacturing_geometry`, `dfm_basic`, `dfa_basic`, `dft_basic`, `bom_basic`,
`thermal_basic`. They are deterministic offline checks on exported XML; none of them is
native DipTrace DRC or ERC.

### Schematic readability review

The existing `run_review` tool accepts `profile="schematic_readability"` without
adding a new tool. Omit `sheets` to check every schematic sheet, including
documentary overview. Only this dedicated profile accepts the explicit bounded
`sheets` selector (1–256 unique existing zero-based indices); other profiles reject
it. `schematic_review` always runs the registered readability check design-wide.
Reports contain a per-sheet coverage/geometry ledger and deterministic findings;
missing geometry is a structured skip, not a clean PASS. See
[the implemented boundaries](REVIEW_ENGINE.md#design-wide-schematic-readability).
No profile invokes native ERC or establishes native font/visual acceptance.

## Annotations and argument strictness

Every tool publishes MCP annotations. `readOnlyHint` means the tool changes no user
document and no external system (plans, previews, reports and job records in the
server's state directory do not count). `destructiveHint` marks writes that can remove
or replace design content; other writes add or update in place behind the same
expected-SHA, backup and transaction guards. `openWorldHint` marks the tools that reach
the network or run an external program.

Unknown arguments are refused with `INVALID_ARGUMENT`, so a misspelled option cannot
silently fall back to its default. Every successful result carries `ok: true`.

## Tool availability

A registered tool may still refuse or report a bounded capability because of:

- wrong document kind;
- unsupported format/feature in the active document;
- missing optional dependency or external adapter;
- platform restriction;
- policy restriction;
- missing real/authoritative physical input;
- stale expected SHA;
- live-session state;
- evidence/trust boundary.

Call `get_capabilities` and handle the stable public error envelope rather than inferring availability only from `tools/list`.

## Public error boundary

Registered tools use the centralized error boundary documented in [API_ERRORS.md](API_ERRORS.md). Safe structured errors are returned without leaking arbitrary internal exception detail or silently converting a refusal into success.

## Write tools

Write-capable tools remain behind the guarded operation path:

1. safe path / allowed-root validation;
2. bounded XML parse/model load;
3. semantic operation validation;
4. exact preview/expected SHA binding;
5. policy/write-impact checks;
6. backup/temporary write/atomic replacement;
7. transaction/recovery metadata;
8. live-session identity checks when applicable.

The public tool surface is not permission to bypass those boundaries.

## Tools added after the 2026-11-10 review

| Tool | What it does | Boundary |
| --- | --- | --- |
| `add_copper_pours` | Full-board four-spoke pour boundaries of one net on the named layers, optionally with a grid of free stitching vias and explicit extra vias | Copper appears only after a native refill; re-running replaces that net's stitching vias |
| `delete_copper_pours` | Removes a net's pours (all layers or named ones) and its stitching vias | — |
| `set_board_outline` | Replaces the outline with a straight-edged polygon | Refuses a locked outline or one that cuts off objects the current outline contains; no holes, cutouts or arcs |
| `delete_parts` | Deletes schematic parts and their net membership | A wire left on a deleted pin is refused; delete it in the same transaction |
| `delete_net_labels` | Deletes the visual labels of one net | Labels are annotations; connectivity is unchanged |
| `run_quality_gate` | The `PCB_BUILD.md` handoff check: gate order, recorded SHAs, and the stage's offline check | Read-only; native DRC/ERC and manual gates stay outside it |
| `run_native_check` | Starts a native DipTrace helper (`pcb_acceptance`, `schematic_acceptance`, `schematic_erc`, `xml_export`) on a copy as a background job | Source installs only; needs a reviewed DipTrace build and external-execution policy; the job records the helper's exit code and files and makes no acceptance decision |

`place_builtin_component` accepts `txid`, so native Net Ports and power symbols can be
staged in one transaction with the wiring. Paged schematic reads (parts, pins, wires,
nets) go through `query_objects` with `selector.kinds`.

The five write tools are new native-document writers that have not yet been opened in
DipTrace through this path (roadmap M1/M2).

## Pipeline tools

`pipeline_source_component` (LCSC/EasyEDA catalog download), `pipeline_nativeize_document`
(graft generated content into a native template) and `pipeline_render_board_preview`
(Top/Bottom SVG) write files directly instead of through a transaction. They resolve
every path inside the allowed roots and require a policy that allows commits;
`pipeline_source_component` also requires external execution. They take no
`expected_sha256`, so `pipeline_nativeize_document` refuses an existing output path.

## Schematic intelligence tools

Schematic design intent / functional blocks / reference motifs, bounded multi-candidate placement optimization, non-mutating wire quality planning/feedback, conservative pin-geometry resolution, and pin-aware joint route/placement scoring remain internal engines. They are now productized through bounded public tools:

- `rank_schematic_placement_candidates` — deterministic ensemble ranking of placement candidates by route quality, readable motifs and congestion (unwired by default; the joint route scorer models hypothetical wires). Already-wired schematic scoring requires explicit `config.optimizer.placement.allow_existing_wires=true` and `config.route.allow_existing_wires=true`; it remains read-only hypothetical scoring, never a repair or commit. Optional `engineering_rules` supplies validated SHA-bound external motifs; optional strict `config` exposes bounded optimizer, route, congestion, candidate-count, and repair controls;
- `plan_schematic_placement_repair` — bounded route-feedback placement repair combined with selective atomic affected-net reroute, stored as one dependency-safe plan. Works on already-wired schematics: the repair scorer models the same world the reroute applies (it removes exactly the affected wire geometry the reroute replaces and keeps unaffected nets as obstacles), affected explicit wires are deleted and selectively replanned, and a clean wired schematic produces an explicit no-op plan instead of spurious motion. `moves` are operator-fixed constraints resolved on the current placement: a part is selected by stable object ID or by unambiguous case-insensitive RefDes (a RefDes shared by several parts, e.g. a multi-part component, is refused fail-closed), duplicate moves for one part are refused, and repair search can never displace the requested positions;
- `apply_schematic_placement_repair_plan` — stages or commits that stored plan through the ordinary expected-SHA transaction path (`dry_run` defaults to true). Plans exceeding the 100-operation transaction limit are rejected at planning time, not only at apply time. Applying a stored no-op plan (`status="noop"`) is an idempotent success: `ok=true`, `changed=false`, no transaction, document SHA unchanged.

Selected results ultimately use ordinary semantic operations/transaction paths. See [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## PCB Generations A-D and analysis tools

The PCB design-engine layers remain internal engines:

- Generation A intent/net intelligence and placement v2;
- Generation B physical/PDN/return-path/noise/via context;
- Generation C routing policy / observed-route engineering checks / feedback;
- Generation D bounded whole-board candidate selection.

They are read-only productized through:

- `compare_pcb_placement_candidates` — generate and rank bounded Generation A-D placement candidates after candidate-specific physical/layout review. Optional `engineering_rules` supplies validated SHA-bound PCB intent overrides;
- `recommend_patterns` — deterministic hard-filter and geometry-score ranking
  of footprint patterns from a pattern library, using smallest occupied area as
  the tie-break between otherwise equal compatible candidates (no model calls);
- `analyze_release_readiness` — bounded DFM/DFA/DFT findings available from exported XML (supplement, not replacement, of DipTrace sign-off).

See [PCB_DESIGN_ENGINE.md](PCB_DESIGN_ENGINE.md).

## Component/Pattern Library mutation

A raw-preserving internal Component/Pattern Library mutation core exists and has controlled real-editor evidence. Public registration of native-library write operations is still a separate API/product decision; do not infer a public tool merely from the internal implementation.

## Cinematic mode is not an MCP-surface expansion

Cinematic replay/profile/recording utilities are Python modules and presentation helpers. They do not add MCP tools and do not change the `tools/list` snapshot.

They are invoked with module CLIs such as:

```bash
python -m diptrace_mcp.diptrace_profile_cli --help
python -m diptrace_mcp.cinematic_cli --help
python -m diptrace_mcp.cinematic_host --help
```

Visible UI replay is presentation automation and does not bypass XML/transaction evidence boundaries. See [CINEMATIC_DEMO_MODE.md](CINEMATIC_DEMO_MODE.md).

## Evidence status

Do not use this document as a universal compatibility matrix. Public registration, repository implementation, runtime availability and real-DipTrace verification are different facts.

The later private/manual Q1 Component Angle campaign is recorded as PASS on the accepted production checkpoint; the source-controlled gate `evidence_status.Q1_COMPONENT_ANGLE_LIVE_VALIDATED` has not been flipped, so `rotate_components` still carries its validation warning (open status question in [TECH_DEBT.md](TECH_DEBT.md)). Historical `v0.2.0` / `v0.2.1` release records and evidence templates retain the status that was true when those artifacts were created; they are not rewritten retroactively.

For current acceptance status use [ROADMAP.md](ROADMAP.md) and [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md).

## Updating the public contract

When an intentional public tool change is approved:

1. update the typed service/domain implementation;
2. update thin server registration;
3. add transport/schema/error tests;
4. regenerate the complete MCP snapshot;
5. update capability discovery and affected skill contracts;
6. review discovery-surface budget impact;
7. update this document and release notes;
8. keep real-host verification claims separate from implementation claims.

Do not hand-edit `reference/mcp-tools-list.snapshot.json` to force a test pass.
