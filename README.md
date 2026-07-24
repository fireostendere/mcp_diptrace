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
- project scaffolding: brand-new schematic and PCB XML documents with sheets, outline,
  layers, stackup, via styles, net classes, and DRC (`create_schematic_document`,
  `create_pcb_document`); **note: these produce synthetic MCP-generated XML, not
  DipTrace-verified files**;
- seed-based project creation: copy a real DipTrace-exported XML seed to start a new
  project with preserved provenance (`create_document_from_seed`);
- schematic authoring: sheets, part placement by library `ComponentStyle`, pin/net
  connectivity, official `Wire`/`Points` wires, and net labels (`add_sheet`, `place_part`,
  `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, `add_net_label`);
- schematic-to-PCB synchronization of RefDes/value/fields, footprint references,
  pin-to-pad connectivity, nets, and ratlines, with additive-by-default and guarded exact
  reconciliation modes plus verified pattern-library subtree copying;
- official DipTrace panelization parameters (`Panel`, V-Scoring / Tab Routing) through
  `set_panelization` and `clear_panelization`;
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
- machine-readable serializer reference for exact XML enums, defaults, aliases, and import
  semantics derived from the supplied documentation archives; it is explicitly reference-only
  and cannot grant DipTrace round-trip trust;
- registry-based offline DRC/ERC reviews with persistent structured findings;
- deterministic silkscreen and bounded local placement planners;
- explicit trace/via operations, bounded multi-layer 45-degree A*, and symmetric via
  insertion;
- congestion-ordered multi-net routing with bounded rip-up/retry (`route_connections`)
  and read-only priority evidence (`analyze_routing_congestion`);
- atomic coupled differential-pair routing from a centerline;
- bounded DSN export, Freerouting jobs, and guarded SES inspection/import;
- stackup, net length/skew, differential-pair geometry, return-path heuristics, and
  preliminary analytical impedance: Hammerstad-Jensen microstrip (single and
  differential) plus IPC-2141 centered symmetric stripline;
- ngspice batch adapter for user-supplied netlists with typed log results;
- typed optional openEMS-runner adapter for frequency-dependent centered/off-center
  stripline results, with bounded jobs and strict result parsing;
- BOM, DFM/DFA/DFT, thermal-metadata, assembly, and design-comparison reviews;
- generic BOM, fabrication-review, and assembly-review manifests;
- policy profiles: `read_only`, `review`, `interactive_edit`, `automation`, and
  `manufacturing`;
- live and offline operation over MCP stdio or Streamable HTTP.

`get_capabilities` is the authoritative source for a particular installation and
document. A registered tool may still be unavailable when the active source type lacks
the required geometry, rules, stackup data, or external adapter.

## Validation Status

The repository CI separates platform responsibilities instead of repeating every gate on
every runner:

- full pytest on Linux with Python 3.10, 3.12, and 3.13;
- Ruff, strict Mypy, and generated-skill checks on Linux with Python 3.12;
- full pytest and CLI smoke tests on macOS and Windows with Python 3.12;
- a native Windows build that verifies a non-empty `diptrace_mcp_bridge.exe` artifact.

The current `main` branch passes this complete matrix. Regression coverage includes the
fail-closed trust authority boundary, required-category semantic comparison for PCB and
schematic round trips, native Windows atomic-job behavior, and terminal cancellation semantics for
Freerouting, ngspice, and openEMS jobs.

Synthetic 4.3 fixtures cover PCB, schematic, Component Library, Pattern Library,
geometry, transactions, review, routing, DSN/SES, and server contracts. A live DipTrace
5.3.0.2 schematic acceptance test separately verified:

- source-SHA conflict protection, backup equality, and atomic write;
- 41 scoped `RefDesMarking` edits on the Power sheet;
- bridge apply followed by an independent DipTrace re-export;
- persistence of all 41 coordinates and unchanged normalized
  sheet/part/pin/net/bus/differential-pair counts;
- no new offline ERC errors after the round trip.

This is strong evidence for the tested paths, not a claim of complete compatibility with
every DipTrace version or every XML object. The bundled serializer reference further constrains
parser behavior, but does not replace real DipTrace open/save/re-export evidence.

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

Close all DipTrace modules, open PowerShell as Administrator, and install the bridge in
PCB Layout, Schematic Capture, Component Editor, and Pattern Editor:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\install_plugin.ps1
```

The installer checks `C:\Program Files\DipTrace5` first and then the legacy
`C:\Program Files\DipTrace` directory. Override it when necessary:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\Apps\DipTrace" -Mode All
```

`-Mode Both` installs only PCB and Schematic support. `-Mode Libraries` installs the
Component and Pattern Editor bridges. Library sessions export the complete active
library for inspection, but use `ImpMode=None`; finish them with `cancel` because native
library mutation remains evidence-gated.

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

1. Open and save a design or library in DipTrace.
2. Select `Tools > Plugins > DipTrace MCP Bridge`.
3. Leave the bridge window open while the MCP client performs reads, plans, and edits.
4. Ask the client to inspect the document before requesting any write.
5. Require a dry-run/transaction preview and review the changed object IDs.
6. Commit with the preview SHA, run post-write checks, then call
   `finish_live_session(action="apply")` or cancel the session.

The bridge buttons provide the same explicit apply/cancel controls. Component and
Pattern Editor bridge profiles are read-only and must be cancelled after inspection.

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

## Trust Model

The server distinguishes provenance from authority. A client may submit evidence, but it
cannot promote its own document to a high-trust validation level.

- **Synthetic MCP-generated**: XML created by `create_schematic_document` or
  `create_pcb_document`. It is classified as `synthetic_parser_only` until stronger,
  independently verified evidence exists.
- **Seed-based**: XML copied by `create_document_from_seed` from a real DipTrace export.
  It preserves the seed provenance, but copying does not create round-trip authority.
- **Recorded evidence**: `record_roundtrip_evidence` binds before/after files, exact paths,
  source type, SHA-256 values, and semantic comparison. User-supplied evidence is useful
  for audit and regression, but is not a trusted root.
- **Serializer reference**: the bundled rule set fingerprints and distills the supplied XML
  documentation. It can constrain parser/writer implementation and tests, but has no trust effect.
- **High trust**: promotion to `diptrace_roundtrip_verified` or
  `external_tool_roundtrip_verified` is intentionally unavailable until the project has
  an authenticated server-owned registry, signature verifier, or committed allowlist.

Every MCP write invalidates prior high-trust claims and records the parent provenance.
Evidence manifests are revalidated on use and rollback; path aliases, source-type
mismatches, stale hashes, incomplete comparison categories, and semantic differences fail
closed.

## Pattern Learning Status

The current baseline can inspect and validate existing Pattern Libraries, compare pad
mapping, and apply an existing pattern to a component when pad numbers match. Pattern
Editor bridge sessions are deliberately read-only.

The project does **not** yet contain persistent training/feedback tools such as
`record_pattern_example`, `accept_pattern_suggestion`, or `reject_pattern_suggestion`.
The next implementation milestone is an append-only, provenance-bound feedback dataset
and deterministic retrieval of similar accepted examples. Fine-tuning is explicitly
later work and is not required for the first useful recommendation system.

Creation or mutation of native Pattern/Component Libraries remains blocked until
controlled DipTrace 5.3 before/after and open/save/re-export fixtures prove the writer
semantics. The committed implementation order and acceptance criteria are recorded in
[the roadmap](docs/ROADMAP.md).

## Known Limits

- The server does not automate the DipTrace GUI.
- DipTrace synchronously waits while a live plug-in session is active.
- One live session is supported at a time.
- A language model still needs visual review, ERC/DRC, and engineering judgment.
- The local router does not implement push-and-shove, free-angle routing, or dynamic
  neck-down; congestion-aware ordering and bounded rip-up/retry are available via
  `route_connections`.
- Automatic via routing requires a confirmed `Lay1`/`Lay2` span on multilayer boards.
- The coupled router requires compatible endpoint spacing/orientation and does not
  synthesize arbitrary uncoupled escapes.
- `calculate_impedance` remains a preliminary analytical estimate. Field-solver results
  are available only from a configured `run_openems_stripline_analysis` backend.
- `place_part` references a library `ComponentStyle` by name; DipTrace resolves symbol
  graphics and pin mapping from its own libraries on import.
- The ngspice adapter runs user-supplied netlists in batch mode and does not generate
  netlists from a design. The openEMS adapter requires a compatible external JSON runner;
  no solver is bundled and the committed parser fixture is explicitly synthetic.
- Copper-pour boundaries are not authoritative refill geometry.
- Generic fabrication manifests do not contain Gerber or NC Drill output.
- Persistent pattern-training feedback and recommendation tools are not implemented yet.
- Library mutation remains unavailable until verified DipTrace 5.3 round-trip fixtures
  exist; real-openEMS golden validation also remains external-runtime acceptance work.

## Documentation

- [Roadmap and actual status](docs/ROADMAP.md)
- [Serializer reference](docs/SERIALIZER_REFERENCE.md)
- [XML compatibility](docs/XML_COMPATIBILITY.md)
- [Testing](docs/TESTING.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [MCP tools](docs/MCP_TOOLS.md)
