# MCP Tools

## Public contract

DipTrace MCP currently exposes **165 registered MCP tools**. The complete public `tools/list` response is generated and frozen in:

`reference/mcp-tools-list.snapshot.json`

CI regenerates that snapshot through the public in-memory MCP transport and fails if the public contract changes unexpectedly. Runtime `get_capabilities` remains authoritative for whether a particular tool/path is usable for the active installation, document, policy and adapters.

The service contract currently contains:

- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations.

Internal EDA modules added after `v0.2.1` intentionally do **not** create one public MCP tool per heuristic.

## Capability groups

The exact names and schemas are in the generated snapshot. Conceptually the public tools cover:

- document discovery/open/read/query;
- PCB, schematic, Component Library and Pattern Library inspection;
- connectivity, BOM, component/library metadata;
- DRC/ERC/review/comparison;
- placement, silkscreen and bounded routing workflows;
- trace, via, text, component and NetClass semantic edits;
- schematic authoring and synchronization;
- transactions, preview/commit, backup/recovery;
- live-session apply/cancel controls;
- evidence/provenance/trust handling;
- bounded external jobs/adapters;
- release/readiness and other project-owned analysis helpers.

Use MCP introspection rather than copying a manually maintained 165-item list into application code or documentation.

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

## Schematic intelligence tools

Schematic design intent / functional blocks / reference motifs, bounded multi-candidate placement optimization, non-mutating wire quality planning/feedback, conservative pin-geometry resolution, and pin-aware joint route/placement scoring remain internal engines. They are now productized through bounded public tools:

- `rank_schematic_placement_candidates` — deterministic ensemble ranking of placement candidates by route quality, readable motifs and congestion;
- `plan_schematic_placement_repair` — bounded route-feedback placement repair combined with selective atomic affected-net reroute, stored as one dependency-safe plan;
- `apply_schematic_placement_repair_plan` — stages or commits that stored plan through the ordinary expected-SHA transaction path (`dry_run` defaults to true).

Selected results ultimately use ordinary semantic operations/transaction paths. See [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## PCB Generations A-D and analysis tools

The PCB design-engine layers remain internal engines:

- Generation A intent/net intelligence and placement v2;
- Generation B physical/PDN/return-path/noise/via context;
- Generation C routing policy / observed-route engineering checks / feedback;
- Generation D bounded whole-board candidate selection.

They are read-only productized through:

- `compare_pcb_placement_candidates` — generate and rank bounded Generation A-D placement candidates;
- `recommend_patterns` — deterministic hard-filter and geometry-score ranking of footprint patterns from a pattern library (no model calls);
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

The later private/manual Q1 Component Angle campaign is PASS on the accepted production checkpoint. Historical `v0.2.0` / `v0.2.1` release records and evidence templates retain the status that was true when those artifacts were created; they are not rewritten retroactively.

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
