# Technical Debt

## Purpose

This document tracks remaining engineering limitations in the current `main` implementation. Historical release/audit debt is preserved in dated records and should not be copied here as if it were still current.

## Highest-priority current debt

### 1. Schematic selective reroute transaction

The schematic stack now has intent, bounded placement candidates, pin geometry, non-mutating wire planning, joint route scoring and route-feedback placement repair.

The missing production step is an atomic selective-reroute transaction that can:

1. choose an improved placement candidate/repair;
2. identify only affected existing nets/wires;
3. regenerate their bounded routes;
4. compose placement moves and wire replacement into one guarded plan;
5. preview/apply/review the whole change under the existing SHA/transaction boundary.

Until that exists, the placement planners correctly refuse already-wired schematics by default.

### 2. Schematic real-world quality acceptance

Repository tests prove deterministic bounded behaviour, not that complete real schematics consistently look good to engineers.

Remaining product evidence should cover representative real circuits and measure:

- connectivity/ERC non-regression;
- symbol/text/wire collisions;
- crossings/overlaps/bends/detour;
- block cohesion and compactness;
- signal-flow readability;
- native open/save/reopen/re-export preservation;
- human review of representative before/after results.

### 3. Schematic rotation/pin-facing authority

Pin geometry can be resolved conservatively from the embedded Design Cache, but non-zero part rotation remains an evidence-sensitive area. Automatic pin-facing rotation decisions should stay conservative until the exact real-host rotation semantics required by the layout engine are validated.

### 4. PCB Generations A-D real-host evidence boundary

PCB Generations A-D are implemented as internal bounded engineering layers. The remaining debt is not “implement B-D”; it is to strengthen authoritative evidence around the places where the model cannot own native physics/geometry:

- poured copper / refill geometry;
- plane/reference behavior;
- native via structures;
- stackup authority;
- manufacturing-specific constraints;
- real-DipTrace product acceptance of Generation D benchmark families.

Generation B/C analysis must continue to preserve unknown current/current-density/voltage-drop/impedance/reference facts rather than inventing them.

### 5. Cinematic real-client acceptance

Cinematic mode is implemented and covered in unit/CI tests, but its useful real-world replay depends on editor/version/configuration-specific calibration and action macros.

Remaining work:

- verify PCB and Schematic action macros against the exact DipTrace 5.3 configurations used for recording;
- perform end-to-end design-coordinate calibration on real open documents;
- capture residual/error evidence;
- add staged playback for via/layer transitions;
- verify any additional UI gestures before promoting them into reusable profiles.

Cinematic replay must remain a presentation layer, not a hidden alternate engineering authority.

### 6. Windows lifecycle acceptance

The current project campaign has 8 canonical manual gates PASS. Claude Desktop restart is explicitly WAIVED, not PASS.

When formal lifecycle acceptance resumes, the next project-required gate is:

`windows_clean_install_repair_uninstall`

followed by elevated plug-in/profile preservation and custom-state preservation.

The existing CI installer tests are useful implementation evidence but do not replace the chosen real clean-machine gate.

### 7. Native manufacturing output

The project still does not claim a verified native DipTrace API/path for Gerber, NC Drill, ODB++, IPC-2581 or assembler sign-off generation. Generic manifests/reviews are not manufacturing files.

This should remain an explicit limitation rather than being papered over by naming an approximation “Gerber export”.

### 8. Field/PI/EMC/thermal authority

Local impedance, return-path, aggressor/victim, PDN and thermal-risk helpers are bounded engineering assistance. They are not field-solver, PI, EMC or thermal sign-off.

External openEMS integration is an adapter boundary and must be validated as an actual external-solver workflow before stronger claims are made.

### 9. Native library public API decision

A raw-preserving internal Component/Pattern Library mutation core exists and has controlled real-editor round-trip evidence.

Remaining debt is product/API design, not basic implementation:

- decide whether/which native library mutations should become public MCP tools;
- define exact capability/evidence boundaries;
- add public schema/snapshot/error/permission tests if exposed;
- avoid broadening compatibility claims beyond the verified operations.

### 10. Documentation/evidence drift prevention

The repository has many intentionally immutable historical artifacts next to current evergreen docs. This creates recurring drift risk.

Current policy:

- dated release/audit/acceptance/compliance records preserve historical facts;
- evergreen docs describe current `main` and link to historical evidence explicitly;
- `CHANGELOG_NEXT.md` tracks post-`v0.2.1` development until the next release is selected;
- CI-generated contracts/badges/inventories remain generated rather than hand-maintained.

The current status split is maintained in `ROADMAP.md`, `TESTING.md`, `CHANGELOG_NEXT.md` and the dated evidence/release records.

## Resolved / superseded debt

The following should no longer be listed as open technical debt:

- PCB Generation B physical-context implementation — implemented;
- PCB Generation C routing-policy implementation — implemented;
- PCB Generation D bounded joint candidate selection — implemented;
- aggregate repository coverage “target 88%” — superseded by the enforced 90% combined supported-environment gate;
- Q1 Component Angle manual campaign — PASS on the later accepted production checkpoint;
- “native Component/Pattern mutation does not exist” — superseded by the internal raw-preserving core and controlled real-editor evidence;
- cinematic branch integration — merged to `main`.

Historical records that said otherwise remain valid snapshots of their original date/release.

## Permanent non-goals / non-claims

These are not ordinary bugs to “fix” by changing wording:

- universal DipTrace 5.x compatibility;
- globally optimal schematic or PCB layout;
- automatic invention of missing electrical/physical values;
- Novarm/DipTrace endorsement;
- trusted Authenticode signing without a protected signing identity;
- independent review when no independent reviewer actually participated;
- production/fabrication/regulatory sign-off from repository CI.
