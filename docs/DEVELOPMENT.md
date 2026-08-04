# Development

## Current baseline

The current source/package version is `0.2.0`. The public MCP contract contains
159 tools. `DipTraceService` remains the stable public Facade; domain
implementations live under `src/diptrace_mcp/services/`.

The 0.2.0 Windows installer and portable bundle build in CI, but the release is
not tagged or published while the remaining human acceptance gates are open.

## Repository structure

```text
src/diptrace_mcp/
  server.py             FastMCP registration, transports, errors, offload boundary
  service.py            public Facade, dependency assembly, safety callbacks
  services/
    context.py          typed shared context and single DocumentGateway
    documents.py        document/query/read models
    bom.py              BOM and component/library metadata reads
    review.py           reviews, findings, and read-only analysis
    discovery.py        document discovery
    exports.py          bounded exports
    jobs.py             job records and resources
    external_jobs.py    external adapters and guarded jobs
    routing.py          routing analysis and plans
    placement.py        placement/silkscreen plans
    semantic_operations.py explicit semantic wrappers
    semantic_engine.py  guarded semantic execution and preview
    synchronization.py  schematic-to-PCB synchronisation
    xml_writes.py       guarded raw XML edits
    scaffolding.py      synthetic and seed-based document creation
    transactions.py     transaction workflows and recovery
    evidence.py         provenance and fail-closed trust
    live_sessions.py    live-session lifecycle
  adapters.py           XML-to-domain adapters
  bridge.py             Windows bridge process and GUI
  capabilities.py       runtime capability payloads
  config.py             environment, paths, and retention settings
  domain.py             normalised models and records
  error_boundary.py     public MCP error envelope
  external_process.py   bounded external-process runner
  geometry.py           geometry primitives
  inspector.py          read/inspection helpers
  model_cache.py        bounded normalised snapshot cache
  operations.py         typed semantic operations
  policy.py             policy profiles
  preview.py            deterministic SVG/JSON previews
  record_store.py       shared safe persistence seam
  sessions.py           live-session state
  transactions.py       transaction store and artifacts
  xml_document.py       secure XML parsing and guarded writes
plugin/
  bridge_entry.py       PyInstaller bridge entry point
  settings/             PCB/Schematic/Component/Pattern profiles
  build_bridge.ps1      bridge build
  install_plugin.ps1    advanced plug-in installation
packaging/
  diptrace_mcp_server.spec
  diptrace_mcp_configure.spec
  windows-constraints.txt
installer/
  DipTraceMCP.iss       Inno Setup installer/uninstaller
scripts/
  build_windows_server.ps1
  build_windows_configurator.ps1
  build_windows_installer.ps1
  audit_release_artifacts.py
  audit_windows_bundle.py
  check_service_facade_contract.py
  validate_service_decomposition.py
skills/
  catalog.json
  capability-map.json
  shared/result.schema.json
  */SKILL.md
tests/
  fixtures/
  test_*.py
```

The Python wheel contains the MCP server and packaged skills. Windows bridge,
settings, standalone server, configurator, installer, and portable assets are
separate build outputs.

## Environment

Linux/macOS/WSL:

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

Install `.[dev,geometry]` when running the exact Shapely/GEOS path.

## Core checks

Run from the repository root:

```bash
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/generate_pcb_skills.py --check
python scripts/generate_mcp_tools_snapshot.py --check
python scripts/check_service_facade_contract.py --check
python scripts/validate_service_decomposition.py --check
python scripts/audit_event_loop.py --json
python scripts/generate_coverage_badge.py --check
python scripts/extract_spec_inventory.py \
  --sources tests/fixtures \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
python scripts/report_format_coverage.py --check
python scripts/make_probe_pack.py --check
python scripts/ingest_fixtures.py --dry-run --synthetic --json
python scripts/audit_acceptance_seeds.py
```

Build and audit Python release archives:

```bash
rm -rf release-dist
python -m hatchling build -d release-dist
python scripts/audit_release_artifacts.py \
  --dist-dir release-dist \
  --check-allowlist
```

The committed release allowlist must contain every publication-safe tracked
file and no private, redirected, oversized, special, or unexpected archive
member.

## Public contract checks

The MCP snapshot is generated through the public in-memory transport:

```bash
python scripts/generate_mcp_tools_snapshot.py --check
```

Current expected values:

- 159 tools;
- 142,746 canonical UTF-8 bytes;
- SHA-256 `073f53681306fd13c5f3f29d61baed9a83fc9eb5c1ed14883846005a39d812db`.

The service-Facade checks are:

```bash
python scripts/check_service_facade_contract.py --check
python scripts/validate_service_decomposition.py --check
```

They currently cover 157 public signatures, 148 explicit delegations, all 195
Facade methods, and the persistent-write classification used by the
service-decomposition inventory.

## Local server

```bash
DIPTRACE_MCP_WORKSPACE="$PWD/tests/fixtures" diptrace-mcp
```

Streamable HTTP is intended for loopback development only:

```bash
diptrace-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

To run the standalone smoke helper:

```bash
python scripts/mcp_smoke.py
python scripts/mcp_smoke.py --transport stdio
```

## Bridge testing without DipTrace

Copy a fixture to a temporary allowed root and start the bridge in headless
mode:

```bash
cp tests/fixtures/pcb.xml /tmp/plugin_exchange.xml
DIPTRACE_MCP_WORKSPACE=/tmp \
DIPTRACE_MCP_STATE_DIR=/tmp/diptrace-state \
python -m diptrace_mcp.bridge \
  --headless \
  --timeout 30 \
  /tmp/plugin_exchange.xml
```

In another process, use the MCP server or the session store to request `apply`
or `cancel`.

CI also runs:

```bash
python scripts/smoke_bridge_headless.py
```

Headless bridge exit codes:

- `0`: requested apply/cancel finalised;
- `2`: timeout elapsed and the session was cancelled, or argparse rejected the
  command before a session existed;
- `1`: post-argument startup, configuration, XML, session, or control failure.

A headless pass proves the project-owned bridge protocol, not DipTrace host
import behaviour.

## Windows bundle build

These commands require Windows and the pinned build prerequisites:

```powershell
.\scripts\build_windows_server.ps1 -PythonCommand python -Clean
.\plugin\build_bridge.ps1 -PythonCommand python -Clean
.\scripts\build_windows_configurator.ps1 -PythonCommand python -Clean
.\scripts\build_windows_installer.ps1 `
  -Version 0.2.0 `
  -IsccPath "$env:ISCC_PATH"
```

Audit extracted portable output and the generated checksum file:

```powershell
python scripts\audit_windows_bundle.py `
  --root <extracted-portable> `
  --sha256 <SHA256SUMS.txt>

python scripts\frozen_server_smoke.py `
  --server <server.exe> `
  --workspace <workspace>
```

The Windows workflow also covers bridge/server/configurator smoke, installer and
portable creation, silent install/repair/uninstall, Unicode and spaced paths,
client-configuration backup and atomic update, workspace preservation, optional
owned-state removal, checksums, provenance, and unsigned-status verification.

Linux/WSL cannot replace exact native Windows workflow evidence for these
artifacts.

## Service-layer rules

Before modifying service boundaries, read
[`SERVICE_DECOMPOSITION.md`](SERVICE_DECOMPOSITION.md).

Required rules:

- keep `DipTraceService` as the explicit stable public Facade;
- pass narrow typed dependencies or callbacks;
- do not pass the complete Facade into a domain service;
- do not create duplicate stores, caches, session managers, transaction stores,
  policies, or document loaders;
- keep domain methods synchronous;
- preserve the single server-owned AnyIO offload boundary;
- preserve SHA, policy, backup, atomic-write, trust, transaction, plan,
  external-process, and live-session gates;
- update the Facade manifest and negative parity tests when a public contract
  intentionally changes.

## Adding or changing a tool

1. Implement or reuse a typed domain model/function.
2. Expose the operation through an explicit Facade method when it belongs to the
   stable public API.
3. Register a thin server wrapper.
4. Add focused unit tests and a public transport test where appropriate.
5. Update capability discovery and error/safety behaviour.
6. Regenerate the complete MCP snapshot.
7. Update the relevant docs and skill contract.
8. Keep real DipTrace verification claims separate from fixture-tested
   implementation claims.

## Fixtures and evidence

Ordinary tests use project-owned synthetic or sanitised XML fixtures and do not
require DipTrace to be installed.

Do not commit user projects, proprietary libraries, external PDFs, screenshots,
or local evidence automatically. Controlled evidence requires exact hashes,
role separation, source type, version/build metadata, provenance, and explicit
redistribution status.

The package-owned trust registry is separate from user-supplied evidence. Local
manifests and sidecars cannot mint high trust.

## Release work

The current 0.2.0 candidate process is documented in:

- [`RELEASE_0_2_0_CHECKLIST.md`](RELEASE_0_2_0_CHECKLIST.md);
- [`releases/v0.2.0.md`](releases/v0.2.0.md);
- [`RELEASE_PROCESS.md`](RELEASE_PROCESS.md).

Do not create or move a tag, replace published assets, or claim signed or
production-ready status from CI alone.