---
name: pcb-project-intake
description: Inventory a bounded DipTrace project, its document identity, models, rules, connectivity, unknowns, and evidence before planning changes. Use when the user says “Inventory this DipTrace project before we plan work.”
---

# PCB project intake

Produce a read-only project baseline. Do not turn absent fields into assumed requirements.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, then `get_capabilities`.
2. Resolve every named document with `get_document_info`; record kind, literal format version,
   document units, byte size, and SHA-256. Treat PCB, schematic, component library, and pattern
   library as different source types.
3. Read only advertised models: `get_board_model`, `get_schematic_model`, `get_design_rules`, and
   `get_connectivity_graph`. Use count-only or paginated board reads when the response is large.
4. Separate caller requirements from document facts. Record an unresolved requirement as
   `blocked_by_input` only when it changes topology, ratings, pin mapping, mechanical datum, units,
   or release criteria.
5. Return the inventory through [`../shared/result.schema.json`](../shared/result.schema.json).

## Quantitative boundaries

- All MCP geometry is millimetres even when root `Units` is `inch` or `mil`; preserve the literal
  root value as document evidence.
- `get_board_model` accepts page limits from 1 through 500 and has a count-only mode; use the
  advertised byte budget instead of requesting the whole board.
- One write transaction is limited to 100 staged operations and 500 conservatively counted affected
  objects/elements; the count may exceed unique physical objects. This skill never opens one.
- A SHA-256 is exactly 64 lowercase hexadecimal characters. Never substitute a path or timestamp
  for document identity.

These limits come from
[`server.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/server.py),
[`capability_model.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/capability_model.py),
[`write_limits.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/write_limits.py), and runtime
`get_capabilities`; runtime values win.

## Refusals

- Do not infer DipTrace 5.3 compatibility from a synthetic scaffold or parser success.
- Do not call a tool absent from runtime discovery; follow
  [`../capability-map.json`](../capability-map.json).
- Do not collapse schematic logical connectivity and PCB ratlines into one completion claim.
- Do not mutate, export, or start external processes.

Label every returned fact `caller` or `document`; label derived prioritization `heuristic`.
