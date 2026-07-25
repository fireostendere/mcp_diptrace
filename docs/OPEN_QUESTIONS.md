# Open Questions — DipTrace XML Format

This document tracks known, high-impact compatibility questions that the public
specifications and committed evidence do not settle. It is not exhaustive. Each question
states the production dependency, a stable code-symbol reference, and an experiment that
requires a real DipTrace installation or other human-controlled evidence.

Do not turn these questions into conventions by round-tripping a writer through this
project's reader. Where evidence is absent, the implementation must disclose, preserve, or
refuse rather than guess.

---

## Q1: Is `Component/@Angle` in radians or degrees?

**Question:** Does DipTrace interpret an ordinary PCB or schematic
`Component/@Angle` value as radians or degrees?

**Why the code depends on it:** The reader
`src/diptrace_mcp/adapters.py::_component_records` applies `math.degrees()`, while the
primary writer `src/diptrace_mcp/semantic_compiler.py::_set_angle_attribute` applies
`math.radians()`. Those functions are exact inverses, so a writer-reader round trip cannot
validate the convention.

**What is documented:** The public specification says only “Component rotation angle.”
It explicitly says radians for text and pictures and degrees for table orientation, but
states no unit for `Component/@Angle`.

**Experiment:** In DipTrace, place one component, set its rotation to exactly 90 degrees,
and export XML without passing the file through MCP. Read the literal value. Approximately
`1.5708` means radians; `90` means degrees.

The repository provides a stricter two-component control/probe
[operator capture recipe](evidence_capture/q1-component-angle.recipe.json). It records the literal
values and UI observations without treating either convention as the expected answer.

**Who can perform:** Human with a licensed DipTrace installation.

---

## Q2: Which objects can an `ImpMode=All` apply delete because the exchange export omitted them?

**Question:** Is an `ExpMode=All` exchange complete enough that returning it under
`ImpMode=All` cannot delete design objects or embedded records that DipTrace omitted from
`plugin_exchange.xml`?

**Why the code depends on it:** The shipped PCB and schematic profiles use
`ImpMode=All`, and `src/diptrace_mcp/sessions.py::SessionStore.finalize` copies the complete
working exchange file back when `src/diptrace_mcp/service.py::DipTraceService.finish_live_session`
requests apply. There is no per-object survival check before that replacement.

**What is documented:** The public plug-in specification defines `ImpMode=All` as importing
all regardless of object-specific settings. The repository's
[exchange reference](../reference/diptrace-xml/REFERENCE.md#exchange-lifecycle) records list
replacement behavior, and a committed
[compatibility observation](XML_COMPATIBILITY.md#preservation-rules) records one live
round trip in which DipTrace removed unreferenced embedded pattern records. The public
plug-in specification does not enumerate everything that an `ExpMode=All` export may omit.
The current profiles are
[`pcb.settings.xml`](../plugin/settings/pcb.settings.xml) and
[`schematic.settings.xml`](../plugin/settings/schematic.settings.xml).

**Experiment:** On a disposable copy, export a board rich in object types: components,
embedded patterns and pad styles, nets, traces, vias, pours, shapes, tables, dimensions,
differential pairs, groups, and board outline. Record counts, IDs, and relevant subtree
hashes by type. Apply one unrelated scalar edit under `ImpMode=All`, save, re-export, and
compare every type. Repeat with a byte-unchanged apply as a canonicalization control. Any
loss must become a refusal or an explicit deletion disclosure.

**Who can perform:** Human with DipTrace 5.3 and a disposable representative design.

---

## Q3: Does Cancel prevent an `ImpMode=All` exchange from being re-imported?

**Question:** When the bridge returns Cancel, does DipTrace leave the design untouched, or
does it still read some or all of the exchange file?

**Why the code depends on it:** `src/diptrace_mcp/bridge.py::BridgeController.finish` and
`src/diptrace_mcp/sessions.py::SessionStore.finalize` distinguish apply from cancel, but
the repository has no acknowledgement from DipTrace proving what the host application did
after the process exited.

**Experiment:** On a disposable board, make the test plug-in write a recognizable harmless
change to the exchange XML, then press Cancel. Save and independently re-export the board.
Check the specific field and object counts, not only whole-file SHA-256, because DipTrace
may canonicalize an otherwise unchanged file.

**Who can perform:** Human with a licensed DipTrace installation.

---

## Q4: Does DipTrace address top-level list entries by `Id` or by position?

**Question:** Are sparse IDs and removal from the middle of top-level arrays preserved, or
does DipTrace renumber entries by list position?

**Why the code depends on it:** Exact synchronization can remove components, nets, traces,
and ratlines in `src/diptrace_mcp/semantic_compiler.py::_apply_sync_schematic_to_pcb`, and
direct routing deletion is implemented by
`src/diptrace_mcp/routing_compiler.py::_delete_traces`. Cross-references are safe only if
the host preserves the documented IDs or consistently rewrites every dependent reference.

**Experiment:** Export a design with three mutually referenced objects whose IDs are
`0`, `1`, and `2`. In a disposable copy, remove the middle object and import it. Save and
re-export. Compare remaining IDs and every reference. Repeat with deliberately sparse IDs
such as `2`, `9`, and `40`.

**Who can perform:** Human with DipTrace and a disposable cross-referenced design.

---

## Q5: Which routed `Point` attributes does DipTrace 5.3 require and preserve?

**Question:** Which optional `Point` attributes does DipTrace 5.3 actually emit, require on
import, and preserve for straight segments, arcs, jumpers, vias, necks, meanders, and
differential-pair points?

**Why the code depends on it:** `src/diptrace_mcp/routing_compiler.py::_write_points`
deletes every existing child and writes a fixed set, including `Jumper="0"` and `Arc="N"`;
`src/diptrace_mcp/routing_compiler.py::_replace_trace` relies on that rewrite. Any
condition-dependent attribute outside that set is lost.

**What is documented:** PCB specification section 4.20.1.6.1.2.1 names 16 trace-point
attributes: `Id`, `X`, `Y`, `Lay`, `Width`, `Jumper`, `Arc`, `ViaStyle`, `PhaseFwd`,
`PhaseBack`, `PairPoint`, `PairSubPoint`, `PairNecked`, `Meander`, `MeanderAngle`, and
`Selected`. What remains unknown is the real 5.3 combination and required semantics for
each geometry, not the existence of the documented names.

**Experiment:** Export one minimal example each of a straight trace, arc, top and bottom
jumper, via transition, necked segment, meander, and differential pair. Preserve the raw
files. Compare the per-`Point` attribute sets, then remove one optional-looking attribute
at a time in disposable imports to distinguish required, derived, and ignored fields.

**Who can perform:** Human with DipTrace 5.3 who can create each routing geometry.

---

## Q6: Under object setting `All`, does `Selected="Y"` become persistent imported selection state?

**Question:** For a newly added PCB or schematic object imported with the object selector
set to `All`, does `Selected="Y"` control or persist the post-import UI selection state?

**Why the code depends on it:** Every creation path that emits this attribute hard-codes
`Selected="N"`; no creation writer emits `Selected="Y"`. Representative paths are
`src/diptrace_mcp/semantic_compiler.py::_apply_add_testpoint`,
`src/diptrace_mcp/semantic_compiler.py::_apply_place_part`,
`src/diptrace_mcp/routing_compiler.py::_write_points`, and
`src/diptrace_mcp/scaffolding.py::build_pcb_document`. If the attribute also represents a
persistent user-visible state, those writers intentionally clear it.

**What is documented:** The
[public plug-in specification text](../reference/diptrace-xml/extracted_text/DipTrace_Plugins.pages.json)
says that a PCB/Schematic object selector set to `Selected` considers incoming
`Selected="Y"`. That filtering behavior is settled. The shipped profiles use selector
`All`, and the specification does not state whether selection/highlighting persists after
import. For Component/Pattern Editor import, the specification says `Selected` is
equivalent to `All`; that is a separate documented rule.

**Experiment:** Under a temporary PCB or schematic profile whose object selector is `All`,
import otherwise identical new objects with `Selected="Y"` and `Selected="N"`. Inspect the
UI selection immediately, then save and re-export both objects. A separate selector
`Selected` control can confirm the documented filter without treating it as the unknown.

**Who can perform:** Human with a licensed DipTrace installation.

---

## Q7: Which `Real` spellings does DipTrace emit and accept?

**Question:** What precision and lexical forms does DipTrace emit for `Real` values, and
does its importer accept equivalent scientific notation such as `9.6e-09`?

**Why the code depends on it:** Writers use bounded general formatting in
`src/diptrace_mcp/semantic_compiler.py::_set_angle_attribute`,
`src/diptrace_mcp/semantic_compiler.py::_apply_net_class_rules`, and
`src/diptrace_mcp/routing_compiler.py::_write_points`. The resulting text can differ from
DipTrace's preferred spelling even when the numeric value is equal.

**Experiment:** First export values spanning large, small, and high-precision magnitudes
and record their literal spellings. Then hand-edit one valid `Real` in a disposable
exchange file from decimal notation to the equivalent `9.6e-09`, import it, and re-export.
Record whether DipTrace rejects, accepts and canonicalizes, or preserves the scientific
notation.

**Who can perform:** Human with a licensed DipTrace installation.

---

## Q8: Which encoding, BOM, and line endings does DipTrace export?

**Question:** What source encoding, BOM policy, XML declaration spelling, and line endings
does each DipTrace editor emit?

**Why the code depends on it:** The parser
`src/diptrace_mcp/xml_document.py::DipTraceDocument.from_bytes` accepts several encodings,
while full-tree output from
`src/diptrace_mcp/xml_document.py::DipTraceDocument.serialize` is UTF-8. Exact untouched
byte preservation and independent DipTrace canonicalization must not be conflated.

**Experiment:** Export minimal PCB, schematic, Component Library, and Pattern Library
documents directly from DipTrace. Inspect raw bytes for BOM, declaration encoding, and
LF/CRLF. Include non-ASCII text such as Cyrillic plus `µ`, `Ω`, `°`, and `±`.

**Who can perform:** Human with each relevant DipTrace 5.3 editor.

---

## Q9: Must an MCP edit preserve the source encoding and BOM?

**Question:** Which loaded encodings can be returned after an edit without DipTrace
rejecting or corrupting the exchange, and must the original BOM/declaration be preserved?

**Why the code depends on it:** Raw replacements in
`src/diptrace_mcp/xml_document.py::DipTraceDocument.apply_edits` retain surrounding bytes,
but `src/diptrace_mcp/xml_document.py::_serialize_new_element` emits UTF-8 and the document
model does not retain an explicit source-encoding field. Structural edits to UTF-16/32
input can therefore produce an invalid mixed-encoding result.

**Experiment:** For clean UTF-8, UTF-8-with-BOM, UTF-16LE/BE, and any encoding DipTrace
itself exports, apply one raw attribute edit and one structural insertion. Import each
result into a disposable design, then save and re-export. Verify non-ASCII text and inspect
the final declaration/BOM.

**Who can perform:** Human with DipTrace and provenance-preserving encoded fixtures.

---

## Q10: How does DipTrace 5.3 encode authoritative copper-pour fill data?

**Question:** Does DipTrace 5.3 store filled copper regions as plain XML text,
Deflate-compressed Base64, another encoding, or only derived data outside the public
exchange format?

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::_board_copper_pour_records`
models only the boundary polygon and explicitly warns that it is not the final refilled
region. Clearance, routing, and DFM logic cannot treat that boundary as authoritative
copper.

**Experiment:** In DipTrace 5.3, create a pour with thermal spokes, a cutout, an island,
and an obstacle, refill it, and export before and after refill. Inspect every
`CopperPour` child and payload without assuming a decoder. If an encoded blob changes,
identify its envelope and compression only from reproducible decode evidence.

**Who can perform:** Human with DipTrace 5.3 and a controlled pour fixture.

---

## Q11: What are the standalone Component and Pattern Editor XML mutation semantics?

**Question:** What complete XML structures, identity rules, and replacement behavior do
the standalone Component and Pattern Editors require for safe library mutation?

**Why the code depends on it:** `src/diptrace_mcp/library_adapters.py::get_library_model`
and `src/diptrace_mcp/library_adapters.py::_components` read observed library structures,
but there is no public Component/Pattern XML format specification and no native library
writer. Reader success does not prove mutation semantics.

**What is documented:** The public plug-in specification documents editor export/import
modes such as `Library All`, `Library Add`, `Library Insert`, `Component All`, `Part All`,
and `Edit`. It does not document the complete library XML schema or identity/canonicalization
rules.

**Experiment:** Export minimal Component and Pattern libraries, then vary one setting at a
time: multi-part structure, pin and pad identity, pattern attachment, mask, paste,
courtyard, additional fields, and embedded graphics. For each, retain export → import →
save → re-export pairs and compare identity references and object counts.

**Who can perform:** Human with licensed Component and Pattern Editors and permission to
share sanitized fixtures.

---

## Q12: How does DipTrace acknowledge plug-in failure or output corruption?

**Question:** What does DipTrace do when the plug-in exits non-zero, exits zero without a
change, produces malformed/truncated XML, or applies successfully?

**Why the code depends on it:** `src/diptrace_mcp/bridge.py::BridgeController.finish` can
report local finalization, and `src/diptrace_mcp/sessions.py::SessionStore.finalize` can
reject local copy/parse failures, but neither receives a host acknowledgement that
DipTrace accepted the import. Local success is not application success.

**Experiment:** On disposable files, run four controlled plug-ins: exit `1`; exit `0`
unchanged; exit `0` with a zero-byte file; and exit `0` with one valid edit. Record dialogs,
whether the design changes, and the process/host exit behavior. Re-export after each case.

**Who can perform:** Human with DipTrace and a controlled test plug-in.

---

## Q13: Which DipTrace 5.3 XML elements and attributes are absent from the public specifications?

**Question:** What XML vocabulary or semantics were added after the public 4.3-era PCB and
schematic specifications?

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::build_snapshot` exposes only
known normalized structures, while
`src/diptrace_mcp/adapters.py::_compatibility_for` reports the version boundary. Unknown
raw XML is generally preserved, but it may remain invisible to analysis or be at risk when
an owning parent is regenerated.

**Experiment:** Inspect the `Docs` directory from a DipTrace 5.3 installation for newer
specifications. Export representative 5.3 PCB and schematic designs and compare all element
paths and attributes with `reference/diptrace-xml/spec_inventory.json`. Record unknowns;
do not promote them from a synthetic fixture alone.

**Who can perform:** Human with DipTrace 5.3 and access to its installation directory.

---

## Q14: Can DipTrace 5.3 open and save its native XML project format directly?

**Question:** Can a current `.dip`, `.dch`, `.eli`, or `.lib` XML project be opened and
saved directly without the plug-in exchange lifecycle, and what subset differs from
exchange XML?

**Why the code depends on it:** `src/diptrace_mcp/xml_document.py::DipTraceDocument.from_bytes`
accepts supported XML roots regardless of filename extension, while
`src/diptrace_mcp/service.py::DipTraceService.resolve_target` still treats the live bridge
as the central write channel. If native XML is directly editable, much of the
`ImpMode`/session risk may be avoidable.

**Experiment:** Create one native XML project in DipTrace 5.3, close it, copy it, change one
safe scalar in the copy, and open the copy directly in DipTrace without a plug-in. Save and
re-export it. Compare roots, object counts, and canonicalization with a plug-in exchange
from the same design.

**Who can perform:** Human with DipTrace 5.3 using disposable project copies.

---

## Q15: What does DipTrace canonicalize on open, save, and re-export?

**Question:** Which byte and semantic changes does DipTrace itself make to an untouched
export or native XML project?

**Why the code depends on it:** `src/diptrace_mcp/xml_document.py::RawTreeSnapshot.compile`
protects untouched MCP regions, while
`src/diptrace_mcp/service.py::_semantic_roundtrip_check` compares selected normalized
categories. Neither defines DipTrace's independent ordering, default omission, derived
records, or numeric canonicalization.

**Experiment:** Export a representative design, open and save it without editing, then
re-export. Compare byte-level and semantic changes separately: ordering, IDs, omitted
defaults, number spelling, derived lists, embedded records, and whitespace.

**Who can perform:** Human with DipTrace and a representative disposable design.

---

## Q16: How does the same design scale across root `Units=mm`, `inch`, and `mil`?

**Question:** Does DipTrace rescale every dimension consistently across the three documented
root units, and are any fields always stored in a fixed unit?

**Why the code depends on it:** Unit normalization is centralized in
`src/diptrace_mcp/geometry.py::to_mm` and
`src/diptrace_mcp/geometry.py::from_mm`, and readers such as
`src/diptrace_mcp/adapters.py::_float_attr_mm` assume dimensional fields follow root
`Units` unless explicitly documented otherwise.

**Experiment:** Export the same unchanged design three times with root units set to `mm`,
`inch`, and `mil`. Normalize documented dimensions and compare them field by field. Record
any attribute that does not scale with root units rather than adding an inferred exception.

**Who can perform:** Human with DipTrace and control of export units.

---

## Q17: What DSN/SES conventions does DipTrace use on a real routed design?

**Question:** Which Specctra quoting, layer, padstack, via, coordinate, and session constructs
does DipTrace emit and accept in a real DSN/SES round trip?

**Why the code depends on it:** `src/diptrace_mcp/specctra.py::export_dsn`,
`src/diptrace_mcp/specctra.py::parse_ses`, and
`src/diptrace_mcp/specctra.py::session_to_operations` are currently validated without a
committed real DipTrace-generated DSN/SES pair. Synthetic inverse tests cannot establish
host conventions.

**Experiment:** Export a multilayer board with at least one routed trace and via to DSN,
route a small change in a compatible external router, import the SES into DipTrace, and
re-export. Preserve the original DSN, SES, source board XML, and final board XML unchanged.

**Who can perform:** Human with DipTrace and a compatible Specctra-format router.

---

## Q18: What hierarchy records are required for a real multi-sheet schematic?

**Question:** Which IDs, paths, connectors, and net records must agree for DipTrace to
preserve a hierarchical multi-sheet schematic?

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::_schematic_sheets` normalizes
known sheet data, while `src/diptrace_mcp/semantic_compiler.py::_apply_add_sheet` and
`src/diptrace_mcp/semantic_compiler.py::_apply_add_wire` author only the currently
implemented structures. A flat or synthetic fixture cannot prove hierarchy semantics.

**Experiment:** Build a minimal two-level hierarchy with repeated block instances, local and
global nets, hierarchy connectors, and cross-sheet references. Export, import without
changes, save, and re-export. Compare all hierarchy paths, block IDs, connector endpoints,
and logical net memberships.

**Who can perform:** Human with DipTrace and a controlled hierarchical schematic.
