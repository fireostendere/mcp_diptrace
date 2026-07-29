---
name: critical-net-router
description: Plan and optionally commit one bounded critical-net or differential-pair route in DipTrace with explicit rules and post-checks. Use when the user says “Route this explicitly named critical PCB net.”
---

# Critical-net router

Route an explicitly named scope. The local router is deterministic bounded 45-degree A*, not
push-and-shove.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, and `get_document_info`; require a PCB and freeze the
   SHA-256.
2. Read `get_design_rules`, `list_unrouted_connections`, and `analyze_routing_congestion`. Require
   concrete endpoints, allowed layers, via policy, and net or pair identity.
3. For one connection use `route_connection`; for exported ratlines use `route_net`. For a real
   pair use `plan_diff_pair_route` or `route_diff_pair`; never route the two legs independently.
4. Omit clearance only to resolve the document DRC TraceToTrace rule. An explicit caller value is
   millimetres and must be named in the report.
5. Prefer `plan_route_nets` plus `apply_route_plan` for a reviewable plan. Inspect SVG/JSON, then
   validate and obtain explicit confirmation before an `expected_sha256` commit.
6. Run `run_drc` and `run_connectivity_check`; rollback on regression.
7. Emit [`../shared/result.schema.json`](../shared/result.schema.json).

## Quantitative boundaries

- One local route plan accepts at most 20 connections.
- `route_connection` defaults to zero vias, a 3.0 detour factor, and at most 100,000 search nodes.
- Multi-route rip-up/retry defaults to four attempts; this remains bounded local retry, not
  push-and-shove.
- A transaction accepts at most 100 operations and 500 conservatively counted affected
  objects/elements; this can be fewer than 500 unique physical objects.

The limits and defaults are implemented in
[`server.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/server.py),
[`service.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/service.py),
[`routing.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/routing.py),
and
[`write_limits.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/write_limits.py).
Runtime capabilities win.

## Refusals

- Stop when pad endpoints, layer span, applicable clearance, or allowed via style is unresolved.
- Stop when an existing route contains arcs or jumpers that the requested rewrite cannot preserve.
- Do not describe congestion score as calibrated engineering risk.
- Do not use the external autorouter unless its DSN/SES geometry and job provenance gates succeed.

Search ranking is `heuristic`; exact rules, route geometry, preview, and post-checks are `document`.
