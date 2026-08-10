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

On Windows use the equivalent environment variables or the installer/configurator.

The state directory stores project-owned records, sessions, backups and related local metadata. Live-session state is separate from ordinary project files.

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

The public MCP contract contains 159 registered tools, but availability can depend on:

- document kind;
- live/offline mode;
- configured adapters;
- policy profile;
- platform;
- available optional dependencies;
- evidence/trust state.

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

The exact tool list is frozen in `reference/mcp-tools-list.snapshot.json`. Major groups include:

- document discovery, parsing and structured reads;
- PCB/schematic/component/pattern inspection;
- connectivity, BOM, DRC/ERC and review;
- placement/routing/trace/via/silkscreen/panel/schematic authoring workflows;
- synchronization and comparison;
- transactions, backups, recovery and live sessions;
- evidence/provenance/trust resources;
- external bounded jobs/adapters;
- release/readiness helpers.

See [MCP_TOOLS.md](MCP_TOOLS.md) for the public contract and use runtime introspection for exact schemas.

## Intelligent schematic workflow

Current internal schematic modules can:

- infer conservative functional blocks and part/net roles;
- apply explicit/project/reference motifs;
- generate bounded placement candidates;
- score readability and estimated interconnect;
- resolve pin geometry conservatively from the embedded Design Cache;
- plan/evaluate bounded wire candidates without mutation;
- jointly score placement candidates using pin-aware routes;
- generate bounded placement repairs when routes explicitly request them.

Important current boundary: placement planners refuse an already-wired schematic by default. Moving symbols while leaving existing wire geometry behind would be unsafe/ugly. Selective atomic placement + affected-wire replacement remains future work.

See [SCHEMATIC_LAYOUT_ENGINE.md](SCHEMATIC_LAYOUT_ENGINE.md).

## PCB Generations A-D

The internal PCB design engine can add higher-level engineering judgement without expanding the public MCP tool surface:

- Generation A: intent/net intelligence and intent-aware placement;
- Generation B: physical/stackup/PDN/return-path/noise/via context;
- Generation C: routing policy and observed-route engineering checks;
- Generation D: bounded whole-board candidate selection.

These layers preserve unknown physical facts and do not turn approximate analysis into field-solver/PI/EMC/thermal/manufacturing sign-off. See [PCB_DESIGN_ENGINE.md](PCB_DESIGN_ENGINE.md).

## Cinematic demo / video / GIF mode

The core engineering path remains XML-first, but `main` now also contains an **optional presentation subsystem** that can deliberately drive the visible DipTrace UI on Windows after the engineering action has already been planned.

This is the important distinction:

- ordinary MCP edits do **not** depend on mouse/keyboard automation;
- cinematic replay **does** use bounded cursor/click/hotkey/text/path actions for presentation;
- cinematic replay is not proof that DipTrace semantically accepted the edit;
- the normal XML preview/SHA/transaction/review path remains authoritative.

### Create/calibrate a UI profile

```bash
python -m diptrace_mcp.diptrace_profile_cli template \
  --editor schematic \
  --version 5.3 \
  --output schematic-5.3.json
```

Probe a visible known point in the DipTrace client area:

```bash
python -m diptrace_mcp.diptrace_profile_cli probe --window "DipTrace"
```

Fit the design-to-client affine transform from at least three non-collinear anchors (four or more recommended):

```bash
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

### Dry-run / real replay

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

The real recorder uses Windows ffmpeg `gdigrab`. PCB trace replay currently fails closed for via/layer transitions until explicit staged macros exist.

See [CINEMATIC_DEMO_MODE.md](CINEMATIC_DEMO_MODE.md).

## Component/Pattern Library boundary

The repository now contains an internal raw-preserving Component/Pattern Library mutation core with controlled real-editor round-trip evidence. Do not interpret that as a new public native-library MCP write contract: public registration remains a separate API/product decision.

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

The bridge timeout default is part of the public operator contract and is also reported by `get_capabilities`.

| Environment variable | Default (seconds) |
| --- | ---: |
| `DIPTRACE_MCP_SESSION_TIMEOUT` | `1800` |

An explicit positive `--timeout` or `DIPTRACE_MCP_SESSION_TIMEOUT` overrides the default for the bridge session.

## Troubleshooting

If a tool unexpectedly refuses to act:

1. call `get_capabilities`;
2. confirm document kind and live/offline state;
3. confirm workspace/allowed roots and state directory;
4. compare the current document SHA with the preview/expected SHA;
5. inspect the stable error code/details rather than retrying blindly;
6. for Windows live exchange, restart the affected MCP client/DipTrace process when configuration changed;
7. for cinematic replay, run profile validation and a dry-run before touching the real desktop.

See [API_ERRORS.md](API_ERRORS.md), [TRANSACTIONS.md](TRANSACTIONS.md), [TESTING.md](TESTING.md) and [WINDOWS_WSL_LOCK_INTEROP.md](WINDOWS_WSL_LOCK_INTEROP.md).
