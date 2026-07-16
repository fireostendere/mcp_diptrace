# Domain Model

The domain layer is independent of XPath and exposes only Pydantic models and JSON-compatible types.
XML element identity is stored separately in `DocumentSnapshot.elements`.

## Documents and Objects

- `DocumentInfo`: source type, version, units, path, live status, size, SHA, compatibility, and warnings.
- `ObjectRecord`: stable ID, XML ID, kind, parent, RefDes/name/value, layer/side/net,
  geometry, confidence, attributes, and relationships.
- `BoardModel`: outline, components, pads, holes, traces, vias, pours, keepouts, layers,
  patterns, rules, stackup, differential pairs, ratlines, texts, and test points.
- `ViaStyleModel`: normalized diameter/hole, `Lay1`/`Lay2`, inclusive layer span,
  provenance (`explicit`/`unspecified`/`invalid`), and original XML attributes.
- `SchematicModel`: sheets, parts, pins, nets, wires, buses, ports, labels, and ERC data.
- `LibraryModel`: components, pins, patterns, pad styles, pads, holes, shapes, and 3D references.
- `ConnectivityGraph`: logical net membership, owner connected components, endpoint
  mapping, and separate physical PCB ratlines.

## SI, Review, and Workflow

- `StackupModel`, `DifferentialPairModel`, `NetLengthMeasurement`.
- `ImpedanceInput`/`ImpedanceResult` with method, assumptions, sensitivity, and confidence.
- `Finding`/`ReviewReport`, `BomRecord`, `ReturnPathAnalysis`.
- `TransactionRecord`, `PlanRecord`, `JobRecord`, `ExportRecord`.
- `QuerySelector`, `QueryRequest`, `WriteScope`.

## Stable IDs

A stable ID is generated deterministically from the source type, object kind, and verified
XML identity. It remains stable across unrelated edits, but is not guaranteed to survive
object deletion and recreation with a different XML identity. The writer modifies the
original XML tree instead of serializing the entire document from the domain model, so
unknown sections are preserved.

## Limitations

- A bounding box may be an estimate when the XML does not contain body or courtyard geometry.
- A copper pour contains its boundary, not the final refilled copper geometry.
- Cross-document pin-to-pad mapping uses explicitly documented assumptions.
- Hierarchy and library mutation are not exposed without verified writer fixtures.
