# Usage

## Install

### PyPI

Python 3.10 or newer:

```bash
python -m pip install diptrace-mcp==0.2.1
diptrace-mcp --help
```

### Published Windows assets

Use the immutable `v0.2.1` GitHub prerelease and keep every downloaded file on the same version:

- `DipTrace-MCP-Setup-0.2.1.exe` — recommended Windows installer;
- `DipTrace-MCP-Portable-0.2.1.zip` — portable bundle;
- `DipTrace-MCP-0.2.1-windows.mcpb` — self-contained stdio MCP server for compatible clients;
- `SHA256SUMS.txt` — release checksums.

See [INSTALL_FROM_RELEASE.md](INSTALL_FROM_RELEASE.md).

### Source checkout

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,geometry]'
```

## Configure the workspace

The ordinary local workspace is selected with `DIPTRACE_MCP_WORKSPACE`. Additional allowed roots may be supplied through `DIPTRACE_MCP_ALLOWED_ROOTS`; paths remain subject to literal safe-path/containment checks.

Example:

```bash
export DIPTRACE_MCP_WORKSPACE="$HOME/projects/eda"
export DIPTRACE_MCP_STATE_DIR="$HOME/.local/state/diptrace-mcp"
diptrace-mcp
```

On Windows use the equivalent environment variables or the installer/configurator. The state directory stores project-owned records, sessions, backups and related local metadata. Live-session state is separate from ordinary project files.

## Start the MCP server

Default stdio:

```bash
diptrace-mcp
```

Trusted-loopback development HTTP:

```bash
diptrace-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

Do not expose the HTTP transport as a general remote network service unless the surrounding deployment adds an appropriate trust boundary; the built-in usage model is local/trusted-loopback.

## Discover capabilities first

The public MCP contract contains **165 registered tools**, but availability can depend on document kind, live/offline mode, configured adapters, policy, platform, optional dependencies and evidence/trust state.

Call `get_capabilities` before assuming that a particular write or adapter path is available.

## Normal offline workflow

The authoritative engineering workflow is XML/model based:

1. discover/read the document;
2. inspect normalized PCB/schematic/library facts;
3. analyse/review or generate a bounded plan;
4. preview the intended semantic operation;
5. keep the expected SHA-256 from the preview/source state;
6. apply through the guarded semantic/transaction path;
7. review/re-open/re-export when the claim requires native DipTrace evidence.

The write path enforces allowed roots, bounded XML parsing, expected SHA, policy/write-impact checks, backup/atomic replacement and transaction/recovery rules.

Internal schematic/PCB optimizers do not write XML directly. They produce typed candidates, metrics, feedback, plans or ordinary semantic operations that reuse the same guarded path.

## Live DipTrace workflow

The Windows bridge supports projects currently open in DipTrace through the plugin XML exchange path.

At a high level:

1. DipTrace exports the current document to the bridge exchange path;
2. the bridge starts a project-owned live session;
3. MCP reads/analyses/modifies the session working copy;
4. the caller requests `apply` or `cancel`;
5. apply rechecks expected identities before returning the final exchange document;
6. cancel/refusal leaves the host exchange content unchanged.

A successful project-owned bridge handshake is not by itself proof that a specific DipTrace version accepted every semantic change. Native acceptance uses open/save/re-export evidence for the affected path.

## Public capability groups

The exact tool list is frozen in `reference/mcp-tools-list.snapshot.json`. Major groups include document discovery/parsing, PCB/schematic/library inspection, connectivity/BOM/DRC/ERC/review, placement/routing/authoring, synchronization/comparison, transaction/recovery/live sessions, evidence/trust, external adapters and release/readiness helpers.

See [MCP_TOOLS.md](MCP_TOOLS.md) for the public contract and use runtime introspection for exact schemas.

## Intelligent schematic workflow

Current internal schematic modules can:

- infer conservative functional blocks and part/net roles;
- apply explicit/project/reference motifs plus deterministic builtin readability motifs;
- generate bounded placement candidates;
- score readability, interconnect and congestion;
- resolve pin geometry conservatively from the embedded Design Cache;
- plan/evaluate bounded wire candidates without mutation;
- jointly score placement candidates using pin-aware routes;
- generate bounded placement repairs when routes explicitly request them;
- identify only explicit sheet-local wire groups affected by moved parts;
- rebuild those affected routes and return one dependency-safe `delete wire -> move part -> add wire` semantic-operation batch.

`schematic_atomic_reroute.py` therefore closes the former already-wired placement gap. If affected pin endpoints or replacement routes cannot be resolved safely, planning fails closed before any source mutation. The returned operation list becomes atomic only when previewed/committed as one unit through the normal guarded semantic transaction path.

`schematic_ensemble.py` adds deterministic motif/congestion pressure to the existing route-aware candidate ranking. It remains bounded and does not claim a global optimum.

See [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## PCB Generations A-D

The internal PCB design engine adds higher-level engineering judgement; bounded read-only candidate comparison is productized as `compare_pcb_placement_candidates` within the 165-tool MCP surface:

- Generation A: intent/net intelligence and intent-aware placement;
- Generation B: physical/stackup/PDN/return-path/noise/via context;
- Generation C: routing policy and observed-route engineering checks;
- Generation D: bounded hard-first whole-board candidate selection;
- `pcb_candidate_ensemble.py`: multiple bounded Generation-A placements using different engineering weight profiles, conservative B/C evidence terms and Generation-D selection, with the existing board as an optional baseline.

These layers preserve unknown physical facts and do not turn approximate analysis into field-solver/PI/EMC/thermal/manufacturing sign-off. See [PCB_DESIGN_ENGINE.md](PCB_DESIGN_ENGINE.md).

## DSN/SES and XML analysis

`specctra_analysis.py` can inspect bounded DSN/SES structure and route geometry before mutation, including unknown nets/layers and the routes that the current SES import path would import or skip.

`xml_analysis.py` provides deterministic semantic fingerprints and structural deltas. It normalizes attribute order, preserves element-order significance and includes unknown XML in the fingerprint. These are analysis/evidence helpers, not compatibility grants.

## Cinematic demo / video / GIF mode

The core engineering path remains XML-first. The optional presentation subsystem can deliberately drive the visible DipTrace UI on Windows after the engineering action has been planned.

The distinction remains strict:

- ordinary MCP edits do not depend on mouse/keyboard automation;
- cinematic replay uses bounded cursor/click/hotkey/text/path actions for presentation;
- cinematic replay is not proof that DipTrace semantically accepted the edit;
- the normal XML preview/SHA/transaction/review path remains authoritative.

### Create/calibrate a UI profile

```bash
python -m diptrace_mcp.diptrace_profile_cli template \
  --editor schematic \
  --version 5.3 \
  --output schematic-5.3.json

python -m diptrace_mcp.diptrace_profile_cli probe --window "DipTrace"

python -m diptrace_mcp.diptrace_profile_cli calibrate \
  schematic-5.3.json anchors.json
```

Install explicitly verified UI action macros and validate readiness:

```bash
python -m diptrace_mcp.diptrace_profile_cli action \
  schematic-5.3.json place_component place-component.json
python -m diptrace_mcp.diptrace_profile_cli validate schematic-5.3.json
```

Do not guess toolbar pixels/shortcuts and put them into a default profile. Calibration/action macros are editor/version/configuration specific.

### Capture/compile a cinematic timeline

```bash
python -m diptrace_mcp.cinematic_cli init demo.jsonl \
  --title "PCB routing demo" \
  --preset cinematic \
  --domain pcb

python -m diptrace_mcp.cinematic_cli event demo.jsonl route_trace --target CLK
python -m diptrace_mcp.cinematic_cli compile demo.jsonl --output demo.cinematic.json
```

Payload recording is disabled by default and must be explicitly enabled when wanted.

### Preflight, dry-run and real replay

Standalone inspection is available:

```bash
python -m diptrace_mcp.cinematic_preflight_cli demo.cinematic.json
```

The actual `cinematic_host.play_manifest()` path also runs the same preflight **unconditionally before any desktop driver action**. Calling the host directly therefore cannot bypass cue/timing/payload/action budgets.

```bash
python -m diptrace_mcp.cinematic_host demo.cinematic.json --dry-run
python -m diptrace_mcp.cinematic_host demo.cinematic.json --window "DipTrace"
```

### Record

```bash
python -m diptrace_mcp.cinematic_recording raw-demo.mp4 \
  --window-title "DipTrace" \
  --fps 60

python -m diptrace_mcp.cinematic_cli ffmpeg raw-demo.mp4 demo --preset cinematic
```

The real recorder uses Windows ffmpeg `gdigrab`. PCB trace replay fails closed for via/layer transitions until explicit staged macros exist.

See [CINEMATIC_DEMO_MODE.md](CINEMATIC_DEMO_MODE.md).

## Component/Pattern Library boundary

`library_mutation.py` is the internal raw-preserving mutation core with controlled real-editor round-trip evidence. `library_mutation_api.py` adds an expected-SHA in-memory package-level request/preview contract.

That package API is deliberately **not a public MCP tool**: `public_registration=False`, so the public surface stays at 165 tools. Public registration remains a separate API/product/evidence decision.

## Evidence capture and reports

The capture tool remains operator-assisted and trust-neutral. A finalized capture candidate can be converted into deterministic review material with:

```bash
python scripts/build_evidence_report.py \
  /path/to/session.candidate.json \
  --capture-root /path/to/capture-root \
  --markdown evidence-report.md \
  --json-output evidence-report.json
```

The builder rechecks artifact SHA bindings and emits XML semantic comparisons. It cannot promote provenance, grant fixture trust or manufacture a PASS result.

See [EVIDENCE_CAPTURE.md](EVIDENCE_CAPTURE.md).

## External adapters

Freerouting, ngspice and openEMS are optional local process adapters. Their output is candidate/evidence data and remains subject to the normal review/trust boundary. The project does not silently send designs to online services.

## Evidence and acceptance

Keep these statements separate:

- repository tests say the implementation behaves as tested on fixtures/runners;
- runtime capabilities say a configured path is currently exposed;
- real DipTrace evidence says a specific real-host path was observed on exact versions/candidate;
- historical release records preserve what was true when that release was cut.

The private/manual Q1 Component Angle campaign is PASS on the later accepted production checkpoint, while the immutable `v0.2.1` release record correctly retains `NOT_RUN` because it predates that campaign.

## Runtime defaults

| Environment variable | Default |
| --- | --- |
| `DIPTRACE_MCP_SESSION_TIMEOUT` | `1800` |
| `DIPTRACE_MCP_SESSION_TTL_SECONDS` | `7200` |
| `DIPTRACE_MCP_MAX_JOB_TIMEOUT_SECONDS` | `60` |

An explicit positive `--timeout` or `DIPTRACE_MCP_SESSION_TIMEOUT` overrides the bridge-session timeout default.

## Developer consistency checks

Evergreen docs are checked against implemented module state and the frozen public tool count:

```bash
python scripts/check_documentation_state.py
```

The same guard runs through `tests/test_documentation_state.py` in the normal CI test matrix. Historical dated evidence/release documents are intentionally outside this freshness rule.

## Troubleshooting

If a tool unexpectedly refuses to act:

1. call `get_capabilities`;
2. confirm document kind and live/offline state;
3. confirm workspace/allowed roots and state directory;
4. compare current SHA with preview/expected SHA;
5. inspect the stable error code/details rather than retrying blindly;
6. for Windows live exchange, restart the affected MCP client/DipTrace process after configuration changes;
7. for cinematic replay, validate the UI profile and use dry-run; manifest preflight itself is automatic in the host.

See [API_ERRORS.md](API_ERRORS.md), [TRANSACTIONS.md](TRANSACTIONS.md), [TESTING.md](TESTING.md) and [WINDOWS_WSL_LOCK_INTEROP.md](WINDOWS_WSL_LOCK_INTEROP.md).
