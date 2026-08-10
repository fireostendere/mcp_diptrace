# Open Questions — DipTrace XML Format

This document tracks compatibility questions that remain open for the current public/package-owned evidence boundary. A question may already have private/manual or older-version observations; those observations are stated explicitly and do not become universal/current-version proof automatically.

Do not close a host-format question from a synthetic fixture or from an MCP writer-reader inverse round trip. Where evidence is incomplete, preserve, disclose, or refuse rather than guess.

---

## Q1: Is `Component/@Angle` in radians or degrees?

**Question:** The project-manual Q1 gate is PASS on DipTrace PCB Layout 5.3.0.3: 90/180/270 degrees serialized as approximately 1.5708/3.1416/4.7124 radians, and the bottom-side change-side case was observed. What remains open is a redistributable/package-owned capture suitable for promoting that convention into reusable public trust evidence.

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::_component_records` converts stored radians to degrees and `src/diptrace_mcp/semantic_compiler.py::_set_angle_attribute` writes radians. The implementation convention is now supported by manual host evidence, but release/public evidence must remain scoped.

**What is documented:** `docs/MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md` and `docs/XML_COMPATIBILITY.md` record the later manual PASS. Immutable `v0.2.1` release evidence correctly remains `NOT_RUN` because it predates that campaign.

**Experiment:** Repeat the controlled 90/180/270 degree and change-side probe with redistributable artifacts using the committed [Q1 capture recipe](evidence_capture/q1-component-angle.recipe.json), preserving distinct source/open-save/re-export roles and literal angle values.

**Who can perform:** Human with licensed DipTrace PCB Layout 5.3.x and permission to provide sanitized evidence.

---

## Q2: Which objects can an `ImpMode=All` apply delete because the exchange export omitted them?

**Question:** Is an `ExpMode=All` exchange complete enough that returning it under `ImpMode=All` cannot delete design objects or embedded records omitted from the exchange?

**Why the code depends on it:** `src/diptrace_mcp/sessions.py::SessionStore.finalize` returns the complete working exchange file on apply, so object classes omitted by DipTrace export can matter even when MCP changes only one scalar.

**What is documented:** A prior live round trip observed DipTrace canonicalization/removal of unreferenced embedded records, but the project has not enumerated every object class that `ExpMode=All` may omit.

**Experiment:** On a disposable object-rich board, compare source/open-save/re-export counts, IDs and relevant subtree hashes before and after one unrelated scalar edit plus an unchanged control.

**Who can perform:** Human with DipTrace 5.3 and a disposable representative design.

---

## Q3: Does Cancel prevent an `ImpMode=All` exchange from being re-imported?

**Question:** The 2026-07-31 DipTrace 5.2.0.4 live campaign proved PCB and Schematic Cancel preserved the tested host state. Does the same behavior hold for the current DipTrace 5.3/profile combinations and broader object sets used by future compatibility claims?

**Why the code depends on it:** `src/diptrace_mcp/bridge.py::BridgeController.finish` distinguishes apply/cancel locally, but the project should not generalize one exact-version host observation to every later editor/profile without evidence.

**What is documented:** `docs/LIVE_ACCEPTANCE_2026-07-31.md` records PCB/Schematic Cancel PASS for DipTrace 5.2.0.4. Current docs treat that as exact-scope evidence, not a universal guarantee.

**Experiment:** Repeat Cancel on disposable current-version PCB and Schematic designs after a recognizable harmless working-copy edit, then save/re-export and verify the edit never reached host state.

**Who can perform:** Human with the current DipTrace 5.3 configuration used for the target compatibility claim.

---

## Q4: Does DipTrace address top-level list entries by `Id` or by position?

**Question:** Are sparse IDs and middle-list removals preserved, or does DipTrace renumber entries by list position?

**Why the code depends on it:** `src/diptrace_mcp/semantic_compiler.py::_apply_sync_schematic_to_pcb` can remove cross-referenced objects, so host renumbering behavior matters to exact synchronization safety.

**Experiment:** In a disposable design remove a middle object, then repeat with deliberately sparse IDs; save/re-export and compare every remaining ID/reference.

**Who can perform:** Human with DipTrace and a disposable cross-referenced design.

---

## Q5: Which routed `Point` attributes does DipTrace 5.3 require and preserve?

**Question:** Which optional `Point` attributes are emitted, required, derived or preserved for straight segments, arcs, jumpers, vias, necks, meanders and differential-pair points?

**Why the code depends on it:** `src/diptrace_mcp/routing_compiler.py::_write_points` owns a bounded known attribute set, so an unmodeled condition-dependent attribute could otherwise be lost when a trace is replaced.

**Experiment:** Export minimal examples of each geometry, compare per-Point attributes, then remove one optional-looking attribute at a time in disposable imports and re-export.

**Who can perform:** Human with DipTrace 5.3 who can create each routing geometry.

---

## Q6: Under object setting `All`, does `Selected="Y"` become persistent imported selection state?

**Question:** For a new PCB or schematic object imported under selector `All`, does `Selected="Y"` control or persist post-import UI selection state?

**Why the code depends on it:** `src/diptrace_mcp/semantic_compiler.py::_apply_add_testpoint` and other creation paths intentionally emit unselected objects, so persistent semantics should not be guessed.

**Experiment:** Import otherwise identical objects with `Selected="Y"` and `Selected="N"`, inspect immediate UI state, then save/re-export both.

**Who can perform:** Human with a licensed DipTrace installation.

---

## Q7: Which `Real` spellings does DipTrace emit and accept?

**Question:** What precision/lexical forms does DipTrace emit for real numbers, and does it accept equivalent scientific notation?

**Why the code depends on it:** `src/diptrace_mcp/semantic_compiler.py::_set_angle_attribute` and other writers use bounded numeric formatting that may differ lexically from DipTrace canonical output.

**Experiment:** Export a range of magnitudes/precisions, then change one disposable valid decimal to equivalent scientific notation and observe import/save/re-export behavior.

**Who can perform:** Human with a licensed DipTrace installation.

---

## Q8: Which encoding, BOM, and line endings does DipTrace export?

**Question:** What encoding, BOM policy, XML declaration spelling and line endings does each DipTrace editor emit?

**Why the code depends on it:** `src/diptrace_mcp/xml_document.py::DipTraceDocument.from_bytes` preserves several supported source encodings/BOMs, but parser support does not establish host export policy.

**Experiment:** Export minimal PCB/Schematic/Component/Pattern documents with non-ASCII text and inspect raw bytes for encoding, BOM, declaration and LF/CRLF.

**Who can perform:** Human with each relevant DipTrace 5.3 editor.

---

## Q9: Must an MCP edit preserve the source encoding and BOM?

**Question:** Which loaded encodings can be returned after an edit without host rejection/corruption, and must the original BOM/declaration be preserved?

**Why the code depends on it:** `src/diptrace_mcp/xml_document.py::DipTraceDocument.apply_edits` preserves supported source codecs/BOMs as a safety policy, but that does not prove DipTrace accepts every parser-supported encoding.

**Experiment:** Apply one raw edit and one structural insertion to controlled UTF-8/BOM/UTF-16 cases that DipTrace can open, then save/re-export and verify text plus declaration/BOM.

**Who can perform:** Human with DipTrace and provenance-preserving encoded fixtures.

---

## Q10: How does DipTrace 5.3 encode authoritative copper-pour fill data?

**Question:** Where and how does DipTrace represent authoritative refilled copper, thermals, cutouts and islands in XML/exchange data?

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::_board_copper_pour_records` models the observed boundary but does not promote it to authoritative final refill geometry.

**Experiment:** Create a controlled pour with thermals/cutout/island/obstacle, export before and after refill, and compare every CopperPour child/payload without assuming a decoder.

**Who can perform:** Human with DipTrace 5.3 and a controlled pour fixture.

---

## Q11: What are the standalone Component and Pattern Editor XML mutation semantics?

**Question:** The internal raw-preserving mutation core now has controlled real Component Editor and Pattern Editor save/reopen/re-export evidence. What remains open is the complete identity/canonicalization space, including `UID32`, partial-vs-full export behavior, and the exact subset safe enough for any future public native-library write contract.

**Why the code depends on it:** `src/diptrace_mcp/library_mutation.py::LibraryMutationEngine` must preserve unowned structures and stable relationships, while public API design must not generalize beyond the operations/editor cases actually verified.

**What is documented:** Current `main` no longer claims that native library mutation is unimplemented. The core is internal/evidence-scoped and public native-library mutation remains unregistered.

**Experiment:** On disposable minimal Component and Pattern libraries, compare repeated untouched exports, full-vs-current-object export, controlled one-setting mutations, UID32/reference stability, save/reopen/re-export and idempotence.

**Who can perform:** Human with licensed Component/Pattern Editors and permission to share sanitized evidence.

---

## Q12: How does DipTrace acknowledge plug-in failure or output corruption?

**Question:** What does DipTrace do when a plug-in exits non-zero, exits zero unchanged, returns malformed/truncated XML, or returns one valid edit?

**Why the code depends on it:** `src/diptrace_mcp/bridge.py::BridgeController.finish` reports local finalization but receives no typed host acknowledgement proving import success.

**Experiment:** On disposable files exercise the four controlled outcomes, record host dialogs/state/exit behavior, and independently re-export after each.

**Who can perform:** Human with DipTrace and a controlled test plug-in.

---

## Q13: Which DipTrace 5.3 XML elements and attributes are absent from current observations?

**Question:** What vocabulary/semantics does representative DipTrace 5.3 data emit that is absent from the project-owned observation inventory?

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::build_snapshot` normalizes known structures while unknown raw XML may remain invisible to analysis or at risk when an owning parent is regenerated.

**Experiment:** Compare representative controlled 5.3 exports against `reference/diptrace-xml/spec_inventory.json`, recording unknown element paths/attributes without promoting synthetic observations.

**Who can perform:** Human with DipTrace 5.3 and suitable representative designs.

---

## Q14: Can DipTrace 5.3 open and save its native XML project format directly?

**Question:** Can current XML `.dip`, `.dch`, `.eli` or `.lib` files be opened/saved directly without the plug-in exchange lifecycle, and how does that path differ from exchange XML?

**Why the code depends on it:** `src/diptrace_mcp/xml_document.py::DipTraceDocument.from_bytes` accepts supported XML roots regardless of extension, while live writes still use the bridge/session trust model.

**Experiment:** On a disposable native XML copy make one safe scalar change, open/save directly in DipTrace, re-export, and compare with an exchange export from the same design.

**Who can perform:** Human with DipTrace 5.3 using disposable project copies.

---

## Q15: What does DipTrace canonicalize on open, save, and re-export?

**Question:** Which byte and semantic changes does DipTrace itself make to an otherwise untouched export/native XML project?

**Why the code depends on it:** `src/diptrace_mcp/xml_document.py::RawTreeSnapshot.compile` protects MCP-owned byte regions while host canonicalization may independently change ordering/defaults/numbers/derived records.

**Experiment:** Export, open/save without editing, re-export, and compare byte-level plus semantic changes separately.

**Who can perform:** Human with DipTrace and a representative disposable design.

---

## Q16: How does the same design scale across root `Units=mm`, `inch`, and `mil`?

**Question:** Does DipTrace rescale every dimensional field consistently across root units, or are some fields stored in a fixed unit?

**Why the code depends on it:** `src/diptrace_mcp/geometry.py::to_mm` and `src/diptrace_mcp/geometry.py::from_mm` assume dimensional fields follow root units unless explicitly modeled otherwise.

**Experiment:** Export the same unchanged design in mm/inch/mil and compare normalized dimensions field by field, recording exceptions rather than inferring them.

**Who can perform:** Human with DipTrace and control of export units.

---

## Q17: What DSN/SES conventions does DipTrace use on a real routed design?

**Question:** Which Specctra quoting, layer, padstack, via, coordinate and session constructs does DipTrace emit/accept in a real DSN/SES round trip?

**Why the code depends on it:** `src/diptrace_mcp/specctra.py::export_dsn` and `src/diptrace_mcp/specctra.py::parse_ses` have bounded regression coverage but no committed real paired DipTrace DSN/SES corpus proving all host conventions.

**Experiment:** Export a controlled multilayer DSN, route a small change in a compatible router, import SES, then preserve/compare original DSN/SES/source/final board XML.

**Who can perform:** Human with DipTrace and a compatible Specctra-format router.

---

## Q18: What hierarchy records are required for a real multi-sheet schematic?

**Question:** Which IDs, paths, connectors and net records must agree for DipTrace to preserve a hierarchical multi-sheet schematic?

**Why the code depends on it:** `src/diptrace_mcp/adapters.py::_schematic_sheets` reads known hierarchy data while `src/diptrace_mcp/semantic_compiler.py::_apply_add_sheet` and `_apply_add_wire` author only the currently implemented subset.

**Experiment:** Build a minimal two-level hierarchy with repeated instances/local/global nets/connectors, then export/open-save/re-export and compare paths, IDs, endpoints and logical net membership.

**Who can perform:** Human with DipTrace and a controlled hierarchical schematic.
