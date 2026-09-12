---
name: library-quality-audit
description: RAG-backed. Audit DipTrace component and pattern libraries for pin, pad, mapping, geometry, and identity defects without mutating native libraries. Use when the user says “Audit these DipTrace component and pattern libraries.”
---

Read [runtime access](../shared/runtime.md) before choosing between explicit-path
MCP, a live bridge session, and native/headless CLI. Their availability is separate.

# Library quality audit

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Use the RAG engineering context and DipTrace library courses to understand symbols,
physical packages, mapping pitfalls and footprint suitability while auditing exact records.

Audit exported Component/Pattern Library records through the public read/validation surface.
Current `main` also contains an internal raw-preserving library mutation core with controlled real
Component Editor / Pattern Editor round-trip evidence, but that core is not registered as a public
native-library write capability and this skill remains read-only.

Use public `tools/list` for exact callable names and `get_capabilities` for document/configured
feature availability.

## Workflow

1. Call `diptrace_status` and `get_capabilities`; resolve native versus XML input below
   before calling `get_document_info` on a parser-supported document.
2. Require Component/Pattern Library XML for the parser. For installed native `.eli` libraries,
   `query_builtin_library_catalog` can obtain a cached XML export through hidden Component Editor
   when the host supports it; this does not mutate the installed library. Do not reject installed
   catalogs merely because a live editor session is absent. Arbitrary binary library export is
   a separate capability: base roundtrip opens/saves but does not export XML.
3. Page with `query_library_items`. Resolve selected records through
   `get_library_component` or `get_library_pattern`.
4. Run `validate_library_component` for pin identity, attached pattern, and pin-to-pad mapping.
   Run `validate_library_pattern` for unique pad numbers, style references, holes, and annular
   geometry.
5. When the caller states footprint requirements, optionally run `recommend_patterns` for a
   deterministic hard-filter and geometry-score ranking of compatible patterns; it is a
   read-only advisory and never mutates the library.
6. Group findings by stable item ID and preserve the source SHA-256. If native open/save evidence
   is requested, use headless `roundtrip --editor component` or `--editor pattern` on a copy;
   editor support is independent of public native-library mutation support.
7. Emit [`../shared/result.schema.json`](../shared/result.schema.json) and keep `actions` proposed
   or refused.

## Quantitative boundaries

- Query pages default to 100 records and accept 1 through 500.
- A through-hole annular ring is meaningful only when both diameter and hole values exist and
  diameter is greater than hole. Report absent values as unavailable; never invent a minimum ring.
- Duplicate pin or pad numbers are deterministic errors. Geometric manufacturability remains a
  separate fabrication-profile question.
- Coordinates returned by the service are millimetres regardless of the document `Units` value.

The public validators remain the source of these audit checks. Internal mutation evidence does not
expand the skill's callable surface.

## Refusals

- Do not call raw XML edits to imitate an unregistered public library writer.
- Do not invoke an internal mutation implementation through unsupported/private entry points.
- Do not report a library as universally DipTrace-round-trip verified; scope evidence to the exact
  controlled operations/editor/candidate that were actually tested.
- Do not infer untested mask, paste, courtyard, identity, or canonicalization semantics from a
  synthetic fixture.
- Do not turn a read-only audit into `set_component_pattern`; that operation is not native library
  mutation.

Use `document` evidence for parsed facts and `heuristic` only for explicitly named engineering
advice. Consult [`../capability-map.json`](../capability-map.json) for the public native-mutation
boundary.
