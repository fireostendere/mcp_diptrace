# Testing

The test strategy intentionally separates implementation correctness from real-DipTrace compatibility evidence. A green unit/CI matrix proves the maintained contracts and fixtures; it does not automatically promote every writer to DipTrace 5.3 round-trip verified status.

## Gates

```bash
python scripts/generate_pcb_skills.py --check
pytest -q
ruff check --no-cache src tests benchmarks scripts
mypy --no-incremental src/diptrace_mcp
pytest -q --cov=src/diptrace_mcp --cov-report=term \
  --cov-report=json:coverage.json --cov-fail-under=84
python scripts/check_coverage.py coverage.json
python benchmarks/benchmark_core.py --repeat 5 --patch-count 1000
python -m benchmarks.benchmark_large_board --components 500
```

CI responsibilities:

- full pytest on Linux with Python 3.10 and 3.13 using the core dependency set;
- full pytest on Linux/Python 3.12 with `.[dev,geometry]`, an executable GEOS
  probe, total coverage, and per-file coverage gates;
- a separately named Linux/Python 3.12 job that removes Shapely, verifies it is
  absent, executes the real pure-Python geometry probe, and runs the
  fallback-focused regression files;
- Ruff, strict Mypy, and generated-skill checks on Linux/Python 3.12;
- full pytest plus CLI smoke tests on macOS/Python 3.12;
- full pytest plus CLI smoke tests on Windows/Python 3.12;
- native Windows build and non-empty verification of `diptrace_mcp_bridge.exe`.

Core CI does not require DipTrace, Java/Freerouting, ngspice, openEMS, or network access.

## Coverage

The canonical coverage command is the full Python 3.12 suite with the optional
geometry backend installed:

```bash
python -m pip install -e ".[dev,geometry]"
python -m pytest -q \
  --cov=src/diptrace_mcp \
  --cov-report=term \
  --cov-report=json:coverage.json \
  --cov-fail-under=84
python scripts/check_coverage.py coverage.json
```

The baseline was measured at commit `f0d7fb1` on Python 3.12 with Shapely
2.1.2. These are coverage.py statement measurements, not hand-estimated
percentages:

| Target | Statements | Missed | Measured | Enforced integer floor |
| --- | ---: | ---: | ---: | ---: |
| Total `src/diptrace_mcp` | 15,273 | 2,443 | 84.0045% | 84% |
| `xml_document.py` | 810 | 98 | 87.9012% | 87% |
| `semantic_compiler.py` | 1,389 | 160 | 88.4809% | 88% |
| `routing_compiler.py` | 561 | 81 | 85.5615% | 85% |

The integer floors are the highest whole percentages the measured checkout
passes. The JSON gate prints the current statement/miss counts on every run and
fails if a required file disappears. Source growth can change those counts;
raising the floors requires a fresh full-suite measurement. The final project
goal of at least 88% total coverage is not yet met.

The maintained suite covers:

- secure XML parsing, units, stable IDs, transforms, mirroring, arcs, bounding boxes, and spatial indexing;
- a generated synthetic adversarial XML corpus plus Hypothesis properties for
  typed DTD/entity/encoding refusal, deep-tree edit safety, XML 1.0 character
  rejection, and byte-exact raw-patch locality;
- normalized PCB, schematic, Component Library, and Pattern Library models;
- preservation of unknown XML and raw bytes outside targeted semantic/raw patch regions;
- byte-exact BOM/XML declaration/CRLF/empty-tag preservation where required;
- transaction state, SHA preview/commit/rollback, policy, backups, and atomic writes;
- fail-closed authority tests for self-minted manifests, path/hardlink/symlink aliases, source-type/SHA binding, incomplete semantic comparisons, and rollback with corrupt evidence;
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
- generated PCB skill packages, strict schemas/examples, dependency contracts, write-order guards, and false-success rejection.

## MCP Protocol Coverage

The test suite establishes an in-memory MCP client/server session and verifies that representative tools, resources, and prompts are actually registered and callable rather than only documented. This includes read/query, transactions, placement, routing, differential-pair, export, external-job, and capability surfaces.

`get_capabilities` remains the runtime source of truth; tests must reject documentation-style false success for unavailable capabilities.

## Real DipTrace Acceptance Already Completed

A live acceptance test with DipTrace 5.3.0.2 separately verified:

- source-SHA conflict protection;
- backup equality;
- atomic write behavior;
- 41 bounded schematic `RefDesMarking` edits on the Power sheet;
- bridge apply followed by an independent DipTrace re-export;
- persistence of all 41 coordinates;
- unchanged normalized sheet/part/pin/net/bus/differential-pair counts;
- no new offline ERC errors after the round trip.

The rebuilt Windows bridge also passes isolated cross-process finish-request tests covering metadata/control publication, cleanup, and exchange-file integrity.

This acceptance evidence is valuable but intentionally scoped. The user project used for the live test is not redistributed, so the same path is not yet automated in public CI.

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

User-controlled manifests/sidecars cannot grant high trust. Future high-trust promotion requires an authenticated server-owned registry, signature verifier, or committed allowlist in addition to exact version and semantic evidence.

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
