# DipTrace MCP

<!-- mcp-name: io.github.fireostendere/diptrace-mcp -->

[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml)
[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)

DipTrace MCP is a local Model Context Protocol server for reading, analysing,
reviewing, and performing guarded edits on DipTrace PCB and schematic projects.
It consists of:

- `diptrace-mcp`, the MCP server used by Codex, Claude Desktop, and other MCP
  clients;
- `diptrace_mcp_bridge.exe`, the Windows plug-in bridge for projects currently
  open in DipTrace;
- an internal EDA-intelligence layer for deterministic schematic/PCB intent,
  candidate generation, scoring and guarded improvement.

## Current status

Version `0.2.1` is the current distribution line. It is prepared as an explicitly
unsigned alpha/development release with:

- the Python package `diptrace-mcp==0.2.1` for PyPI;
- `DipTrace-MCP-Setup-0.2.1.exe`;
- `DipTrace-MCP-Portable-0.2.1.zip`;
- `DipTrace-MCP-0.2.1-windows.mcpb`;
- wheel, source distribution, checksums, SBOM, dependency, notice, provenance,
  and release records.

The previous [`v0.2.0`](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0)
release remains immutable. Existing tags and files are never replaced.

The Windows executables are unsigned. CI, SHA-256, PyPI Trusted Publishing, and
package attestations establish tested behaviour, byte identity, and publication
provenance. They do not create a trusted Authenticode signature, universal
compatibility, independent review, or production readiness.

## Public Release Status

The project uses the OSI-approved Apache-2.0 open-source `LICENSE`. Participation
and release controls are documented in `CONTRIBUTING.md`, `GOVERNANCE.md`,
`docs/LICENSE_DECISION.md`, `docs/PUBLIC_RELEASE_CHECKLIST.md`,
`docs/RELEASE_PROCESS.md`, `CHANGELOG.md`, and `CITATION.cff`. Security reports
use the private security channel; a verified Code of Conduct enforcement channel
is not yet published.

- Python archives are built from an exact allowlist and audited for entry
  points, packaged skills, bounds, metadata, and every `RECORD` hash and size.
- PyPI publication uses GitHub OpenID Connect and a protected `pypi`
  environment; no long-lived PyPI API token is stored.
- The PyPI publish job receives only the already validated wheel and source distribution
  from the separate build job.
- Windows installer, bridge, standalone executable, configurator, portable
  bundle, and MCPB remain unsigned development assets.
- CI, checksums, Trusted Publishing, and attestations do not create a
  code-signing or production-readiness claim.

## What it provides

The public MCP surface contains 159 registered tools, 157 public
`DipTraceService` methods, and 148 explicit Facade-to-domain-service
delegations. Runtime `get_capabilities` remains authoritative for the active
installation and document.

Main capability groups:

- PCB, schematic, Component Library, and Pattern Library reading and modelling;
- structured DRC/ERC, connectivity, BOM, assembly, DFM/DFA/DFT, comparison, and
  signal-integrity assistance;
- guarded component, schematic, NetClass, text, trace, via, panelisation,
  placement, routing, and synchronisation workflows;
- preview, expected SHA-256, policy, backup, atomic replace, rollback, and
  live-session apply/cancel boundaries;
- optional Freerouting, ngspice, and openEMS process adapters;
- local stdio and trusted-loopback Streamable HTTP transports.

Internal EDA development deliberately does not expand that public tool surface
one heuristic at a time. PCB Generation A adds an internal engineering-intent
model and intent-aware placement v2: component/function grouping, multi-role net
classification, electrical criticality, conservative ground/power strategy and
placement scoring above the existing geometry legalizer. Missing current, edge
rate, impedance and other physical facts remain explicit unknowns.

DipTrace MCP is not a replacement for DipTrace's interactive EDA engine. It
does not claim native Component/Pattern Library mutation, native Gerber/NC Drill
generation, fabrication sign-off, Novarm/DipTrace endorsement, universal
DipTrace 5.x compatibility, field-solver accuracy, PI/EMC sign-off, or globally
optimal PCB placement.

## Installation

### PyPI

Python 3.10 or newer is required:

```bash
python -m pip install diptrace-mcp==0.2.1
diptrace-mcp --help
```

The PyPI package installs the Python MCP server and packaged skills. It does not
install the Windows DipTrace bridge plug-in automatically.

### Windows installer

1. Download `DipTrace-MCP-Setup-0.2.1.exe` and `SHA256SUMS.txt` from the same
   `v0.2.1` GitHub Release.
2. Verify the SHA-256 value.
3. Run the installer and select the DipTrace location, workspace, state
   directory, and optional Codex/Claude configuration.
4. Restart DipTrace and the MCP client.
5. Call `get_capabilities`.

Windows may show a SmartScreen warning because the binaries are unsigned.

### Portable Windows bundle

Download and verify `DipTrace-MCP-Portable-0.2.1.zip`, extract it to a stable
location, read its `README_FIRST.txt`, and use the included helper tools.

### Python source installation

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

See [installation from release assets](docs/INSTALL_FROM_RELEASE.md) for the
complete path.

## MCPB, Registry, and Smithery

Version `0.2.1` adds the immutable distribution route prepared after `v0.2.0`:

- deterministic Windows MCPB packaging;
- canonical Registry identity `io.github.fireostendere/diptrace-mcp`;
- official Registry `server.json` generation from a public MCPB URL and verified
  SHA-256;
- Smithery publication from the same public MCPB;
- PyPI Trusted Publishing for the Python server.

The MCPB contains the self-contained Windows stdio server. It does not silently
install the DipTrace bridge plug-in. Live exchange requires the matching bridge
and settings from the same GitHub release.

See [MCP distribution and package publication](docs/MCP_DISTRIBUTION.md).

## Architecture

```text
MCP client (Codex / Claude / other)
                 |
                 | stdio or trusted loopback HTTP
                 v
             FastMCP
                 |
                 v
        application/service layer
                 |
                 +--> typed domain services
                 +--> internal EDA intelligence
                 |       +--> schematic layout/optimizer
                 |       +--> PCB intent/placement/optimizer
                 +--> shared stores, policy, cache, document gateway
                 |
                 v
        typed semantic operations
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

Intelligent layout modules emit normal semantic operations and stay behind the
existing preview/SHA/transaction/review safety path. The public MCP contract is
not a second EDA engine.

## Safety model

The main write invariants are:

1. paths remain inside configured allowed roots;
2. XML is bounded and parsed before mutation;
3. previews and commits are bound to exact SHA-256 values;
4. existing targets are backed up;
5. writes use temporary files and atomic replacement;
6. policy and conservative write-impact limits are enforced;
7. live apply rechecks the working, exchange, and original-file identities;
8. cancel leaves the host exchange file unchanged;
9. user-controlled sidecars cannot mint high trust;
10. internal EDA heuristics cannot silently invent physical facts or bypass the
    guarded semantic-operation path.

The private/manual Q1 Component Angle GUI/re-export campaign is PASS on DipTrace
PCB Layout 5.3.0.3. Package-owned public evidence/trust promotion remains a
separate reviewed contract, so conservative public warnings are not removed
merely because the private campaign passed. Several other real
Windows/DipTrace/client acceptance items remain disclosed limitations.

## Data Handling

- `DIPTRACE_MCP_WORKSPACE` selects the ordinary workspace; caller paths remain
  subject to `DIPTRACE_MCP_ALLOWED_ROOTS` and literal path checks.
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

## Documentation

- [Usage](docs/USAGE.md)
- [MCP tools and resources](docs/MCP_TOOLS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [PCB design engine and A-D roadmap](docs/PCB_DESIGN_ENGINE.md)
- [Placement engine](docs/PLACEMENT_ENGINE.md)
- [Domain model](docs/DOMAIN_MODEL.md)
- [MCP distribution and package publication](docs/MCP_DISTRIBUTION.md)
- [Windows and Python installation](docs/INSTALL_FROM_RELEASE.md)
- [Testing](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Transactions](docs/TRANSACTIONS.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [v0.2.1 release checklist](docs/RELEASE_0_2_1_CHECKLIST.md)
- [v0.2.1 release record](docs/releases/v0.2.1.md)

## Contributing, security, and license

Contributions use DCO 1.1 and the provenance/privacy rules in
[CONTRIBUTING.md](CONTRIBUTING.md). Report suspected vulnerabilities through the
private channel in [SECURITY.md](SECURITY.md), not public issues.

Apache License 2.0. See [LICENSE](LICENSE).
