# XML Compatibility

DipTrace MCP uses feature detection, raw-preserving patches, and explicit evidence levels rather than assuming compatibility from a file extension or application version alone.

The runtime source of truth is `get_capabilities`. This document describes the maintained compatibility baseline, not a promise that every XML object in every DipTrace build has been round-trip verified.

## Supported Source Types

- `DipTrace-PCB`;
- `DipTrace-Schematic`;
- `DipTrace-ComponentLibrary`;
- `DipTrace-PatternLibrary`.

Standalone Component/Pattern Libraries are currently supported for normalized reading and validation. Native library mutation remains evidence-gated and is not registered as a normal capability.

## Official Format Evidence

The implementation is constrained by the official DipTrace XML and plug-in specifications plus controlled observed exports. The maintained references include PCB, Schematic, Component Editor, Pattern Editor, and executable plug-in XML documentation.

`Version` is preserved in document identity and compatibility reports, but it is not the sole compatibility gate. Readers use feature detection, tolerate documented optional/default fields, preserve unknown sections, and require each writer to validate the structures it needs.

A live import/re-export acceptance run with DipTrace 5.3 has confirmed real Schematic XML using `Version="5.3.0.2"`. Component and Pattern Library exports have also been observed from DipTrace 5.3, while some public specification examples remain 4.3-era. Application version and XML `Version` are therefore treated as related but non-equivalent evidence.

## Implemented Readers

- `<Source>` and official standalone `<Library>` root validation;
- rejection of `DOCTYPE` and `ENTITY` declarations;
- PCB outline, components, pads, holes, nets, ratlines, copper layers, physical stackup, and rules;
- trace arcs, segment width/layer, vias, pour boundaries, text, keepouts, and differential pairs;
- schematic sheets, parts, pins, nets, fixture-covered wires, labels, buses, hierarchy records, and ERC data;
- Component Library parts, pins, fields, attached patterns, and pin-to-pad mapping;
- Pattern Library pad styles, pads, holes, shapes, mask/paste metadata, courtyard-related geometry where present, and 3D references;
- unknown/unsupported XML remains accessible through raw XML inspection and is preserved outside targeted patches.

## Implemented Writers

- synthetic document scaffolding through `create_schematic_document` and `create_pcb_document`;
- seed-based copies through `create_document_from_seed`;
- low-level guarded XML edits through `apply_xml_edits`;
- semantic component, part, pattern-assignment, group, board-text, schematic property/no-connect/net, NetClass, and test-point edits;
- schematic authoring: sheets, part placement, logical pin/net connectivity, official `<Net>/<Wires>/<Wire>/<Points>` wires, and net-bound labels;
- additive and guarded exact schematic-to-PCB synchronization, including PCB components, embedded pattern/pad-style subtrees, pad membership, nets, ratlines, and explicit multi-part pin mapping where inference is insufficient;
- official PCB `<Panel>` parameters for V-Scoring / Tab Routing;
- official PCB trace/via structures and coupled differential-pair segment metadata;
- atomic writes, backups, SHA conflict protection, and reparsing after modification.

## Compatibility and Evidence Levels

A parser success is not equivalent to a real DipTrace writer round trip. The project distinguishes:

- `synthetic_parser_only` — MCP-generated XML accepted by the MCP parser;
- `synthetic_operation_fixture` — MCP-generated XML exercised by semantic operations;
- `diptrace_exported` — XML exported by DipTrace;
- `diptrace_open_save_verified` — file opened and saved by DipTrace;
- `diptrace_roundtrip_verified` — controlled open/save/re-export evidence with semantic comparison;
- `external_tool_roundtrip_verified` — equivalent evidence including an external tool path.

User-controlled manifests, sidecars, labels, or hashes cannot mint high-trust levels by themselves.

## Compatibility Matrix

| Source | Read | Write | Evidence status |
| --- | --- | --- | --- |
| PCB XML 4.3.0.3 synthetic fixtures | yes | partial semantic writes | parser/operation regression coverage; unknown XML preserved |
| PCB XML 5.3.0.2 installed examples | yes | not broadly mutation-verified | complex multilayer examples parsed locally; redistributable round-trip fixtures still needed |
| Other DipTrace 5.x PCB XML | feature-detected | per-operation | preserve unknown XML; matching fixture preferred |
| Schematic XML 4.3.0.3 synthetic fixtures | yes | partial semantic writes | parser/operation regression coverage |
| Schematic XML 5.3.0.2 live project | yes | bounded raw/semantic writes | real bridge apply + independent DipTrace re-export verified for scoped marking edits |
| Schematic XML 5.3.0.2 installed examples | yes | not broadly mutation-verified | multi-sheet examples parsed locally; hierarchy/writer fixture coverage still incomplete |
| Component Library XML 4.3 fixture | yes | expert raw XML only | normalized read/validate + unknown preservation |
| Pattern Library XML 4.3 fixture | yes | expert raw XML only | normalized read/validate + unknown preservation |
| Component Library XML 5.3 local export | yes | unavailable as native writer | local read-only bridge acceptance; redistributable fixture pending |
| Pattern Library XML 5.3 local export | yes | unavailable as native writer | local read-only bridge acceptance; redistributable fixture pending |
| Other 5.3.x libraries | feature-detected | unavailable | preserve unknown XML; matching fixtures preferred |
| DSN/SES bounded subset | yes | guarded SES import | synthetic/mocked regression coverage; real paired DipTrace fixture still required |

## Known Writer Evidence Gaps

The following are implemented but still need stronger real-DipTrace evidence before they should be described as broadly round-trip verified:

- authored schematic wires;
- generated ratlines;
- representative PCB semantic writes on DipTrace 5.3;
- schematic-to-PCB synchronization across controlled 5.3 before/after fixtures;
- SES import through a real DipTrace-produced DSN/SES pair;
- Component/Pattern Library writers, which remain blocked and unregistered.

The trust layer also currently reports incomplete all-path invalidation coverage for `plan_apply`, `ses_import`, `schematic_to_pcb_sync`, and `live_session_apply`. This is a trust/evidence gap, not permission to silently claim higher compatibility.

## Mask, Paste, Courtyard, and `Common`

The parser already models significant mask/paste and pattern geometry, but some DipTrace 5.3 semantics remain evidence-gated. Controlled exports are still required for:

- top/bottom mask and paste;
- `Common` versus explicit values;
- zero, positive expansion, and negative reduction;
- custom mask/paste shapes;
- SMD and through-hole pads;
- top/bottom courtyard lines, arcs, and polygons;
- mirrored/rotated/bottom-side placed instances.

The global `Common` policy must not be normalized from inference alone. One-setting-at-a-time DipTrace exports are the acceptance source.

## Layer Resolution

Copper layers are resolved by case-insensitive name or exact ID. The normalized result includes layer identity and type (`Signal`, `Plane`, or unknown).

Routing requires active trace segments on routable signal layers. Plane layers are not accepted as active trace-routing layers, although through-via spans may cross plane layers. On multilayer boards, automatic via routing requires a confirmed span; an omitted span is accepted only in the explicitly supported two-layer case.

## Preservation Rules

- raw patches preserve original bytes outside targeted regions where the patch model permits;
- structural additions serialize only the new subtree instead of regenerating the whole document;
- unknown XML is preserved whenever the operation does not need to own that structure;
- semantic post-parse checks compare the resulting model against the intended operation;
- DipTrace itself may canonicalize numeric fields or derived structures on import/export, so byte equality is required for untouched MCP regions but not across an independent DipTrace round trip.

A prior live schematic acceptance run observed DipTrace canonicalization and removal of unreferenced embedded pattern records. That behavior is treated as application canonicalization rather than proof that arbitrary reserialization is safe.

## Binary and Native-XML Files

Legacy binary `.dip`/`.dch` files are not parsed as binary project formats. Export them through DipTrace XML first.

Some current `.dip`, `.dch`, `.eli`, or `.lib` files may already contain XML. Direct analysis is allowed only when the content passes official DipTrace XML root validation; the extension alone is not trusted.

## Current 5.3 Baseline

The maintained code and documentation were reviewed against an installed DipTrace 5.3.0.2 environment. A live schematic round trip preserved all 41 scoped marking-coordinate changes, stable normalized object counts, and offline ERC severity counts.

Representative installed PCB, multi-sheet schematic, Component Library, and Pattern Library exports have also parsed without warnings through local bridge acceptance. Because those files are not committed as redistributable fixtures, they increase confidence but do not close automated CI evidence gates.

See [ROADMAP.md](ROADMAP.md) for the fixture pack and writer-verification exit criteria.
