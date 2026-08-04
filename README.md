# DipTrace MCP

**English** | [Русский](README_RU.md)

[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml)
[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)

DipTrace MCP is a local Model Context Protocol server for reading, analysing,
reviewing, and safely editing DipTrace XML designs. It contains two cooperating
components:

- `diptrace-mcp`, the MCP server used by Codex, Claude Desktop, and other MCP
  clients;
- `diptrace_mcp_bridge.exe`, the Windows executable plug-in that exchanges XML
  with a design currently open in PCB Layout or Schematic Capture.

## Current status

The source tree and build metadata are versioned as **0.2.0**. The latest
published GitHub release is still **v0.1.2**. Version 0.2.0 is a reviewed,
unsigned development-stage release candidate; it is not tagged or published
while the remaining real Windows and DipTrace acceptance gates are open.

The current code is usable as a human-in-the-loop engineering tool for PCB,
schematic, and library reading; structured review; guarded semantic writes;
schematic authoring and synchronisation; bounded placement/routing; live
PCB/Schematic exchange; and Windows installer/portable candidate builds.

It is not a replacement for DipTrace's interactive EDA engine. Native
Component/Pattern Library mutation and native manufacturing-output generation
are intentionally unavailable. Runtime `get_capabilities` is authoritative for
a particular installation, document, policy, and external-adapter setup.

## Public Release Status

The project uses the OSI-approved Apache-2.0 open-source `LICENSE`. Participation
and release controls are documented in `CONTRIBUTING.md`, `GOVERNANCE.md`,
`docs/LICENSE_DECISION.md`, `docs/PUBLIC_RELEASE_CHECKLIST.md`,
`docs/RELEASE_PROCESS.md`, `CHANGELOG.md`, and `CITATION.cff`. Security reports
use the private security channel; a verified Code of Conduct enforcement channel
is not yet published.

- Latest published development release: `v0.1.2`; its source distribution,
  wheel, Windows bridge executable, hashes, and provenance remain immutable.
- Current source/package version: `0.2.0`; it is a reviewed candidate and is not
  tagged or published.
- The 0.2.0 Windows installer, bridge, standalone executable, configurator, and
  portable bundle pass CI but are not public release downloads yet.
- Python archives are built from an exact allowlist and audited for wheel entry
  points, packaged skills, bounds, and every `RECORD` hash/size.
- Candidate Windows binaries are unsigned; CI and SHA-256 are not code
  signatures, and no production-ready or universal-compatibility claim is made.

The candidate record and remaining gates are in
[`docs/releases/v0.2.0.md`](docs/releases/v0.2.0.md) and
[`docs/RELEASE_0_2_0_CHECKLIST.md`](docs/RELEASE_0_2_0_CHECKLIST.md).
Published v0.1.2 installation instructions remain in
[`docs/INSTALL_FROM_RELEASE.md`](docs/INSTALL_FROM_RELEASE.md).

## Public MCP contract

The current public surface contains:

- 159 registered MCP tools;
- 157 public `DipTraceService` methods;
- 148 explicit Facade-to-domain-service delegations;
- one server-owned AnyIO worker-thread boundary for all registered tools.

The complete wire-level `tools/list` contract is frozen in
[`reference/mcp-tools-list.snapshot.json`](reference/mcp-tools-list.snapshot.json):
159 tools, 142,746 canonical UTF-8 bytes, SHA-256
`073f53681306fd13c5f3f29d61baed9a83fc9eb5c1ed14883846005a39d812db`.

A registered tool is not automatically available for every document and is not
a claim of real DipTrace round-trip verification. See
[`docs/MCP_TOOLS.md`](docs/MCP_TOOLS.md).

## Main capabilities

### Read and model

- normalised PCB, schematic, Component Library, and Pattern Library models;
- stable object identifiers, selectors, spatial queries, and connectivity;
- design rules, stackup, net classes, via styles, traces, pours, lengths, and
  differential pairs;
- BOM extraction, consistency checks, and bounded export records;
- byte-preserving XML access for supported encodings, with hostile DTD/entity
  input rejected.

### Review and analysis

- bounded DRC/ERC, connectivity, BOM, assembly, DFM/DFA/DFT, thermal-metadata,
  and design-comparison workflows;
- persistent findings and explicit skipped/partial categories;
- NetClass-aware routing and trace-to-trace clearance resolution;
- preliminary Hammerstad-Jensen microstrip and IPC-2141 centred stripline
  calculations;
- optional typed Freerouting, ngspice, and openEMS process boundaries.

These checks are engineering assistance, not fabrication, assembly, or
regulatory sign-off.

### Guarded writes

- component and schematic-part move, rotate, side, lock, value, property,
  pattern, alignment, distribution, and grouping operations;
- board-text, NetClass, test-point, trace, via, and panelisation edits;
- schematic sheets, parts, wires, labels, connectivity, and no-connect state;
- additive and guarded exact schematic-to-PCB synchronisation;
- synthetic PCB/schematic scaffolding and seed-based creation;
- transaction preview, validation, expected SHA-256, commit, backup, rollback,
  and conservative write-impact limits;
- live `apply`/`cancel` bridge flow with exchange-path and original-file SHA
  revalidation.

`dry_run=true` is the default where exposed. Raw XML editing remains an expert
escape hatch.

### Placement and routing

- deterministic silkscreen and bounded local placement plans;
- trace/via primitives and bounded multi-layer 45-degree A* routing;
- congestion-ordered multi-net routing with bounded batch-local rip-up/retry;
- atomic centreline-based differential-pair routing;
- DSN export, guarded Freerouting jobs, and SES inspection/import.

The router is not push-and-shove, free-angle, or a global EDA autorouter.

## Architecture

```text
MCP client (Codex / Claude / other)
                 |
                 | stdio or loopback Streamable HTTP
                 v
       FastMCP server.py
                 |
                 v
 DipTraceService public Facade
                 |
                 +--> typed in-process domain services
                 +--> shared stores, cache, policy, and document gateway
                 |
                 v
       XML files / shared state
                 ^
                 |
       diptrace_mcp_bridge.exe
                 ^
                 |
              DipTrace
```

`DipTraceService` remains the stable public Facade and top-level dependency
owner. Domain implementations live under `src/diptrace_mcp/services/`; they
receive narrow typed dependencies and do not hold the complete Facade or create
duplicate stores. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/SERVICE_DECOMPOSITION.md`](docs/SERVICE_DECOMPOSITION.md).

## Safety model

The principal write invariants are:

1. caller paths remain inside configured allowed roots;
2. input XML is bounded, reparsed, and checked before mutation;
3. previews and commits are bound to exact SHA-256 values;
4. existing targets are backed up before replacement;
5. writes use temporary files and `os.replace`;
6. policy and conservative write-impact limits are enforced;
7. live apply rechecks the working SHA, exchange path, and original exchange
   SHA before replacement;
8. explicit cancel leaves the exchange XML unchanged;
9. trust/evidence authority cannot be minted by user-controlled sidecars.

The capability report intentionally does not claim complete trust-invalidation
coverage for `plan_apply`, `ses_import`, `schematic_to_pcb_sync`, and
`live_session_apply`. Q1 Component Angle GUI/re-export evidence also remains
`NOT_RUN`, so rotation results retain a structured warning.

## Data Handling

- `DIPTRACE_MCP_WORKSPACE` selects the ordinary design workspace; paths remain
  subject to `DIPTRACE_MCP_ALLOWED_ROOTS` and literal caller-path checks.
- `DIPTRACE_MCP_STATE_DIR` stores local records plus live-session `original.xml`
  and `working.xml`; explicit `apply` or `cancel` controls finalisation.
- Freerouting, ngspice, and openEMS run only through typed local process
  boundaries and isolated job directories; online sourcing is disabled by
  default.
- MCP `stdio` keeps traffic on local process pipes and does not create a network
  listener.
- `streamable-http` is intended only for trusted loopback use, for example
  `127.0.0.1:8765`; OAuth and multi-user isolation are not implemented.
- User projects, private evidence, proprietary libraries, and screenshots are
  not uploaded or committed automatically; the operator controls external data
  and publication.

## Installation

### Current source tree

Python 3.10 or newer is required.

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

Windows PowerShell:

```powershell
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\diptrace-mcp.exe --help
```

Install `.[geometry]` when exact Shapely/GEOS geometry paths are required.
Source installation does not install the DipTrace executable plug-in
automatically; see [`plugin/`](plugin/) and
[`docs/USAGE.md`](docs/USAGE.md) for the advanced path.

### Published release assets

Use [`v0.1.2`](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.2)
for the latest immutable public assets. The 0.2.0 installer and portable bundle
are candidate build outputs only until a `v0.2.0` GitHub release is published.
Do not treat filenames shown in candidate documentation as existing downloads.

## Validation

The CI matrix covers:

- Linux Python 3.10, 3.12, and 3.13;
- macOS and Windows Python 3.12;
- Shapely/GEOS and explicit no-Shapely fallback paths;
- Ruff, strict Mypy, DCO, public tool snapshots, service-Facade contract,
  service-decomposition safety, event-loop responsiveness, release artifacts,
  and provenance/compliance checks;
- native Windows bridge, standalone server, configurator, installer, and
  portable-bundle builds and smoke tests.

The exact PR #49 documentation/release-candidate head passed CI run
`30940972328` and Windows installer run `30940972331`. Earlier controlled live
acceptance covers selected DipTrace 5.3 schematic and DipTrace 5.2.0.4
PCB/Schematic paths. It does not prove universal DipTrace 5.x compatibility.

## Remaining release blockers for v0.2.0

- clean Windows 11 install, repair, and uninstall acceptance;
- real current DipTrace 5 checks across PCB, Schematic, Component, and Pattern
  modules;
- real Codex and Claude Desktop configuration/restart verification;
- elevated plug-in installation while preserving the original user profile;
- custom-state preservation acceptance;
- final frozen artifacts, per-file checksums, public-download verification, and
  any required external legal review.

## Documentation

- [Usage](docs/USAGE.md)
- [MCP tools and resources](docs/MCP_TOOLS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Testing](docs/TESTING.md)
- [Roadmap and actual status](docs/ROADMAP.md)
- [Review coverage](docs/REVIEW_ENGINE.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Transactions](docs/TRANSACTIONS.md)
- [Windows installer](docs/WINDOWS_INSTALLER.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Open compatibility questions](docs/OPEN_QUESTIONS.md)

## Contributing and security

Contributions are accepted under the DCO 1.1 and provenance/privacy rules in
[`CONTRIBUTING.md`](CONTRIBUTING.md). The repository owner retains merge
authority. Report suspected vulnerabilities only through the private channel
in [`SECURITY.md`](SECURITY.md), not through public issues.

The project does not claim Novarm/DipTrace endorsement, a production deployment
base, independent review, signed binaries, universal compatibility, or complete
manufacturing sign-off.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).