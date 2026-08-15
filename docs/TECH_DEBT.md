# Technical Debt

## Purpose

This document tracks remaining engineering limitations in the current implementation. Historical release/audit debt remains in dated records and must not be copied here as if it were still current.

## Highest-priority current debt

### 1. Schematic real-world quality acceptance

The schematic stack now includes intent, bounded placement, pin-aware route scoring, placement repair, deterministic motif/congestion ensemble ranking and atomic selective affected-net reroute planning.

Repository tests prove deterministic bounded behaviour, not that complete real schematics consistently look good to engineers. Remaining product evidence should cover representative real circuits and measure connectivity/ERC non-regression, collisions, crossings/overlaps/bends/detour, block cohesion, compactness, signal-flow readability, native open/save/reopen/re-export preservation and human review of representative before/after results.

### 2. Fuller schematic global optimisation

`schematic_atomic_reroute.py` closes the former dangerous gap where moving a symbol could leave stale existing wire geometry. Remaining optimisation debt is broader rather than transactional:

- stronger sheet-level congestion-aware net scheduling;
- global same-net junction/tree optimisation instead of independent MST-edge planning;
- richer project/reference motif ingestion;
- a fuller bounded generate -> score -> repair -> reroute loop with objective history and explicit stopping criteria;
- broader real-project tuning without hiding score terms.

### 3. Schematic rotation/pin-facing authority

Pin geometry can be resolved conservatively from the embedded Design Cache, but non-zero part rotation remains evidence-sensitive. Automatic pin-facing rotation decisions should stay conservative until exact real-host rotation semantics are validated for the affected path.

### 4. PCB Generations A-D real-host evidence boundary

PCB Generations A-D plus the bounded `pcb_candidate_ensemble.py` are implemented internal engineering layers. Remaining debt is authoritative evidence around native physics/geometry that the model cannot own:

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

The project still does not claim a verified native DipTrace path for Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off generation. Generic manifests/reviews are not manufacturing files.

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

The 167-tool MCP surface includes the bounded intelligence engines and read-only built-in-library bridge; the package-level native-library mutation API remains intentionally unregistered.

### 11. Evidence review automation depth

`evidence_report.py` now turns finalized capture candidates into deterministic SHA-checked XML semantic reports without granting trust/PASS. Remaining debt is richer claim-specific comparison: connectivity, visual/geometry assertions and manufacturing-specific review must remain explicit rather than being inferred from a generic semantic fingerprint.

## Resolved / superseded debt

The following should no longer be listed as open technical debt:

- schematic selective affected-net reroute transaction — implemented by `schematic_atomic_reroute.py` and ordinary guarded semantic transactions;
- basic schematic motif/congestion candidate ensemble — implemented by `schematic_ensemble.py`;
- PCB Generation B physical-context implementation — implemented;
- PCB Generation C routing-policy implementation — implemented;
- PCB Generation D bounded joint candidate selection — implemented;
- multi-profile bounded A-D candidate generation — implemented by `pcb_candidate_ensemble.py`;
- DSN/SES pre-import structural/route analysis absence — implemented by `specctra_analysis.py`;
- XML semantic fingerprint/delta absence — implemented by `xml_analysis.py` with property regression coverage;
- evidence report assembly being entirely manual — deterministic review-only report generation exists;
- cinematic manifest preflight being optional — the real playback path now invokes it unconditionally;
- documentation/evidence drift having only a prose policy — `scripts/check_documentation_state.py` plus `tests/test_documentation_state.py` enforce current evergreen state in CI;
- aggregate repository coverage “target 88%” — superseded by the enforced 90% combined supported-environment gate;
- Q1 Component Angle manual campaign — PASS on the later accepted production checkpoint;
- “native Component/Pattern mutation does not exist” — superseded by the internal raw-preserving core and controlled real-editor evidence;
- cinematic branch integration — merged before this development pass.

Historical records that said otherwise remain valid snapshots of their original date/release.

## Documentation/evidence state policy

Dated release/audit/acceptance/compliance records preserve historical facts. Evergreen docs describe current implementation and explicitly link to historical evidence. `CHANGELOG_NEXT.md` tracks post-`v0.2.1` development until the next release is selected.

`scripts/check_documentation_state.py` guards key current-state relationships against code and the frozen public-tools snapshot. It intentionally does not rewrite or reinterpret immutable historical records.

## Permanent non-goals / non-claims

These are not ordinary bugs to “fix” by changing wording:

- universal DipTrace 5.x compatibility;
- globally optimal schematic or PCB layout;
- automatic invention of missing electrical/physical values;
- Novarm/DipTrace endorsement;
- trusted Authenticode signing without a protected signing identity;
- independent review when no independent reviewer actually participated;
- production/fabrication/regulatory sign-off from repository CI.
