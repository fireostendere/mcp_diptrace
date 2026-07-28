# MCP Tools and Resources

The complete runtime tool list must be requested through MCP `tools/list`. Actual availability for a specific document, source type, geometry set, policy profile, and external-adapter configuration is reported by `get_capabilities`.

A registered tool is not the same as a DipTrace-verified write path. The project intentionally distinguishes implementation, runtime availability, and real DipTrace round-trip evidence.

## Input Schemas, Units, and Errors

All geometric tool descriptions state the normalization rule used by the API: all distances are
in millimetres, regardless of the document's own `Units` attribute. High-value compact payloads
use typed schemas directly. In particular, `stage_operations` publishes all 39 registered
operation `kind` values as an enum.

Every tool that accepts `dry_run` says so in its concrete `tools/list` description.
`dry_run=true` is a preview and must not write; a real write requires `dry_run=false` plus
the `expected_sha256` returned by the inspected preview.

The full `QuerySelector`, PCB scaffold, synchronization, panelization, and route-connection
schemas are available once in the JSON schema catalog at `diptrace://schemas/tool-inputs`. They
are referenced instead of being duplicated across dozens of tool schemas, keeping `tools/list`
within its measured token budget.

Opaque IDs are provenance-bound: object/stable IDs come from `query_objects` or normalized
model/list tools; transaction, plan, report, export, and job IDs come from the corresponding
create/run tool. Callers must not invent them.

MCP tool failures currently use the transport's error response and human-readable message.
Exception classes retain internal codes for service tests and persisted job failures, but the MCP
wire does not promise a structured `code` or `suggested_action` payload.

## Read and Query

- status, document information, scanning, summaries, and capabilities;
- normalized PCB, schematic, Component Library, and Pattern Library models;
- `query_objects`, `get_object`, structured selectors, spatial queries, and stable IDs;
- components, nets, rules, stackup, connectivity graph, and XML fragments;
- BOM, copper-pour boundaries, unrouted connections, and route details;
- net lengths, differential pairs, and preliminary single-ended/differential impedance;
- library component/pattern lookup and validation, including pin-to-pad checks.

## Semantic Writes

- document creation: `create_schematic_document` and `create_pcb_document` generate synthetic DipTrace-shaped XML with sheets, outline, layers, stackup, via styles, net classes, and DRC; their optional `format_version` sets the literal root and embedded-library `Version` attributes but does not convert the 4.3-era scaffold structure or assert compatibility;
- seed-based document creation through `create_document_from_seed` for workflows that need to preserve a real DipTrace-exported XML structure, its existing `Version` literal, and provenance byte-for-byte;
- components: move, rotate, side, lock, properties, pattern, align, distribute, and group;
- board text: list, move, rotate, visibility, and style;
- schematic properties: value, fields, no-connect, and net rename;
- schematic authoring: `add_sheet`, `place_part`, `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, and `add_net_label`;
- schematic-to-PCB: `sync_schematic_to_pcb` creates/updates PCB components, copies allowed pattern/pad-style subtrees, maps pins to pads, and creates nets/ratlines; default mode is additive, while opt-in `exact` reconciliation can remove unmatched synchronized objects and traces on nets whose endpoint set changed;
- rules: NetClass assignment, widths, gaps, and length constraints;
- panelization: `set_panelization` / `clear_panelization` write official DipTrace `Panel` parameters;
- standalone test points;
- trace/via primitives, bounded multi-layer route plans, and symmetric via insertion;
- `analyze_routing_congestion` for deterministic routing-priority evidence;
- `route_connections` for congestion-ordered multi-net routing with bounded batch-local rip-up/retry;
- `plan_diff_pair_route` and `route_diff_pair` for coupled centerline-based differential-pair routing.

High-level writes use dry-run or transaction planning, expected source SHA, preview,
reparse, targeted connectivity/DRC/ERC regression checks, commit, backup, and rollback.
Those checks cover a bounded subset and may skip unavailable geometry or rules; see the
[review coverage matrix](REVIEW_ENGINE.md). `apply_xml_edits` remains an expert escape
hatch rather than the preferred API.

Every semantic transaction, raw XML edit, generated document, seed copy, and overwrite
is independently limited by a fail-closed count of affected normalized objects and exact
XML elements. The count is recomputed before transaction mutation and again at commit; it
includes nested library patterns, pads, pins, holes, and shapes. The normalized and XML
views are conservatively summed because no complete mapping exists between them, so their
overlap can cause a write with fewer than 500 unique physical design objects to be refused.
Exact conflict-checked rollback is exempt from the object count, but still passes the active
write policy. The live-session external apply handshake is not yet independently capped
and remains disclosed by `get_capabilities` pending WO-15.

## Trust and Verification Caveat

The capability layer intentionally does **not** claim that every write path has fully proven trust invalidation and real DipTrace round-trip coverage.

At the current baseline, `get_capabilities` explicitly reports remaining trust-coverage work for:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

These operations may be implemented and tested while still lacking the same trust/evidence closure as the strongest paths. Runtime capability discovery takes precedence over broad documentation summaries.

## Analysis and Review

- bounded registry-based DRC, ERC, connectivity, board, and schematic review with
  structured skips;
- partial manufacturing, assembly, testability, BOM, and thermal profiles whose
  uncovered categories remain explicit;
- silkscreen and bounded local placement planners;
- return-path and plane-continuity heuristics;
- BOM and schematic/PCB comparison;
- DSN/SES inspection;
- persistent structured findings and bounded review artifacts.

## Exports and External Jobs

- bounded DSN export, Freerouting jobs, guarded SES inspection/import;
- ngspice batch jobs for user-supplied netlists (`run_ngspice_simulation`), requiring `DIPTRACE_MCP_NGSPICE` or ngspice on `PATH`;
- typed centered/off-center stripline solver jobs (`run_openems_stripline_analysis`) with frequency-dependent complex impedance/propagation results, requiring `DIPTRACE_MCP_OPENEMS_RUNNER`;
- generic BOM CSV;
- generic fabrication-review and assembly-review manifests;
- job status, result, cancel, list, log, DSN, SES, and export-artifact resources.

Generic manifests do **not** generate Gerber, NC Drill, ODB++, IPC-2581, or vendor-native placement packages. Native-output requests fail explicitly instead of returning false success.

## Resources

- `diptrace://status`, `diptrace://capabilities`, `diptrace://schemas/tool-inputs`;
- document summary, board, schematic, stackup, connectivity, library, review, and findings resources;
- transaction/plan summary, operations, diff, SVG, and JSON previews;
- bounded raw-edit diffs at `diptrace://raw-preview/{preview_id}/diff`;
- job status, result, log, DSN, SES, and field-solver resources;
- `diptrace://export/{export_id}/{artifact}`.

Large payloads are exposed through explicit resources instead of being echoed by tool
responses. Preview formats are SVG, JSON geometry, and XML diff; PNG preview is not
currently registered.

`get_board_model` defaults to a count-only summary. Select one collection, including
`cutouts`, `components`, `traces`, or `warnings`, and use `offset`/`limit` to retrieve
a page. The complete serialized response is capped at 256 KiB. A nested record larger
than the 32 KiB per-item detail cap is replaced by an explicitly marked summary with
its original byte count and the full-model resource URI; pagination still consumes
that record. These are computational transport caps, not design limits.

Transaction responses never echo staged operations or inline preview artifacts. They
return a bounded transaction summary, counts, and URIs for the transaction summary,
operations, SVG, JSON, and bounded diff resources. `written` is `false` for preview
and `true` after a successful commit.

`apply_xml_edits` also returns only diff metadata and a raw-preview resource URI. Its
stored diff prefix is capped by both line and character counts, and reports the total
and stored counts plus each truncation reason.

## Deliberately Not Registered

- native Component/Pattern Library mutation;
- persistent pattern feedback/retrieval/recommendation tools;
- push-and-shove, free-angle, or full global autorouting;
- native Gerber/NC Drill/ODB++/IPC-2581 manufacturing generation;
- unverified full-wave or frequency-dependent solver backends presented as built-in capability;
- arbitrary shell execution or unrestricted network-backed sourcing.

Reasons are returned through `reasons_unavailable`. See [ROADMAP.md](ROADMAP.md) for evidence-gated work and implementation order.
