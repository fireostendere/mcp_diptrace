# Local Reference Materials Audit

## Decision

The local `etc/` directory is useful as a **lead and operator-input collection**, not as a new
source of authoritative DipTrace facts. None of its bytes are part of this repository at the
audited commit, and this report does not propose adding them.

The safe disposition is:

- retain the four generated specification bundles and the plug-in context pack outside Git until
  their source repository, exact revision, author, license, and redistribution permission can be
  verified;
- treat all statements attributed to “DipTrace serializer, repository revision 7276” as
  unverified;
- treat the legacy `.eli` and `.lib` files as operator-owned binary inputs, not XML fixtures and
  not redistributable test data;
- use a small, stratified subset of those libraries to produce candidate XML through the
  [operator-assisted evidence workflow](EVIDENCE_CAPTURE.md);
- reuse only facts independently supported by the already committed public specification
  extracts;
- turn contradictions into open questions or capture recipes rather than reader/writer
  conventions.

There is no new fact in `etc/` that should directly change production code or
`spec_inventory.json` on the strength of these files alone.

## Scope and method

This audit was made against commit `8343e1f284bb31d348d1d62a0e095e210048bbf7`. The inspected
`etc/` directory was a local, untracked directory beside that checkout. It was not copied into the
audit checkout and must not be described as shipped, bundled, or committed.

The audit:

- read every one of the 22 small Markdown, DOCX, and PDF documents;
- read only the eight-byte format prefix of each legacy library;
- fully hashed a deterministic, size-stratified sample of 12 `.eli` and 12 `.lib` files;
- did not fully read or hash all 966 legacy libraries;
- compared claims with the committed public source extracts, inventory, documentation, code, and
  tests;
- copied no source bytes into this document or the generated inventory.

The reproducible read-only inventory command is:

```bash
python scripts/audit_reference_materials.py \
  --root /path/to/local/etc
```

It prints JSON to standard output. By default it hashes all small documents, counts the complete
library population, identifies every library by its eight-byte prefix, and hashes only the
stratified sample. It never emits file contents.

## Inventory

| Kind | Files | Bytes | Minimum | Maximum | Disposition |
| --- | ---: | ---: | ---: | ---: | --- |
| `.eli` | 463 | 1,734,696,577 | 3,464 | 158,674,428 | local binary candidate inputs |
| `.lib` | 503 | 352,771,704 | 2,907 | 17,559,294 | local binary candidate inputs |
| `.md` | 13 | 268,183 | 4,678 | 72,546 | unverified explanatory/generated text |
| `.docx` | 4 | 125,074 | 24,914 | 44,347 | rendering of generated specifications |
| `.pdf` | 5 | 2,594,025 | 245,604 | 1,003,154 | four renderings plus one corpus proposal |
| **Total** | **988** | **2,090,455,563** |  |  | local only |

The arithmetic reconciles in both dimensions: 22 documents plus 966 legacy libraries equals 988
files; 2,987,282 documentation bytes plus 2,087,468,281 library bytes equals 2,090,455,563 bytes.

All 463 `.eli` files begin with the legacy `DTELIB` binary signature. All 503 `.lib` files begin
with the legacy `DTCLIB` binary signature. None is XML by content, irrespective of its filename
extension. This is an observation about this local collection only.

The 12 Markdown/DOCX/PDF files under `DipTrace_XML_Specification/` form four three-format bundles.
Within each bundle the title, structure, examples, and the revision-7276 assertion match. Normalized
five-word-shingle similarity is 0.734–0.786 between Markdown and DOCX and 0.671–0.740 between DOCX
and PDF. These are renderings of substantially the same source, not three independent witnesses.

The fifth PDF, `Библиотека примеров DipTrace.pdf`, is a corpus plan. It proposes controlled
single-change pairs, approximately 195 artifacts, and screenshots as supporting evidence. It is
useful experiment-design input, but it has no author, source, license, or evidence manifest. Its
statement that XML plus a manifest is authoritative conflicts with the repository trust model:
operator-controlled manifests cannot mint high trust.

## Provenance and legal assessment

### Generated specifications

Every generated specification says it was produced from “the DipTrace serializer, repository
revision 7276.” The material does not include:

- a repository URL or repository identity;
- the serializer source or a patch;
- a commit/tree hash corresponding to revision 7276;
- a generator and reproducible invocation;
- a signed source manifest;
- an author;
- a license or redistribution grant.

The PDF metadata names `Typst 0.15.1` as creator and dates all four PDFs to 2026-07-24. The DOCX
core properties have an empty creator and dates within seconds of the PDFs. This establishes
rendering time, not source provenance. Revision 7276 may be real, but it cannot be checked from
the supplied material, so its claims cannot be promoted as facts.

The files also do not contain the official Component Editor and Pattern Editor PDFs named by the
plug-in pack. They contain newly generated documents with different titles and the unsupported
serializer-source claim. They are not substitutes for the named official PDFs.

### Plug-in context pack

The nine Markdown files mix three evidence classes without per-claim citations:

1. text that is independently present in the public plug-in specification;
2. interpretation of shipped example plug-ins that are not included here;
3. alleged implementation/source behavior tied only to revision 7276.

The pack-level verification note cannot authenticate classes 2 or 3. The safe reuse procedure is
claim-by-claim: locate the same fact in the committed public extract, cite its page, and ignore the
pack wording. If the public source does not say it, keep the item as an open question or operator
probe.

### Legacy libraries

There is no origin manifest, DipTrace version manifest, creation history, owner statement, or
redistribution license for the 966 binary libraries. Their names and content plausibly include
Novarm and third-party component/vendor catalog data. A hash proves byte identity, not authorship
or permission.

Do not commit the binaries, their decoded contents, or large excerpts. A human may use them
locally in licensed DipTrace, export a minimal sanitized test library, and pass that XML through
the candidate evidence workflow. The candidate still needs independent review and an explicit
redistribution decision.

## Contradictions and unsupported claims

The following are not minor wording issues. They would change writer safety or trust if accepted.

| Claim in local material | Conflict or missing evidence | Required disposition |
| --- | --- | --- |
| All four generated specs are current behavior from source revision 7276. | No source repository, revision mapping, generator, author, or license is supplied. | Do not cite as implementation authority. |
| Ordinary component/part rotation angles are radians. | [`OPEN_QUESTIONS.md` Q1](OPEN_QUESTIONS.md#q1-is-componentangle-in-radians-or-degrees) correctly records that the public PCB/Schematic specs do not state the unit. | Keep Q1 open; use the existing two-component capture recipe. |
| XML is “Always UTF-8.” | [`OPEN_QUESTIONS.md` Q8/Q9](OPEN_QUESTIONS.md#q8-which-encoding-bom-and-line-endings-does-diptrace-export) separates what DipTrace emits from what MCP must preserve. The parser intentionally accepts additional encodings. | Do not narrow the parser or writer from this claim. |
| Every `Real` follows root units. | [`OPEN_QUESTIONS.md` Q16](OPEN_QUESTIONS.md#q16-how-does-the-same-design-scale-across-root-unitsmm-inch-and-mil) exists because fixed-unit exceptions are not ruled out. | Keep field-by-field unit experiments. |
| Root `Version` is the DipTrace product version. | The evidence workflow deliberately records the application build and XML `Version` separately; current compatibility evidence shows that they are related but not interchangeable. | Preserve the literal value and do not use it as an application-build assertion. |
| Coordinate Y values are stored negated or sign-flipped. | The plug-in pack itself says not to assume a Y-axis flip, while the generated specs repeatedly describe serializer-side sign changes. No raw source-to-file derivation is supplied. | Preserve file values as read; use controlled UI-coordinate probes before adding any conversion. |
| Full-file lists must be dense and are bound positionally. | [`OPEN_QUESTIONS.md` Q4](OPEN_QUESTIONS.md#q4-does-diptrace-address-top-level-list-entries-by-id-or-by-position) deliberately treats sparse-ID behavior as unknown. | Do not add positional renumbering. |
| Cancel never imports, exit codes are ignored, timestamp alone decides success, and there is no size limit. | [`OPEN_QUESTIONS.md` Q3](OPEN_QUESTIONS.md#q3-does-cancel-prevent-an-impmodeall-exchange-from-being-re-imported) and [Q12](OPEN_QUESTIONS.md#q12-how-does-diptrace-acknowledge-plug-in-failure-or-output-corruption) require real process experiments. | Keep the handshake fail-closed; do not close either question. |
| `ImpMode=All`, nested ID-less lists, `Edit`, and `Enabled="N"` have the stronger replacement/delete semantics stated in the pack. | The public plug-in document names modes and selectors but does not fully specify these deletion and nested-subtree consequences. The committed reference currently states them more strongly than its cited public inventory proves. | Require a primary citation or controlled evidence; retain safety refusals meanwhile. |
| `UID32` is stable. | The same local collection's generated CompEdit and PattEdit specs say it is regenerated on every save. Neither claim has authoritative provenance. | Add UID lifetime/identity to the Q11 experiment; do not use it as stable identity. |
| Schematic has no `Dim` setting and `Patterns` has no export effect. | The committed public plug-in extract explicitly lists Schematic `Dim` and `Patterns`; the current profile uses both. | Keep the public settings; treat actual runtime effect as a version-specific probe. |
| Hierarchy `BlockId`, sheet fallback, and positional resolution behavior are fully specified. | [`OPEN_QUESTIONS.md` Q18](OPEN_QUESTIONS.md#q18-what-hierarchy-records-are-required-for-a-real-multi-sheet-schematic) correctly records that real multi-sheet requirements are not settled. | Keep Q18 open and collect a controlled hierarchy fixture. |
| An unresolved Component Library internal-connection reference causes a delayed DipTrace access violation. | The public format text can establish documented reference fields, but the crash claim depends only on the unavailable implementation/source provenance. | Validate references defensively, but do not document a host crash as proven behavior. |
| Component/Pattern XML specifications are among the maintained committed references. | [`spec_inventory.json`](../reference/diptrace-xml/spec_inventory.json) records only PCB, Schematic, and plug-in sources. [`XML_COMPATIBILITY.md`](XML_COMPATIBILITY.md) currently overstates this at line 18. | Correct the documentation or add properly sourced, reproducible official extracts. |
| The public inventory records `PadStyle`/`MainStack` and the listed shape enum. | The committed inventory has no `PadStyle` or `MainStack` element entry, although related text exists in the raw public PCB extract. | Fix the extractor/source citation before claiming inventory coverage. Do not backfill from revision-7276 text. |
| A `.eli` or `.lib` extension implies native XML. | Every local library in this collection has a legacy binary signature. | Continue content-based root validation; export through DipTrace before XML analysis. |

## Useful content and exact destinations

This matrix separates what can be reused from what must remain evidence-gated.

| Class | Useful item | Exact target | Action |
| --- | --- | --- | --- |
| Authoritative fact | PCB/Schematic and Component/Pattern Editor export/import modes, object tags, and the documented half of `Selected` behavior | [`DipTrace_Plugins.pages.json`](../reference/diptrace-xml/extracted_text/DipTrace_Plugins.pages.json), `plugin/settings/*.settings.xml`, `tests/test_plugin_settings.py` | Keep the committed public extract as the source. Strengthen the test so every shipped profile tag/value is checked against a small reviewed table derived from pages 4–8. Do not derive that table from `etc/plugin_sdk`. |
| Authoritative fact | Root units and attribute semantics that occur in the public PCB/Schematic specifications | `scripts/extract_spec_inventory.py`, [`spec_inventory.json`](../reference/diptrace-xml/spec_inventory.json), and generator tests | Continue the reproducible extractor path. A generated revision-7276 table must not bypass it. |
| Explanatory content | One intentional GUI change per before/after pair; unchanged control objects; screenshots only as supporting evidence | [`EVIDENCE_CAPTURE.md`](EVIDENCE_CAPTURE.md), recipe-authoring section | Rephrase as project guidance. Do not copy the unknown-origin PDF or call candidates “golden.” |
| Explanatory content | A prioritized probe catalog for mask, paste, courtyard, pad shape/hole, pour refill, hierarchy, and DSN/SES | [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) and the future generated probe pack | Generate recipes from maintained questions. Avoid a second 200-file hand-maintained roadmap. |
| Observed candidate evidence | All 463 `.eli` and 503 `.lib` files are legacy binary in this local collection | `scripts/capture_diptrace_evidence.py` candidate manifest schema | Use optional `input_artifacts` path/hash/size metadata to bind an XML candidate to exact local bytes without copying the binary. Finalize and ingest revalidate the original input; authority remains `operator_supplied_unverified`. |
| Observed candidate evidence | Size-stratified component/pattern libraries can expose real 5.3 element and attribute vocabulary after licensed export | `docs/evidence_capture/` with a concrete Q11 library recipe; later independent ingest/review | Export small sanitized subsets, capture source/open-save/re-export XML, then compare paths/attributes against the committed inventory. Never infer schema from the binary header. |
| Candidate schema lead | 27 element names appear as headings in the generated specs but not as element entries in the committed inventory, including `PadStyle`, `MainStack`, `Pattern`, `Model3D`, `SubFolders`, `Categories`, and `Terminal` | a future read-only vocabulary-diff report over captured XML; `library_adapters.py::_pad_styles`, `_patterns`, and `_components` | Use the names to prioritize probes only. Add a parser field after public documentation or reviewed real-export evidence exists. |
| Unknown/contradiction | Component/part angle, source encoding, root-unit coverage, sparse IDs, cancel/failure behavior, native XML, and hierarchy resolution | Q1, Q3, Q4, Q8, Q9, Q12, Q14, Q16, and Q18 in [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) | Keep open. The local material supplies hypotheses, not answers. |
| Unknown/contradiction | Library `UID32` lifetime, full-save versus partial-export root attributes, list identity, mask/paste defaults, and library mutation semantics | Q11 in [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md); `library_adapters.py::get_library_model` | Extend Q11's experiment checklist. Do not add a library writer. |
| Documentation correction | Maintained evidence and inventory claims are stronger than the committed provenance chain | [`XML_COMPATIBILITY.md`](XML_COMPATIBILITY.md) “Official Format Evidence”; [`REFERENCE.md`](../reference/diptrace-xml/REFERENCE.md) “Exchange lifecycle” and pattern/library sections | Label each claim as public-spec, observed fixture, or unresolved. Point to exact committed sources. |
| Do not commit | Generated MD/DOCX/PDF specs, the nine-file context pack, the corpus-plan PDF, and all legacy binaries | repository-wide | Keep outside Git unless ownership and redistribution are resolved. Even with permission, prefer generated structured data and short cited explanations over a duplicate documentation dump. |

## Real-library sampling result

The deterministic sample spans the smallest and largest library plus ten equal-count size strata
for each extension. Every sampled file has the expected legacy binary signature.

| Kind | Sampled size range | Largest sampled example | What this proves |
| --- | ---: | --- | --- |
| `.eli` | 3,464–158,674,428 bytes | `res_networks.eli` | only byte identity and legacy component-library format |
| `.lib` | 2,907–17,559,294 bytes | `_bga_p0.80.lib` | only byte identity and legacy pattern-library format |

The full sample hashes are emitted by `scripts/audit_reference_materials.py`. They should remain
local unless a reviewed evidence candidate needs to bind a specific binary input. Publishing a
hash list does not grant redistribution permission and does not reveal XML vocabulary.

For useful XML evidence, prefer this operator sequence:

1. Choose a small library from a different size stratum and bind it on the source record with
   `--input-artifact ROLE=PATH`.
2. Open it in the licensed matching editor.
3. Save/export a minimal sanitized XML library under a new name.
4. Capture source/open-save/re-export roles with the evidence collector.
5. Record the DipTrace application build separately from XML `Version`.
6. Record redistribution permission; default to no permission.
7. Run an independent vocabulary and semantic diff.
8. Promote only through a reviewed repository allowlist, once that mechanism exists.

## Proposed separate pull requests

### PR 1: provenance-only audit

Commit this report, the read-only inventory script, and its synthetic tests. Do not include
`etc/`, generated extracts, library bytes, or claims from revision 7276.

### PR 2: documentation honesty

- Correct `XML_COMPATIBILITY.md` so the maintained reproducible inventory is described as PCB and
  Schematic plus the plug-in settings specification.
- Add per-claim evidence labels to the exchange and library sections of
  `reference/diptrace-xml/REFERENCE.md`.
- Extend Q11 with the unresolved `UID32`, root-attribute, and binary-to-XML identity questions.
- Keep Q1/Q3/Q4/Q8/Q9/Q12/Q14/Q16/Q18 open.

### PR 3: operator library-evidence recipes

- Delivered: optional strict `input_artifacts` metadata binds private inputs by canonical relative
  path, SHA-256, and size, with record/finalize/ingest revalidation and no byte copy.
- Add concrete Component Editor and Pattern Editor recipes for Q11.
- Add optional screenshot hashes as supporting, never authoritative, artifacts.
- Add a read-only XML vocabulary diff against `spec_inventory.json`.
- Refuse promotion until independent review, redistribution approval, and a committed allowlist
  exist.

### PR 4: only after evidence

Regenerate structured inventory data, add schema/code validation, or change
`library_adapters.py` only for facts that have a primary source citation or reviewed real-export
evidence. Keep native Component/Pattern writers blocked until the mutation semantics are
demonstrated.

## Document hashes

These hashes identify the exact local documents audited; they do not authenticate their origin.

| Local path under `etc/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `DipTrace_XML_Specification/DipTrace_CompEdit_XML_Specification.docx` | 24,914 | `21ab21bb2d9907a13fb8deb3f85b79bd3673a96f371afa31684f17cd63590507` |
| `DipTrace_XML_Specification/DipTrace_CompEdit_XML_Specification.md` | 29,379 | `cf76b6698cab8fa5300e48003a0516e4a53d0e2b58259d40439c600f8ac6fc48` |
| `DipTrace_XML_Specification/DipTrace_CompEdit_XML_Specification.pdf` | 399,910 | `716070eccb4f451e2dfc4246e8997f932a0fd643b013c7dc3bef444623d6d31c` |
| `DipTrace_XML_Specification/DipTrace_PCB_XML_Specification.docx` | 44,347 | `e342bb2a567b361306f3891f0ae3dcff6a2135bc9f7589fee24bf129f2363984` |
| `DipTrace_XML_Specification/DipTrace_PCB_XML_Specification.md` | 72,546 | `ec70cb9ecc5766c500cad4ed7c99e1d712d6e02b9e4075a59bd02ede965916b9` |
| `DipTrace_XML_Specification/DipTrace_PCB_XML_Specification.pdf` | 1,003,154 | `590c3772382c7987b49d5ba829e54868a659cca687c30302cd502989737b7ede` |
| `DipTrace_XML_Specification/DipTrace_PattEdit_XML_Specification.docx` | 26,651 | `91fa331a354bfa09a528d931a9030f07d4fb9824f3ff7e16e1ca5fb90897ac4c` |
| `DipTrace_XML_Specification/DipTrace_PattEdit_XML_Specification.md` | 33,081 | `b000a248bdbf7a2f17d24a12b9453928c8a4c1a2b96388800b085aa52838bdf3` |
| `DipTrace_XML_Specification/DipTrace_PattEdit_XML_Specification.pdf` | 480,951 | `5ed6b7c287db920faabbe71cf3dee2d15b901d668a77ac0c6c5227438b34fd8d` |
| `DipTrace_XML_Specification/DipTrace_Schematic_XML_Specification.docx` | 29,162 | `a33acecfd747eef424e577b50429a80f1652d1305f39267a9821b864c8357805` |
| `DipTrace_XML_Specification/DipTrace_Schematic_XML_Specification.md` | 37,643 | `d6ed68ae448b453841ba7b83aff51dccf9966450b55f7cc4d58e0265d31f080a` |
| `DipTrace_XML_Specification/DipTrace_Schematic_XML_Specification.pdf` | 464,406 | `213c3496bd154f701f5b5b5c0a458427f72cff5c2f84406478391536b7b7a63e` |
| `plugin_sdk/01_plugin_architecture.md` | 25,223 | `1ff3a4ebc2efe1f2c6c00774c094c796c6b5ad5d2e83a1a428e24656a02ea00d` |
| `plugin_sdk/02_diptrace_xml_conventions.md` | 11,779 | `bc394b87c01b59c8152e513a38467a311057f0ba9812e008d5f146613e6d2e56` |
| `plugin_sdk/10_pcb_xml_reference.md` | 13,561 | `2f00698fba0e7a0f54e38ec828f7156fe6947efef75780260a4730aee6d2d223` |
| `plugin_sdk/20_schematic_xml_reference.md` | 9,262 | `f010c7f29daed2a474ec27b2e96f760941cd7f83a078bb7d4351c1a561c28958` |
| `plugin_sdk/30_compedit_xml_reference.md` | 8,275 | `e2178030ca0d09972dca821dd5598a146b840fdafc47141f9823104f6dba1d36` |
| `plugin_sdk/40_pattedit_xml_reference.md` | 7,878 | `c4af40003ba20021ca21106ab1ce0945875a44b8d073a1fed7d27bec06b047a2` |
| `plugin_sdk/50_common_operations.md` | 8,353 | `338cdfa5ab1e6df45256cb072a63b1173eea8e8634018a2263a1d94f3486673c` |
| `plugin_sdk/60_common_mistakes.md` | 6,525 | `d1b38e4477ac9dd70251c79c7221315debb952a060d34172b9731ff92fdcf981` |
| `plugin_sdk/README.md` | 4,678 | `23d5c0456ea8d6e168a7c784f6bc8c2019763213a953f49bd628ad9e3023994a` |
| `Библиотека примеров DipTrace.pdf` | 245,604 | `a8fcd59eee261642882e836fb726faaaebc134bc1bcfebf997ad67fed25e5960` |
