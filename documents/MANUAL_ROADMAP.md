# Manual Roadmap

## Scope

This document contains only gates that a neural model or repository test cannot
honestly close. Automation may prepare candidates, run deterministic checks,
calculate hashes, compare XML, assemble reports, or control a bounded tool. A
human with the required equipment, authority, and context owns the observation
and PASS decision.

The engineering work that can be implemented and tested in the repository is in
the [project roadmap](ROADMAP.md).

## Retest policy

The historical 12/12 manual matrix and schematic cases 01-18 are already closed
for their recorded checkpoints. Do not replay them wholesale. A gate is run only
when one of these applies:

- production code affecting the observed path changed;
- a DipTrace/client/tool version, UI profile, OS, DPI, stackup, board family, or
  manufacturing process enters a new compatibility claim;
- an earlier artifact is unavailable, tampered with, ambiguous, or lacks
  redistribution permission;
- the project makes a stronger claim than the existing evidence supports.

Every run must bind the source, generated candidate, host/tool versions, and
result to exact hashes. Failed and invalid attempts remain in the record.

## Gate index

Priorities below apply only after the named trigger occurs; they are not blanket
merge blockers.

| Claim-local priority | Gate | Trigger | Blocks |
| --- | --- | --- | --- |
| P0 | M1 Native whole-board PCB acceptance | Default/public whole-board mutation or stronger native PCB claim | Default enablement and native quality/refill claim |
| P0 | M2 Focused schematic native acceptance | New topology, rotation, or readability scope | That exact new schematic claim |
| P0 | M3 Engineering rule/physics source review | A new/changed pack or built-in principle is enabled | Engineering claim based on that source |
| P2 | M4 Cinematic/UI acceptance | New reusable profile or unverified gesture | That profile/gesture claim |
| P0 | M5 Focused real-client compatibility | Changed public schema ships in a named client release | That client compatibility claim |
| P1 | M6 Manufacturing package and DFM review | Fabrication/assembly-ready claim | That production package claim |
| P1 | M7 First article, assembly, and bring-up | Working-hardware claim | That hardware revision claim |
| P1 | M8 SI/PI/thermal/EMC correlation and sign-off | Physical-performance/compliance claim | The corresponding claim only |
| P1 | M9 Real DSN/SES round trip | External-router interoperability claim | That tool/dialect scope |
| P2 | M10 DipTrace format probe campaigns | Broader writer/format claim | The affected compatibility scope |
| P2 | M11 Evidence/fixture trust promotion | Reusable evidence, fixture, or reviewer-corpus labels | The requested trust level |
| P2 | M12 Product/API decisions | New public surface or default model/prompt | Implementation/promotion of that choice |
| P3 | M13 Legal, signing, and independent governance | Stronger signed/independent/production claim | That stronger release claim |

## Feature and client claim gates

### M1. Native whole-board PCB acceptance

Why manual: repository geometry cannot observe authoritative DipTrace refill,
native DRC behavior, real plane connectivity, final thermal geometry, or human
layout quality.

Scope, operator, and setup:

- PCB engineer with the exact DipTrace build(s) named by the compatibility claim;
- one exact-candidate smoke before default/public mutation; for a broad quality
  claim, one representative case per claimed topology (a useful baseline is
  simple two-layer, switching/high-di/dt, and mixed sensitive/power);
- exact source commit, rule pack, planner configuration, and generated candidate.

Procedure:

1. Record source and candidate SHA-256 values and the exact DipTrace build.
2. Open the candidate, perform native Top/Bottom copper refill, and run native
   DRC.
3. Inspect connectivity, continuous Bottom GND, useful Top GND, distributed
   stitching (including sparse upper regions), real four-spoke thermals on GND
   connector pads, islands/cutouts, return paths, compactness, centering,
   symmetry, courtyard/assembly clearance, and silkscreen.
4. Verify the smallest practical 2.54 mm footprints against predefined
   outline/edge-margin/area targets, and document the reason for any substantial
   residual whitespace.
5. Save, close, reopen, re-export, and compare semantic, connectivity, and
   geometry reports with the planned result.

Required evidence:

- source, candidate, saved-native, and re-export hashes;
- DipTrace version/profile and planner/rule-pack identities;
- native DRC report;
- uncropped Top/Bottom/refill screenshots and close-ups of thermals/stitching;
- deterministic evidence JSON/Markdown and operator verdict.

PASS:

- no blocking DRC item or unexplained semantic/connectivity delta;
- refill produces continuous intended ground, no unexplained islands, no
  critical trace crossing a reference-plane gap, return vias at relevant layer
  transitions, distributed stitching, and actual thermal spokes;
- board outline, placement, and silkscreen satisfy the project rules in
  [AGENTS.md](../AGENTS.md);
- save/reopen/re-export preserves the accepted result.

Repeat after changes to whole-board planning, placement/routing, outline,
pours/vias/thermals, silkscreen, XML writing, DipTrace refill semantics, or when
adding a new board-family claim.

### M2. Focused schematic native acceptance

Why manual: exact symbol orientation/pin-facing behavior and engineer-perceived
readability are not established by synthetic geometry.

Run only the impacted cases:

- indexed bus/net-label strategy;
- an already-wired net with one nearby intentional degree-three junction inside
  the implemented bounded-detour policy;
- multi-net move plus atomic reroute;
- rotation candidates only for the exact symbol families being enabled;
- one representative larger schematic only when scaling behavior changed.

Arbitrary hand-authored multi-junction topology remains outside this gate until
the implementation explicitly supports it.

Procedure and evidence:

1. Bind the baseline, operations, objective history, rule pack, and candidate by
   hash.
2. Inspect connectivity/ERC and before/after readability in DipTrace Schematic.
3. Save, close, reopen, and re-export.
4. Compare endpoints, junctions, labels, unaffected nets, and residual wire
   fragments.
5. Retain screenshots, ERC output, comparison report, and dated, identified
   operator verdict.

PASS: no lost or false connection, unaffected nets remain unchanged, proven
junction topology survives, no stale fragments remain, orientation matches the
claimed semantics, and an engineer accepts the result as readable.

Repeat only after changes to schematic ensemble/interconnect/atomic reroute/pin
geometry/rotation or for a newly claimed topology. Do not replay cases 01-18.

### M3. Engineering rule and physics-source review

Why manual: a model can transcribe a source but cannot grant engineering
applicability, resolve every ambiguous condition, or establish redistribution
rights.

Authorities: a qualified engineer validates the authoritative
datasheet/application note for the exact MPN, variant, and revision; the rights
holder or legal reviewer separately validates redistribution.

For every rule or built-in physics principle, verify:

- document SHA-256 and revision;
- page/table/figure locator;
- units, min/typ/max meaning, tolerance, and conversion;
- operating conditions and applicability to the selected part/stackup/process;
- whether the source and extracted record may be redistributed.

Evidence: rule-by-rule technical review table, corrections, technical reviewer
identity/date, source identity, and a separate rights disposition of
`redistributable` or `not_redistributable`. Source bytes that cannot be
redistributed stay outside the repository.

PASS: every enabled rule/principle is unambiguously traceable, its context and
units are preserved, contradictions are resolved or disabled, and model memory
is not used as a source.

Repeat when the source revision, MPN/variant, pack bytes, formula, units, or
operating conditions change.

### M4. Real cinematic and UI-profile acceptance

Why manual: deterministic frame metrics cannot prove that a real DipTrace UI
gesture works or that the animation looks natural to a viewer.

Setup: Windows, exact DipTrace editor/build, ffmpeg, target DPI/theme/layout, and
the real UI profile.

Procedure:

1. Calibrate anchors and preserve residual/error measurements.
2. Run preflight and dry-run before any real replay.
3. Record PCB and schematic paths affected by the change.
4. Inspect the full video and GIF frame by frame.
5. Verify one-by-one human-like placement/routing, complete final geometry,
   stable design-boundary fit, approximately 10% margin, no editor controls,
   no clipping, jumps, black frames, or global mouse/keyboard interference.

Evidence: profile, anchors/residuals, manifest and media hashes, MP4/GIF, frame
assessment, host configuration, and operator verdict.

PASS: the complete design remains the focus, the purple PCB boundary or visible
schematic bounds are intact with margin, construction is visibly staged, and all
gestures succeed without unsafe fallback.

Repeat after capture/framing/macro changes, a new via/layer gesture, DipTrace
version/editor changes, DPI/theme/layout changes, or promotion of a new reusable
profile.

### M5. Focused real-client compatibility

Why manual: hosted tests do not prove restart, discovery, rendering, or calls in
an installed desktop client.

Run this gate only when a release names a changed client compatibility claim.
For the current intelligence schema, test the real named Codex/Claude Desktop
versions after restart:

- `tools/list` and `get_capabilities`;
- the changed schematic and PCB intelligence tools with and without an
  engineering rule pack;
- error rendering for invalid rules and an oversized/unsupported request.

Evidence: exact client/server/package versions, configuration, logs or screen
capture, responses, and operator verdict.

PASS: restart loads the exact server, discovery succeeds within client limits,
calls and structured errors render correctly, and no settings are lost.

The full clean-install 12-gate matrix is unnecessary unless installer, bridge,
packaging, configuration, or lifecycle code changed.

## P1 — fabrication and physical performance

### M6. Native manufacturing package and DFM review

Why manual: this repository does not generate authoritative native Gerber/NC
Drill/ODB++/IPC-2581 output, and only a fabricator/assembler can accept the
chosen process rules.

Procedure:

1. Freeze board revision, BOM, footprints, stackup, finish, copper weight, and
   fabricator/assembler rule deck.
2. Perform native refill and DRC in DipTrace.
3. Generate the required manufacturing/assembly outputs with the supported
   native or reviewed external exporter.
4. Inspect every layer and drill file in an independent CAM viewer.
5. Submit to the selected fabricator/assembler and resolve or explicitly waive
   every DFM issue.

Review at minimum: pad/via spacing, NPTH/slots, copper islands/thermals, mask
dams/slivers, paste/stencil webs, acute copper and neck-downs, silkscreen-to-pad,
polarity/pin 1, centroids, heights, edge clearances, and panelization.

Evidence: hashed output ZIP, layer/drill inventory, CAM screenshots/report,
native DRC, BOM/CPL, DFM report, and waiver ledger.

PASS: fabricator and assembler accept the exact package; no unexplained blocking
warning remains; CAM geometry matches design intent.

Repeat after board, footprint, stackup, rule deck, fabricator, toolchain, or
output-setting changes.

### M7. First article, assembly, and bring-up

Why manual: only physical hardware reveals solderability, shorts, component
orientation, assembly defects, actual current, temperature, and functional
behavior.

Procedure:

1. Record board/assembly revisions and specimen serials; perform visual/AOI
   inspection.
2. Check shorts and continuity before power.
3. First-power with a documented current limit.
4. Measure rails, idle/load current, reset/clock, interfaces, and required
   functions one subsystem at a time.
5. Exercise worst-case load and inspect thermal behavior and stability.
6. Verify test-point access and observe soldering of representative connector
   GND pads; use a separate process coupon only when desolder/rework capability
   is part of the claim.

Evidence: photos, measurements, instrument IDs/calibration state, logs, limits,
and failure/repair history.

PASS: written electrical and functional limits are met, connector GND pads with
thermal relief solder reliably, and there is no unexplained overheating,
instability, assembly, or access problem.

Repeat for changes to schematic, layout, BOM, footprint, fab/assembly process,
or firmware that affect the tested path.

### M8. SI, PI, thermal, and EMC correlation/sign-off

These are separate claim gates; run only the applicable one.

- **SI:** approve real stackup/materials and signal targets; correlate an
  external solver with coupon/TDR/VNA or oscilloscope eye/jitter measurements.
- **PI:** use measured load profiles; verify rail ripple, droop, transient
  response, ground bounce, and, when required, PDN impedance.
- **Thermal:** run worst-case load/ambient/enclosure soak with calibrated
  thermocouples or IR and compute junction margin.
- **EMC:** define the applicable standard/test plan, run pre-compliance
  emissions/immunity, then use an accredited lab for a compliance claim.

Evidence must include exact geometry/stackup/materials, solver and instrument
versions, calibration, input decks, raw results, predefined targets, reviewer,
and margin. The interfaces in
[FIELD_SOLVER_PROTOCOL.md](../docs/FIELD_SOLVER_PROTOCOL.md) and
[IMPEDANCE_AND_SI.md](../docs/IMPEDANCE_AND_SI.md) may carry evidence but do not
grant PASS.

PASS: each subgate passes only when predefined numeric targets and tolerances are
met on the exact hardware, simulation-to-measurement discrepancy stays within
the declared tolerance, and the responsible engineer resolves or explicitly
waives every anomaly. EMC compliance requires the applicable accredited-lab
report.

Repeat after relevant stackup, geometry, clock/edge rate, switching supply,
decoupling, enclosure, cable/connector, load, or component substitutions.

### M9. Real DSN/SES and external-router round trip

Why manual: parser tests do not establish DipTrace/Freerouting dialect or native
import correctness.

Procedure: export a controlled real multilayer DSN, route a bounded subset in
the selected external router, import SES into DipTrace, run native DRC/visual
review, then save/reopen/re-export.

Evidence: source/DSN/SES/final hashes, tool versions, parser/import report,
screenshots, and DRC output.

PASS: nets, layers, padstacks, vias, coordinates, and untouched geometry are
preserved; no unknown/skipped construct or unexplained change remains.

Repeat after DSN/SES parser/export/import code, router version/dialect, layer
model, or supported-construct changes.

## P2 — format knowledge and evidence trust

### M10. DipTrace format probe campaigns

Use the generated [probe pack](../docs/PROBE_PACK.md) and the strict
[evidence-capture workflow](../docs/EVIDENCE_CAPTURE.md). Each experiment needs
three distinct byte roles: `source -> open_save -> reexport`.

Run only probes needed by an active feature/claim, in this order:

1. safety: Q2 exchange completeness, Q10 authoritative copper fill, Q12 host
   acknowledgement/corrupt output;
2. writer breadth: Q4 sparse IDs, Q5 routed Point vocabulary, Q11 library
   identity/canonicalization, Q17 DSN/SES, Q18 hierarchy;
3. format breadth: Q3 current-version Cancel, Q7-Q9 numeric/encoding/BOM, and
   Q13-Q16 vocabulary/direct XML/canonicalization/units;
4. reusable evidence/UI: Q1 redistributable angle capture and Q6 persistent
   selection.

PASS for capture: exact host version and inputs are recorded, the three roles
are distinct and hash-bound, the observation is unambiguous, all deltas are
classified and retained, and a human reviews the result. A new unexplained delta
leaves the compatibility question unresolved but does not invalidate an
otherwise correct capture. Capture does not promote trust automatically.

Repeat only the affected probe after changes to the corresponding
reader/writer/bridge/parser ownership, claimed editor/build/profile, or after
evidence hash/permission invalidation.

### M11. Evidence or fixture trust promotion

Why manual: tooling cannot establish authorship, redistribution permission, or
independence of review.

For each candidate:

1. confirm authorship, sanitization, containment, and redistribution rights;
2. run capture, hash, semantic/connectivity audit, and deterministic report;
3. have an independent reviewer compare the literal artifacts and operator
   claim;
4. promote through a separate reviewed registry/fixture change.

Required evidence: candidate manifest, stage hashes, audit/report outputs,
rights and sanitization attestation, independent-review record, and the exact
registry/fixture diff. The same gate approves ground-truth labels used by the
reviewer evaluation corpus.

PASS: bytes, hashes, provenance, permission, and review agree; the reviewer is
not the artifact source; no sensitive information remains. Generic fixture
`--apply` must stay unavailable until this authority model is explicitly
approved.

Repeat for every new byte set, source, trust level, corpus label set, or rights
change.

### M12. Product and public-API decisions

A human product owner must decide before code expands any of these surfaces:

- public Component/Pattern mutation and its exact permitted operations;
- a native manufacturing-output workflow and supported tool/version matrix;
- supported Python/OS/DipTrace/client ranges;
- whether a new MCP tool is justified instead of reusing the existing contract;
- promotion of a model, prompt, or rule-pack version to the project default.

The decision record must name users, threat model, permissions, compatibility
claim, evidence required, failure behavior, and maintenance owner. Once approved,
implementation belongs in the automated roadmap.

PASS: a dated owner-approved decision records the exact scope, threat model,
evidence, maintenance owner, and either approval or explicit deferral. Revisit
only when the proposed public surface, default, or compatibility claim changes.

## P3 — stronger release and governance claims

### M13. Legal, signing, and independent governance

Run only when the intended release claim requires it. Historical unchecked
items in [PUBLIC_RELEASE_CHECKLIST.md](../docs/PUBLIC_RELEASE_CHECKLIST.md) are a
v0.1.2 snapshot, not an unconditional current backlog.

Treat these as separate conditional subgates. Manual authorities must cover:

- dependency/transitive/bundled Windows/PyInstaller content, wheel-shipped
  skills/schemas, fixtures/evidence, trademark/non-affiliation wording, and any
  required Novarm/DipTrace permission;
- a protected Authenticode account/certificate, owner verification, protected
  signing environment, timestamp verification, reviewer, and rollback;
- a real independent reviewer/release approver, MFA/recovery/retention owners,
  security and conduct backup, and conflict/recusal policy.

PASS cannot be supplied by a self-signed certificate, the same maintainer
calling themselves independent, a model review, or a fictional contact channel.

Required evidence, as applicable: legal review scope and references; exact
signed hashes plus signer/timestamp verification; protected-environment and
recovery record; independent-review approval and recusal record.

PASS: every subgate required by the intended release claim has a named real
authority and retained evidence. Repeat after a dependency/bundled-material or
license change, signer/certificate/policy change, governance-owner change, or a
stronger release claim.

## Work that is not manual-only

Do not burden operators with repository work that automation can perform:

- pytest, Ruff, Mypy, coverage, generated snapshots, documentation drift, and
  release allowlist checks;
- candidate generation, offline review, hashes, semantic/connectivity/geometry
  diffs, and report assembly;
- evidence capture/quarantine mechanics;
- release build, manifest/SBOM/checksum generation, and public redownload hash
  checks after publication is authorized;
- bounded execution of ngspice, openEMS, or Freerouting when a real runtime and
  inputs are supplied;
- frame/crop measurements and deterministic cinematic preflight.

Humans own requirements, source/model applicability, real-host and visual
verdicts, physical measurements, fabrication acceptance, rights/provenance,
protected signing, publication authorization, and independent approval.
