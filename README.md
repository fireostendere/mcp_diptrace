# DipTrace MCP

**English** | [Русский](README_RU.md)

DipTrace MCP is a local Model Context Protocol server for reading, analyzing, reviewing, and safely editing DipTrace designs through the official XML formats. The repository contains two cooperating components:

- `diptrace-mcp`, the MCP server used by Codex, Claude Desktop, and other MCP clients;
- `diptrace_mcp_bridge.exe`, the executable plug-in that connects the server to a design currently open in PCB Layout or Schematic Capture.

## Current Readiness

The project is already usable as a human-in-the-loop engineering tool for PCB/schematic reading and review, guarded semantic edits, schematic authoring, schematic-to-PCB synchronization, bounded placement/routing, differential-pair analysis, and release-review workflows.

It is not yet a full replacement for DipTrace's interactive EDA engine. The main remaining gap is no longer MCP tool count; it is broad, automated, redistributable evidence that all important write paths survive real DipTrace 5.3 open/save/re-export cycles with the intended semantics.

Native Component/Pattern Library mutation and native manufacturing output generation are therefore intentionally not presented as completed capabilities.

See [the roadmap](docs/ROADMAP.md) for the current priority order and exit criteria. Runtime truth for a specific document always comes from `get_capabilities`.

## Public Release Status

The project is licensed under the Apache License 2.0, an OSI-approved
open-source license; the full text is committed as [`LICENSE`](LICENSE). The
selection rationale is recorded in
[docs/LICENSE_DECISION.md](docs/LICENSE_DECISION.md).

The repository publishes its participation and release policy:

- [contribution workflow](CONTRIBUTING.md);
- [current governance](GOVERNANCE.md);
- [license decision matrix and selection record](docs/LICENSE_DECISION.md);
- [public-release checklist](docs/PUBLIC_RELEASE_CHECKLIST.md) and
  [release process](docs/RELEASE_PROCESS.md);
- [changelog](CHANGELOG.md) and [citation metadata](CITATION.cff).

General contributions remain closed until contribution-provenance terms are
approved. Suspected vulnerabilities must be reported through the private
security channel published in [SECURITY.md](SECURITY.md), never in public
issues. A verified Code of Conduct channel does not yet exist, so a Code of
Conduct policy is not published. Contribution-provenance and signing work
remain explicit blockers. The repository does not claim an existing community,
adoption, sponsorship, vendor endorsement, or support program acceptance.

Version 0.1.0 is the current release. The tag `v0.1.0`, unsigned artifacts,
`SHA256SUMS.txt`, and the provenance record in
[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) identify the same commit.
CI builds the Python source distribution and wheel from an exact versioned
allowlist and audits their contents, bounds, entry points, packaged skills,
and wheel `RECORD`. The wheel contains the MCP server and packaged skills;
complete Windows live integration also needs the separately delivered bridge
settings, installer, and executable.

## Current Capabilities

- runtime capability discovery through `get_capabilities`, including precise unavailability reasons;
- project scaffolding: brand-new schematic and PCB XML documents with sheets, outline, layers, stackup, via styles, net classes, and DRC (`create_schematic_document`, `create_pcb_document`); callers may set the literal XML `format_version`, but this does not convert the scaffold structure or verify compatibility; **these produce synthetic MCP-generated XML, not DipTrace-verified files**;
- seed-based project creation from a real DipTrace-exported XML seed with preserved provenance (`create_document_from_seed`);
- schematic authoring: sheets, part placement by library `ComponentStyle`, pin/net connectivity, official `Wire`/`Points` wires, and net labels (`add_sheet`, `place_part`, `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, `add_net_label`);
- schematic-to-PCB synchronization of RefDes/value/fields, footprint references, pin-to-pad connectivity, nets, and ratlines, with additive-by-default and guarded `exact` reconciliation modes;
- verified pattern-library subtree copying for synchronization workflows;
- official DipTrace panelization parameters (`Panel`, V-Scoring / Tab Routing) through `set_panelization` and `clear_panelization`;
- normalized PCB, schematic, Component Library, and Pattern Library domain models;
- stable object references, structured selectors, connectivity graphs, and spatial queries;
- millimeter-normalized geometry, transforms, mirroring, arcs, optional exact GEOS geometry, and SVG/JSON previews;
- raw-preserving XML patches for supported UTF-8/UTF-16LE/BE/ASCII/Latin-1
  sources that retain unknown XML, the source BOM, line endings, and formatting
  outside targeted nodes; unsupported encodings fail closed;
- semantic transactions with plan, preview, validation, expected SHA-256, commit, backup, and rollback;
- component/part move, rotate, side, lock, property, pattern, alignment, distribution, and grouping operations;
- board-text edits, documented NetClass rules, and standalone-pad test points;
- Component/Pattern Library reading, validation, and pin-to-pad checks;
- bounded, registry-based offline DRC/ERC reviews with persistent findings, structured
  skips, and an explicit [implemented/partial/missing coverage matrix](docs/REVIEW_ENGINE.md);
- deterministic silkscreen and bounded local placement planners;
- explicit trace/via operations, bounded multi-layer 45-degree A*, and symmetric via insertion;
- congestion-ordered multi-net routing with bounded rip-up/retry (`route_connections`) and read-only priority evidence (`analyze_routing_congestion`);
- atomic coupled differential-pair routing from a centerline;
- bounded DSN export, Freerouting jobs, and guarded SES inspection/import;
- stackup, net length/skew, differential-pair geometry, return-path heuristics, and preliminary analytical impedance: Hammerstad-Jensen microstrip (single and differential) plus IPC-2141 centered symmetric stripline;
- ngspice batch adapter for user-supplied netlists with typed log results;
- typed optional openEMS-runner adapter for frequency-dependent centered/off-center stripline results, with bounded jobs and strict result parsing;
- bounded BOM, DFM/DFA/DFT, thermal-metadata, assembly, and design-comparison review
  profiles; their geometry and evidence limits are explicit and they are not fabrication
  or assembly sign-off;
- generic BOM, fabrication-review, and assembly-review manifests;
- policy profiles: `read_only`, `review`, `interactive_edit`, `automation`, and `manufacturing`;
- live and offline operation over MCP stdio or Streamable HTTP.

`get_capabilities` is authoritative for a particular installation and document. A registered tool may still be unavailable when the active source type lacks required geometry, rules, stackup data, or an external adapter.

## Validation Status

The repository CI separates platform responsibilities:

- full pytest on Linux with Python 3.10, 3.12, and 3.13;
- Ruff, strict Mypy, and generated-skill checks on Linux/Python 3.12;
- full pytest and CLI smoke tests on macOS and Windows/Python 3.12;
- a native Windows build that verifies and smoke-runs the
  `diptrace_mcp_bridge.exe` artifact.

The current `main` branch passes this matrix. Regression coverage includes the fail-closed trust authority boundary, required semantic-comparison categories for PCB/schematic, native Windows atomic-job behavior, and terminal cancellation semantics for Freerouting, ngspice, and openEMS jobs.

Synthetic 4.3 fixtures cover PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES, and server contracts. A separate live DipTrace 5.3.0.2 schematic acceptance test verified:

- source-SHA conflict protection, backup equality, and atomic write;
- 41 scoped `RefDesMarking` edits on the Power sheet;
- bridge apply followed by an independent DipTrace re-export;
- persistence of all 41 coordinates and unchanged normalized sheet/part/pin/net/bus/differential-pair counts;
- no new offline ERC errors after the round trip.

This is strong evidence for the tested paths, not a claim of complete compatibility with every DipTrace version or XML object.

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

DipTrace starts the plug-in as a separate executable and passes a temporary XML path. The bridge stores a working copy under `%LOCALAPPDATA%\DipTraceMCP`, waits for an MCP `apply` or `cancel` request, verifies the caller-observed working SHA-256, revalidates that the original exchange file is unchanged and still inside an allowed root, and exits only after the session is finalized. DipTrace then imports the exchange XML on `apply`.

## Requirements

- Python 3.10 or newer;
- Windows 10/11 for live integration with desktop DipTrace;
- a DipTrace build that supports executable XML plug-ins;
- an MCP client such as Codex or Claude Desktop;
- PowerShell and administrator access only when installing the plug-in under `C:\Program Files\DipTrace` or `DipTrace5`.

Offline XML analysis also works on Linux, macOS, and WSL.

## Windows Quick Start

### 1. Install the MCP server

```powershell
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Install the optional GEOS geometry backend when exact polygon, ellipse, obround,
swept-trace geometry, and the supported exact spatial-clearance paths are needed:

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

Close all DipTrace modules, open PowerShell as Administrator, and install the bridge in PCB Layout, Schematic Capture, Component Editor, and Pattern Editor:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\install_plugin.ps1
```

The installer checks `C:\Program Files\DipTrace5` first and then the legacy `C:\Program Files\DipTrace` directory. Override it when necessary:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\Apps\DipTrace" -Mode All
```

`-Mode Both` installs only PCB/Schematic support. `-Mode Libraries` installs only Component/Pattern Editor bridges. Library sessions export the complete active library for inspection but use `ImpMode=None`; finish them with `cancel` because native library mutation remains evidence-gated.

### 3. Connect Codex

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\path\to\mcp_diptrace\.venv\Scripts\diptrace-mcp.exe"

codex mcp list
```

Alternatively, merge [`examples/codex-config.toml`](examples/codex-config.toml) into `~/.codex/config.toml` and replace the example paths.

### 4. Start a live session

1. Open and save a design or library in DipTrace.
2. Select `Tools > Plugins > DipTrace MCP Bridge`.
3. Leave the bridge window open while the MCP client performs reads, plans, and edits.
4. Ask the client to inspect the document before requesting a write.
5. Require a dry-run/transaction preview and inspect changed object IDs.
6. Commit with the preview SHA, run post-write checks, read the latest working-document SHA, then call `finish_live_session(action="apply", expected_sha256="...")`; cancellation needs no hash.

The bridge buttons provide the same explicit apply/cancel controls. Its window shows a
SHA-bound, bounded impact summary: normalized and structural counts plus at most the first
20 changed stable IDs, with unavailable or truncated state disclosed. Live apply enforces
the same 500-object conservative limit both when the MCP request is published and again
inside the bridge immediately before replacement. Component and Pattern Editor bridge
profiles are read-only (`ImpMode=None`); unknown profiles are also fail-closed.

`finish_live_session` waits only for a bounded local bridge result: `applied`, `cancelled`,
or `not_acknowledged`. `applied` means that the bridge replaced and verified the local
exchange XML; it is not an acknowledgement from the DipTrace host. A provably dead
same-platform/same-PID-namespace bridge is marked `abandoned` automatically. Windows and
WSL PID namespaces are never guessed across; an unknown-liveness orphan expires after the
configurable two-hour session TTL or can be closed explicitly with
`abandon_live_session(reason="...")`, which never applies its working XML.
Windows/WSL lifecycle mutations share an atomic nonce-bound lease directory because
native `flock` and Windows byte locks do not interoperate on NTFS. Ordinary operations
never time-expire or force-reclaim an unknown lease owner; explicit abandonment
returns a typed timeout instead of risking a split-brain writer.

## Offline Mode

Pass a path inside `DIPTRACE_MCP_WORKSPACE` or `DIPTRACE_MCP_ALLOWED_ROOTS`:

> Run `summarize_design` for `boards/controller.xml`, then list the power nets.

Legacy binary `.dip`/`.dch` files must first be exported with `File > Export > DipTrace XML`. A native XML `.dip`/`.dch` can be read directly only when the file actually begins with an official DipTrace XML root.

## Data Handling

- Design and source paths supplied through MCP must resolve inside
  `DIPTRACE_MCP_WORKSPACE` or `DIPTRACE_MCP_ALLOWED_ROOTS`. The state directory and
  executable paths are separate, operator-owned settings.
- `DIPTRACE_MCP_STATE_DIR` can contain complete design XML in session working copies
  and transaction snapshots, plus operations, previews, plans, review reports,
  external-job logs/results, exports, and backups. Treat that directory as sensitive
  project data and choose its access controls accordingly.
- In a live session, DipTrace supplies a temporary exchange path. The bridge copies the
  input to `original.xml` and `working.xml` under the state directory; only explicit
  `apply`, with the expected working-file SHA-256, copies the result back to the
  exchange path. `cancel` leaves the exchange input unchanged.
- Offline backups are stored in the configured central state tree, keyed by canonical
  target-path hash, rather than in an implicit backup directory beside the design.
  Keep `DIPTRACE_MCP_STATE_DIR` outside the project when that separation is required.
  Count/age retention removes only validated terminal records and expired backup
  histories on a best-effort basis; active, nonterminal, corrupt, or unverifiable state
  may remain, and the thresholds are not storage quotas.
- Freerouting, ngspice, and an openEMS runner are optional local subprocesses invoked
  only through their corresponding tools. Their isolated job directories and bounded
  logs/results are retained under the state directory. Process containment does not
  provide a network sandbox for those third-party programs.
- The default `stdio` transport exchanges requests and results with the configured
  local MCP client. Optional `streamable-http` listens on the configured host and port;
  its default is loopback (`127.0.0.1:8765`) and it has no built-in remote
  authentication. Keep it on loopback unless an authenticated reverse proxy is
  configured.

See [Usage: Backups and State Directory](docs/USAGE.md#11-backups-and-state-directory),
[Security and Policy](docs/SECURITY_AND_POLICY.md), and
[External Adapters](docs/EXTERNAL_ADAPTERS.md) for the detailed boundaries.

## Write Safety

High-level writes default to preview/dry-run behavior. A safe workflow is:

1. load the document and record its SHA-256;
2. create or stage scoped semantic operations;
3. inspect the diff and SVG/JSON preview;
4. rerun the applicable bounded connectivity/DRC/ERC checks and inspect every skip;
5. commit with `expected_sha256`;
6. reparse the modified XML and run post-write checks;
7. apply the live session explicitly, or roll back/cancel.

`apply_xml_edits` remains an expert escape hatch. It requires exact match counts, preserves bytes outside targets, reparses the result, creates a backup before commit, and rejects SHA conflicts.

Creation tools may create an absent target without a hash. Replacing an existing target
requires both `overwrite=true` and its current caller-observed `expected_sha256`;
`expected_seed_sha256` binds the seed input and is not a substitute for the target hash.

XML containing `DOCTYPE` or `ENTITY` is rejected. Caller-supplied design and source
paths are constrained to configured roots; server state and executable paths are
separate operator-owned settings. External processes are available only through typed
allowlisted adapters.

### WO-11 safety checkpoint — 2026-07-25

- Paths supplied in MCP calls are literal: environment variables and `~` are not
  expanded. Expansion is reserved for operator-owned server configuration;
  caller-supplied design and source paths remain subject to allowed-root enforcement.
- Supported XML writes preserve the detected source codec/BOM and untouched bytes.
  Raw edits and raw-preserving semantic edits are reparsed and must equal the
  requested semantic element tree; clean UTF-32 input currently fails closed.
- Typed request data, normalized XML numbers, and SES numeric tokens reject `NaN`
  and infinities. DSN output refuses quoted values requiring unverified escaping or
  non-ASCII encoding, while SES input refuses backslash escapes and literal controls
  in quoted tokens. The real DipTrace conventions remain open evidence questions.
- External adapters have bounded streaming logs/results and a global concurrency
  limit. POSIX process groups and Windows kill-on-close Job Objects contain
  descendants, and root processes are explicitly reaped.
- Offline backups live under the central state directory, isolated by canonical
  target-path hash. Existing targets are backed up before replacement; new targets
  have no previous bytes to back up. Retention prunes validated terminal records and
  expired per-target backup histories, protects active/nonterminal state, and treats
  count/age thresholds as cleanup targets rather than hard quotas.

## Trust Model

The server distinguishes provenance from authority. A client may submit evidence but cannot promote its own document to a high-trust validation level.

- **Synthetic MCP-generated**: XML created by `create_schematic_document` or `create_pcb_document` is classified as `synthetic_parser_only` until stronger independently verified evidence exists.
- **Seed-based**: XML copied by `create_document_from_seed` from a real DipTrace export preserves seed provenance but does not create round-trip authority.
- **Public user-supplied evidence intake**: `validate_roundtrip_evidence` checks distinct allowed-root source/saved/re-export roles, exact SHA-256 values, source type, document binding, and, when a re-export is supplied, structural semantic comparison without writing. `record_roundtrip_evidence` explicitly writes only a manifest and provenance sidecar after repeating those gates. Both report `authority=user_supplied`, keep `requires_diptrace_verification=true`, and can never grant high trust.
- **High trust**: the package-owned exact-hash registry is implemented and
  disclosed through capabilities/resources, but it currently contains 0
  reviewed entries. No existing document is promoted. The
  [first entry requires independent human review](docs/TRUSTED_PROVENANCE_REGISTRY.md);
  user/workspace data cannot add one.

Trust invalidation is implemented for the main verified mutation paths, but the capability layer intentionally does **not** claim complete coverage for every write path yet. Current explicitly reported gaps are `plan_apply`, `ses_import`, `schematic_to_pcb_sync`, and `live_session_apply`. Closing these fail-closed trust paths is a near-term roadmap priority.

Evidence manifests are revalidated on use and rollback; path aliases, source-type mismatches, stale hashes, incomplete comparison categories, and semantic differences fail closed.

## Pattern Recommendation Status

The current baseline can inspect and validate existing Pattern Libraries, compare pad mapping, and assign an existing pattern to a component when pad numbers match. Pattern Editor bridge sessions are deliberately read-only.

Persistent feedback/recommendation tools such as `record_pattern_example`, `accept_pattern_suggestion`, and `reject_pattern_suggestion` are not implemented yet. The revised roadmap prioritizes DipTrace 5.3 evidence closure, trust-path coverage, and mask/paste/courtyard verification before this recommendation layer.

After that baseline is stronger, the planned path is an append-only provenance-bound feedback dataset, deterministic retrieval of similar accepted examples, and measurable ranked existing-pattern suggestions. Fine-tuning is later optional work.

Native Pattern/Component Library creation or mutation remains blocked until controlled DipTrace 5.3 before/after and open/save/re-export fixtures prove writer semantics.

## Shipped Agent Skills

The wheel now includes eight compact workflows under `diptrace_mcp/skills`: project intake,
library audit, schematic ERC review, testpoint planning, critical-net routing, signal-integrity
review, release gating, and operator-assisted evidence capture. They share one result schema and
are selected by a written mechanical survival rule; the former 57-package duplicated catalog is
not shipped.

Skills orchestrate registered MCP tools and the two packaged evidence CLIs. They do not add hidden
EDA capabilities, grant evidence trust, override runtime `get_capabilities`, or auto-register
themselves with an agent host; point that host at the installed `diptrace_mcp/skills` directory. See
[the shipped catalog and limits](skills/README.md).

## Known Limits

- The server does not automate the DipTrace GUI.
- DipTrace synchronously waits while a live plug-in session is active.
- One live session is supported at a time.
- A language model still needs visual review, ERC/DRC, and engineering judgment.
- The local router does not implement push-and-shove, free-angle routing, or dynamic neck-down; congestion-aware ordering and bounded rip-up/retry are available through `route_connections`.
- Automatic via routing requires a confirmed `Lay1`/`Lay2` span on multilayer boards.
- The coupled router requires compatible endpoint spacing/orientation and does not synthesize arbitrary uncoupled escapes.
- `calculate_impedance` remains a preliminary analytical estimate; field-solver results are available only through a configured `run_openems_stripline_analysis` backend.
- `place_part` references a library `ComponentStyle` by name; DipTrace resolves symbol graphics and pin mapping from its own libraries on import.
- The ngspice adapter runs user-supplied netlists and does not generate netlists from a design.
- The openEMS adapter requires a compatible external JSON runner; no solver is bundled and the committed parser fixture is synthetic.
- Copper-pour boundaries are not authoritative refill geometry.
- Generic fabrication manifests do not contain Gerber or NC Drill output.
- Persistent pattern-feedback/recommendation tools are not implemented yet.
- Native Component/Pattern Library mutation remains unavailable until verified DipTrace 5.3 round-trip fixtures exist.
- Authored schematic wires and generated ratlines still need broader real DipTrace 5.3 round-trip evidence.
- Real-openEMS golden validation remains external-runtime acceptance work.

## Documentation

- [Roadmap and actual status](docs/ROADMAP.md)
- [XML compatibility](docs/XML_COMPATIBILITY.md)
- [Complete usage guide](docs/USAGE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Domain model](docs/DOMAIN_MODEL.md)
- [Geometry engine](docs/GEOMETRY_ENGINE.md)
- [Transactions](docs/TRANSACTIONS.md)
- [MCP tools](docs/MCP_TOOLS.md)
- [Review engine](docs/REVIEW_ENGINE.md)
- [Placement engine](docs/PLACEMENT_ENGINE.md)
- [Routing engine](docs/ROUTING_ENGINE.md)
- [Impedance and SI](docs/IMPEDANCE_AND_SI.md)
- [External adapters](docs/EXTERNAL_ADAPTERS.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Testing and benchmarks](docs/TESTING.md)
- [Skill contracts](docs/SKILL_CONTRACTS.md)
- [PCB skills](skills/README.md)
- [Development](docs/DEVELOPMENT.md)
- [Russian README](README_RU.md)
