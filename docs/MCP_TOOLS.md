# MCP Tools and Resources

The complete runtime tool list should always be requested through MCP `tools/list`.
Actual availability for a specific document is reported by `get_capabilities`.

## Read and Query

- status, information, scan, summary, and capabilities;
- board, schematic, and library models, plus `query_objects` and `get_object`;
- components, nets, rules, stackup, and the connectivity graph;
- BOM, copper pours, unrouted connections, and route details;
- net lengths, differential pairs, and preliminary single-ended/differential impedance.

## Semantic Writes

- components: move, rotate, side, lock, properties, pattern, align, distribute, and group;
- board text: list, move, rotate, visibility, and style;
- schematic: value, fields, no-connect, and net rename;
- rules: NetClass assignment, widths, gaps, and length constraints;
- standalone test points;
- trace and via primitives, bounded multi-layer local route plans, and symmetric via insertion;
- `plan_diff_pair_route` and `route_diff_pair` using a coupled centerline and atomic pair metadata.

All writes use a plan or dry-run transaction, expected SHA, preview, reparse,
connectivity/DRC regression gate, commit, and rollback. `apply_xml_edits` is retained as
an expert escape hatch and is not the recommended API.

## Analysis and Review

- registry-based DRC, ERC, connectivity, board, and schematic review;
- manufacturing, assembly, testability, BOM, and thermal profiles;
- silkscreen and placement planners;
- return-path and plane-continuity analysis;
- BOM and design comparison;
- DSN and SES inspection.

## Exports and Jobs

- bounded DSN export, Freerouting jobs, and SES import;
- generic BOM CSV;
- generic fabrication and assembly review manifests;
- job status, result, cancel, and list operations, plus export listing.

Generic manifests do not generate Gerber, NC Drill, ODB++, IPC-2581, or vendor-specific
component-placement files. A request for native output ends with
`capability_unavailable`, not false success.

## Resources

- `diptrace://status`, `diptrace://capabilities`;
- document summary, board, schematic, stackup, connectivity, library, review, and findings;
- transaction and plan summary, diff, SVG, and JSON;
- job status, result, log, DSN, SES, and manifest;
- `diptrace://export/{export_id}/{artifact}`.

Large payloads are exposed through bounded resources. PNG is not available. Preview
formats are SVG, JSON geometry, and XML diff.

## Not Registered

Schematic wire synthesis, library mutation, push-and-shove routing, native manufacturing,
panelization, and unverified stripline or full-wave solvers are not registered. Reasons
are returned through `reasons_unavailable`.
