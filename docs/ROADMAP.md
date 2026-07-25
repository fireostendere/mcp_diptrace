# Roadmap and Actual Status

This document separates three things that were previously easy to mix together:

1. **implemented code** — production code, typed contracts, and tests exist;
2. **runtime availability** — the feature is available for the active document and configured adapters;
3. **DipTrace-verified compatibility** — the write path has controlled open/save/re-export evidence from a real DipTrace build.

`complete v1/v2/v3` below means that the implementation exists and is covered by the repository test suite. It does **not** imply full equivalence with the DipTrace GUI or complete DipTrace 5.3 round-trip evidence.

The authoritative runtime source remains `get_capabilities`.

## Current Readiness — 2026-07-25

The project has moved beyond a parser/MCP prototype. The strongest areas are read/query, engineering review, guarded semantic edits, transactions, schematic-to-PCB comparison/synchronization, and bounded routing/placement workflows.

The main remaining risk is no longer missing MCP surface area. It is the gap between synthetic/fixture-tested writer behavior and broad, redistributable, automated evidence from real DipTrace 5.3 open/save/re-export cycles.

### WO-11 input and write-safety checkpoint — 2026-07-25

The human-free input/write hardening baseline now includes:

- literal caller-supplied paths, with environment/home expansion limited to
  server-owned configuration before allowed-root enforcement;
- layered DTD/entity rejection and source-codec/BOM preservation for supported
  UTF-8, UTF-16LE/BE, US-ASCII, and ISO-8859-1 raw and semantic writes;
- reparsing plus semantic-tree equality checks for low-level raw edits and
  raw-preserving semantic compilation;
- typed rejection of `NaN` and infinities in request models, normalized XML
  numbers, and SES numeric tokens;
- a deliberately narrow DSN writer that refuses unverified escaping/non-ASCII
  conventions, and an SES reader that refuses unverified backslash escaping and
  literal controls in quoted tokens;
- bounded external-process streaming, one cross-adapter concurrency limit, POSIX
  process-group cleanup, and Windows kill-on-close Job Objects with explicit
  root-process reaping;
- central per-target offline backup histories plus count/age cleanup of validated
  terminal records. Active/nonterminal state is protected, and cleanup thresholds
  are soft targets rather than storage quotas.

For an existing target, the original bytes are captured before replacement. A
brand-new target has no previous content and therefore has no backup; an explicit
overwrite of an existing target does.

This checkpoint is an implemented safety boundary, not evidence of additional DipTrace
format compatibility. [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) Q8/Q9 still require human
experiments for DipTrace's emitted/accepted encoding and BOM behavior, and Q17 still
requires a real DipTrace-generated DSN/SES pair. Refusals remain until that evidence is
available.

### Format Coverage (measured from official specifications)

The reproducible inventory extracted from the official DipTrace XML specifications (PCB and
Schematic, v4.3.0.3, 2023) contains **270 literal XML elements**, **727 XML attributes**, and
**232 element text-content definitions**. Prose-only tag mentions and text values previously
misclassified as attributes are excluded. Current coverage against this measured inventory:

| Metric | Value |
| --- | --- |
| Total literal XML elements in spec | 270 |
| XML attributes in spec | 727 |
| Element text-content definitions | 232 |
| Explicit attribute omission clauses | 4 |
| Documented parent/child relationships | 90 across 80 parents |
| Normalized (reader produces typed field) | 58 |
| Written only (writer can create/modify) | 19 |
| Mentioned only (literal, not an XML call) | 19 |
| Passthrough (unknown XML, kept byte-for-byte) | 174 |
| **Coverage** | **28.5%** |

See [FORMAT_COVERAGE.md](FORMAT_COVERAGE.md) for the full element-by-element inventory, and
[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) for the current maintained set of high-impact unresolved
compatibility questions.

### Local reference-material audit (not shipped evidence)

An operator-supplied, untracked directory of generated format notes and legacy Component/Pattern
library binaries was reviewed in
[REFERENCE_MATERIALS_AUDIT.md](REFERENCE_MATERIALS_AUDIT.md). It is not bundled, indexed by the
runtime, counted as a fixture pack, or used by the specification generator. The generated notes
lack a reproducible source revision and redistribution grant; the libraries lack an origin/version
manifest and contain legacy binary data rather than XML. Consequently, the audit changes probe
priorities and documentation wording, but supplies no production convention and closes no open
question.

The useful next gates are human/evidence work:

1. verify source identity, author, license, and redistribution permission before reusing any local
   document or binary;
2. extend candidate capture with typed `input_artifacts` hashes so a private binary input can be
   associated with its exported XML without copying the binary into Git;
3. use licensed Component/Pattern Editors to export minimal sanitized examples, with one
   intentional GUI change and unchanged controls per experiment;
4. capture source/open-save/re-export roles, keeping screenshots supporting-only;
5. independently review and explicitly allowlist a redistributable candidate before it can become
   a CI fixture or change the structured inventory.

Current practical classification:

| Area | Status | Main remaining gap |
| --- | --- | --- |
| PCB/schematic read/query | mature beta | broader redistributable DipTrace 5.3 fixtures |
| Component/Pattern Library read/validate | mature beta | more 5.3 mask/paste/courtyard fixtures |
| Guarded semantic edits | mature beta | close all trust-invalidation/write-path evidence gaps |
| Schematic authoring | beta | live round-trip evidence for authored wires and more operations |
| Schematic → PCB synchronization | beta | full trust-path coverage and broader real 5.3 round trips |
| Placement | beta, bounded | no global placer/legalizer equivalent to a full EDA engine |
| Local/multi-net routing | beta, bounded | no push-and-shove/free-angle/global router |
| Differential-pair/SI analysis | beta | external solver validation remains optional/runtime-dependent |
| Native Component/Pattern Library mutation | blocked | controlled 5.3 writer fixtures and semantics |
| Native manufacturing output | out of current core scope | no verified DipTrace API for Gerber/NC Drill generation |
| Pattern recommendation | planned | feedback dataset, deterministic retrieval, held-out metrics |

## Revised Priority Order

Feature count is no longer the bottleneck. New high-level tools should not outrun compatibility evidence. The implementation priority is therefore:

### Priority A — Close compatibility and trust evidence

1. close trust invalidation coverage for every write path currently reported as untested by `get_capabilities`:
   - `plan_apply`;
   - `ses_import`;
   - `schematic_to_pcb_sync`;
   - `live_session_apply`;
2. collect a redistributable DipTrace 5.3 fixture pack covering PCB, schematic, Component Library, Pattern Library, controlled before/after writer cases, and a real DSN/SES pair;
3. add explicit real-DipTrace acceptance for authored schematic wires and generated ratlines;
4. verify mask/paste/courtyard/`Common` semantics with one-setting-at-a-time exports;
5. make these cases executable in CI without requiring DipTrace to be installed.

Exit condition: the project can distinguish parser-tested, operation-tested, DipTrace-exported, and DipTrace-roundtrip-verified paths without relying on broad documentation claims.

### Priority B — Native library writers

Only after Priority A supplies writer evidence:

- create/update patterns;
- create/update components, parts, pins, graphics, and fields;
- attach a pattern to a component;
- maintain explicit pin-to-pad mapping;
- preserve unknown/unsupported library XML;
- prove idempotence and DipTrace 5.3 open/save/re-export equivalence.

### Priority C — Human-guided pattern recommendation

After the compatibility baseline is stable:

1. append-only feedback records;
2. deterministic package feature extraction and retrieval;
3. held-out top-1/top-3/rejection metrics;
4. ranked existing-pattern suggestions;
5. controlled human correction capture.

The first useful recommendation system should select among **existing** patterns. Fine-tuning is explicitly later work and is not required for the initial system.

### Priority D — Optional external validation

- capture a real openEMS result and integration run;
- optionally broaden Freerouting integration fixtures;
- keep external-solver availability separate from core parser/writer trust.

## Phase Summary

| Phase | Status | Implemented |
| --- | --- | --- |
| 0 | complete | baseline contract, SDK/Pydantic/package audit, capability discovery |
| 1 | complete v1 | PCB/schematic/library domain model, stable IDs, XML adapters, structured query |
| 2 | complete v1 | millimeter-normalized geometry, transforms/mirroring/arcs, spatial index, SVG/JSON preview |
| 3 | complete v1 | semantic compiler, persistent transactions, policy, SHA/preview/commit/rollback |
| 4 | complete v1 | component/part/text/rule/test-point edits, pattern swap, groups, library read/validate |
| 5 | complete v1 | registry DRC/ERC/connectivity/geometry findings and persistent reports |
| 6 | complete v1 | deterministic silkscreen candidates, plans, previews, and apply |
| 7 | complete v1 | bounded local placement candidates, scoring, legalization, and apply |
| 8 | complete v2 | trace/via primitives, bounded multi-layer 45-degree A*, and symmetric vias |
| 9 | complete v1 | bounded DSN export, Freerouting job, SES inspect/import, and post-review |
| 10 | complete v3 | coupled-pair routing, lengths/skew, microstrip and IPC-2141 symmetric stripline impedance |
| 11 | complete v1 | return-path/plane heuristics, BOM/design comparison, DFM/DFA/DFT, and thermal skips |
| 12 | partial v2 | library validation, generic release manifests, typed optional openEMS jobs; library mutation and native fabrication remain unavailable |
| 13 | complete v1 | workflow prompts, skill contracts, CI matrix, benchmark harness, truthful discovery |
| 14 | complete v1 | project scaffolding: new schematic/PCB XML documents with stackup, rules, and sheets |
| 15 | complete v1 | schematic authoring: sheets, part placement, pin connectivity, wires, and net labels |
| 16 | complete v1 | official panelization parameters (V-Scoring / Tab Routing) and clearing |
| 17 | complete v1 | ngspice batch adapter for user-supplied netlists with typed log results |
| 18 | complete v2 | congestion-aware multi-net ordering with bounded rip-up/retry |
| 19 | complete v2 | additive and guarded exact schematic-to-PCB reconciliation with explicit multi-part pin mapping |
| 20 | complete implementation baseline | fail-closed authority boundary, PCB/schematic semantic comparison, native Windows CI, external-job cancellation; full write-path trust invalidation still has explicitly reported gaps |
| 21 | planned | human-guided pattern feedback dataset, deterministic retrieval, measurable recommendation workflow |

## Implemented Boundary

Implemented semantic operations include move, rotate, side, lock, value, properties, pattern, align, distribute, group, board text, no-connect, net rename, NetClass rules, standalone test points, trace/via primitives, local routing, differential-pair routing, schematic authoring, panelization, and schematic-to-PCB synchronization.

Pattern swap requires exact pad-number compatibility. Component and Pattern Libraries are available for reading and validation.

Native library create/update and attach-pattern mutation are intentionally unavailable because the repository does not yet contain sufficient controlled DipTrace 5.3 writer fixtures. Capability discovery must continue to report this as unavailable rather than registering placeholder tools.

## Routing and SI Limits

- The local router supports bounded vias and multi-layer routing with orthogonal/45-degree segments.
- `route_connections` provides congestion-aware ordering and bounded batch-local rip-up/retry.
- It is not push-and-shove, free-angle, dynamic neck-down, or a global autorouter.
- The DSN serializer rejects unsupported geometry rather than silently dropping data.
- SES import always passes internal inspection, preview, and review before commit.
- Differential-pair synthesis writes both traces and the pair `Segment` atomically.
- Analytical impedance is preliminary: Hammerstad-Jensen single/coupled microstrip and IPC-2141 centered symmetric stripline.
- Frequency-dependent/off-center stripline analysis requires the optional external openEMS runner.

## Review and Manufacturing Limits

- Copper-pour handling reads the boundary, not authoritative refilled copper geometry.
- Return-path analysis is a geometry heuristic with confidence reporting, not full-wave SI.
- Generic fabrication manifests are not Gerber/NC Drill/ODB++/IPC-2581 packages.
- Generic placement CSV must be mapped to the selected assembler's coordinate convention.
- The ngspice adapter runs user-supplied netlists; it does not generate a netlist from a DipTrace design.
- Online component sourcing is disabled by default.

## Project Creation and Synchronization Limits

- `create_schematic_document` and `create_pcb_document` generate **synthetic** 4.3-era XML structures. They are classified as `synthetic_parser_only` until independent DipTrace evidence exists.
- `create_document_from_seed` copies a real DipTrace-exported XML seed and preserves unknown XML and provenance, but does not auto-upgrade round-trip trust.
- `place_part` references a library `ComponentStyle`; DipTrace resolves symbol graphics and pin mapping from configured libraries during import.
- Schematic wires use the official `Wire`/`Points` structure, while logical pin-to-net connectivity is maintained separately through `connect_pins`/`disconnect_pins`.
- Panelization writes official `Panel` parameters; tab coordinates are recomputed by DipTrace and MCP does not expand final panel geometry.
- Exact schematic-to-PCB reconciliation is opt-in, refuses locked objects by default, and removes traces only when a synchronized net's endpoint set changes.
- Multi-net rip-up/retry is limited to traces produced within the current routing batch.

## Trust, Semantic Comparison, and CI Baseline

The following baseline must not be weakened by later feature work:

- runtime state, user-supplied evidence, fixture labels, and trusted authority are separate concepts;
- user-controlled JSON, sidecars, hashes, and fixture manifests cannot mint `diptrace_roundtrip_verified` or `external_tool_roundtrip_verified`;
- high-trust promotion remains unavailable until an authenticated server-owned registry, signature verifier, or committed allowlist exists;
- evidence is bound to exact document role/path, source type, before/after SHA-256, and required semantic-comparison categories;
- rollback reparses and revalidates restored provenance/evidence;
- PCB comparison covers components, pads, nets, trace endpoints, ordered points, widths, segment layers, via styles/spans, locks, and differential-pair membership;
- schematic comparison covers sheets/hierarchy, parts, values/patterns, pins, pin-to-net connectivity, wire geometry, labels, buses, and hierarchy records;
- `comparison_complete` is derived from required categories and cannot be asserted by a caller while categories are absent;
- CI runs Linux Python 3.10/3.12/3.13, Linux static analysis, macOS/Windows tests and CLI smoke, plus a real Windows bridge build;
- external-job cancellation is terminal across Freerouting, ngspice, and openEMS.

### Known trust-coverage gap

The capability report currently does **not** claim `all_write_paths_invalidate_trust=true`. The explicitly listed untested paths are:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

Closing this list is Priority A work. Documentation must not summarize the trust model as if every possible write path has already been proven equivalent.

## Human-Guided Pattern Recommendation

The existing baseline can inspect/validate libraries and assign an existing compatible pattern. Pattern Editor bridge sessions remain read-only.

| Milestone | Status | Deliverable | Exit criterion |
| --- | --- | --- | --- |
| P0 | complete | Pattern/Component Library read/validation, exact pin-to-pad checks, existing-pattern assignment, read-only Pattern Editor bridge | Existing patterns can be inspected and selected without writer claims |
| P1 | planned after compatibility closure | typed append-only feedback: `record_pattern_example`, `accept_pattern_suggestion`, `reject_pattern_suggestion` | immutable decision records with document/library SHA, provenance, rationale, candidates, train/test split |
| P2 | planned | deterministic feature extraction and retrieval | exact constraints remove invalid candidates; top-1/top-3 metrics run on held-out data |
| P3 | planned | ranked suggestion workflow integrated with capabilities | agent explains ranked existing patterns and never mutates a library implicitly |
| P4 | planned | controlled human correction capture | before/after XML and optional screenshots are linked; XML + manifest remain authoritative |
| P5 | blocked by real writer evidence | native Pattern/Component Library writers | every writer passes controlled DipTrace 5.3 import and open/save/re-export equivalence |
| P6 | deferred | optional fine-tuning/export pipeline | considered only after retrieval baseline, held-out metrics, privacy controls, and dataset quality are established |

The feedback dataset should be append-only and local by default. User projects, datasheets, screenshots, and library XML must never be committed automatically. Each record should preserve reproducible normalized package features, source hashes, chosen pattern, rejected alternatives, rationale, provenance, and validation outcome.

Deterministic retrieval should begin with hard filters such as pad count/type, pitch, package/body dimensions, mounting holes, thermal-pad requirements, and side constraints, followed by normalized geometry-distance ranking. Baseline metrics are top-1 accuracy, top-3 accuracy, invalid-pattern rejection precision, and manual-correction rate.

## Remaining Evidence-Gated Work

### 1. Redistributable DipTrace 5.3 Fixture Pack — highest priority

Add a small non-proprietary fixture pack exported by the current DipTrace 5.3 branch. Keep files byte-for-byte as exported; do not hand-normalize them before commit.

Target layout:

```text
tests/fixtures/diptrace_5_3/
  manifest.json
  hierarchy/schematic.xml
  pours/before_refill.xml
  pours/after_refill.xml
  libraries/components.xml
  libraries/patterns.xml
  schematic_roundtrip/<case>/before.xml
  schematic_roundtrip/<case>/after.xml
  pcb_roundtrip/<case>/before.xml
  pcb_roundtrip/<case>/after.xml
  specctra/source_board.xml
  specctra/input.dsn
  specctra/output.ses
```

Required coverage:

- hierarchical multi-sheet schematic with hierarchy connectors and a global net;
- controlled schematic writer pairs for placement, wire/connectivity, net label, property/value, and attached pattern;
- controlled PCB writer pairs for representative component/property/rule/trace/via operations;
- copper-pour before/after refill, including cutout/island or thermal behavior where possible;
- Component Library with simple and multi-part components, custom fields, attached patterns;
- Pattern Library with SMD/THT pads, non-trivial graphics, pin-to-pad mapping, courtyard, and mask/paste evidence;
- real DSN/SES pair produced from the same board with at least one routed trace and multilayer/via case;
- authored schematic wire and generated ratline open/save/re-export acceptance.

`manifest.json` must record exact DipTrace version/build, OS, export workflow, source type, units, SHA-256 for every file, intended before/after difference, and redistribution permission.

This item is complete when all four native source types parse, fixture-specific assertions pass, guarded SES import is exercised, writer cases survive DipTrace open/save/re-export, and CI can run the pack without DipTrace installed.

### 2. Mask, Paste, Courtyard, and `Common` Verification

Capture focused 5.3 pattern-library and placed-PCB exports covering:

- top/bottom mask and paste;
- `Common`, explicit zero, positive expansion, negative reduction;
- SMD and through-hole pads;
- custom mask/paste shapes;
- top/bottom courtyard lines, arcs, and polygons;
- rotated, bottom-side, and mirrored components.

For ambiguous values, capture two exports differing by exactly one GUI setting. Machine-readable before/after XML plus manifest are authoritative; screenshots are supporting evidence only.

### 3. Evidence-Gated Library Writers

After items 1-2:

- create/update patterns;
- create/update components, parts, pins, graphics, and custom fields;
- attach patterns and maintain explicit pin-to-pad mapping;
- preserve unknown/unsupported XML structures;
- require explicit collision/replacement behavior;
- use existing SHA/preview/commit/rollback transaction boundaries.

A writer is complete only when the result imports into DipTrace 5.3 without warnings, survives open/save/re-export semantically, repeated identical operation is idempotent, and `get_capabilities` registers it truthfully.

### 4. Optional Real openEMS Acceptance

The typed openEMS runner protocol, parsing, bounded jobs, failure handling, timeout handling, and synthetic CI backend are implemented. Remaining evidence is a captured real solver result and one configured integration run. Absence of the solver must continue to produce explicit unavailability rather than fallback/fabricated output.

## Existing 5.3 Evidence

A live DipTrace 5.3.0.2 schematic acceptance test has already verified source-SHA protection, backup equality, atomic write, 41 scoped `RefDesMarking` edits, bridge apply, independent DipTrace re-export, coordinate persistence, stable normalized object counts, and no new offline ERC errors.

Representative installed 5.3 PCB and multi-sheet schematic examples have also parsed without warnings, as have small Component/Pattern Library exports through read-only bridge profiles. Those local exports were not retained as redistributable fixtures, so they improve confidence but do not close CI evidence gates.

A synthetic four-layer `power_multilayer` pre-fixture exists for parser/operation regression. It must not be treated as proof of DipTrace 5.3 compatibility until the corresponding native-import/re-export artifacts are captured.

## Closure Definition

The near-term roadmap closes in this order:

1. eliminate the explicit write-path trust-invalidation gaps;
2. commit the redistributable DipTrace 5.3 fixture pack;
3. verify mask/paste/courtyard/`Common`, authored wires, ratlines, and real DSN/SES paths;
4. implement and round-trip native library writers;
5. implement P1-P3 pattern feedback/retrieval/recommendation and evaluate held-out metrics;
6. add P4 correction capture;
7. consider P6 fine-tuning only if deterministic retrieval has measurable limitations;
8. capture optional real-openEMS acceptance evidence.

Phase 12 remains partial until evidence-gated library writers exist. Phase 21 remains planned until the feedback/retrieval/recommendation workflow is implemented and measured.

Completion does not mean full DipTrace GUI equivalence. Full push-and-shove/global autorouting, GUI automation, native manufacturing generation without a verified DipTrace API, and always-on online sourcing remain explicit product boundaries rather than unfinished core milestones.
