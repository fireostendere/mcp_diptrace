# External Adapters and Dependencies

## Freerouting

The adapter is enabled only through `DIPTRACE_MCP_FREEROUTING`. The JAR requires either
a discovered Java runtime or an explicit `DIPTRACE_MCP_JAVA` path. The capability probe
checks the file and execution mode. Jobs use a fixed argument vector, `shell=false`, a
sanitized environment, an isolated job directory, a timeout, cancellation, and bounded
logs. DSN and SES artifacts are tied to the source SHA.

## Solver Adapters

ngspice, LTspice, openEMS, FastHenry, and a generic user CLI are not registered. A
production adapter must provide typed input, a fixed command contract, a capability and
version probe, a license note, isolated artifacts, timeout and cancellation support, and
a tested parser. The core does not execute arbitrary commands and does not return fake
simulation results.

## Dependency Evaluation

| Dependency | License | Windows wheels | Decision |
| --- | --- | --- | --- |
| Shapely/GEOS | BSD-3-Clause | yes | Optional `geometry` extra: exact shapes and STRtree; the core fallback remains pure Python |
| Rtree/libspatialindex | MIT/BSD | yes | Not added: the uniform-grid index is sufficient |
| Pyclipper/Clipper | MIT/BSL | yes | Candidate for polygon offsets after fixtures are available |
| NetworkX | BSD-3-Clause | pure Python | Not required for the current connectivity graph or A* implementation |
| NumPy/SciPy | BSD | yes | Not required by the core and too large for the current tasks |
| OR-Tools | Apache-2.0 | yes | Not required by the bounded local placer |
| Pillow | HPND | yes | Optional PNG output is planned; SVG is sufficient for the core |
| Hypothesis | MPL-2.0 | pure Python | Development-only property tests |
| psutil | BSD-3-Clause | yes | Not required: subprocess timeout and cancellation use the standard library |

The `geometry` extra contains Shapely 2.x. Its Windows wheels include GEOS and NumPy and
support Python 3.10 and later. Query results are sorted by stable ID for deterministic
behavior. The `preview`, `routing`, and `simulation` extras are currently empty and do
not conceal runtime dependencies. The `bridge` extra contains PyInstaller; `dev`
contains pytest, Ruff, Mypy, and Hypothesis.
