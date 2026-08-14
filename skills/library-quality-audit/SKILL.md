---
name: library-quality-audit
description: Audit DipTrace component and pattern libraries for pin, pad, mapping, geometry, and identity defects without mutating native libraries. Use when the user says “Audit these DipTrace component and pattern libraries.”
---

# Library quality audit

Audit exported Component/Pattern Library records through the public read/validation surface.
Current `main` also contains an internal raw-preserving library mutation core with controlled real
Component Editor / Pattern Editor round-trip evidence, but that core is not registered as a public
native-library write capability and this skill remains read-only.

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
5. When the caller states footprint requirements, optionally run `recommend_patterns` for a
   deterministic hard-filter and geometry-score ranking of compatible patterns; it is a
   read-only advisory and never mutates the library.
6. Group findings by stable item ID and preserve the source SHA-256.
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
