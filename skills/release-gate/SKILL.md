---
name: release-gate
description: RAG-backed. Produce an explicit evidence-based PASS or BLOCKED decision from implemented DipTrace review profiles and disclosed missing checks. Use for a final PASS or BLOCKED decision before fabrication, assembly, or release; «финальная проверка перед заказом», «готова ли плата к производству». Use when the user says “Run the final evidence-based release gate for this design.”
---

Read [runtime access](../shared/runtime.md) before choosing between explicit-path
MCP, a live bridge session, and native/headless CLI. Their availability is separate.

# Release gate

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Audit source-backed design decisions and DFM/DFA/DFT criteria carried from earlier
stages; consult missing criteria, including DipTrace verification/export course material.

Return `PASS` only for the exact requested revision and declared review scope. A green MCP run is
not fab-house approval or DipTrace-format certification.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, and `get_document_info`; record the exact SHA-256.
2. Select profiles by document kind:
   - PCB: `run_review` with profiles `board_review`, `drc_basic`, `connectivity`,
     `dfm_basic`, `dfa_basic`, `dft_basic`, `bom_basic`, and `thermal_basic`;
     supplement with
     `analyze_release_readiness` for bounded DFM/DFA/DFT findings available from
     exported XML (it supplements, not replaces, DipTrace sign-off).
   - schematic: `run_review` with profiles `schematic_review`, `erc_basic`,
     `connectivity`, and `bom_basic`.
3. Compare each result against the implemented/partial/missing matrix in
   [`REVIEW_ENGINE.md`](https://github.com/fireostendere/mcp_diptrace/blob/d27f33e9013c6d87cf9c5478bf91f42a1ad9afa9/docs/REVIEW_ENGINE.md).
4. Deduplicate by check ID and stable object identity. Preserve waivers, DNP state, explicit
   no-connects, confidence, approximation flags, and every `skipped` disclosure.
5. For native acceptance, consume SHA-bound evidence or run the supported headless workflow on
   a copy through [evidence capture](../diptrace-evidence-capture/SKILL.md). A full PCB release
   requires native refill/DRC and the specified connectivity evidence; a fabrication release also
   requires actual CAM inspection through [production pack](../diptrace-production-pack/SKILL.md).
   Do not mark these requirements outside scope merely because an MCP tool is absent.
   Decide `PASS` only when no critical/error finding remains, all caller-mandatory implemented
   checks ran, the SHA stayed stable, and every unavailable category was accepted as outside scope.
6. Otherwise decide `BLOCKED` and list the shortest evidence-producing next actions.
7. Emit [`../shared/result.schema.json`](../shared/result.schema.json); put the decision in summary
   and as a finding, not in the transport `status`.

## Known skipped PCB checks

| Check | Skip reason | What clears it |
|---|---|---|
| `pcb.silk_to_pad` | `not_implemented` in every run | Nothing offline. Cover it with native DRC and the silkscreen inspection, and list it as acknowledged |
| `pcb.thermal_metadata` | `explicit_component_power_metadata_unavailable` | A component field `power_w`, `power (w)`, `mcp.powerw` or `dissipation_w`; otherwise thermal review stays with bring-up |
| `pcb.trace_board_edge` | `trace_to_board_rules_unavailable` | A `TraceToBoard` value in the document's DRC layer clearances |

An offline `error` from estimated geometry stays a finding: for example `pcb.component_overlap`
on estimated component boxes, or a connector that intentionally overhangs the outline. Only an
explicit operator waiver that names the finding, backed by native DRC on the same SHA,
dispositions it.

## Quantitative boundaries

- Confidence is bounded from 0 through 1 but cannot overrule evidence class.
- Results are paged/bounded; follow resource URIs and truncation metadata, or re-read the stored
  report with `get_findings`, rather than assuming the first 100 findings are complete.
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
