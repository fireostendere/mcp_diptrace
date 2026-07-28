# Development

## Structure

```text
src/diptrace_mcp/
  adapters.py          XML-to-domain adapters and semantic write compiler
  capabilities.py      feature discovery payloads
  bridge.py            Windows bridge process and GUI
  config.py            environment and path policy
  domain.py            normalized models and transaction records
  geometry.py          pure geometry primitives
  inspector.py         legacy read facade over the normalized model
  connectivity.py      normalized logical/physical connectivity graph
  impedance.py         verified preliminary analytical microstrip model
  policy.py            policy-profile enforcement
  operations.py        semantic write operations
  preview.py           deterministic SVG/JSON previews
  server.py            FastMCP registration and CLI
  service.py           use cases and write workflow
  sessions.py          shared live-session state
  transactions.py      transaction store and artifacts
  external_adapters.py typed Freerouting process boundary
  exports.py           bounded generic export artifacts
  xml_document.py      secure XML parsing and guarded edits
plugin/
  bridge_entry.py       checked PyInstaller entry point
  settings/            official DipTrace plug-in settings structure
  build_bridge.ps1     PyInstaller build
  install_plugin.ps1
scripts/
  generate_pcb_skills.py  reproducible PCB skill-package generator
skills/
  catalog.json         authoritative workflow inventory
  capability-map.json  runtime aliases, limitations, and unavailable contracts
  */SKILL.md            generated English agent workflows
tests/
  fixtures/            minimal PCB and Schematic XML
  test_skill_packages.py  executable skill contract and eval-data checks
```

## Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Checks

```bash
python scripts/generate_pcb_skills.py --check
pytest -q
ruff check --no-cache src tests benchmarks scripts plugin
python -m compileall -q src tests
python scripts/mcp_smoke.py
mypy --no-incremental src/diptrace_mcp plugin
python benchmarks/benchmark_core.py --repeat 5 --patch-count 1000
```

`plugin/bridge_entry.py` is the current hand-maintained Python inventory under
`plugin/`. The directory-level Ruff and Mypy commands intentionally include any
future Python sources there. Generated PyInstaller distribution output is ignored
by Git and explicitly excluded from both static analyzers. PowerShell build and
installer scripts are outside the Python static-analysis scope.

By default, the smoke test uses a deterministic in-memory MCP transport. To verify a
separate stdio process, run:

```bash
python scripts/mcp_smoke.py --transport stdio
```

Tests do not require an installed DipTrace application and operate on XML fixtures. The
real MCP SDK and Pydantic v2 are used; shadow compatibility shims are prohibited.
Package-local files under `skills/*/evals/` are declarative test data consumed by
`tests/test_skill_packages.py`; they are not a second executable test suite.

## Local Run

```bash
DIPTRACE_MCP_WORKSPACE="$PWD/tests/fixtures" diptrace-mcp
```

Streamable HTTP:

```bash
diptrace-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

## Testing the Bridge Without DipTrace

Copy a fixture to a temporary directory and start the bridge in headless mode:

```bash
cp tests/fixtures/pcb.xml /tmp/plugin_exchange.xml
DIPTRACE_MCP_WORKSPACE=/tmp \
  DIPTRACE_MCP_STATE_DIR=/tmp/diptrace-state \
  python -m diptrace_mcp.bridge --headless --timeout 30 /tmp/plugin_exchange.xml
```

In another process, call `SessionStore.request_finish("cancel")` or start the MCP server
with the same `DIPTRACE_MCP_STATE_DIR`.

CI runs `python scripts/smoke_bridge_headless.py`, which performs the complete
cross-process `apply` handshake in a temporary directory and verifies the
replacement and cleanup. Headless exit code `0` means a requested `apply` or
`cancel` was finalized, `2` means the timeout elapsed and the bridge cancelled
the session, and `1` means a post-argument startup, configuration, XML, session,
or control-processing failure. As with other `argparse` CLIs, an invalid or
incomplete command line also exits `2` before a session exists. Fatal failures
after the exchange path has been resolved inside an allowed root are recorded
as typed JSON in `diptrace_mcp_bridge.log` beside the exchange file, capped at
64 KiB.

## SDK Versions

The project uses the stable MCP Python SDK 1.x line and pins an upper bound of `<2`.
As of July 2026, SDK 2.x is still a pre-release line with breaking changes, while 1.x is
the recommended production line. A future major-version upgrade requires a separate
review of the FastMCP API, MCP Inspector, transports, and client configuration.

## Adding a Domain-Specific Tool

1. Add a domain model or pure function to a permanent module and a use case to `service.py`.
2. Add a fixture, or extend an existing fixture with the smallest official XML fragment required.
3. Cover the pure function with a test.
4. Register a thin wrapper in `server.py`.
5. Update the tool table in `docs/USAGE.md`.
6. Update `get_capabilities`, limitations, and the relevant skill contract.

## Format Rules

- Do not invent XML element names or numeric semantics.
- Verify changes against the specifications installed with DipTrace or the official documentation page.
- Do not parse legacy binary `.dip` or `.dch` files as XML.
- Preserve exact `Id`, `UpdateId`, and cross-list references.
- Every new write operation must support preview, match guards, hash guards, and backup.
- Keep application-version compatibility separate from XML-format evidence. Prefer
  feature detection and round-trip fixtures over assumptions based solely on `Version`.
