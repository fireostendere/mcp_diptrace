# DipTrace MCP

<!-- mcp-name: io.github.fireostendere/diptrace-mcp -->

**English** | [Русский](README_RU.md)

[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml)
[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)

DipTrace MCP is a local Model Context Protocol server for reading, analysing,
reviewing, and performing guarded edits on DipTrace PCB and schematic projects.
It consists of:

- `diptrace-mcp`, the MCP server used by Codex, Claude Desktop, and other MCP
  clients;
- `diptrace_mcp_bridge.exe`, the Windows plug-in bridge for projects currently
  open in DipTrace.

## Current status

[`v0.2.0`](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0)
is the latest published release. It is an explicitly unsigned
alpha/development GitHub prerelease tagged at commit
`31766cb6e667dc24f3e2921decfd65c03eebd271`.

Public assets include:

- `DipTrace-MCP-Setup-0.2.0.exe`;
- `DipTrace-MCP-Portable-0.2.0.zip`;
- Python wheel and source distribution;
- `SHA256SUMS.txt`, SBOM, dependency, notice, provenance, and release records.

The Windows executables are unsigned. CI and SHA-256 establish tested behaviour
and byte identity, not a trusted publisher signature, universal compatibility,
or production readiness.

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

DipTrace MCP is not a replacement for DipTrace's interactive EDA engine. It
does not claim native Component/Pattern Library mutation, native Gerber/NC Drill
generation, fabrication sign-off, Novarm/DipTrace endorsement, or universal
DipTrace 5.x compatibility.

## Installation

### Windows installer

1. Download `DipTrace-MCP-Setup-0.2.0.exe` and `SHA256SUMS.txt` from the
   [`v0.2.0` release](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0).
2. Verify the SHA-256 value.
3. Run the installer and select the DipTrace location, workspace, state
   directory, and optional Codex/Claude configuration.
4. Restart DipTrace and the MCP client.
5. Call `get_capabilities`.

Windows may show a SmartScreen warning because the binaries are unsigned.

### Portable Windows bundle

Download and verify `DipTrace-MCP-Portable-0.2.0.zip`, extract it to a stable
location, read its `README_FIRST.txt`, and use the included helper tools.

### Python source installation

Python 3.10 or newer is required:

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

The Python wheel/source install does not install the Windows DipTrace bridge
plug-in automatically.

See [installation from release assets](docs/INSTALL_FROM_RELEASE.md) for the
complete path.

## MCPB, Registry, and Smithery preparation

Version 0.2.0 contains no MCPB and is not published to PyPI, the official MCP
Registry, or Smithery. The repository now prepares:

- a deterministic Windows MCPB builder;
- a canonical registry name: `io.github.fireostendere/diptrace-mcp`;
- an official Registry `server.json` template and generator;
- future Smithery and official Registry publication instructions.

These changes do not publish another release. A public MCPB must be shipped
under a new immutable version; existing `v0.2.0` assets must not be replaced.
See [MCP distribution preparation](docs/MCP_DISTRIBUTION.md).

## Architecture

```text
MCP client (Codex / Claude / other)
                 |
                 | stdio or trusted loopback HTTP
                 v
             FastMCP
                 |
                 v
     DipTraceService public Facade
                 |
                 +--> typed domain services
                 +--> shared stores, policy, cache, document gateway
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
9. user-controlled sidecars cannot mint high trust.

Q1 Component Angle GUI/re-export validation remains `NOT_RUN`, and several real
Windows/DipTrace/client acceptance items remain disclosed limitations.

## Documentation

- [Usage](docs/USAGE.md)
- [MCP tools and resources](docs/MCP_TOOLS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MCPB, official Registry, and Smithery preparation](docs/MCP_DISTRIBUTION.md)
- [Windows installation](docs/INSTALL_FROM_RELEASE.md)
- [Testing](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Transactions](docs/TRANSACTIONS.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [v0.2.0 release record](docs/releases/v0.2.0.md)

## Contributing, security, and license

Contributions use DCO 1.1 and the provenance/privacy rules in
[CONTRIBUTING.md](CONTRIBUTING.md). Report suspected vulnerabilities through the
private channel in [SECURITY.md](SECURITY.md), not public issues.

Apache License 2.0. See [LICENSE](LICENSE).
