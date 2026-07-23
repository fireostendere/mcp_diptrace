# External Adapters and Dependencies

## Freerouting

The adapter is enabled only through `DIPTRACE_MCP_FREEROUTING`. The JAR requires either
a discovered Java runtime or an explicit `DIPTRACE_MCP_JAVA` path. The capability probe
checks the file and execution mode. Jobs use a fixed argument vector, `shell=false`, a
sanitized environment, an isolated job directory, a timeout, cancellation, and bounded
logs. Cancellation is terminal: a process that exits because `terminate()` raced with
the worker loop cannot overwrite `cancelled` with `failed`. DSN and SES artifacts are
tied to the source SHA.

## Solver Adapters

The ngspice adapter is implemented for user-supplied netlists. It is enabled through
`DIPTRACE_MCP_NGSPICE` or an `ngspice` executable on `PATH`, and runs batch mode
(`ngspice -b input.cir`) with a fixed argument vector, `shell=false`, a sanitized
environment, an isolated job directory, a timeout, cancellation, bounded logs, and a
typed log summary (data-row counts and error lines). The adapter never generates
netlists from a design and never fabricates simulation results: an unavailable
executable ends in `external_tool_unavailable`.

The same terminal-cancellation rule applies to ngspice and openEMS jobs.

The openEMS stripline adapter is implemented through a fixed typed runner protocol and is
enabled only through `DIPTRACE_MCP_OPENEMS_RUNNER`. It supports centered and off-center
geometry, frequency sweeps, complex characteristic impedance, propagation data, optional
loss separation, mesh/convergence metadata, and solver provenance. The runner is invoked
only with `--input` and `--output` paths inside the isolated job directory. Results are
strictly parsed and must match the requested frequency vector. See
[Field-Solver Runner Protocol](FIELD_SOLVER_PROTOCOL.md).

The repository does not bundle openEMS or claim that the synthetic parser fixture is a
solver result. Runtime availability requires a compatible openEMS-backed runner, and the
remaining real-solver acceptance run is reported separately from adapter implementation.
LTspice, FastHenry, and a generic user CLI are not registered. The core does not execute
arbitrary commands and does not return fake simulation results.

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
| openEMS | GPL-3.0-or-later | platform packages | External runtime through the typed runner protocol; not bundled |

The `geometry` extra contains Shapely 2.x. Its Windows wheels include GEOS and NumPy and
support Python 3.10 and later. Query results are sorted by stable ID for deterministic
behavior. The `preview`, `routing`, and `simulation` extras are currently empty and do
not conceal runtime dependencies. The `bridge` extra contains PyInstaller; `dev`
contains pytest, Ruff, Mypy, and Hypothesis.
