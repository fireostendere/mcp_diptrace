---
name: schematic-erc-review
description: Review a DipTrace schematic with bounded ERC, logical connectivity, metadata, and BOM checks before layout. Use when the user says “Review this DipTrace schematic before layout.”
---

# Schematic ERC review

Produce a read-only disposition with explicit implemented, skipped, and unavailable checks.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, and `get_document_info`; require a schematic source
   and freeze its SHA-256.
2. Read `get_schematic_model` and `get_connectivity_graph`. Preserve sheet identity, hierarchy,
   explicit no-connect state, RefDes, pin numbers, and net names.
3. Run `run_erc`, `run_schematic_review`, `run_connectivity_check`, and `run_bom_review` only when
   advertised.
4. Deduplicate findings by check ID plus object identity, not by message text.
5. Report every missing mandatory category in `skipped_checks`; a skipped mandatory check forbids
   `completed`.
6. Validate the report with [`../shared/result.schema.json`](../shared/result.schema.json).

## Quantitative boundaries

- Query and report pages default to 100 records; follow returned continuation metadata rather than
  assuming one page is complete.
- Confidence is a number from 0 through 1 in the shared schema. It is not a substitute for an
  evidence class.
- SHA-256 identity is 64 lowercase hexadecimal characters and must remain unchanged throughout the
  read-only run.
- All geometric distances are millimetres, independent of document `Units`.

The implemented review profiles live in
[`review.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/review.py),
[`advanced_review.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/advanced_review.py),
and are summarized in
[`REVIEW_ENGINE.md`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/docs/REVIEW_ENGINE.md).
Do not claim checks outside that
matrix.

## Refusals

- Do not infer electrical pin roles from pin names alone.
- Do not call a PCB ratline a schematic logical connection.
- Do not treat explicit no-connects or DNP parts as defects without contradicting evidence.
- Do not mutate the schematic or assign patterns during a review.

Use `document` for parser/check output, `caller` for supplied intent, and `heuristic` for model
prioritization.
