# Domain Model

The normalized document/domain layer is independent of XPath and exposes Pydantic models and JSON-compatible types. XML element identity is stored separately in `DocumentSnapshot.elements`.

The intelligent-layout layer builds additional typed intent models above normalized documents. These models may consume exported connectivity and project/operator constraints, but they do not become a second XML representation and do not write files directly.

## Documents and Objects

- `DocumentInfo`: source type, version, units, path, live status, size, SHA, compatibility, and warnings.
- `ObjectRecord`: stable ID, XML ID, kind, parent, RefDes/name/value, layer/side/net, geometry, confidence, attributes, and relationships.
- `BoardModel`: outline, components, pads, holes, traces, vias, pours, keepouts, layers, patterns, rules, stackup, differential pairs, ratlines, texts, and test points.
- `ViaStyleModel`: normalized diameter/hole, `Lay1`/`Lay2`, inclusive layer span, provenance (`explicit`/`unspecified`/`invalid`), and original XML attributes.
- A routed physical via is a trace point with a valid `ViaStyle` **and** an actual change between the incoming and outgoing `Lay`. `ViaStyle` on a same-layer point is preserved as trace metadata but is not normalized as a via. Standalone/static vias are normalized from `Components/Component[@Type='Via']`.
- `SchematicModel`: sheets, parts, pins, nets, wires, buses, ports, labels, and ERC data.
- `LibraryModel`: components, pins, patterns, pad styles, pads, holes, shapes, and 3D references.
- `ConnectivityGraph`: logical net membership, owner connected components, endpoint mapping, and separate physical PCB ratlines.

## Intelligent schematic/PCB intent

The layout engines deliberately distinguish **observed document facts** from **engineering intent inferred or supplied from those facts**.

Schematic intent remains in the schematic layout modules. PCB Generation A adds the internal models in `pcb_design_intent.py`:

- `PCBDesignIntent`: document-level component, net, functional-block and power/ground intent plus explicit assumptions/warnings;
- `PCBComponentIntent`: role, functional block/anchor, mechanical-anchor status, noise emission/sensitivity, thermal role, placement priority, confidence and reasons;
- `PCBNetIntent`: multi-role electrical classification, component membership, criticality, noise risk, via penalty, reference-plane expectation, optional electrical constraints, confidence and reasons;
- `PCBFunctionalBlock`: deterministic principal-anchor/support grouping;
- `PCBPowerGroundStrategy`: continuous-plane, local plane/pour, local-copper-minimized, Kelvin-candidate, chassis/shield or explicit-star intent;
- `PCBElectricalConstraints`: optional edge rate, frequency, current, impedance/tolerance, length/skew, via/layer/reference/spacing/stub/shielding facts;
- `PCBIntentOverrides`: project/operator facts that replace or supplement heuristic inference when XML cannot prove a property.

A net may have several roles at once. For example, a current-sense net can be analog, precision-sensitive and current-sense simultaneously. Physical values stay `None` unless exported or supplied; role classification never fabricates a current, edge rate or impedance target.

The power/ground intent model is policy, not copper geometry. Generation A prefers a continuous reference for ordinary ground and never infers a split/star ground merely because analog/digital names are present. Deeper PDN, return-path, stackup and field reasoning belongs to later PCB generations.

## Placement models

The existing `PlacementConfig`/`PlacementProposal`/`PlacementPlanningResult` models describe bounded local legalization and retain the established outline/keepout/overlap safety behavior.

PCB Generation A adds `PCBPlacementV2Config`, `PCBPlacementV2Score`, `PCBPlacementV2Analysis` and `PCBPlacementV2Plan`. The v2 planner consumes `PCBDesignIntent`, reuses the existing placement scorer for hard geometry, adds decomposed electrical-intent terms, and emits ordinary semantic move operations. It is intentionally an internal EDA layer rather than a new public MCP contract.

## SI, Review, and Workflow

- `StackupModel`, `DifferentialPairModel`, `NetLengthMeasurement`.
- `ImpedanceInput`/`ImpedanceResult` with method, assumptions, sensitivity, and confidence.
- `FieldSolverRequest`/`FieldSolverResult`/`FieldSolverPoint` for a frequency-bound, convergence-aware external stripline result.
- `Finding`/`ReviewReport`, `BomRecord`, `ReturnPathAnalysis`.
- `TransactionRecord`, `PlanRecord`, `JobRecord`, `ExportRecord`.
- `QuerySelector`, `QueryRequest`, `WriteScope`.

## Stable IDs

A stable ID is generated deterministically from the source type, object kind, and verified XML identity. It remains stable across unrelated edits, but is not guaranteed to survive object deletion and recreation with a different XML identity. The writer modifies the original XML tree instead of serializing the entire document from the domain model, so unknown sections are preserved.

Intent models reference normalized stable IDs rather than inventing a parallel object identity. Operator overrides may select by stable ID or unambiguous human identifier, then resolve to the normalized stable ID before optimization.

## Limitations

- A bounding box may be an estimate when the XML does not contain body or courtyard geometry.
- A copper pour contains a normalized polygon for its exported boundary, layer, and net identity, not the final refilled copper geometry. Clearance and routing consumers must disclose `boundary_only`; GEOS polygon distance is exact only with respect to that boundary, while the no-Shapely fallback is a conservative AABB approximation.
- PCB Generation A noise/thermal/current-return fields are design intent and deterministic placement proxies, not physical simulation results.
- Cross-document pin-to-pad mapping uses explicitly documented assumptions.
- `via_count` is the number of normalized physical vias on a net, while `layer_transition_count` counts only routed layer changes; standalone static vias may increase the former without increasing the latter.
- Hierarchy and library mutation are not exposed without verified writer fixtures.
