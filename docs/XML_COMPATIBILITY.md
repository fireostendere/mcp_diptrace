# XML Compatibility

## Supported Source Types

- `DipTrace-PCB`
- `DipTrace-Schematic`
- `DipTrace-ComponentLibrary` — normalized reading and validation for the tested 4.3 fixture.
- `DipTrace-PatternLibrary` — normalized reading and validation for the tested 4.3 fixture.

## Official Format Evidence

- [PCB XML specification](https://www.diptrace.com/books/DipTraceXML_Pcb_En.pdf)
- [Schematic XML specification](https://diptrace.com/books/DipTraceXML_Schematic_En.pdf)
- [Component Editor XML specification](https://www.diptrace.com/books/DipTraceXML_CompEdit_En.pdf)
- [Pattern Editor XML specification](https://www.diptrace.com/books/DipTraceXML_PattEdit_En.pdf)
- [DipTrace plug-ins specification](https://diptrace.com/books/DipTrace_Plugins.pdf)

`Version` is preserved in document identity and the compatibility report, but it is not
the only gate. The reader uses feature detection, tolerates omitted optional/default
parameters, and preserves unknown sections. Each write operation separately verifies
the fields it requires.

A live import/re-export acceptance run with DipTrace 5.3 confirms that real Schematic
XML may use `Version="5.3.0.2"`, while the publicly available specifications and some
examples still use `4.3.0.3`. Component and Pattern Library documents have been observed
with `5.3.0.0` and embedded legacy versions. The application version and the XML
`Version` value are not treated as interchangeable.

## Implemented Readers

- XML root validation for `<Source>` and official standalone `<Library>` roots.
- Rejection of `DOCTYPE` and `ENTITY` declarations.
- PCB outline, components, pads, holes, nets, ratlines, copper layers, physical stackup, and rules.
- Trace arcs, segment width and layer, vias, pour boundaries, text, keepouts, and differential pairs.
- Schematic sheets, parts, pins, nets, fixture-covered wires, buses, and ERC blobs.
- Component Library parts, pins, fields, attached patterns, and pin-to-pad mapping.
- Pattern pad styles, pads, holes, shapes, mask/paste metadata, and 3D references.

## Implemented Writers

- New document scaffolding: `create_schematic_document` and `create_pcb_document`
  generate official-structure XML (sheets, outline, layers, stackup, via styles, net
  classes, DRC) and validate it by parsing before writing.
- Low-level XML edits through `apply_xml_edits`.
- Semantic component, part, pattern, group, text, schematic no-connect/net, NetClass, and
  test-point edits.
- Schematic authoring: sheets, part placement, pin/net connectivity, official
  `<Net>/<Wires>/<Wire>/<Points>` wires, and net-bound text labels.
- Additive schematic-to-PCB authoring: PCB components, embedded pattern/pad-style subtrees,
  net pad endpoints, and ratlines. Pattern-library units must match PCB units; multi-part
  pin-to-pad mapping must be explicit when it cannot be proven from XML.
- Official PCB `<Panel>` panelization parameters (V-Scoring / Tab Routing).
- Official PCB `<Net>/<Traces>/<Trace>/<Points>/<Point>` patches for trace and via primitives.
- Atomic coupled-pair patches: two traces plus `DifferentialPairs/Segments/Segment`.
- Atomic write, backup, and reparse after writing.

## Compatibility Matrix

| Source | Read | Write | Round-trip |
| --- | --- | --- | --- |
| PCB XML 4.3.0.3 synthetic fixture | yes | partial semantic writes | tested objects plus preservation of unknown XML |
| PCB XML 5.3.0.2 installed example | yes; local bridge acceptance | not mutated | complex four-layer design parsed without warnings; redistributable fixture pending |
| Other DipTrace 5.x XML | feature-detected | per-operation evidence gate | preserve unknown XML; a matching fixture is preferred |
| Schematic XML 4.3.0.3 synthetic fixture | yes | partial semantic writes | tested objects plus preservation of unknown XML |
| Schematic XML 5.3.0.2 live project | yes | bounded raw/semantic writes | manual bridge apply and independent DipTrace re-export verified |
| Schematic XML 5.3.0.2 installed example | yes; local bridge acceptance | not mutated | seven-sheet design parsed without warnings; hierarchy not proven |
| Component Library XML 4.3 fixture | yes | expert XML only | read/validate plus preservation of unknown XML |
| Pattern Library XML 4.3 fixture | yes | expert XML only | read/validate plus preservation of unknown XML |
| Component Library XML 5.3.0.2 installed example | yes; local bridge acceptance | unavailable | 187-component library parsed without warnings; redistributable fixture pending |
| Pattern Library XML 5.3.0.2 installed example | yes; local bridge acceptance | unavailable | 181-pattern library parsed without warnings; redistributable fixture pending |
| Other Component/Pattern Library XML 5.3.x | feature-detected | unavailable | preserve unknown XML; matching fixtures preferred |
| DSN/SES fixtures | bounded subset | semantic SES import | tested bounded subset |

## Notes

- Unknown XML sections and original bytes outside targeted nodes are preserved by the
  raw-patch compiler. Structural additions serialize only the new subtree. After reparse,
  the semantic tree must match the compiled model.
- Native binary `.dip` and `.dch` files are not parsed directly. Export them to DipTrace
  XML first, unless the specific file is already stored as XML and begins with an
  official DipTrace XML root.
- PCB and Schematic golden fixtures are synthetic 4.3.0.3 fixtures derived from the
  public official specifications. A real 5.3.0.2 schematic acceptance run preserved all
  41 scoped marking coordinates and the normalized sheet/part/pin/net/bus/differential-
  pair counts after DipTrace import and re-export. The user project is not redistributed,
  so a permitted fixture is still required for automated 5.3 round-trip CI.
- DipTrace canonicalized numeric values and derived fields during that re-export and
  removed two unreferenced embedded Pattern records. Neither PatternStyle was referenced
  by a part before or after import. Byte equality is therefore required across MCP
  patching outside targets, but not across a subsequent DipTrace import/export cycle.
- Segment parameters are written on the second point, as required by the official PCB XML specification.
- Via-style geometry reads documented `Size`/`HoleSize` and observed
  `Diameter`/`Hole` aliases. Explicit `Lay1`/`Lay2` values are normalized to an inclusive
  physical layer span. An omitted span is accepted only on a two-layer board. On larger
  stackups, automatic via routing is disabled until the span is known.
- A copper-pour boundary is not interpreted as final refilled copper.
- Schematic wire authoring follows the official specification structure; a live DipTrace
  import/re-export acceptance run for authored wires is still pending, so the writer is
  covered by synthetic round-trip tests only.
- Library mutation remains unavailable until writer round-trip fixtures exist.
- The installer includes read-only Component and Pattern Editor bridge profiles. They use
  the official whole-library export mode with imports disabled, allowing local 5.3
  inspection without implying writer or round-trip support.
- **Synthetic MCP-generated XML** (from `create_schematic_document` or
  `create_pcb_document`) has the correct XML structure but has not been verified by
  DipTrace open/save. Use `create_document_from_seed` with a real DipTrace export when
  compatibility is required.
- **Plane layer routing** is not supported. Only Signal layers accept active trace
  segments. Through-via spans across Plane layers are allowed.
- **Ratline generation** follows the DipTrace XML structure but has not been verified
  by DipTrace open/save/re-export. Synthetic scaffolding ratlines are experimental.

## Version Baseline

The documentation and live acceptance path were reviewed against an installed DipTrace
5.3 build exporting XML `Version="5.3.0.2"`. The official XML specification PDFs used
by this project still show 4.3-era examples, so compatibility claims remain
feature-based and fixture-based rather than inferred solely from the application
version number.
