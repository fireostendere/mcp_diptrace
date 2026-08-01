# Testing

The test strategy intentionally separates implementation correctness from real-DipTrace compatibility evidence. A green unit/CI matrix proves the maintained contracts and fixtures; it does not automatically promote every writer to real-DipTrace round-trip verified status.

## Gates

```bash
python scripts/generate_pcb_skills.py --check
python scripts/audit_acceptance_seeds.py
pytest -q
ruff check --no-cache src tests benchmarks scripts plugin
mypy --no-incremental src/diptrace_mcp plugin
pytest -q --cov=src/diptrace_mcp --cov-report=term \
  --cov-report=json:coverage.json --cov-fail-under=85
python scripts/check_coverage.py coverage.json
python scripts/ingest_fixtures.py --dry-run --synthetic --json
python scripts/measure_mcp_surface.py --baseline-bytes 121335 --max-growth-percent 15
python scripts/generate_mcp_tools_snapshot.py --check
python benchmarks/benchmark_core.py --repeat 5 --patch-count 1000
python -m benchmarks.benchmark_large_board --components 500
```

CI responsibilities:

- full pytest on Linux with Python 3.10 and 3.13 using the core dependency set;
- full pytest on Linux/Python 3.12 with `.[dev,geometry]`, an executable GEOS
  probe, a real cross-process headless bridge handshake, total coverage, and
  per-file coverage gates;
- a separately named Linux/Python 3.12 job that removes Shapely, verifies it is
  absent, executes the real pure-Python geometry probe, and runs the
  fallback-focused regression files;
- Ruff and strict Mypy over the server plus hand-maintained `plugin/` Python,
  consolidated-skill manifest/wheel/link checks, an exact public `tools/list`
  snapshot check, and the read-only acceptance-seed audit on Linux/Python 3.12;
- a deterministic, temporary `ingest_fixtures.py --dry-run --synthetic` run
  that validates the candidate/hash/path and embedded-registry inspection
  pipeline without writing or granting trust;
- full pytest plus CLI and real headless bridge smoke tests on macOS/Python 3.12;
- full pytest plus CLI and real headless bridge smoke tests on Windows/Python 3.12;
- native Windows build, non-empty verification, and a `--help` smoke-run of
  `diptrace_mcp_bridge.exe`.

Core CI does not require DipTrace, Java/Freerouting, ngspice, openEMS, or network access.

The committed [public tool snapshot](../reference/mcp-tools-list.snapshot.json) is
captured through an in-memory MCP client/server transport. It contains every
non-null field of every wire-level `Tool`, sorted by tool name, plus the SHA-256
and byte length of a canonical UTF-8 descriptor array. This is the
behaviour-preservation baseline for Phase 9 decomposition. Any intended tool
name, description, input/output schema, annotation, icon, metadata, title, or
execution-contract change must regenerate the snapshot in the same commit;
`--check` reports drift and never rewrites it.

The acceptance-seed audit currently reports `status: "no_seeds"` and
`seed_count: 0`. It validates a future committed v2 manifest, provenance
invariants, exact hashes, canonical paths, and actual source types, but it
always reports `trust_promoted: false` and performs no writes. The executable
temporary stand-in procedure and the operator handoff boundary are documented
in [ACCEPTANCE_SEED_AUDIT.md](ACCEPTANCE_SEED_AUDIT.md).

## Artifact Smoke Test

The release wheel must install and serve without the development extras. Build
both artifacts, audit them, install the wheel into a clean virtual
environment, and complete a real MCP stdio handshake:

```bash
python -m hatchling build -d release-dist
python scripts/audit_release_artifacts.py --dist-dir release-dist --check-allowlist
python3.12 -m venv /tmp/diptrace-mcp-smoke
/tmp/diptrace-mcp-smoke/bin/pip install release-dist/diptrace_mcp-*-py3-none-any.whl
/tmp/diptrace-mcp-smoke/bin/diptrace-mcp --help
```

A minimal stdio client must then complete `initialize`, report the same tool
count as the committed snapshot, answer `get_capabilities`, and complete one
read-only call. Last executed for the v0.1.2 candidate on 2026-08-01 with
Linux/Python 3.12.3: clean install, `initialize=ok`, `tools/list=ok`, 159
tools, `get_capabilities=ok`, and `summarize_design=ok`.

## Coverage

The canonical coverage command is the full Python 3.12 suite with the optional
geometry backend installed:

```bash
python -m pip install -e ".[dev,geometry]"
python -m pytest -q \
  --cov=src/diptrace_mcp \
  --cov-report=term \
  --cov-report=json:coverage.json \
  --cov-fail-under=85
python scripts/check_coverage.py coverage.json
```

The fresh v0.1.2 candidate measurement was run on 2026-08-01 with Python 3.12.3,
Shapely 2.1.2, and GEOS 3.13.1. The suite completed with **991 passed and 4
skipped**. These are coverage.py statement measurements, not hand-estimated
percentages:

| Target | Statements | Missed | Measured | Enforced integer floor |
| --- | ---: | ---: | ---: | ---: |
| Total `src/diptrace_mcp` | 16,922 | 2,379 | 85.941378% | 85% |
| `bridge.py` | 264 | 83 | 68.560606% | 64% |
| `xml_document.py` | 808 | 86 | 89.356436% | 87% |
| `semantic_compiler.py` | 1,349 | 159 | 88.2135% | 88% |
| `routing_compiler.py` | 561 | 75 | 86.631016% | 85% |

The integer floors are the highest whole percentages the measured checkout
passes. The JSON gate prints the current statement/miss counts on every run and
fails if a required file disappears. Source growth can change those counts;
raising the floors requires a fresh full-suite measurement. The final project
goal of at least 88% total coverage is not yet met.

`scripts/smoke_bridge_headless.py` is not a `--help` probe. In a temporary
directory it starts the actual module in a child process, waits for the atomic
active-session publication, changes the bounded working XML, publishes an
`apply` control request with the working SHA-256, and verifies the exchange
replacement, terminal metadata, and active-state cleanup. Unit tests separately
cover cancel, timeout, malformed action, typed startup errors, and bounded error
logging without opening the GUI.

The maintained suite covers:

- secure XML parsing, units, stable IDs, transforms, mirroring, arcs, bounding boxes, and spatial indexing;
- a generated synthetic adversarial XML corpus plus Hypothesis properties for
  typed DTD/entity/encoding refusal, deep-tree edit safety, XML 1.0 character
  rejection, and byte-exact raw-patch locality;
- normalized PCB, schematic, Component Library, and Pattern Library models;
- preservation of unknown XML and raw bytes outside targeted semantic/raw patch regions;
- byte-exact BOM/XML declaration/CRLF/empty-tag preservation where required;
- transaction state, SHA preview/commit/rollback, policy, backups, and atomic writes;
- bounded transaction SVG/JSON copper previews, including positionless traces,
  boundary-only pours, before/after trace geometry, and explicit point-budget
  truncation;
- thread- and spawned-process serialization of the single-active-session invariant,
  guarded raw/transaction writes, finish requests, and finalization;
- live-session dead-PID, Linux PID-reuse, cross-namespace unknown-liveness, activity-TTL,
  manual/automatic abandonment, bounded local finish outcomes, late finalization, and
  terminal abandoned-record retention;
- Windows creation-time PID identity, dead-owner lease recovery, non-expiring unknown
  cross-namespace lease refusal, and transaction/finalize
  barrier orderings;
- a manual-only Windows/WSL NTFS lock-interoperability probe; CI tests its path-free
  report builder and parser, while the two-host topology run remains documented
  evidence rather than a simulated CI result;
- independent live-apply object-limit checks at request and bridge-finalize boundaries,
  including the exact 500 boundary, cumulative/oversized post-request substitution,
  malformed working XML refusal, and unchanged exchange bytes on every refusal;
- bridge preview summary SHA-cache races, normalized/structural counts, first-stable-ID
  bounds, and explicit unavailable/incomplete GUI text;
- fail-closed authority tests for self-minted manifests, path/hardlink/symlink aliases, source-type/SHA binding, incomplete semantic comparisons, and rollback with corrupt evidence;
- public MCP evidence-intake tests for typed schemas, read-only preview non-mutation,
  explicit metadata recording, failed observations, tampered role hashes, reused roles,
  allowed-root refusal, bounded responses, and preservation of observed normalizations;
- PCB semantic comparison of components, pads, nets, trace coordinates/order, widths, segment layers, endpoints, via styles/spans, locks, and differential-pair membership;
- schematic semantic comparison of sheets/hierarchy, parts, values/patterns, pins, pin-to-net connectivity, wire geometry, labels, and buses;
- component, text, rule, test-point, existing-pattern assignment, and group operations;
- review registry/findings, silkscreen plans, local placement plans, scoring, and legalization;
- trace/via compiler, bounded multi-layer 45-degree A*, explicit via spans, unknown-span rejection, and coupled-pair routing;
- plane-layer routing rejection and through-via spanning across plane layers;
- congestion-aware multi-net ordering and bounded batch-local rip-up/retry;
- pattern validation, embedded pattern lookup, pad mapping, and external-pattern rejection;
- unknown format-version feature detection and unknown/optional XML preservation;
- exact optional GEOS DRC for rotated pads;
- DSN/SES bounded parsing/import logic and mocked Freerouting jobs;
- external-job state, timeout, log bounds, malformed output, and terminal cancellation behavior;
- stackup, length/skew/differential-pair analysis, and analytical impedance golden cases;
- typed openEMS runner protocol, synthetic result parsing, centered analytical sanity checks, unavailable backend, malformed/non-converged output, and timeout handling;
- return-path/pour-boundary heuristics, exact and conservative-fallback pour obstacles
  for clearance/A*, BOM review, schematic/PCB comparison, and generic exports;
- CSV-injection protection;
- MCP tool/resource/prompt contracts;
- eight wheel-shipped PCB skills, one strict shared result schema, registered-capability
  parity, source and installed-wheel link resolution, byte-identical evidence CLI
  mirrors, staged operator handoff guards, a trust-neutral synthetic forward path, and
  a 400 KiB ceiling for the packaged skill payload.

## MCP Protocol Coverage

The test suite establishes in-memory MCP client/server sessions and verifies that
representative tools, resources, and prompts are actually registered and
callable rather than only documented.

`tests/test_mcp_tool_chain.py` is a fixture-driven public-transport workflow,
not a parametrized registry smoke test. Its current chain invokes **63 distinct
wire tool names** across document discovery, PCB/schematic/library reads, BOM,
exports, stable-id query/get, a bounded raw-edit preview, a SHA-bound semantic
transaction, synthetic document creation, test-point inspection, routing
inspection, differential-pair analysis, pour inspection, and stored review
findings. IDs for objects, transactions, exports, pairs, raw-diff resources, and
reports are obtained from the public response that creates or discovers them.
The chain copies committed synthetic fixtures to a temporary allowed root,
checks that both preview paths leave the source bytes unchanged, and never
starts a live bridge or external executable. Impedance targets and
manufacturing/clearance thresholds are deliberately absent: those require
published inputs or operator evidence, not values invented by a transport test.

The acceptance threshold is at least 40 successfully invoked distinct tools;
the measured count above is descriptive and may move as the workflow evolves.
The test records tool names at actual invocation time and rejects duplicate
calls, so the threshold cannot be met by calling one wire tool repeatedly.

`get_capabilities` remains the runtime source of truth; tests must reject documentation-style false success for unavailable capabilities.

## Real DipTrace Acceptance Already Completed

### DipTrace 5.3.0.2 schematic campaign

A live schematic acceptance test separately verified source-SHA conflict protection,
backup equality, atomic write behavior, 41 bounded `RefDesMarking` edits on the Power
sheet, bridge apply followed by an independent DipTrace re-export, persistence of all
41 coordinates, unchanged normalized sheet/part/pin/net/bus/differential-pair counts,
and no new offline ERC errors after the round trip.

### DipTrace 5.2.0.4 Windows bridge with WSL MCP — 2026-07-31

A second campaign verified:

- PCB apply with GUI confirmation, Save As, independent XML re-export, semantic
  comparison, and unchanged 65-net/77-component connectivity counts in the tested board;
- PCB cancel after a committed working-copy edit, with the exchange XML, GUI, and
  re-export remaining at baseline;
- PCB wrong-SHA refusal without exchange or GUI mutation;
- Schematic apply with the intended value change confirmed in the GUI;
- Schematic cancel and wrong-SHA refusal with the original exchange SHA preserved;
- Windows-native `exchange_path` plus `exchange_path_platform="windows"` in every
  session, with WSL translation performed only in memory;
- no phantom `C:\mnt\c\...` target; and
- clean bridge build/install hash checks across PCB, Schematic, Component, and Pattern
  plug-in destinations.

The campaign's final result was `ACCEPTANCE: PASS` and `RELEASE BLOCKER: NO` for the
tested matrix. The detailed evidence boundary is recorded in
[LIVE_ACCEPTANCE_2026-07-31.md](LIVE_ACCEPTANCE_2026-07-31.md).

The rebuilt Windows bridge also passes isolated cross-process finish-request tests
covering metadata/control publication, cleanup, and exchange-file integrity. The real
projects and full operator artifact directory are not redistributed, so these host
checks remain local acceptance evidence rather than public-CI fixtures or package-owned
high-trust registry entries.

## Highest-Priority Remaining Test Gaps

### 1. All-write-path trust invalidation

The capability report currently does not claim complete coverage. Explicitly listed paths still needing closure are:

- `plan_apply`;
- `ses_import`;
- `schematic_to_pcb_sync`;
- `live_session_apply`.

The exit criterion is not merely a unit test for a helper. Each write path must prove that stale higher-trust evidence cannot survive a mutation or rollback transition incorrectly.

### 2. Redistributable DipTrace 5.3 fixture pack

CI still needs controlled, redistributable real-DipTrace fixtures for:

- hierarchical multi-sheet schematic;
- representative PCB 5.3 exports and writer before/after pairs;
- Component Library and Pattern Library exports;
- authored schematic wire before/after cases;
- generated ratline before/after cases;
- copper-pour before/after refill;
- mask/paste/courtyard/`Common` one-setting-at-a-time evidence;
- real paired DSN/SES artifacts.

The fixture pack should be usable in CI without DipTrace installed and must include exact version/build, source role, SHA-256, intended semantic differences, and redistribution permission.

### 3. Native library writer acceptance

This remains blocked until the fixture/evidence items above exist. Every future Component/Pattern Library writer must prove:

- controlled before/after semantics;
- DipTrace 5.3 import without warnings;
- open/save/re-export semantic equivalence;
- preservation of unsupported/unknown XML;
- idempotence on a second identical operation;
- truthful capability registration.

### 4. External-tool real-runtime evidence

Optional remaining integration evidence includes:

- a captured real-openEMS golden result and configured run;
- a broader real Freerouting matrix where useful.

Synthetic/fake backends remain the default deterministic CI mechanism and must never be presented as real solver output.

## Fixture Trust Model

Fixtures and evidence are classified by what they actually prove:

- `synthetic_parser_only` — MCP-generated XML tested by the MCP parser;
- `synthetic_operation_fixture` — MCP-generated XML exercised by operations;
- `diptrace_exported` — XML exported by DipTrace;
- `diptrace_open_save_verified` — opened and saved by DipTrace;
- `diptrace_roundtrip_verified` — opened, saved, re-exported, and semantically compared;
- `external_tool_roundtrip_verified` — equivalent evidence including an external tool.

User-controlled manifests/sidecars cannot grant high trust. The package-owned
exact-hash registry mechanism is implemented, but its committed registry has 0
reviewed entries. The [first entry](TRUSTED_PROVENANCE_REGISTRY.md) requires
independent human review in addition to exact version and semantic evidence.

The synthetic `power_multilayer` fixture is an operation fixture, not proof of DipTrace 5.3 compatibility.

`tests/fixture_hashes.sha256` records the exact bytes of every Git-tracked runtime
fixture under `tests/fixtures/`; Markdown instructions and `.gitkeep` directory
markers are deliberately excluded. Regenerate it with
`python scripts/generate_fixture_hash_manifest.py` and verify it with `--check`.
The pytest suite runs that check automatically, so fixture or line-ending drift
cannot land without a matching manifest update.

This SHA-256 manifest proves byte integrity only. It does **not** prove that a file
came from DipTrace, raise its validation level, or replace the provenance rules
above.

The operator evidence path has a separate, read-only ingest gate:

```bash
python scripts/ingest_fixtures.py --dry-run --synthetic --json
```

CI's synthetic stand-in exists only under a temporary directory. The same command
can validate a real capture when given explicit `--capture-root`, `--candidate`,
`--destination-root`, and `--fixture-id` arguments. It rechecks manifest and
detached hashes, contained artifact paths, byte hashes, XML inventories, source
type, redistribution permission, and prospective destination conflicts. Optional
private `input_artifacts` are reopened at their original contained paths and their
hashes and sizes are rechecked, but their bytes are never added to the destination
plan.
The embedded registry is checked and currently contains zero reviewed entries.
`--apply` remains a typed refusal because fixture mutation is not implemented,
and `validation_level_granted` remains null.

## Benchmarks

`benchmarks/benchmark_core.py` reports timings for parsing/model creation, indexing, bounding-box queries, clearance review, placement candidates, one-net routing, SVG rendering, and semantic patches.

`benchmarks/benchmark_large_board.py` generates a deterministic PCB with 500–3,000
components in memory and exercises the public XML parser, normalized model builder,
byte-accounted model cache, selector query, spatial-index build, and spatial query. It
never writes or commits a large fixture. The generated XML is classified
`synthetic_parser_only`; it is not a DipTrace export and supplies no format provenance.

Pytest runs the 500-component case and requires all measured stages together to finish
within 30 seconds, with no individual stage exceeding 128 MiB of peak Python allocation
reported by `tracemalloc`. These deliberately loose load budgets catch runaway work or
memory growth on shared CI runners; they are not product latency guarantees, RSS limits,
engineering goldens, or evidence of acceptable performance on real 300+ component boards.
Use the JSON-producing command above, optionally with up to `--components 3000`, for
machine-specific regression comparison.

The original core benchmark remains reporting-only: wall-clock measurements from its
small fixture are not CI pass/fail gates. Deterministic functional correctness remains
the primary gate for both harnesses.

See [ROADMAP.md](ROADMAP.md) for the acceptance order and [XML_COMPATIBILITY.md](XML_COMPATIBILITY.md) for the compatibility matrix.
