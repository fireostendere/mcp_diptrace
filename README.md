# DipTrace MCP

**English** | [Русский](README_RU.md)

DipTrace MCP is a local Model Context Protocol server for reading, analyzing, reviewing,
and safely editing DipTrace designs through the official XML formats. The repository
contains two cooperating components:

- `diptrace-mcp`, the MCP server used by Codex, Claude Desktop, and other MCP clients;
- `diptrace_mcp_bridge.exe`, the executable plug-in that connects the server to a
  design currently open in PCB Layout or Schematic Capture.

## Current Capabilities

- runtime capability discovery through `get_capabilities`, including precise
  unavailability reasons;
- normalized PCB, schematic, Component Library, and Pattern Library domain models;
- stable object references, structured selectors, connectivity graphs, and spatial
  queries;
- millimeter-normalized geometry, transforms, mirroring, arcs, exact optional GEOS
  geometry, and SVG/JSON previews;
- raw-preserving XML patches that retain unknown XML, BOM, line endings, and formatting
  outside targeted nodes;
- semantic transactions with plan, preview, validation, expected SHA-256, commit,
  backup, and rollback;
- component/part move, rotate, side, lock, property, pattern, alignment, distribution,
  and grouping operations;
- board-text edits, documented net-class rules, and standalone-pad test points;
- Component/Pattern Library reading, validation, and pin-to-pad checks;
- registry-based offline DRC/ERC reviews with persistent structured findings;
- deterministic silkscreen and bounded local placement planners;
- explicit trace/via operations, bounded multi-layer 45-degree A*, and symmetric via
  insertion;
- atomic coupled differential-pair routing from a centerline;
- bounded DSN export, Freerouting jobs, and guarded SES inspection/import;
- stackup, net length/skew, differential-pair geometry, return-path heuristics, and
  preliminary single-ended/differential microstrip impedance;
- BOM, DFM/DFA/DFT, thermal-metadata, assembly, and design-comparison reviews;
- generic BOM, fabrication-review, and assembly-review manifests;
- policy profiles: `read_only`, `review`, `interactive_edit`, `automation`, and
  `manufacturing`;
- live and offline operation over MCP stdio or Streamable HTTP.

`get_capabilities` is the authoritative source for a particular installation and
document. A registered tool may still be unavailable when the active source type lacks
the required geometry, rules, stackup data, or external adapter.

## Validation Status

The core test suite, Ruff, and strict Mypy are clean on the current source tree. Synthetic
4.3 fixtures cover PCB, schematic, Component Library, Pattern Library, geometry,
transactions, review, routing, DSN/SES, and server contracts.

A live DipTrace 5.3.0.2 schematic acceptance test also verified:

- source-SHA conflict protection, backup equality, and atomic write;
- 41 scoped `RefDesMarking` edits on the Power sheet;
- bridge apply followed by an independent DipTrace re-export;
- persistence of all 41 coordinates and unchanged normalized
  sheet/part/pin/net/bus/differential-pair counts;
- no new offline ERC errors after the round-trip.

This validation is strong evidence for the tested path, not a claim of complete
compatibility with every DipTrace version or every XML object.

## Architecture

```text
MCP client                    diptrace-mcp
(Codex/Claude)  <-------->    analysis and guarded XML edits
                                     |
                                     | shared state directory
                                     v
DipTrace       <-------->    diptrace_mcp_bridge.exe
               temporary plugin_exchange.xml
```

DipTrace starts the plug-in as a separate executable and passes a temporary XML path.
The bridge stores a working copy under `%LOCALAPPDATA%\DipTraceMCP`, waits for an MCP
`apply` or `cancel` request, verifies the expected SHA-256, and exits only after the
session is finalized. DipTrace then imports the exchange XML on `apply`.

## Requirements

- Python 3.10 or newer;
- Windows 10/11 for live integration with desktop DipTrace;
- a DipTrace build that supports executable XML plug-ins;
- an MCP client such as Codex or Claude Desktop;
- PowerShell and administrator access only when installing the plug-in under
  `C:\Program Files\DipTrace`.

Offline XML analysis also works on Linux, macOS, and WSL.

## Windows Quick Start

### 1. Install the MCP server

```powershell
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Install the optional GEOS geometry backend when exact polygon, ellipse, obround, swept
trace, and spatial DRC operations are needed:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[geometry]"
```

Verify the entry point:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --help
```

### 2. Build and install the DipTrace plug-in

Build the unsigned executable locally from this repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\build_bridge.ps1
```

Close all DipTrace modules, open PowerShell as Administrator, and install the bridge:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\install_plugin.ps1
```

The installer checks `C:\Program Files\DipTrace5` first and then the legacy
`C:\Program Files\DipTrace` directory. Override it when necessary:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\Apps\DipTrace" -Mode Both
```

### 3. Connect Codex

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\path\to\mcp_diptrace\.venv\Scripts\diptrace-mcp.exe"

codex mcp list
```

Alternatively, merge [`examples/codex-config.toml`](examples/codex-config.toml) into
`~/.codex/config.toml` and replace the example paths.

### 4. Start a live session

1. Open and save a design in DipTrace.
2. Select `Tools > Plugins > DipTrace MCP Bridge`.
3. Leave the bridge window open while the MCP client performs reads, plans, and edits.
4. Ask the client to inspect the document before requesting any write.
5. Require a dry-run/transaction preview and review the changed object IDs.
6. Commit with the preview SHA, run post-write checks, then call
   `finish_live_session(action="apply")` or cancel the session.

The bridge buttons provide the same explicit apply/cancel controls.

## Offline Mode

Pass a path inside `DIPTRACE_MCP_WORKSPACE` or `DIPTRACE_MCP_ALLOWED_ROOTS`:

> Run `summarize_design` for `boards/controller.xml`, then list the power nets.

Legacy binary `.dip` and `.dch` files must first be exported with
`File > Export > DipTrace XML`. A native XML `.dip` or `.dch` can be read directly
only when the file actually begins with an official DipTrace XML root.

## Write Safety

High-level writes default to preview/dry-run behavior. A safe workflow is:

1. load the document and record its SHA-256;
2. create or stage scoped semantic operations;
3. inspect the diff and SVG/JSON preview;
4. validate connectivity and localized DRC/ERC;
5. commit with `expected_sha256`;
6. reparse the modified XML and run post-write checks;
7. apply the live session explicitly, or roll back/cancel.

`apply_xml_edits` remains an expert escape hatch. It requires exact match counts,
preserves bytes outside targets, reparses the result, creates a backup before commit,
and rejects SHA conflicts.

XML containing `DOCTYPE` or `ENTITY` is rejected. Filesystem access is constrained to
configured roots. External processes are available only through typed, allowlisted
adapters.

## Known Limits

- The server does not automate the DipTrace GUI.
- DipTrace synchronously waits while a live plug-in session is active.
- One live session is supported at a time.
- A language model still needs visual review, ERC/DRC, and engineering judgment.
- The local router does not implement push-and-shove, rip-up/retry, free-angle routing,
  or dynamic neck-down.
- Automatic via routing requires a confirmed `Lay1`/`Lay2` span on multilayer boards.
- The coupled router requires compatible endpoint spacing/orientation and does not
  synthesize arbitrary uncoupled escapes.
- Impedance output is a preliminary analytical microstrip estimate, not a field-solver
  or full-wave result.
- Copper-pour boundaries are not authoritative refill geometry.
- Generic fabrication manifests do not contain Gerber or NC Drill output.
- Schematic wire writers, library mutation, panelization, and unverified solvers remain
  unavailable.
- The locally built unsigned bridge may require Windows Defender/SmartScreen approval.

## Documentation

- [Complete guide](docs/USAGE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Domain model](docs/DOMAIN_MODEL.md)
- [XML compatibility matrix](docs/XML_COMPATIBILITY.md)
- [Geometry engine](docs/GEOMETRY_ENGINE.md)
- [Transactions](docs/TRANSACTIONS.md)
- [MCP tools and resources](docs/MCP_TOOLS.md)
- [Review engine](docs/REVIEW_ENGINE.md)
- [Placement engine](docs/PLACEMENT_ENGINE.md)
- [Routing engine](docs/ROUTING_ENGINE.md)
- [Impedance and preliminary SI](docs/IMPEDANCE_AND_SI.md)
- [External adapters](docs/EXTERNAL_ADAPTERS.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Testing and benchmarks](docs/TESTING.md)
- [Skill contracts](docs/SKILL_CONTRACTS.md)
- [English PCB skill catalog](skills/README.md)
- [Development](docs/DEVELOPMENT.md)
- [Roadmap and actual status](docs/ROADMAP.md)
- [Russian README](README_RU.md)

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,geometry]'
python scripts/generate_pcb_skills.py --check
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts
python -m mypy --no-incremental src/diptrace_mcp
```

See [Development](docs/DEVELOPMENT.md) and [Testing](docs/TESTING.md) before submitting
changes.
