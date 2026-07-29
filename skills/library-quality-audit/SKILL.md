---
name: library-quality-audit
description: Audit DipTrace component and pattern libraries for pin, pad, mapping, geometry, and identity defects without mutating native libraries. Use when the user says “Audit these DipTrace component and pattern libraries.”
---

# Library quality audit

Validate library records as exported. Native Component/Pattern Library mutation is not an
implemented or evidence-qualified capability.
Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status`, `get_capabilities`, then `get_document_info`.
2. Require `component_library` or `pattern_library`; otherwise return `blocked_by_input`.
3. Page with `query_library_items`. Resolve selected records through
   `get_library_component` or `get_library_pattern`.
4. Run `validate_library_component` for pin identity, attached pattern, and pin-to-pad mapping.
   Run `validate_library_pattern` for unique pad numbers, style references, holes, and annular
   geometry.
5. Group findings by stable item ID and preserve the source SHA-256.
6. Emit [`../shared/result.schema.json`](../shared/result.schema.json) and keep `actions` proposed
   or refused.

## Quantitative boundaries

- Query pages default to 100 records and accept 1 through 500.
- A through-hole annular ring is meaningful only when both diameter and hole values exist and
  diameter is greater than hole. Report absent values as unavailable; never invent a minimum ring.
- Duplicate pin or pad numbers are deterministic errors. Geometric manufacturability remains a
  separate fabrication-profile question.
- Coordinates returned by the service are millimetres regardless of the document `Units` value.

The validators are the source of these checks:
[`library_adapters.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/library_adapters.py)
and
[`server.py`](https://github.com/fireostendere/mcp_diptrace/blob/20e4bc107e3810945f729d3c81d0a379d9af8012/src/diptrace_mcp/server.py).

## Refusals

- Do not call raw XML edits to imitate a library writer.
- Do not report a library as DipTrace-round-trip verified without reviewed provenance.
- Do not infer courtyard, mask, paste, or Component/Pattern Editor semantics absent from public
  specification or committed evidence.
- Do not turn a read-only audit into `set_component_pattern`; that tool is not native library
  mutation.

Use `document` evidence for parsed facts and `heuristic` only for explicitly named engineering
advice. Consult [`../capability-map.json`](../capability-map.json) for the native-mutation refusal.
