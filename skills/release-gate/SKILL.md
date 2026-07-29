---
name: release-gate
description: Produce an explicit evidence-based PASS or BLOCKED decision from implemented DipTrace review profiles and disclosed missing checks. Use when the user says “Run the final evidence-based release gate for this design.”
---

# Release gate

Return `PASS` only for the exact requested revision and declared review scope. A green MCP run is
not fab-house approval or DipTrace-format certification.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, and `get_document_info`; record the exact SHA-256.
2. Select profiles by document kind:
   - PCB: `run_board_review`, `run_drc`, `run_connectivity_check`,
     `run_manufacturing_review`, `run_assembly_review`, `run_testability_review`,
     `run_bom_review`, and `run_thermal_review`.
   - schematic: `run_schematic_review`, `run_erc`, `run_connectivity_check`, and
     `run_bom_review`.
3. Compare each result against the implemented/partial/missing matrix in
   [`REVIEW_ENGINE.md`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/docs/REVIEW_ENGINE.md).
4. Deduplicate by check ID and stable object identity. Preserve waivers, DNP state, explicit
   no-connects, confidence, approximation flags, and every `skipped` disclosure.
5. Decide `PASS` only when no critical/error finding remains, all caller-mandatory implemented
   checks ran, the SHA stayed stable, and every unavailable category was accepted as outside scope.
6. Otherwise decide `BLOCKED` and list the shortest evidence-producing next actions.
7. Emit [`../shared/result.schema.json`](../shared/result.schema.json); put the decision in summary
   and as a finding, not in the transport `status`.

## Quantitative boundaries

- Confidence is bounded from 0 through 1 but cannot overrule evidence class.
- Results are paged/bounded; follow resource URIs and truncation metadata rather than assuming the
  first 100 findings are complete.
- Document identity is a 64-character lowercase SHA-256.
- The server's write limits are 100 operations and 500 conservatively counted affected
  objects/elements per write, but this gate is read-only.

## Refusals

- No invented fabrication clearances, DFM thresholds, impedance goldens, or fab capability tables.
- No `PASS` with an unacknowledged mandatory `skipped` item or incomplete bounded payload.
- Generic fabrication/assembly manifests are not native manufacturing outputs.
- A parser-tested synthetic document is not DipTrace-round-trip evidence.

Use [`../capability-map.json`](../capability-map.json) for explicit missing contracts. Classify
check output as `document`; model synthesis is `heuristic`; operator waivers are `operator`.
