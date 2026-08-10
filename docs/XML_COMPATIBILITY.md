# XML Compatibility

DipTrace MCP uses feature detection, raw-preserving mutation, typed semantic operations and explicit evidence levels rather than assuming compatibility from a file extension or application version alone.

Runtime `get_capabilities` is authoritative for the active installation/document. This document describes the maintained compatibility baseline of current `main`; it is not a promise that every DipTrace 5.x object or editor path has been round-trip verified.

## Supported source types

- `DipTrace-PCB`;
- `DipTrace-Schematic`;
- `DipTrace-ComponentLibrary`;
- `DipTrace-PatternLibrary`.

PCB and Schematic have public guarded write paths. Component/Pattern Library XML has normalized read/validation support plus an **internal raw-preserving mutation core with controlled real Component Editor / Pattern Editor round-trip evidence**. Native library mutation is still not registered as a normal public MCP write capability.

## Evidence classes

Do not collapse these levels:

- `synthetic_parser_only` — project-generated XML accepted by the parser;
- `synthetic_operation_fixture` — project-generated XML exercised by semantic operations;
- `diptrace_exported` — XML exported by DipTrace;
- `diptrace_open_save_verified` — controlled native open/save evidence;
- `diptrace_roundtrip_verified` — controlled open/save/re-export with semantic comparison;
- `external_tool_roundtrip_verified` — equivalent evidence including an external tool path.

User-controlled manifests/sidecars/hashes cannot mint package-owned high trust.

Historical/manual evidence stays bound to the exact build/candidate on which it was observed. Later `main` development does not inherit a PASS automatically.

## Maintained real-host observations

The current project evidence includes, within the stated exact scopes:

- Windows/WSL live acceptance on DipTrace 5.2.0.4 for scoped PCB/Schematic apply, cancel and wrong-SHA behavior; PCB apply included GUI/save/independent re-export confirmation;
- later real PCB and Schematic open/save/re-export round trips on the accepted production checkpoint;
- real Component Editor and Pattern Editor writer save/reopen/re-export with semantic preservation and writer idempotence for the internal raw-preserving mutation core;
- generated PCB ratlines and authored schematic wires surviving native round trip;
- MASK / PASTE / COURTYARD / `COMMON` semantics campaign PASS on the accepted checkpoint;
- Q1 Component Angle GUI/re-export PASS on DipTrace PCB Layout 5.3.0.3, including 90/180/270 degree serialization and bottom-side/change-side behavior.

The immutable `v0.2.1` release record predates the later Q1 campaign and therefore correctly retains `NOT_RUN` for that release. Do not rewrite release history from later evidence.

## Implemented readers

Current readers/model adapters cover, among other structures:

- bounded `<Source>` validation plus feature-detected standalone `<Library>` roots;
- rejection of `DOCTYPE` / `ENTITY` declarations;
- PCB outline, components, pads, holes, nets, ratlines, copper layers, physical stackup and rules;
- traces/arcs/width/layer/vias, pour boundaries, text, keepouts and differential pairs;
- schematic sheets, parts, pins, nets, wires, labels, buses, hierarchy records and ERC data where modeled;
- Component Library components/parts/pins/fields/pattern attachment/pin-to-pad mapping;
- Pattern Library pad styles/pads/holes/shapes/mask/paste/courtyard/3D references where present;
- raw preservation/access for unmodeled XML outside structures owned by a targeted operation.

Parser support is not a normative specification of the DipTrace format.

## Implemented writers

Public/guarded write paths include:

- synthetic document scaffolding and seed-based copies;
- bounded raw XML edits;
- semantic PCB component/text/group/pattern assignment/test-point/NetClass and related property edits;
- schematic sheets, part placement, logical pin/net connectivity, official wire structures and net-bound labels;
- additive/exact schematic-to-PCB synchronization for the implemented object classes;
- PCB panel parameters;
- trace/via structures and differential-pair metadata;
- preview/expected-SHA/policy/backup/atomic-write/transaction/reparse checks.

The internal Component/Pattern mutation core can perform bounded raw-preserving native-library changes under its own evidence boundary, but it remains below the public MCP write-tool boundary until a separate API decision.

Internal schematic/PCB optimizers only produce candidates/plans/semantic operations; they do not become an alternate XML writer.

## Compatibility matrix

| Source / path | Read | Write | Maintained evidence boundary |
| --- | --- | --- | --- |
| PCB synthetic fixtures | yes | scoped semantic writes | parser/operation regression, unknown XML preservation |
| PCB DipTrace 5.2.0.4 live project | yes | scoped live write | real apply + GUI/save/re-export; cancel/wrong-SHA PASS for tested matrix |
| PCB DipTrace 5.3.x | feature-detected | per operation | later real round-trip/scoped semantics evidence exists; not universal writer coverage |
| Schematic synthetic fixtures | yes | scoped authoring/semantic writes | parser/operation regression |
| Schematic DipTrace 5.2.0.4 live project | yes | scoped live write | real apply; cancel/wrong-SHA PASS for tested matrix |
| Schematic DipTrace 5.3.x | feature-detected | bounded semantic writes | later real open/save/re-export plus authored-wire evidence; broader hierarchy/product-readability acceptance remains scoped |
| Component Library synthetic/project fixtures | yes | internal raw-preserving core | automated regression; public native writer not registered |
| Pattern Library synthetic/project fixtures | yes | internal raw-preserving core | automated regression; public native writer not registered |
| Component Editor real controlled path | yes | internal core | save/reopen/re-export + semantic preservation/idempotence evidence on accepted checkpoint |
| Pattern Editor real controlled path | yes | internal core | save/reopen/re-export + semantic preservation/idempotence evidence on accepted checkpoint |
| DSN/SES bounded subset | yes | guarded SES import path | synthetic/mocked regression; real paired DipTrace DSN/SES acceptance remains a separate claim |

`Version` participates in identity/reporting but is not the sole compatibility gate. Changing a literal format version is not conversion evidence.

## Q1 Component Angle

The old implementation question “radians or degrees?” is no longer unknown at the project-manual level for the accepted production checkpoint.

Observed with DipTrace PCB Layout 5.3.0.3:

- GUI 90° -> `Angle="1.5708"`;
- 180° -> `3.1416`;
- 270° -> `4.7124`;
- GUI 360° normalizes to 0° and canonical zero may omit the attribute;
- Change Side from Top 90° produced Bottom `Angle="4.7124"`, `Flip="Y"`, with `mirrored=true` in the reader.

Package-owned public trust promotion is separate from the private/manual campaign. The code/documentation should therefore distinguish “manual convention observed” from “every released artifact/path publicly verified”.

## Mask, paste, courtyard and `COMMON`

The accepted manual campaign closed the earlier project-level semantics gate:

- MASK — PASS;
- PASTE — PASS;
- COURTYARD — PASS after the historical parser defect was repaired;
- `COMMON` — PASS, with native Common represented by omission and explicit override represented distinctly without invented numeric defaults.

This is scoped evidence, not universal proof for every pad/custom-shape/editor combination.

## Ratlines and authored wires

The historical `diptrace_ratline_and_wire_roundtrip` gate is PASS. Later schematic readability routing is broader than that gate and therefore still has its own product-level quality acceptance work.

## Library mutation boundary

Earlier documentation correctly treated native Component/Pattern mutation as unavailable. Current `main` now has a raw-preserving internal mutation core and controlled real editor evidence.

Remaining boundaries are:

- the full format/canonicalization space is not claimed understood;
- public write-tool registration has not been approved;
- real evidence is scoped to the exercised operations/candidates;
- provenance/redistribution restrictions still apply to source materials;
- unsupported/unmodeled structures must remain preserved or refused rather than guessed.

## Copper pours and physical PCB evidence

The normalized copper-pour boundary is not automatically authoritative final refill geometry. PCB Generations B-D may consume exported stackup/reference/pour-related facts conservatively, but missing refill/current/current-density/voltage-drop/reference authority remains explicit.

Claims involving final poured copper, plane behavior, via structures or manufacturing semantics require native generate/open/refill/DRC/save/reopen/re-export evidence as documented in `PCB_DESIGN_ENGINE.md` and `ROADMAP.md`.

## Encoding and byte preservation

`DipTraceDocument` preserves supported source encodings/BOM/untouched bytes where the raw patch model permits. UTF-32/unsupported declarations fail closed. That is an MCP safety property, not proof that DipTrace emits or imports every supported parser encoding.

Independent DipTrace save/re-export may canonicalize ordering, defaults, numbers, whitespace or derived structures. Byte equality is required for untouched MCP regions where promised, not for an independent native round trip.

## Layer/routing resolution

Copper layers are resolved by identity/name and normalized type. Active trace routing requires routable signal layers; through-via spans may cross plane layers under the existing bounded rules. Multilayer automatic via routing requires an explicit/confirmed span except for the documented simple two-layer case.

Routing-point vocabulary, real DSN/SES conventions, complex jumper/meander/arcs and other feature-specific host behavior retain the evidence boundaries documented in `OPEN_QUESTIONS.md` / generated `PROBE_PACK.md`.

## Preservation rules

- targeted raw patches preserve bytes outside owned regions where supported;
- structural additions serialize the new/owned subtree rather than regenerating the entire document;
- unknown XML is preserved whenever the operation does not own that structure;
- post-parse checks compare the resulting normalized state against intended semantic effects;
- live apply/cancel/wrong-SHA uses session/exchange/original identity checks;
- external/native canonicalization is reported as observed evidence rather than silently inferred.

## Native file extensions

Legacy binary `.dip` / `.dch` files are not parsed as binary project formats. Export to supported XML first.

Some current `.dip`, `.dch`, `.eli` or `.lib` files may themselves contain XML. Direct analysis is allowed only when the content passes supported DipTrace XML root validation; the extension is not trusted by itself.

## Remaining compatibility questions

Important unresolved or claim-specific areas include:

- completeness of `ExpMode=All` relative to all object classes under `ImpMode=All`;
- broad current-version cancel/apply semantics beyond the exact accepted matrices;
- sparse-ID/list renumbering behavior across all affected object classes;
- complete routed `Point` vocabulary and canonicalization;
- exact `Real` lexical forms and editor encoding/BOM policy;
- authoritative copper-pour fill/refill representation;
- complete native library identity/canonicalization rules beyond the tested internal mutations;
- host acknowledgement of plug-in failure/corrupt output;
- real DSN/SES conventions;
- complete multi-sheet hierarchy preservation rules.

Open questions must remain explicit rather than being “closed” by synthetic inverse tests.
