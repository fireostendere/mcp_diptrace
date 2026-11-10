# Technical Debt

## Purpose

This document tracks remaining engineering limitations in the current implementation. Historical release/audit debt remains in dated records and must not be copied here as if it were still current.

## Review findings — 2026-11-10

The server review in [MCP_REVIEW_2026-11-10.md](MCP_REVIEW_2026-11-10.md) reproduced the
defects below; B1-B8, B10-B13, B15 and B16 are closed. The
`B` numbers match that record and [the project roadmap](../documents/ROADMAP.md).

| Id | Debt | Why it matters |
| --- | --- | --- |
| B6 | Silkscreen text boxes ignore rotation and bottom-side mirroring; no repository board has rotated or bottom-side text to verify a fix against | Silkscreen clearance may test the wrong box |
| B9 | A net reference that matches no name still falls back to an XML id | `connect_pins(net="1")` attaches to net id 1 instead of creating net `1` |
| B14 | `get_capabilities` is keyed by capability, with no published tool → capability-key map; the pipeline tools have no key | Clients cannot look a tool up in the report |

Two status questions also remain open: documents record the Q1 Component Angle
campaign as PASS while `evidence_status.Q1_COMPONENT_ANGLE_LIVE_VALIDATED` is still
`False` (one side is stale), and the tool gaps G1–G12 in the review record need a
product/API decision before any of them is built.

## Highest-priority current debt

### 1. Schematic real-world quality acceptance

The schematic stack now includes intent, bounded placement, pin-aware route
scoring, bounded iterative repair with objective history, global interconnect
strategy, deterministic motif/congestion ensemble ranking and atomic selective
affected-net reroute planning with conservative junction reuse.

Repository tests prove deterministic bounded behaviour, not that complete real schematics consistently look good to engineers. Remaining product evidence should cover representative real circuits and measure connectivity/ERC non-regression, collisions, crossings/overlaps/bends/detour, block cohesion, compactness, signal-flow readability, native open/save/reopen/re-export preservation and human review of representative before/after results.

### 2. Fuller schematic global optimisation

`schematic_atomic_reroute.py` closes the former dangerous gap where moving a symbol could leave stale existing wire geometry. Remaining optimisation debt is broader rather than transactional:

- global same-net Steiner-tree optimisation beyond the current bounded endpoint selection and literal multi-junction preservation for proven acyclic existing wire graphs;
- broader reviewed engineering-rule-pack coverage and caller-supplied evidence
  bindings; arbitrary PDF retrieval/extraction and model interpretation belong to
  OpenCode/mcp-rag, not this deterministic server;
- broader real-project tuning without hiding score terms.

### 3. Schematic rotation/pin-facing authority

Pin geometry can be resolved conservatively from the embedded Design Cache. Confidence-gated cardinal rotation candidates and atomic delete/rotate/rebuild planning now exist at package level, but automatic enabling remains evidence-sensitive and M2-gated until exact real-host rotation semantics are validated for the affected path.

### 4. PCB Generations A-D real-host evidence boundary

PCB Generations A-D, candidate-specific `pcb_quality.py` review and the bounded
`pcb_whole_board.py` pipeline are implemented internal engineering layers.
Remaining debt is authoritative evidence around native physics/geometry that
neither deterministic heuristics nor a language-model reviewer can own:

- poured copper/refill geometry;
- plane/reference behaviour;
- native via structures;
- stackup authority;
- manufacturing-specific constraints;
- real-DipTrace product acceptance of Generation D benchmark families and selected ensemble candidates.

Generation B/C analysis must preserve unknown current/current-density/voltage-drop/impedance/reference facts rather than inventing them.

### 5. DSN/SES interoperability acceptance

`specctra_analysis.py` can now inspect DSN/SES structure, route geometry, unknown nets/layers and importability before mutation. Remaining debt is real-tool interoperability breadth: more controlled Freerouting/Specctra-family samples, complex layer/via cases, round-trip evidence and explicit compatibility boundaries for syntax that the current bounded parser intentionally refuses.

### 6. Cinematic real-client acceptance

Cinematic playback now enforces `cinematic_preflight.py` inside the actual host path, so malformed/oversized manifests cannot bypass the safety budget by calling `play_manifest()` directly.

The repository PCB and Schematic GIF/MP4 examples are operator-accepted in the
current DipTrace configuration as of 2026-08-16, including complete-design
framing with margin and control-free crops.

Remaining work is broader real-client evidence and UI breadth:

- repeat PCB/Schematic action-macro and calibration evidence for additional
  DipTrace configurations;
- retain residual/error evidence when promoting a new reusable profile;
- add staged playback for via/layer transitions;
- verify additional UI gestures before promoting reusable profiles.

Cinematic replay remains presentation automation, not an alternate engineering authority.

### 7. Windows lifecycle acceptance

The accepted checkpoints have all 12 blocking manual gates PASS.

`windows_clean_install_repair_uninstall`, including an operator-confirmed from-zero run on a separate new Windows machine, and exact-candidate `elevated_plugin_install_profile_preservation` are complete. Custom-state preservation and Claude Desktop restart are also operator-confirmed PASS on a separate machine. CI installer tests remain implementation evidence, not a replacement for real-host gates.

### 8. Native manufacturing output

`native_cad` drives the real PCB editor's Gerber X2, NC Drill and pick-and-place export
dialogs on an isolated copy for the verified builds (5.3.0.3 and 5.3.5.1, Windows
only). It is a Python API, not an MCP tool or packaged CLI, and its output is not
inspected CAM: `export_fabrication_outputs(request_native_outputs=true)` still
refuses. ODB++, IPC-2581 and assembler sign-off have no path at all. Generic
manifests/reviews are not manufacturing files.

### 9. Field/PI/EMC/thermal authority

Impedance, return-path, aggressor/victim, PDN and thermal-risk helpers remain bounded engineering assistance. They are not field-solver, PI, EMC or thermal sign-off. External solver adapters must be validated as real external-solver workflows before stronger claims are made.

### 10. Native library public API decision

`library_mutation.py` provides the raw-preserving internal Component/Pattern mutation core. `library_mutation_api.py` now provides an expected-SHA package-level request/preview contract and remains deliberately `public_registration=False`.

Remaining debt is a product/API decision, not implementation absence:

- decide whether any native library mutation deserves public MCP registration;
- if yes, define exact permission/evidence boundaries and public schemas;
- intentionally update the frozen tools snapshot and discovery budget;
- add transport/error/permission tests;
- avoid broadening compatibility claims beyond verified operations.

The 152-tool MCP surface includes the bounded intelligence engines and read-only built-in-library bridge; the package-level native-library mutation API remains intentionally unregistered.

### 11. Evidence review automation depth

`evidence_report.py` now turns finalized capture candidates into deterministic
SHA-checked XML semantic reports with domain summaries and connectivity
fingerprints without granting trust/PASS. Remaining debt is richer
claim-specific visual/geometry and manufacturing review; connectivity equality
still does not imply electrical or native-layout acceptance.

## Resolved / superseded debt

The following should no longer be listed as open technical debt:

- schematic selective affected-net reroute transaction — implemented by `schematic_atomic_reroute.py` and ordinary guarded semantic transactions;
- basic schematic motif/congestion candidate ensemble — implemented by `schematic_ensemble.py`;
- bounded schematic global interconnect strategy, iterative objective history and
  topology-preserving reroute for proven acyclic multi-junction wire graphs — implemented;
- SHA-bound external engineering-rule ingestion with provenance/redistribution
  controls — implemented by `reference_rules.py`;
- PCB Generation B physical-context implementation — implemented;
- PCB Generation C routing-policy implementation — implemented;
- PCB Generation D bounded joint candidate selection — implemented;
- multi-profile bounded A-D candidate generation — implemented by `pcb_candidate_ensemble.py`;
- candidate-specific PCB physical/layout review and composed whole-board planning
  — implemented by `pcb_quality.py` and `pcb_whole_board.py`;
- DSN/SES pre-import structural/route analysis absence — implemented by `specctra_analysis.py`;
- XML semantic fingerprint/delta absence — implemented by `xml_analysis.py` with property regression coverage;
- evidence report assembly being entirely manual — deterministic review-only report generation exists;
- cinematic manifest preflight being optional — the real playback path now invokes it unconditionally;
- documentation/evidence drift having only a prose policy — `scripts/check_documentation_state.py` plus `tests/test_documentation_state.py` enforce current evergreen state in CI;
- aggregate repository coverage “target 88%” — superseded by the enforced 90% combined supported-environment gate;
- Q1 Component Angle manual campaign — PASS on the later accepted production checkpoint;
- “native Component/Pattern mutation does not exist” — superseded by the internal raw-preserving core and controlled real-editor evidence;
- cinematic branch integration — merged before this development pass;
- pipeline tools bypassing allowed roots and policy, live-session commits failing with
  the state directory outside the workspace, dangling wire ends after wire/pin edits,
  review profiles passing on the wrong document kind, QC blind to open copper (B1),
  differential microstrip impedance (B2), undisclosed missing geometry (B3), length
  checks on unrouted nets (B4), BOM grouping across supplier codes (B5), Net Ports in the schematic BOM and
  schematic-to-PCB comparison, annotated gate rows being dropped, and stale public tool
  counts — fixed with the 2026-11-10 review.

Historical records that said otherwise remain valid snapshots of their original date/release.

## Documentation/evidence state policy

Dated release/audit/acceptance/compliance records preserve historical facts.
Evergreen docs describe current implementation and explicitly link to historical
evidence. `CHANGELOG_NEXT.md` tracks post-`v0.3.0` development until the next
release is selected.

`scripts/check_documentation_state.py` guards key current-state relationships against code and the frozen public-tools snapshot, and rejects any other public tool count in an evergreen document. It intentionally does not rewrite or reinterpret immutable historical records.

## Permanent non-goals / non-claims

These are not ordinary bugs to “fix” by changing wording:

- universal DipTrace 5.x compatibility;
- globally optimal schematic or PCB layout;
- automatic invention of missing electrical/physical values;
- Novarm/DipTrace endorsement;
- trusted Authenticode signing without a protected signing identity;
- independent review when no independent reviewer actually participated;
- production/fabrication/regulatory sign-off from repository CI.
