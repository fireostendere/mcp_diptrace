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
| 10 | complete v3 | coupled-pair routing, lengths/skew, microstrip and IPC-2141 symmetric stripline impedance |
| 11 | complete v1 | return-path/plane heuristics, BOM/design comparison, DFM/DFA/DFT, and thermal skips |
| 12 | partial | library validation and generic release manifests; no library mutation, native fabrication, or solver |
| 13 | complete v1 | workflow prompts, skill contracts, CI matrix, benchmark harness, truthful discovery |
| 14 | complete v1 | project scaffolding: new schematic/PCB XML documents with stackup, rules, and sheets |
| 15 | complete v1 | schematic authoring: sheets, part placement, pin connectivity, wires, and net labels |
| 16 | complete v1 | official panelization parameters (V-Scoring / Tab Routing) and clearing |
| 17 | complete v1 | ngspice batch adapter for user-supplied netlists with typed log results |
| 18 | complete v1 | sequential multi-net routing with bounded rip-up/retry |
| 19 | complete v1 | additive schematic-to-PCB component/net/ratline synchronization with explicit multi-part pin mapping |

## Phase 4: Verified Boundary

Implemented operations include move, rotate, side, lock, value, properties, pattern,
align, distribute, group, board text, no-connect, net rename, NetClass rules, and
standalone test points. Pattern swap requires exact pad-number matching. Component and
Pattern Libraries are available for reading and validation.

Library create/update and attach-pattern mutation are not implemented because the
repository does not contain verified round-trip writer fixtures for those structures.
Capability discovery reports the exact unavailability instead of registering empty tools.

## Phases 8-10: Strict Limits

- The local router supports bounded vias and multi-layer routing with orthogonal and
  45-degree segments, but not push-and-shove. Sequential multi-net routing with bounded
  rip-up/retry is available through `route_connections`.
- The DSN serializer rejects unsupported geometry instead of silently losing data.
- SES always passes internal inspection, preview, and review before import.
- Differential-pair synthesis writes both traces and the pair `Segment` atomically.
- Impedance uses preliminary-only Hammerstad-Jensen single/coupled microstrip and the
  IPC-2141 centered symmetric stripline closed form; frequency-dependent and off-center
  stripline analysis requires an external solver.

## Phases 11-12: Strict Limits

- The copper-pour adapter reads the boundary, not the final refill.
- Return-path analysis is a geometry heuristic with confidence reporting, not full-wave SI.
- A generic fabrication manifest is not a Gerber/NC Drill package.
- Generic placement CSV requires mapping to the selected assembler's coordinate convention.
- The ngspice adapter runs user-supplied netlists in batch mode; it does not generate
  netlists from a design. openEMS and FastHenry adapters remain unregistered until typed
  parsers and tests exist.
- Online component sourcing is disabled by default.

## Phases 14-18: Strict Limits

- Scaffolding generates official 4.3-era XML structures; DipTrace import may canonicalize
  numeric values and derived fields, as with any other XML import.
- `place_part` references a library `ComponentStyle` by name; the symbol graphics and pin
  mapping are resolved by DipTrace from the configured libraries on import, not by the MCP.
- Schematic wires follow the official `Wire`/`Points` schema; pin-to-net connectivity is
  maintained separately via `connect_pins`/`disconnect_pins`.
- Panelization writes official `Panel` parameters only; tab coordinates are recomputed by
  DipTrace (`TabsDone="N"`), and no panel geometry is expanded by the MCP.
- The ngspice adapter never fabricates simulation results: an unavailable executable ends
  in `external_tool_unavailable`.
- Multi-net rip-up/retry is bounded to batch-local candidates and never rips traces that
  were routed outside the current call.

## Next Engineering Tasks

1. Add redistributable real-world fixtures from the current DipTrace 5.3 branch for
   hierarchy, pours/refill, libraries, schematic before/after cases, and SES.
2. Verify custom mask, paste, and courtyard geometry against permitted 5.3 exports and
   normalize the global `Common` policy only after its XML fields are confirmed.
3. Implement library writers only after round-trip evidence is available.
4. Add an optional field-solver adapter for frequency-dependent and off-center stripline
   analysis.
5. Extend multi-net routing with congestion-aware ordering heuristics.
6. Extend schematic-to-PCB synchronization with a verified destructive reconciliation mode;
   the v1 operation intentionally preserves extra PCB objects and all existing traces.

A native manufacturing adapter is excluded from the roadmap: without a verified
DipTrace API it is not planned. Generic manifests are not presented as Gerber or NC
Drill output.
