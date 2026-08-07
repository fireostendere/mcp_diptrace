# MCP distribution and package publication

## Current state

Version `v0.2.1` is the current published development prerelease.

Published and immutable release identities:

- GitHub prerelease: `v0.2.1`;
- PyPI package: `diptrace-mcp==0.2.1`;
- Windows installer: `DipTrace-MCP-Setup-0.2.1.exe`;
- portable bundle: `DipTrace-MCP-Portable-0.2.1.zip`;
- Windows MCPB: `DipTrace-MCP-0.2.1-windows.mcpb`;
- canonical registry identity: `io.github.fireostendere/diptrace-mcp`.

The annotated tag and published files must never be moved or replaced. A corrected build requires a new version.

The release remains explicitly unsigned alpha/development software. Publication does not imply production readiness, universal DipTrace 5.x compatibility, Novarm/DipTrace endorsement or completed real-system acceptance.

## Distribution roles

- **PyPI** distributes the cross-platform Python MCP server, packaged skills and command-line entry points.
- **GitHub Release** is the immutable release set for Windows installer, portable bundle, MCPB, Python packages, hashes and provenance records.
- **MCPB** contains the self-contained Windows stdio server for clients that support local bundles.
- **MCP registries/directories** index the immutable release identity; they do not strengthen the project's compatibility claims.

The Python package and MCPB do not silently install the DipTrace bridge plug-in. Live exchange still requires the matching Windows bridge/settings and real host acceptance.

## PyPI Trusted Publishing

`0.2.1` was published through the guarded tag-bound GitHub OIDC workflow. The authorized identity is:

```text
PyPI project:       diptrace-mcp
GitHub owner:       fireostendere
GitHub repository:  mcp_diptrace
Workflow filename:  pypi.yml
Environment:        pypi
```

No long-lived PyPI token is required. Future versions must preserve the build/publish separation and publish only validated artifacts from an exact annotated tag.

A clean package smoke for the published version is:

```bash
python -m pip install --no-cache-dir diptrace-mcp==0.2.1
diptrace-mcp --help
```

## Windows and MCPB build path

The repository retains deterministic Windows server, installer, portable and MCPB builders. They are build infrastructure, not evidence that a clean real Windows machine or real MCP client accepted the release.

A future release must:

1. build from the exact candidate/tag;
2. validate wheel/sdist and Windows artifacts;
3. freeze filenames, sizes and SHA-256 values;
4. publish immutable bytes;
5. redownload the public bytes and repeat checksum/install/stdio smoke;
6. record the public identities in the release record.

The existing `v0.2.1` publication is already complete; these steps are not a pending `0.2.1` task.

## Registry / Smithery metadata

Registry metadata must reference only public immutable bytes and their verified SHA-256. Never point registry metadata at a transient CI artifact.

For a future version, generate metadata from the final public MCPB URL and hash, validate it against the registry's then-current schema/tooling, publish it, and record the returned version identity. Registry publication remains distribution metadata; it does not substitute for DipTrace/Windows/client acceptance.

## Manual acceptance boundary

All remaining acceptance work is external/manual and is maintained in `docs/ROADMAP.md` plus the generated manual acceptance pack:

```bash
python scripts/prepare_manual_acceptance.py acceptance \
  --version 0.2.1 \
  --commit <exact-commit>
```

That matrix covers clean Windows install/repair/uninstall, current real DipTrace PCB/Schematic/Component/Pattern behavior, real Codex and Claude Desktop restart/configuration, elevated plug-in installation and custom-state preservation. Claim-specific legal/openEMS/public-redownload work is separately identified.

## Immutability rule

Do not replace bytes under an existing GitHub tag, PyPI version, Registry version or directory release. If a material issue is found, document the affected version, preserve its original identity, withdraw/yank only where appropriate, and publish a corrected new version.
