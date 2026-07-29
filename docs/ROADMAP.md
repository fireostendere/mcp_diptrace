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
  server-owned configuration and caller design/source paths kept behind allowed-root
  enforcement;
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
- strict generated identifiers and non-redirected roots for all six persistent stores;
- central per-target offline backup histories plus count/age cleanup of validated
  terminal records and expired backups. Existing-target writes require that
  retention-managed backup writer; the former unmanaged destination-path fallback is
  rejected before mutation. Active/nonterminal state is protected, and cleanup
  thresholds are soft targets rather than storage quotas.

For an existing target, the original bytes are captured before replacement. A
brand-new target has no previous content and therefore has no backup; an explicit
overwrite of an existing target does. Synthetic and seed-copy overwrite paths now also
require the caller-observed current target SHA; the seed's optional SHA binds a different
input and cannot authorize replacing the target.

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
5. run the committed trust-neutral ingest validator to recheck candidate/detached/artifact hashes,
   containment, fresh XML inventories, and prospective destination conflicts;
6. independently review the first package-owned registry entry and a separate candidate-to-fixture
   authorization before a redistributable candidate can become a CI fixture or change the
   structured inventory.

The ingest checkpoint is now executable in CI as
`python scripts/ingest_fixtures.py --dry-run --synthetic --json`. It is intentionally
non-promoting: it verifies that the embedded registry exists and currently contains zero approved
entries, `--apply` is refused because fixture mutation is not implemented, the acceptance tree is
untouched, and no validation level is granted.

### Live-session recovery and final-apply checkpoint — 2026-07-29

The single-active-session state now records platform, PID namespace, PID, and a
Linux `/proc` or Windows creation-time process token. A provably dead
same-namespace bridge is terminally abandoned
immediately; cross Windows/WSL namespace state remains honestly `unknown` and uses a
two-hour TTL measured from the last validated session activity. Operators can use
`abandon_live_session(reason)` without copying working XML, and
`diptrace://status` exposes the bounded last transition without leaking the exchange
path. Applied, cancelled, and abandoned records share validated retention.

`finish_live_session` now returns only bounded local outcomes (`applied`, `cancelled`,
`not_acknowledged`) and explicitly states that the executable plug-in protocol supplies
no DipTrace-host import acknowledgement. Apply remains allowed only for the shipped
`ImpMode=All` PCB/Schematic profiles. The external path/original hash/current working
hash gates remain in force, and the conservative 500-object/element impact is recomputed
both before the control marker and inside the bridge before replacement, including a
valid oversized substitution after request publication.

The bridge window now shows a working-SHA-bound impact summary with normalized and
structural counts and at most 20 changed stable IDs. Cache keys come from the same stable
read as the payload; unavailable parsing and truncated IDs remain explicit. This closes
the live-session lifecycle and object-cap work, but it does not answer the separate
open DipTrace-host acknowledgement/`ImpMode=All` behavior questions or the disclosed
`live_session_apply` trust-invalidation gap.

### CI geometry and coverage checkpoint — 2026-07-28

Linux/Python 3.12 now installs `.[dev,geometry]`, proves that the GEOS backend is
active, and runs the full suite with pytest-cov. A separate explicitly no-Shapely
job removes the optional package, proves it is absent, exercises the real
pure-Python conservative geometry path, and runs the fallback-focused tests.
This prevents exact-geometry tests from being silently skipped in every CI job
while also preserving evidence for the fallback installation.

After the combined WO-14 bridge, transaction-recovery, public MCP workflow,
synthetic-load, live-session profile-safety, WO-16 registry/evidence intake,
live-apply target binding, bounded copper preview, schema-backed API inputs,
acceptance-seed audit, and cross-platform live-session lifecycle slices, the
canonical geometry-enabled suite measured 16,844 statements, 2,360 misses, and
**85.9891%** total coverage. `bridge.py` moved from an untested CI executable
path to 182 of 262 statements, or **69.4656%**, backed by a real cross-process
apply handshake plus cancel/timeout/error and request-correlation tests. CI
enforces an integer 85% total floor plus measured
per-file floors of 64% for `bridge.py`, 87% for `xml_document.py`, 88% for
`semantic_compiler.py`, and 85% for `routing_compiler.py`. The intended project
target remains at least 88% total; that target is explicitly still open and
must be reached with additional tests rather than omit rules or a weakened
denominator. The reproducible command and full measurement table are in
[TESTING.md](TESTING.md).

### WO-14 synthetic load checkpoint — 2026-07-28

CI now generates a deterministic 500-component PCB in memory instead of committing a
large XML fixture. The load test exercises the public parser, normalized model, bounded
model cache, selector query, and spatial index with explicit aggregate-time and
peak-`tracemalloc` budgets. The same reporting harness accepts 500–3,000 components for
local comparison.

This input is explicitly `synthetic_parser_only`: it proves bounded execution of MCP
code, not compatibility or performance with a real DipTrace 300+ component board.
Human-captured large-board evidence therefore remains open and keeps its distinct
provenance requirements.

### Public evidence-intake checkpoint — 2026-07-28

Two typed MCP tools now expose the user-supplied half of the evidence harness.
`validate_roundtrip_evidence` performs allowed-root, distinct-role, source-type,
exact-SHA, and current-document binding checks without writing; when a re-export is
supplied, it also performs the structural semantic comparison.
`record_roundtrip_evidence` repeats those gates and writes only the evidence manifest
and provenance sidecar. Both remain `authority=user_supplied`, report
`requires_diptrace_verification=true`, and are structurally unable to grant high trust.
Observed representation-only normalizations are disclosed in the preview and preserved
in the manifest; they never suppress a semantic difference.

The measured MCP surface moved from 156 tools / 121,335 JSON bytes to 159 tools /
128,661 bytes (approximately 32,165 tokens), a 6.0378% increase and below the Phase-2
15% discovery-budget ceiling. All 44 former `dict[str, Any]` tool parameters now use
named schema-backed object types: their exact contracts live once at
`diptrace://schemas/tool-inputs`, and each compact inline parameter carries the matching
`x-diptrace-schema` URI. The read-only/record split is transport-tested for valid
evidence, failed comparison, tampered SHA, reused roles, allowed-root refusal, bounded
responses, and preview filesystem non-mutation. This checkpoint does not provide the
client with authority over the separate package-owned registry. That registry is
implemented but currently has zero independently reviewed entries, so no current
document is promoted to high trust.

The narrower discovery-budget measurement intentionally counts only tool name,
description, and input schema. A separate Phase-9 prerequisite now freezes the
complete non-null public `Tool` model, including output schemas and any future
titles, annotations, icons, metadata, or execution fields. The committed
[snapshot](../reference/mcp-tools-list.snapshot.json) contains 159 name-sorted
tools; its canonical descriptor is 141,026 UTF-8 bytes with SHA-256
`1ba2398269ba3463b92daae6ca0ed06edbdbe6bd23607176c4a849176091fae3`.
It is produced only through the public in-memory MCP transport, and CI fails on
any unregenerated contract drift. This snapshot is the required behavioural
baseline before the service/compiler/store decomposition begins.

The first behavior-preserving Phase-9 slice is now guarded by that baseline:
`semantic_compiler.py` dispatches all 39 registered operation models through one
type-to-handler table, and a parity test fails if the operation registry and
compiler diverge. The same cleanup removed the unused service `_snapshot` helper,
the unused document reserializer, and four exception subclasses with no callers;
the canonical 159-tool snapshot remains byte-identical.

### Public MCP workflow checkpoint — 2026-07-28

CI now executes a fixture-driven in-memory MCP workflow through the public
client/server transport. The current workflow reaches **63 distinct wire tool
names**, exceeding the Phase-5 acceptance floor of 40 without enumerating all
159 registered tools. It carries discovered stable ids and generated
transaction/export/report/resource ids into dependent calls, binds preview
operations to the fixture SHA, verifies bounded metadata/resources, and proves
that raw and semantic previews do not change the source document.

The workflow uses temporary copies of committed synthetic fixtures. It does not
touch the acceptance fixture tree, promote fixture provenance, start a live
bridge, invoke an external executable, or introduce impedance/fabrication
thresholds. The measured scope and remaining evidence boundary are documented
in [TESTING.md](TESTING.md).

### Live-session concurrency checkpoint — 2026-07-28

Session creation, edits, transaction commit/rollback, finish requests, and finalization
now share an atomic state-root lease directory across threads, processes, Windows, and
WSL. Concurrent creators produce exactly one active
session; concurrent finalizers produce one terminal transition; and a
request/finalize race leaves canonical JSON state with no stale active or control
marker. The lease has a nonce and exact process identity; unknown cross-namespace
owners are never expired or force-reclaimed because doing so cannot fence the old
writer. `abandon_live_session(reason)` therefore returns a typed lock timeout while
such an owner remains. Spawned-process and thread-barrier regressions exercise the maintained
behavior without starting DipTrace; a Windows/WSL NTFS probe also established that
native `flock` and Windows byte locks are not interoperable. The exact manual-only
procedure, path-free output contract, host observation, and CI boundary are recorded in
[WINDOWS_WSL_LOCK_INTEROP.md](WINDOWS_WSL_LOCK_INTEROP.md).

### WO-16 acceptance-seed consumer checkpoint — 2026-07-28

CI now runs a bounded, read-only audit of the protected acceptance-seed
directory. Its current explicit result is `status: "no_seeds"` with
`seed_count: 0`; this is reported as an honest absence of evidence, not silently
skipped. A future v2 fixture manifest is checked against the committed schema,
the existing `FixtureManifest` provenance invariants, exact fixture hashes,
canonical in-root paths, and actual DipTrace XML or Specctra source types.

The consumer cannot write, register a fixture, alter the authority registry, or
promote trust. It consults the embedded registry for its actual entry count but
does not infer a match from seed metadata; it reports `trust_promoted: false`
and `registry_match: false`. A tested literal
synthetic stand-in procedure lives in
[ACCEPTANCE_SEED_AUDIT.md](ACCEPTANCE_SEED_AUDIT.md), executes only in an OS
temporary directory, and is explicitly not DipTrace evidence. Real exports and
the independent reviewed authority decision remain human-gated.

### WO-17 skill consolidation checkpoint — 2026-07-29

The former 57-package, approximately 4.4 MiB duplicated skill catalog is replaced
by eight distinct source-authored workflows selected through a committed mechanical
survival rule. Package-local `agents/`, `evals/`, examples, and 57 near-identical
result schemas are gone. The survivors cover project intake, library audit, schematic
ERC, testpoint planning, critical-net routing, SI review, release gating, and
operator-assisted evidence capture through one shared evidence-typed result schema.

Skills are now actual wheel package data under `diptrace_mcp/skills`; a measured
no-dependency wheel is 382,106 bytes, and its 175,348-byte skill payload is below the
400 KiB skill-delivery ceiling. CI resolves
every advertised capability against the registered MCP surface, checks source and
installed-wheel links, rejects the former external-solver contradiction, verifies
byte-identical packaged evidence CLIs and their generated hash manifest, and executes
the trust-neutral synthetic ingest forward path outside the acceptance fixture tree.

The evidence skill keeps the candidate -> dry-run ingest -> exact-SHA MCP validation
-> explicit operator confirmation -> metadata-record sequence. It cannot grant trusted
authority or modify acceptance fixtures. The SI skill distinguishes analytical
single-ended microstrip, coupled differential microstrip, and single-ended symmetric
stripline from unavailable differential stripline and separately configured ngspice/
openEMS adapters.

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
| 2 | complete v2 | millimeter-normalized geometry, transforms/mirroring/arcs, spatial index, and bounded SVG/JSON preview with trace centerlines and explicitly boundary-only copper pours |
| 3 | complete v1 | semantic compiler, persistent transactions, policy, SHA/preview/commit/rollback |
| 4 | complete v1 | component/part/text/rule/test-point edits, pattern swap, groups, library read/validate |
| 5 | partial v1 | persistent registry findings and skips for a bounded DRC/ERC subset; the review coverage matrix records missing and approximate categories |
| 6 | complete v1 | deterministic silkscreen candidates, plans, previews, and apply |
| 7 | complete v1 | bounded local placement candidates, scoring, legalization, and apply |
| 8 | complete v2 | trace/via primitives, bounded multi-layer 45-degree A*, and symmetric vias |
| 9 | complete v1 | bounded DSN export, Freerouting job, SES inspect/import, and post-review |
| 10 | complete v3 | coupled-pair routing, lengths/skew, microstrip and IPC-2141 symmetric stripline impedance |
| 11 | partial v1 | return-path/plane heuristics, BOM/design comparison, and bounded DFM/DFA/DFT/thermal metadata checks with explicit skips |
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

- The local router supports bounded vias and multi-layer routing with orthogonal/45-degree
  segments and indexed obstacle candidates. Single-net routes add clearance-checked
  orthogonal access from physical off-grid pad anchors to the fixed search grid;
  coupled differential-pair center anchors remain on-grid.
- `route_connections` provides congestion-aware ordering and bounded batch-local rip-up/retry.
- It is not push-and-shove, free-angle, dynamic neck-down, or a global autorouter.
- The DSN serializer rejects unsupported geometry rather than silently dropping data.
- SES import always passes internal inspection, preview, and review before commit.
- Differential-pair synthesis writes both traces and the pair `Segment` atomically.
- Analytical impedance is preliminary: Hammerstad-Jensen single/coupled microstrip and IPC-2141 centered symmetric stripline.
- Frequency-dependent/off-center stripline analysis requires the optional external openEMS runner.

## Review and Manufacturing Limits

- The representative [review coverage matrix](REVIEW_ENGINE.md) is the authoritative
  summary of implemented, partial, and missing offline checks. A zero-finding report is
  incomplete unless its skips and uncovered categories were also reviewed.
- Copper-pour handling now applies layer-aware, same-net-exempt boundary obstacles to
  trace clearance review and local A*. Findings and route results disclose
  `pour_geometry: "boundary_only"`; authoritative DipTrace 5.3 refill geometry remains
  human-gated by `OPEN_QUESTIONS.md` Q10.
- Return-path analysis is a geometry heuristic with confidence reporting, not full-wave SI.
- Generic fabrication manifests are not Gerber/NC Drill/ODB++/IPC-2581 packages.
- Generic placement CSV must be mapped to the selected assembler's coordinate convention.
- The ngspice adapter runs user-supplied netlists; it does not generate a netlist from a DipTrace design.
- Online component sourcing is disabled by default.

## Project Creation and Synchronization Limits

- `create_schematic_document` and `create_pcb_document` generate **synthetic** XML using the existing 4.3-era scaffold structure. Their `format_version` parameter changes only the literal root and embedded-library `Version` attributes; it is not a format conversion or compatibility assertion. Generated documents remain `synthetic_parser_only` until independent DipTrace evidence exists.
- `create_document_from_seed` copies a real DipTrace-exported XML seed and preserves unknown XML and provenance, but does not auto-upgrade round-trip trust.
- Creation of an absent target needs no target SHA. Replacing existing design/source XML
  requires `overwrite=true` and its current `expected_sha256`; seed copies keep the
  independent `expected_seed_sha256` check for their source bytes.
- `place_part` references a library `ComponentStyle`; DipTrace resolves symbol graphics and pin mapping from configured libraries during import.
- Schematic wires use the official `Wire`/`Points` structure, while logical pin-to-net connectivity is maintained separately through `connect_pins`/`disconnect_pins`.
- Panelization writes official `Panel` parameters; tab coordinates are recomputed by DipTrace and MCP does not expand final panel geometry.
- Exact schematic-to-PCB reconciliation is opt-in, refuses locked objects by default, and removes traces only when a synchronized net's endpoint set changes.
- Multi-net rip-up/retry is limited to traces produced within the current routing batch.
- Semantic transactions, raw XML edits, generated documents, seed copies, and overwrites
  fail closed above a conservative sum of 500 affected normalized objects and exact XML
  elements. The views can overlap, so the gate may refuse fewer than 500 unique physical
  design objects; this avoids undercounting derived geometry changed alongside unknown XML.
  The impact is recomputed at commit. Exact conflict-checked rollback is the only implemented
  restoration exemption and still passes the active write policy; independent enforcement at
  the live external apply handshake remains WO-15 work and is disclosed by `get_capabilities`.

## Trust, Semantic Comparison, and CI Baseline

The following baseline must not be weakened by later feature work:

- runtime state, user-supplied evidence, fixture labels, and trusted authority are separate concepts;
- user-controlled JSON, sidecars, hashes, and fixture manifests cannot mint `diptrace_roundtrip_verified` or `external_tool_roundtrip_verified`;
- the package-owned exact-hash registry and MCP disclosure are implemented,
  but the committed registry has 0 reviewed entries; the first entry remains
  human-gated by the independent review procedure in
  [TRUSTED_PROVENANCE_REGISTRY.md](TRUSTED_PROVENANCE_REGISTRY.md);
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
