# Testing

## Gates

```bash
python scripts/generate_pcb_skills.py --check
pytest -q
ruff check --no-cache src tests benchmarks scripts
mypy --no-incremental src/diptrace_mcp
python benchmarks/benchmark_core.py --repeat 5 --patch-count 1000
```

CI runs full pytest on Linux with Python 3.10, 3.12, and 3.13. Ruff, strict Mypy,
and generated-skill checks run once on Linux/Python 3.12. macOS and Windows run full
pytest plus CLI smoke tests on Python 3.12, and a separate Windows job builds and
verifies a non-empty `diptrace_mcp_bridge.exe`. Core tests do not require DipTrace,
Java, Freerouting, openEMS, or network access.

## Coverage

- secure parsing, units, stable IDs, transforms/mirroring/arcs/bounding boxes/spatial index;
- normalized PCB, schematic, Component Library, and Pattern Library models;
- preservation of unknown XML and semantic round-trips;
- required-category PCB comparison of trace coordinates/order, widths, segment layers,
  endpoints, via styles/spans, locks, and differential-pair membership;
- required-category schematic comparison of sheets/hierarchy, parts, pins, pin-to-net
  connectivity, wire geometry, labels, and buses;
- byte-exact preservation of BOM, XML declaration, CRLF, empty tags, and unknown sections
  outside low-level and semantic patch targets;
- transaction state, SHA, preview, commit, rollback, and policy;
- fail-closed trust authority tests: self-minted manifests, path/hardlink/symlink roles,
  source-type/SHA binding, incomplete comparisons, and rollback with corrupt evidence;
- component, text, rule, test-point, pattern, and group operations;
- review registry and findings, silkscreen plans, and placement plans;
- trace/via compiler, multi-layer 45-degree A*, explicit blind/full via spans, rejection
  of unknown four-layer spans, and coupled-pair plus symmetric-via round-trips;
- resolve_copper_layer / require_routing_layer / require_via_layer with synthetic 4-layer
  PCB (Signal + Plane layers); plane-layer routing rejection, through-via spanning;
- pattern validation with embedded pattern library (style/name/unique-name lookup,
  pad mapping, external pattern rejection);
- unknown format-version feature detection and preservation of optional or unknown XML;
- exact GEOS DRC for rotated pads, DSN/SES, and mocked Freerouting jobs;
- external-job cancellation behavior, including a deterministic Python 3.10 regression
  for the process-exit race;
- stackup, length/skew/differential-pair analysis, and single/coupled impedance golden cases;
- typed openEMS runner protocol, synthetic result parsing, centered analytical sanity,
  malformed/non-converged output, unavailable backend, and timeout handling;
- return path and pour boundaries, BOM, and schematic/PCB comparison;
- generic exports, CSV-injection protection, and MCP tool/resource/prompt contracts.
- all 57 English PCB skill packages, strict result schemas and examples, actual MCP tool
  mappings, dependency contracts, write-order guards, and false-success rejection.

`tests/test_skill_packages.py` is the only executable skill test suite. The
`skills/*/evals/scenarios.json` and `skills/*/evals/assertions.json` files are generated
behavioral fixtures consumed by that suite. `scripts/generate_pcb_skills.py --check`
separately rejects package drift from the catalog and capability maps.

## Benchmarks

`benchmarks/benchmark_core.py` emits JSON timings for parsing/model creation, indexing,
bounding-box queries, clearance review, placement candidates, one-net routing, SVG
rendering, and semantic patches. Unit tests do not enforce timing thresholds. The
benchmark is intended for revision comparisons and large-fixture runs, not unstable CI
pass/fail decisions based on wall-clock time.

## Remaining Fixture Gaps

- a redistributable real-world hierarchical multi-sheet schematic;
- a dense multilayer PCB with exact mask, paste, courtyard, and refill polygons;
- multiple native XML versions and real DSN/SES pairs;
- an optional real Freerouting test matrix;
- a captured real-openEMS SI golden result (the committed protocol fixture is explicitly
  synthetic).

A live acceptance test with DipTrace 5.3 separately verifies the source SHA guard, 41
bounded schematic-marking patches, backup equality, atomic write, bridge apply, and an
independent DipTrace re-export. All 41 coordinates survived the application round-trip;
normalized design counts and offline ERC severity counts remained unchanged. The
rebuilt Windows bridge also passes an isolated cross-process headless finish-request
test that verifies metadata/control publication, cleanup, and exchange-file integrity.

User projects are not added to repository fixtures without explicit permission. A
permitted 5.3 fixture is still required to automate this acceptance path in CI.

## Fixture Trust Model

Test fixtures are classified by `validation_level`:

- `synthetic_parser_only` — MCP-generated XML, tested only by the MCP parser.
- `synthetic_operation_fixture` — MCP-generated XML, tested by parser + operations.
- `diptrace_exported` — XML exported by DipTrace.
- `diptrace_open_save_verified` — XML that DipTrace opened and saved.
- `diptrace_roundtrip_verified` — XML that DipTrace opened, saved, and re-exported.
- `external_tool_roundtrip_verified` — Same plus external tool round-trip.

User-controlled manifests and sidecars cannot grant `diptrace_roundtrip_verified` or
higher at all. CI rejects self-minted high trust, missing required comparison categories,
path/source-type/SHA mismatches, and semantic differences. Future high-trust promotion
requires an authenticated server-owned registry, signature verifier, or committed
allowlist in addition to exact DipTrace version and round-trip evidence.

The `power_multilayer` fixture is classified as `synthetic_operation_fixture` and must
not be used as evidence of DipTrace 5.3 compatibility.
