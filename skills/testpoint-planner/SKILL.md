---
name: testpoint-planner
description: Measure and improve explicit standalone-pad testpoint coverage through a guarded DipTrace PCB transaction. Use when the user says “Plan guarded fixture testpoints for these PCB nets.”
---

# Testpoint planner

Plan only explicit MCP/DipTrace standalone-pad testpoints; reported coverage is not a fixture-access
simulation.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, and `get_document_info`; require a PCB and freeze its
   SHA-256.
2. Use `list_testpoints` and `review_testpoint_coverage` for the exact net scope. Preserve excluded,
   sensitive, high-speed, RF, clock, reset, and user-locked nets.
3. Call `find_testpoint_candidates` with explicit side, probe diameter, clearance, grid, and
   candidates per net. Ask the operator when fixture-side access or sensitive-net policy is absent.
4. Stage `add_testpoints(..., dry_run=true)` in a transaction. Never commit from a request for a
   plan.
5. Inspect `preview_transaction`, then `validate_transaction`. Commit only after explicit
   confirmation with `expected_sha256`.
6. Re-run `run_testability_review`, `run_drc`, and `run_connectivity_check`; rollback on regression.
7. Emit [`../shared/result.schema.json`](../shared/result.schema.json).

## Quantitative boundaries

- `candidates_per_net` is 1 through 100; the free-grid search is bounded to 5,000 candidate points.
- The API defaults are probe diameter 1.0 mm, clearance 0.5 mm, and grid 2.54 mm. They are search
  parameters, not universal fixture rules; expose them and let the operator override them.
- Each transaction accepts at most 100 operations and 500 conservatively counted affected
  objects/elements; this can be fewer than 500 unique physical objects.
- All distances are millimetres regardless of root `Units`.

The actual bounds are enforced in
[`service.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/service.py),
[`capability_model.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/capability_model.py),
and
[`write_limits.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/write_limits.py).

## Refusals

- Do not claim probe access, fixture mechanics, or fabrication clearance from the free-grid check.
- Do not add a point to an unresolved or sensitive net without explicit operator scope.
- Do not use raw XML or bypass locked objects.
- Do not report `completed` after a skipped DRC/connectivity check or stale SHA.

Candidate ranking is `heuristic`; committed object identity and post-checks are `document` evidence.
