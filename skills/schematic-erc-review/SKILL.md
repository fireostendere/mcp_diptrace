---
name: schematic-erc-review
description: RAG-backed. Review a DipTrace schematic with bounded ERC, logical connectivity, metadata, and BOM checks before layout. Use for a read-only schematic review or ERC disposition; «проверь схему», «ревью схемы», «ERC схемы». Use when the user says “Review this DipTrace schematic before layout.”
---

Read [runtime access](../shared/runtime.md) before choosing between explicit-path
MCP, a live bridge session, and native/headless CLI. Their availability is separate.

# Schematic ERC review

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Derive an engineering checklist from the circuit-analysis/design corpus and DipTrace
schematic/ERC courses, then inspect the actual circuit beyond automated ERC findings.

Produce a read-only disposition with explicit implemented, skipped, and unavailable checks.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

Readability or crossing cleanup covers all sheets by default, including documentary overview
connections. Only an explicit user restriction permits narrower scope; never silently select
the active/core sheet. One representative sheet is incremental construction, not final
acceptance. Report per-sheet coverage with findings and unavailable checks; whole-schematic
final acceptance includes every sheet and page-fit visual inspection.

Inspect different-net full-polyline crossings, ambiguous collinear overlaps, foreign
glyph/pin/stub crossings and port-tip-on-foreign-shaft superposition. Treat documentary lines
separately from electrical wires and rectangle borders; intentional same-net junctions and
shared documentary endpoints are not errors. Report missing geometry explicitly, not as a
clean empty result. Claim only implemented checks advertised by the current runtime; disclose
native font metrics and caption-clearance limits. Clean ERC is not a visual pass, and geometry
alone cannot prove readability or native/ERC acceptance. Follow the schematic style for
visible local support wiring and justified exact named native ports, not blanket labels.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, and `get_document_info`; require a schematic source
   and freeze its SHA-256.
2. Read `get_schematic_model` and `get_connectivity_graph`. Preserve sheet identity, hierarchy,
   explicit no-connect state, RefDes, pin numbers, and net names.
3. Run `run_review` with profiles `erc_basic`, `schematic_review`, `connectivity`, and
    `bom_basic` only when advertised.
   For readability, use the advertised `schematic_readability` profile; omit `sheets`
   to check all sheets. Only an explicit user restriction permits its bounded
   zero-based `sheets` selector. The full `schematic_review` stays design-wide.
   Inspect `metrics["schematic.readability"]`: selected/excluded indices, per-sheet
   counts, `all_sheets_checked`, `geometry_complete` and missing geometry. A scoped
   result or incomplete geometry is not whole-schematic acceptance.
4. For native opening/roundtrip evidence, use the headless schematic workflow on a protected
   copy through [evidence capture](../diptrace-evidence-capture/SKILL.md). The base roundtrip
   does not run native ERC; the bounded schematic helper's `--erc` captures the native ERC
   result of a guarded `.dchxml` on a verified build (`erc_status: no_errors_found`, or
   `erc_status: review_required` until its image is viewed). Report only the portion that
   stays unavailable rather than saying headless Schematic is unavailable. Deduplicate by
   check ID plus object identity.
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
[`review.py`](https://github.com/fireostendere/mcp_diptrace/blob/d27f33e9013c6d87cf9c5478bf91f42a1ad9afa9/src/diptrace_mcp/review.py),
[`advanced_review.py`](https://github.com/fireostendere/mcp_diptrace/blob/d27f33e9013c6d87cf9c5478bf91f42a1ad9afa9/src/diptrace_mcp/advanced_review.py),
[`schematic_readability.py`](https://github.com/fireostendere/mcp_diptrace/blob/d27f33e9013c6d87cf9c5478bf91f42a1ad9afa9/src/diptrace_mcp/schematic_readability.py),
and are summarized in
[`REVIEW_ENGINE.md`](https://github.com/fireostendere/mcp_diptrace/blob/d27f33e9013c6d87cf9c5478bf91f42a1ad9afa9/docs/REVIEW_ENGINE.md).
Do not claim checks outside that
matrix.

## Refusals

- Do not infer electrical pin roles from pin names alone.
- Do not call a PCB ratline a schematic logical connection.
- Do not treat explicit no-connects or DNP parts as defects without contradicting evidence.
- Do not mutate the schematic or assign patterns during a review.

Use `document` for parser/check output, `caller` for supplied intent, and `heuristic` for model
prioritization.
