# Development

## Current baseline

The current source/package version is `0.2.1`. The public MCP contract currently registers 165 tools (intentionally expanded from the earlier frozen 159 to productize bounded EDA intelligence engines). `DipTraceService` is the stable public Facade; typed domain implementations live under `src/diptrace_mcp/services/`.

`v0.2.1` is already published as an unsigned GitHub development prerelease and as `diptrace-mcp==0.2.1` on PyPI. Development on `main` has continued after that immutable release, so a source checkout may contain capabilities not present in the published `v0.2.1` artifacts.

## Repository structure

```text
src/diptrace_mcp/
  server.py                     FastMCP registration, transport, errors, offload
  service.py                    stable DipTraceService Facade
  services/                     typed application/domain services
  adapters.py                   XML-to-domain adapters
  domain.py                     normalized records/models
  operations.py                 typed semantic operations
  xml_document.py               secure XML parsing / guarded writes
  transactions.py               transaction store/artifacts
  sessions.py                   live-session state
  bridge.py                     Windows live XML bridge

  schematic_layout.py           intent, motifs, metrics, first placement planner
  schematic_optimizer.py        bounded placement candidate search
  schematic_wire_planner.py     non-mutating route metrics/feedback
  schematic_pin_geometry.py     conservative Design Cache pin resolution
  schematic_joint_optimizer.py  pin-aware hypothetical route scoring
  schematic_placement_repair.py bounded placement repair

  pcb_design_intent.py          PCB Generation A intent/net intelligence
  pcb_placement.py              intent-aware PCB placement v2
  pcb_physical.py               Generation B physical/PDN/return/via context
  pcb_routing_policy.py         Generation C route policy/observed-route checks
  pcb_joint_optimizer.py        Generation D candidate selector

  cinematic.py                  deterministic presentation timeline
  cinematic_cli.py              capture/compile/ffmpeg helper CLI
  cinematic_host.py             Windows visible replay host
  cinematic_recording.py        visible and hidden-window ffmpeg recording
  diptrace_ui.py                UI profiles + affine coordinate calibration
  diptrace_profile_cli.py       profile template/probe/calibrate/action/validate
  diptrace_cinematic_semantic.py semantic replay adapters
  diptrace_window.py            Windows target-window/client geometry

plugin/
  bridge_entry.py               PyInstaller bridge entry point
  settings/                     PCB/Schematic/Component/Pattern profiles
  build_bridge.ps1
  install_plugin.ps1
packaging/
installer/
scripts/
skills/
tests/
```

The Python wheel contains the Python MCP server and packaged skills. Windows bridge, standalone executable, configurator, installer, portable and MCPB assets are separate release outputs.

## Environment

Linux/macOS/WSL:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,geometry]'
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,geometry]"
```

Use `.[dev]` when intentionally testing the pure-Python no-Shapely fallback.

## Core checks

Run from the repository root:

```bash
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/sync_skill_scripts.py --check
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

The exact required CI set is `.github/workflows/ci.yml`.

## Coverage policy

The geometry-enabled Linux 3.12 job keeps an 85% Linux-only floor and runs `scripts/check_coverage.py` for selected per-file floors. CI separately combines coverage from Linux geometry, Linux fallback, macOS and Windows and enforces a **90% supported-environment aggregate floor**.

Do not treat the old `v0.1.2` ~86% measurement as the current target. See [TESTING.md](TESTING.md).

## Public contract checks

```bash
python scripts/generate_mcp_tools_snapshot.py --check
python scripts/check_service_facade_contract.py --check
python scripts/validate_service_decomposition.py --check
```

Current expected values:

- 165 MCP tools.

The MCP discovery budget and exact snapshot are CI-gated. Internal schematic/PCB/cinematic work should not expand the public surface without an explicit API decision.

## Local server

```bash
DIPTRACE_MCP_WORKSPACE="$PWD/tests/fixtures" diptrace-mcp
```

Trusted-loopback development HTTP:

```bash
diptrace-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

Smoke helper:

```bash
python scripts/mcp_smoke.py
python scripts/mcp_smoke.py --transport stdio
```

## Bridge testing without DipTrace

```bash
cp tests/fixtures/pcb.xml /tmp/plugin_exchange.xml
DIPTRACE_MCP_WORKSPACE=/tmp \
DIPTRACE_MCP_STATE_DIR=/tmp/diptrace-state \
python -m diptrace_mcp.bridge \
  --headless \
  --timeout 30 \
  /tmp/plugin_exchange.xml
```

CI also runs:

```bash
python scripts/smoke_bridge_headless.py
```

A headless pass proves the project-owned exchange/session protocol, not native DipTrace import semantics.

## Windows build path

Use the current package version when building release-shaped artifacts:

```powershell
.\scripts\build_windows_server.ps1 -PythonCommand python -Clean
.\plugin\build_bridge.ps1 -PythonCommand python -Clean
.\scripts\build_windows_configurator.ps1 -PythonCommand python -Clean
.\scripts\build_windows_installer.ps1 `
  -Version 0.2.1 `
  -IsccPath "$env:ISCC_PATH"
```

Audit portable output and checksums with the repository scripts. Native Windows workflow evidence cannot be replaced by Linux/WSL inference.

## Service-layer rules

Before modifying service boundaries, read [SERVICE_DECOMPOSITION.md](SERVICE_DECOMPOSITION.md).

Required rules:

- keep `DipTraceService` as the explicit stable public Facade;
- pass narrow typed dependencies/callbacks;
- do not pass the complete Facade into a domain service;
- do not duplicate stores, caches, sessions, transactions, policies or document loaders;
- keep domain methods synchronous and preserve the server-owned offload boundary;
- preserve SHA, policy, backup, atomic-write, trust, transaction, plan, external-process and live-session gates;
- update Facade/snapshot/parity tests when the public contract intentionally changes.

## Internal EDA rules

Schematic and PCB optimizers are proposal/scoring layers, not new write authorities.

- keep observed document facts separate from inferred intent and operator facts;
- keep missing physical values explicit;
- use deterministic bounded candidate generation and stable tie-breakers;
- make hard safety/legality violations dominant over cosmetic soft scores;
- emit ordinary semantic operations or typed plan references;
- never write XML directly from an optimizer;
- keep real-host evidence separate from synthetic regression evidence.

See [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md) and [PCB_DESIGN_ENGINE.md](PCB_DESIGN_ENGINE.md).

## Cinematic development

The cinematic presentation tools currently run as Python modules rather than installed console scripts:

```bash
python -m diptrace_mcp.diptrace_profile_cli --help
python -m diptrace_mcp.cinematic_cli --help
python -m diptrace_mcp.cinematic_host --help
python -m diptrace_mcp.cinematic_recording --help
```

Real desktop playback is Windows-specific. Use dry-run/profile validation before moving the real cursor. Do not hard-code guessed toolbar pixels into the default profile; profiles must be explicitly calibrated and populated with verified actions.

See [CINEMATIC_DEMO_MODE.md](CINEMATIC_DEMO_MODE.md).

## Adding or changing a public tool

1. Implement/reuse a typed domain model/function.
2. Expose an explicit Facade method if it belongs to the stable public API.
3. Register a thin server wrapper.
4. Add focused unit and public-transport tests.
5. Update capability/error/safety behaviour.
6. Regenerate the complete MCP snapshot.
7. Update relevant docs/skill contract.
8. Keep real DipTrace verification claims separate from fixture-tested implementation claims.

For internal EDA improvements, prefer not adding a new public tool unless the API itself needs to change.

## Fixtures, evidence and historical docs

Ordinary tests use project-owned synthetic or sanitised XML fixtures and do not require DipTrace.

Do not automatically commit user projects, proprietary libraries, external PDFs/screenshots or private evidence. Controlled evidence requires exact hashes, source type, versions/builds, provenance and redistribution status.

Dated release/acceptance/compliance documents are historical snapshots. Preserve their original facts even when current `main` has moved on.

## Release work

Current published release record:

- [releases/v0.2.1.md](releases/v0.2.1.md)

Current generic release procedure:

- [RELEASE_PROCESS.md](RELEASE_PROCESS.md)

Do not move an existing tag, replace published bytes or claim signed/production-ready status from CI alone.
