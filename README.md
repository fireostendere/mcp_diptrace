# DipTrace MCP

<!-- mcp-name: io.github.fireostendere/diptrace-mcp -->

[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml)
[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)

DipTrace MCP is a local Model Context Protocol server and Windows live-XML bridge for reading, analysing, reviewing and performing guarded edits on DipTrace PCB, schematic and library data.

The repository also contains internal deterministic EDA layers for schematic layout, PCB design intelligence and an optional cinematic presentation/replay subsystem. Those layers deliberately reuse the existing semantic-operation, preview, SHA, transaction and review boundaries instead of creating a second unsafe write path.

## Current status

The source/package version is `0.2.1`. The annotated `v0.2.1` GitHub development prerelease and `diptrace-mcp==0.2.1` on PyPI were published on 2026-08-05. Published `v0.2.1` assets include the Windows installer, portable bundle, MCPB, wheel, source distribution, checksums and provenance records.

Development has continued on `main` after the release without changing the public MCP contract. The public surface remains:

- **159 registered MCP tools**;
- **157 public `DipTraceService` methods**;
- **148 explicit Facade-to-domain-service delegations**.

Runtime `get_capabilities` remains authoritative for the active installation, document, policy and optional adapters.

The Windows executables are unsigned alpha/development assets. CI, SHA-256, PyPI Trusted Publishing and package attestations establish tested behaviour, byte identity and publication provenance; they do not establish Authenticode trust, universal DipTrace compatibility, independent review or production readiness.

## What is implemented

### Guarded MCP and live bridge

- PCB, schematic, Component Library and Pattern Library parsing/querying;
- structured DRC/ERC, connectivity, BOM, assembly, DFM/DFA/DFT and comparison workflows;
- guarded semantic writes, previews, expected SHA-256, backups, atomic replacement, transactions and rollback;
- live DipTrace apply/cancel sessions through the Windows XML bridge;
- bounded local placement/routing and schematic authoring support;
- optional Freerouting, ngspice and openEMS process adapters;
- stdio and trusted-loopback Streamable HTTP transports.

### Intelligent schematic layout

The internal schematic track currently includes:

- deterministic design intent, functional blocks and provenance-bearing reference motifs;
- hierarchical placement and bounded multi-candidate placement optimisation;
- conservative Component Library pin-geometry resolution;
- non-mutating wire planning with readability metrics and explicit placement feedback;
- pin-aware joint placement/routing scoring;
- bounded placement repair driven by route feedback.

Selective atomic replacement of existing wires after a placement repair, stronger sheet-level congestion scheduling, automatic reference-motif ingestion and product-level real-DipTrace readability acceptance remain future work. See [Schematic Layout Engine](docs/SCHEMATIC_LAYOUT_ENGINE.md).

### PCB design engine — Generations A-D

The internal PCB design engine is implemented through four bounded generations:

- **Generation A:** engineering intent, functional blocks, multi-role net classification, explicit electrical constraints and intent-aware placement v2;
- **Generation B:** exported stackup/reference context, conservative PDN/current-path analysis, return-path integration, timing-gated aggressor/victim triage and via roles;
- **Generation C:** routing-policy compilation, route ordering, observed-route SI checks, copper/topology strategy and bounded placement feedback;
- **Generation D:** lexicographically safe whole-board candidate selection plus a synthetic engineering-trap benchmark catalog.

Missing current, edge rate, impedance, stackup authority, current density and other physical facts remain explicit unknowns. Synthetic/analytic results are not promoted to field-solver, PI, EMC, thermal or native-DipTrace proof. Real-DipTrace product acceptance for Generation D remains pending. See [PCB Design Engine](docs/PCB_DESIGN_ENGINE.md).

### Cinematic demo mode

`main` includes an optional Windows presentation layer that can replay already-planned schematic/PCB actions through the visible DipTrace UI and record MP4/GIF demonstrations.

It provides version/editor-specific UI profiles, affine design-coordinate to normalized-client-coordinate calibration, semantic replay adapters, deterministic pacing, dry-run playback and ffmpeg recording helpers. It is **presentation automation, not the authoritative engineering write path**: normal XML preview/SHA/transaction validation remains authoritative.

Real-client calibration and verified UI macros are still required for the exact DipTrace configuration used for recording. See [Cinematic Demo Mode](docs/CINEMATIC_DEMO_MODE.md).

## Installation

### PyPI

Python 3.10 or newer:

```bash
python -m pip install diptrace-mcp==0.2.1
diptrace-mcp --help
```

The Python package installs the MCP server and packaged skills. It does not install the Windows DipTrace bridge automatically.

### Windows installer

1. Download `DipTrace-MCP-Setup-0.2.1.exe` and `SHA256SUMS.txt` from the same `v0.2.1` GitHub prerelease.
2. Verify the SHA-256 value.
3. Run the installer and select the DipTrace location, workspace, state directory and optional client configuration.
4. Restart DipTrace and the MCP client.
5. Call `get_capabilities`.

Windows may show a SmartScreen warning because the binaries are unsigned.

### Portable bundle / MCPB

`DipTrace-MCP-Portable-0.2.1.zip` contains the standalone Windows server, bridge, settings and helper tools. `DipTrace-MCP-0.2.1-windows.mcpb` contains the self-contained Windows stdio server for compatible MCP clients. The MCPB does not silently install the DipTrace bridge.

See [Install from Published Release Assets](docs/INSTALL_FROM_RELEASE.md) and [MCP Distribution](docs/MCP_DISTRIBUTION.md).

### Source checkout

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,geometry]'
diptrace-mcp --help
```

## Architecture

```text
MCP client
    |
    | stdio / trusted loopback HTTP
    v
FastMCP registration + public error boundary
    |
    v
DipTraceService Facade
    |
    +--> typed domain services
    +--> shared stores / policy / cache / document gateway
    +--> internal EDA intelligence
    |      +--> schematic layout + wire/placement co-optimisation
    |      +--> PCB Generations A-D
    |
    v
typed semantic operations
    |
    v
guarded preview / SHA / transaction / review path
    |
    v
XML / live-session state <--> Windows bridge <--> DipTrace

optional presentation branch:
planned semantic actions -> calibrated cinematic replay -> visible DipTrace UI / video
```

See [Architecture](docs/ARCHITECTURE.md) and [Domain Model](docs/DOMAIN_MODEL.md).

## Safety and evidence model

The core write invariants are:

1. paths remain inside configured allowed roots;
2. XML is bounded and parsed before mutation;
3. previews and commits are bound to exact SHA-256 identities;
4. existing targets are backed up;
5. writes use temporary files plus atomic replacement;
6. policy and conservative write-impact limits are enforced;
7. live apply rechecks working/exchange/original identities;
8. cancel leaves the host exchange document unchanged for the tested accepted paths;
9. user-controlled sidecars cannot mint package-owned high trust;
10. internal EDA heuristics cannot invent missing physical facts or bypass the guarded operation path;
11. cinematic replay is not semantic acceptance evidence unless independently verified in the real host.

Manual real-host evidence is bound to the exact candidate on which it was captured. The latest accepted manual-production checkpoint is documented in [Manual Acceptance Checkpoint](docs/MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md); later development on `main` does not silently inherit that evidence.

The private/manual Q1 Component Angle campaign is PASS for DipTrace PCB Layout 5.3.0.3, while the immutable `v0.2.1` release record correctly retains `NOT_RUN` because that release predates the later campaign. Claude Desktop restart is explicitly **WAIVED, not PASS**, for the current campaign; Windows lifecycle gates remain pending.

## Important boundaries

The project does not claim:

- native Gerber/NC Drill/ODB++/IPC-2581 manufacturing generation;
- field-solver, PI, EMC or thermal sign-off from local heuristics;
- universal DipTrace 5.x compatibility;
- Novarm/DipTrace endorsement or affiliation;
- trusted Authenticode signing;
- independent review or production readiness;
- globally optimal schematic or PCB layout.

An internal raw-preserving Component/Pattern Library mutation core exists and has controlled real-editor round-trip evidence. It is not silently exposed as a new public MCP write surface.

## Development and testing

The combined supported-environment coverage gate is **90%**. The geometry-enabled Linux job intentionally keeps an **85% Linux-only floor**; coverage from Linux fallback, macOS and Windows is combined before the repository-wide 90% gate is evaluated. Per-file floors are also enforced for selected critical modules.

See [Testing](docs/TESTING.md) and [Development](docs/DEVELOPMENT.md).

## Documentation

- [Usage](docs/USAGE.md)
- [MCP Tools](docs/MCP_TOOLS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Schematic Layout Engine](docs/SCHEMATIC_LAYOUT_ENGINE.md)
- [PCB Design Engine](docs/PCB_DESIGN_ENGINE.md)
- [Placement Engine](docs/PLACEMENT_ENGINE.md)
- [Routing Engine](docs/ROUTING_ENGINE.md)
- [Transactions](docs/TRANSACTIONS.md)
- [Testing](docs/TESTING.md)
- [Release Process](docs/RELEASE_PROCESS.md)
- [Cinematic Demo Mode](docs/CINEMATIC_DEMO_MODE.md)
- [XML Compatibility](docs/XML_COMPATIBILITY.md)

## License and security

Apache-2.0. See `LICENSE`, `CONTRIBUTING.md`, `GOVERNANCE.md` and `SECURITY.md`. Security reports should use the repository's private vulnerability-reporting channel.
