# Roadmap and Actual Status

The statuses below mean that production code, typed contracts, and tests exist. `v1`
does not imply full equivalence with the DipTrace GUI.

| Phase | Status | Implemented |
| --- | --- | --- |
| 0 | complete | baseline contract, SDK/Pydantic/package audit, capability discovery |
| 1 | complete v1 | PCB/schematic/library domain model, stable IDs, XML adapters, structured query |
| 2 | complete v1 | millimeter-normalized geometry, transforms/mirroring/arcs, spatial index, SVG/JSON preview |
| 3 | complete v1 | semantic compiler, persistent transactions, policy, SHA/preview/commit/rollback |
| 4 | complete v1 | component/part/text/rule/test-point edits, pattern swap, groups, library read/validate |
| 5 | complete v1 | registry DRC/ERC/connectivity/geometry findings and persistent reports |
| 6 | complete v1 | deterministic silkscreen candidates, plans, previews, and apply |
| 7 | complete v1 | bounded local placement candidates, scoring, legalization, and apply |
| 8 | complete v2 | trace/via primitives, bounded multi-layer 45-degree A*, and symmetric vias |
| 9 | complete v1 | bounded DSN export, Freerouting job, SES inspect/import, and post-review |
| 10 | complete v2 | coupled-pair routing, lengths/skew, and single-ended/differential microstrip impedance |
| 11 | complete v1 | return-path/plane heuristics, BOM/design comparison, DFM/DFA/DFT, and thermal skips |
| 12 | partial | library validation and generic release manifests; no library mutation, native fabrication, or solver |
| 13 | complete v1 | workflow prompts, skill contracts, CI matrix, benchmark harness, truthful discovery |

## Phase 4: Verified Boundary

Implemented operations include move, rotate, side, lock, value, properties, pattern,
align, distribute, group, board text, no-connect, net rename, NetClass rules, and
standalone test points. Pattern swap requires exact pad-number matching. Component and
Pattern Libraries are available for reading and validation.

`add_wire`, `disconnect_wire`, library create/update, and attach-pattern mutation are not
implemented because the repository does not contain verified round-trip writer fixtures
for those structures. Capability discovery reports the exact unavailability instead of
registering empty tools.

## Phases 8-10: Strict Limits

- The local router supports bounded vias and multi-layer routing with orthogonal and
  45-degree segments, but not push-and-shove or rip-up/retry.
- The DSN serializer rejects unsupported geometry instead of silently losing data.
- SES always passes internal inspection, preview, and review before import.
- Differential-pair synthesis writes both traces and the pair `Segment` atomically.
- Impedance uses preliminary-only Hammerstad-Jensen single and coupled microstrip models.
- Stripline impedance requires a verified model or an external solver.

## Phases 11-12: Strict Limits

- The copper-pour adapter reads the boundary, not the final refill.
- Return-path analysis is a geometry heuristic with confidence reporting, not full-wave SI.
- A generic fabrication manifest is not a Gerber/NC Drill package.
- Generic placement CSV requires mapping to the selected assembler's coordinate convention.
- Panelization is not implemented without verified XML semantics.
- ngspice, openEMS, and FastHenry adapters remain unregistered until typed parsers and tests exist.
- Online component sourcing is disabled by default.

## Next Engineering Tasks

1. Add redistributable real-world fixtures from the current DipTrace 5.3 branch for
   hierarchy, pours/refill, libraries, schematic before/after cases, and SES.
2. Verify custom mask, paste, and courtyard geometry against permitted 5.3 exports and
   normalize the global `Common` policy only after its XML fields are confirmed.
3. Implement schematic wire and library writers only after round-trip evidence is available.
4. Add an optional field-solver adapter for stripline and frequency-dependent analysis.

A native manufacturing adapter is excluded from the roadmap: without a verified
DipTrace API it is not planned. Generic manifests are not presented as Gerber or NC
Drill output.
