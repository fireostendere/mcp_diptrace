# Testing

## Gates

```bash
pytest -q
ruff check src tests benchmarks
mypy --no-incremental src/diptrace_mcp
python benchmarks/benchmark_core.py --repeat 5 --patch-count 1000
```

CI runs pytest, Ruff, and strict Mypy on Linux with Python 3.10, 3.12, and 3.13, and on
Windows and macOS with Python 3.12. Core tests do not require DipTrace, Java,
Freerouting, or network access.

## Coverage

- secure parsing, units, stable IDs, transforms/mirroring/arcs/bounding boxes/spatial index;
- normalized PCB, schematic, Component Library, and Pattern Library models;
- preservation of unknown XML and semantic round-trips;
- byte-exact preservation of BOM, XML declaration, CRLF, empty tags, and unknown sections
  outside low-level and semantic patch targets;
- transaction state, SHA, preview, commit, rollback, and policy;
- component, text, rule, test-point, pattern, and group operations;
- review registry and findings, silkscreen plans, and placement plans;
- trace/via compiler, multi-layer 45-degree A*, explicit blind/full via spans, rejection
  of unknown four-layer spans, and coupled-pair plus symmetric-via round-trips;
- unknown format-version feature detection and preservation of optional or unknown XML;
- exact GEOS DRC for rotated pads, DSN/SES, and mocked Freerouting jobs;
- stackup, length/skew/differential-pair analysis, and single/coupled impedance golden cases;
- return path and pour boundaries, BOM, and schematic/PCB comparison;
- generic exports, CSV-injection protection, and MCP tool/resource/prompt contracts.

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
- solver-backed SI/PI golden data.

A live acceptance test with DipTrace 5.3 separately verifies the source SHA guard, 41
bounded schematic-marking patches, backup equality, atomic write, bridge apply, and an
independent DipTrace re-export. All 41 coordinates survived the application round-trip;
normalized design counts and offline ERC severity counts remained unchanged. The
rebuilt Windows bridge also passes an isolated cross-process headless finish-request
test that verifies metadata/control publication, cleanup, and exchange-file integrity.

User projects are not added to repository fixtures without explicit permission. A
permitted 5.3 fixture is still required to automate this acceptance path in CI.
