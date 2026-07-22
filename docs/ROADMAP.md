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
| 12 | partial v2 | library validation, generic release manifests, and typed optional openEMS jobs; library mutation and native fabrication remain unavailable |
| 13 | complete v1 | workflow prompts, skill contracts, CI matrix, benchmark harness, truthful discovery |
| 14 | complete v1 | project scaffolding: new schematic/PCB XML documents with stackup, rules, and sheets |
| 15 | complete v1 | schematic authoring: sheets, part placement, pin connectivity, wires, and net labels |
| 16 | complete v1 | official panelization parameters (V-Scoring / Tab Routing) and clearing |
| 17 | complete v1 | ngspice batch adapter for user-supplied netlists with typed log results |
| 18 | complete v2 | congestion-aware multi-net ordering with bounded rip-up/retry |
| 19 | complete v2 | additive and guarded exact schematic-to-PCB reconciliation with explicit multi-part pin mapping |

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
  netlists from a design. The openEMS runner adapter has a typed fixed protocol, bounded
  jobs, strict parsing, and failure tests, but no solver is bundled and its current parser
  fixture is explicitly synthetic.
- Online component sourcing is disabled by default.

## Phases 14-19: Strict Limits

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
- Congestion-aware ordering is a deterministic corridor/bounding-box heuristic, not a global
  router or push-and-shove engine.
- Exact schematic-to-PCB reconciliation is opt-in, refuses locked objects by default, and
  removes traces only when a synchronized net's endpoint set changes.

## Remaining Evidence-Gated Work

All implementation work that does not depend on the missing DipTrace 5.3 exports has
been completed. By the current project decision, items 1 and 2 below are explicitly
deferred until suitable files can be produced; item 3 remains blocked by that evidence.
The optional solver adapter in item 4 is implemented at the protocol/job layer, with only
real-runtime acceptance evidence outstanding.

### 1. Redistributable DipTrace 5.3 Fixture Pack — Deferred

Add a small synthetic, non-proprietary fixture pack exported by the current DipTrace
5.3 branch. Keep the files exactly as exported; do not hand-normalize XML before it is
committed. The target layout is:

```text
tests/fixtures/diptrace_5_3/
  manifest.json
  hierarchy/schematic.xml
  pours/before_refill.xml
  pours/after_refill.xml
  libraries/components.xml
  libraries/patterns.xml
  schematic_roundtrip/<case>/before.xml
  schematic_roundtrip/<case>/after.xml
  specctra/source_board.xml
  specctra/input.dsn
  specctra/output.ses
```

Required coverage:

- a main schematic sheet, a nested hierarchy block, hierarchy connectors, and a global
  net;
- the same PCB immediately before and after a copper-pour refill, including at least one
  cutout/island or thermal case when the GUI permits it;
- a component library with a simple component, a multi-part component, custom fields,
  and attached patterns;
- a pattern library with SMD and through-hole pads, non-trivial graphics, and pin-to-pad
  mapping evidence;
- controlled schematic before/after pairs where each pair changes one feature only:
  part placement, wire/connectivity, net label, property/value, or attached pattern;
- a real DSN/SES pair generated from the included PCB without editing the design between
  DSN export and SES import; include a routed trace and a via/multi-layer case.

The official examples installed under the user's DipTrace `Examples` directory should be
used to bootstrap local 5.3 validation instead of recreating large designs. In particular,
the `PCB_2`/`PCB_4`/`PCB_6`, `Differential_Pairs`, routed/unrouted, Banana Pi, CNC, and
SPICE examples provide useful real schematic and PCB coverage. They are shipped as binary
`.dch`/`.dip` files, so relevant cases must first be opened and exported/saved as native
5.3 XML. This installed set does not contain component/pattern library fixtures, controlled
single-setting before/after pairs, or DSN/SES files, and therefore cannot satisfy the
evidence gate by itself. Treat exported derivatives as local validation data unless their
redistribution terms are explicitly confirmed; committed fixtures must have clear
redistribution permission.

`manifest.json` must record the exact DipTrace version/build, operating system, export
workflow, source type, units, SHA-256 of every fixture, the intended semantic difference
for each before/after pair, and confirmation that the files may be redistributed in the
repository.

This item is complete when all four native source types parse, fixture-specific semantic
assertions pass, the real SES imports through the guarded preview path, and CI exercises
the pack without requiring DipTrace to be installed.

### 2. Mask, Paste, Courtyard, and `Common` Verification — Deferred

Add a focused 5.3 pattern-library export and a PCB export containing placed instances of
the patterns. The evidence matrix must cover, where the DipTrace UI supports it:

- top and bottom mask and paste settings;
- `Common`, explicit zero, positive expansion, and negative reduction;
- SMD and through-hole pads;
- custom mask/paste shapes;
- top and bottom courtyard geometry using lines, arcs, and polygons;
- rotated, bottom-side, and mirrored placed components.

For every ambiguous setting, capture two exports that differ by exactly one GUI value and
record that value in the fixture manifest. Screenshots may be kept as supporting evidence,
but machine-readable before/after exports and the manifest are authoritative.

This item is complete when the XML fields are mapped to typed model fields, transforms
are verified on placed instances, unknown fields survive a guarded round trip, and tests
prove the normalization behavior. The global `Common` policy must not be changed from
inference alone; normalize it only after the 5.3 exports identify its exact semantics.

### 3. Evidence-Gated Library Writers — Blocked by Items 1-2

After items 1 and 2 supply round-trip evidence, implement native-XML mutation for:

- creating and updating patterns;
- creating and updating components, parts, pins, graphics, and custom fields;
- attaching a pattern to a component and maintaining explicit pin-to-pad mapping;
- preserving unsupported and unknown XML structures instead of regenerating the whole
  library from the reduced domain model.

Library writes must use the existing transaction boundary: confined workspace paths,
expected source SHA, preview, commit/rollback, atomic replacement, reparsing, and
post-write validation. Name collisions and replacement must be explicit; a writer must
not silently overwrite an unrelated library item.

This item is complete when every supported mutation has before/after fixture tests, the
result imports into DipTrace 5.3 without warnings, a DipTrace open/save/re-export cycle is
semantically equivalent, a second identical MCP operation produces no change, and
capability discovery truthfully registers the new tools.

### 4. Optional Frequency-Dependent Field-Solver Adapter — Implemented v1

The openEMS runner adapter is implemented with a fixed typed JSON protocol. The MCP tool
is registered, but runtime capability is available only when
`DIPTRACE_MCP_OPENEMS_RUNNER` points to a compatible backend.

The typed request must include conductor geometry, stackup/material properties, trace
offset, frequency sweep, and solver/mesh controls. The typed result must include the
frequency vector, complex characteristic impedance, propagation constant, available loss
terms, solver version, convergence/mesh metadata, logs, and generated artifacts.

Implemented validation cases are:

- centered symmetric stripline checked against the existing analytical implementation;
- off-center stripline that is explicitly unsupported by the closed-form implementation;
- a multi-frequency sweep with a stored synthetic protocol fixture that is never presented
  as real solver output;
- unavailable executable, timeout, malformed output, and non-converged solver outcomes.

Execution uses an isolated job workspace, sanitized environment, fixed command arguments,
explicit time/result/log limits, and the existing asynchronous job/error contracts. CI
parses the synthetic protocol fixture and runs deterministic fake backends by default.

Typed parsing, failure handling, portability, timeout, frequency binding, and centered
analytical sanity tests are complete. A captured real-openEMS result and one configured
integration run remain an acceptance-evidence task; they do not cause fallback or
fabricated output when the solver is absent.

## Roadmap Closure Definition

The remaining completion order is: obtain the deferred fixture pack, verify the geometry
policy, then implement and round-trip the library writers. Phase 12 and the declared
roadmap remain partial until those evidence-gated items pass. The openEMS adapter is
complete v1 at the protocol/job layer and gains solver-verified status only after a real
captured integration run.

Completion does not mean full DipTrace GUI equivalence. A native manufacturing adapter is
excluded without a verified DipTrace API; generic manifests are not Gerber or NC Drill
output. Full push-and-shove/global autorouting, GUI automation, and always-on online
sourcing also remain explicit product boundaries rather than unfinished roadmap items.
