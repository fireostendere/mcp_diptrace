# MCP Tools and Resources

The complete runtime tool list must be requested through MCP `tools/list`. Actual availability for a specific document, source type, geometry set, policy profile, and external-adapter configuration is reported by `get_capabilities`.

A registered tool is not the same as a DipTrace-verified write path. The project intentionally distinguishes implementation, runtime availability, and real DipTrace round-trip evidence.

## Read and Query

- status, document information, scanning, summaries, and capabilities;
- normalized PCB, schematic, Component Library, and Pattern Library models;
- `query_objects`, `get_object`, structured selectors, spatial queries, and stable IDs;
- components, nets, rules, stackup, connectivity graph, and XML fragments;
- BOM, copper-pour boundaries, unrouted connections, and route details;
- net lengths, differential pairs, and preliminary single-ended/differential impedance;
- library component/pattern lookup and validation, including pin-to-pad checks.

## Semantic Writes

- document creation: `create_schematic_document` and `create_pcb_document` generate synthetic DipTrace-shaped XML with sheets, outline, layers, stackup, via styles, net classes, and DRC;
- seed-based document creation through `create_document_from_seed` for workflows that need to preserve a real DipTrace-exported XML structure and provenance;
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

High-level writes use dry-run or transaction planning, expected source SHA, preview, reparse, targeted connectivity/DRC/ERC regression checks, commit, backup, and rollback. `apply_xml_edits` remains an expert escape hatch rather than the preferred API.

## Trust and Verification Caveat

The capability layer intentionally does **not** claim that every write path has fully proven trust invalidation and real DipTrace round-trip coverage.

At the current baseline, `get_capabilities` explicitly reports remaining trust-coverage work for:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

These operations may be implemented and tested while still lacking the same trust/evidence closure as the strongest paths. Runtime capability discovery takes precedence over broad documentation summaries.

## Analysis and Review

- registry-based DRC, ERC, connectivity, board, and schematic review;
- manufacturing, assembly, testability, BOM, and thermal profiles;
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

- `diptrace://status`, `diptrace://capabilities`;
- document summary, board, schematic, stackup, connectivity, library, review, and findings resources;
- transaction/plan summary, operations, diff, SVG, and JSON previews;
- job status, result, log, DSN, SES, and field-solver resources;
- `diptrace://export/{export_id}/{artifact}`.

Large payloads are exposed through bounded resources. Preview formats are SVG, JSON geometry, and XML diff; PNG preview is not currently registered.

## Deliberately Not Registered

- native Component/Pattern Library mutation;
- persistent pattern feedback/retrieval/recommendation tools;
- push-and-shove, free-angle, or full global autorouting;
- native Gerber/NC Drill/ODB++/IPC-2581 manufacturing generation;
- unverified full-wave or frequency-dependent solver backends presented as built-in capability;
- arbitrary shell execution or unrestricted network-backed sourcing.

Reasons are returned through `reasons_unavailable`. See [ROADMAP.md](ROADMAP.md) for evidence-gated work and implementation order.
