# DipTrace MCP 0.2.1 Release Checklist

This checklist prepares version `0.2.1` for an immutable GitHub prerelease,
PyPI Trusted Publishing, a Windows MCPB asset, the official MCP Registry, and
Smithery. It does not authorize publication by itself.

## Candidate status

- Version: `0.2.1`.
- Candidate branch: `release/v0.2.1-pypi`.
- Base commit: `6e5ac7fe66fde0dd61dca52ea6cbefe1ea058f47`.
- Tag: `v0.2.1`, not created.
- GitHub Release: not created.
- PyPI project: not created or published.
- MCPB asset: CI candidate only until the final release.
- Official MCP Registry and Smithery: not published.
- Windows signing status: unsigned.
- Release class: alpha/development prerelease.

Existing `v0.2.0` tags and assets are immutable and must not be replaced.

## Scope

Version `0.2.1` packages the post-`v0.2.0` distribution work:

- deterministic Windows MCPB generation and SHA-256 output;
- official MCP Registry metadata template and concrete `server.json` generator;
- canonical registry identity `io.github.fireostendere/diptrace-mcp`;
- synchronized release and installation documentation;
- PyPI package version `0.2.1`;
- a guarded PyPI Trusted Publishing workflow;
- wheel and source-distribution validation from the exact release candidate.

No stronger production, signing, compatibility, endorsement, or manufacturing
claim is introduced.

## Automated gates

- [ ] `pyproject.toml`, package fallback version, changelog, citation metadata,
      MCPB manifest, and release documentation agree on `0.2.1`.
- [ ] Ruff and strict Mypy pass.
- [ ] DCO passes for the exact pull-request head.
- [ ] Linux Python 3.10/3.12/3.13, macOS, and Windows tests pass.
- [ ] Geometry and explicit no-Shapely fallback jobs pass.
- [ ] Public MCP snapshot, Facade contract, decomposition, event-loop,
      provenance, compliance, and release-artifact gates pass.
- [ ] Wheel and source distribution build from the exact allowlist.
- [ ] `twine check --strict` passes for both Python distributions.
- [ ] Clean virtual environments install and smoke both the wheel and sdist.
- [ ] Windows standalone server, bridge, installer, portable bundle, and MCPB
      candidate build successfully.
- [ ] MCPB checksum and manifest inspection pass.
- [ ] The final candidate head has no unreviewed changes after the green runs.

## PyPI Trusted Publisher setup

Create a pending publisher on PyPI before the first upload. Use these exact
values:

- PyPI project name: `diptrace-mcp`;
- GitHub owner: `fireostendere`;
- GitHub repository: `mcp_diptrace`;
- workflow filename: `pypi.yml`;
- GitHub environment: `pypi`.

Create the GitHub environment `pypi` and restrict it to the release manager.
Where repository settings allow it, require approval and restrict deployment to
the protected `v0.2.1` tag.

The workflow uses OpenID Connect. Do not create or store a long-lived PyPI API
token. The publish job must retain only `contents: read` and `id-token: write`.
It must contain only artifact download and the pinned PyPA publishing action.

A pending publisher does not reserve the package name until the first successful
publication. Re-check that `diptrace-mcp` remains available immediately before
publication.

## Manual acceptance still open

The following remain limitations and must not be marked complete without dated
real-system evidence:

- clean Windows 11 install, repair, and uninstall acceptance;
- current real DipTrace 5 across PCB, Schematic, Component, and Pattern modules;
- preservation of pre-existing custom state;
- real Codex and Claude Desktop configuration, restart, and
  `get_capabilities`;
- elevated Program Files plug-in installation with user-profile client config;
- external legal review or Novarm/DipTrace permission where required;
- Q1 Component Angle GUI/re-export evidence, which remains `NOT_RUN`.

These items prohibit stronger claims but do not prevent an explicitly unsigned
alpha/development prerelease under the documented solo-maintainer exception.

## Publication sequence

1. Complete review and exact-head CI on the release pull request.
2. Merge only after the candidate is frozen and approved.
3. Create annotated tag `v0.2.1` at the exact approved merge commit.
4. Build the final GitHub assets from that tag, including wheel, sdist, Windows
   installer, portable bundle, MCPB, checksums, SBOM, notices, provenance, and
   release record.
5. Publish an explicitly unsigned GitHub prerelease and redownload every public
   asset for checksum and smoke verification.
6. Confirm the PyPI pending publisher and protected `pypi` environment use the
   exact owner, repository, workflow filename, environment, and project name.
7. Manually dispatch `.github/workflows/pypi.yml` from tag `v0.2.1` with
   `publish=true`.
8. Verify the PyPI release files, Trusted Publisher identity, attestations,
   project links, README rendering, and version metadata.
9. In a clean environment run:

   ```bash
   python -m pip install --no-cache-dir diptrace-mcp==0.2.1
   diptrace-mcp --help
   ```

10. Generate concrete `server.json` from the publicly downloaded MCPB URL and
    verified SHA-256, then submit the exact version to the official MCP Registry
    and Smithery.
11. Record immutable URLs, workflow runs, hashes, PyPI file identities,
    attestations, registry metadata, and public-download results in a
    post-release documentation pull request.

## Fail-closed rules

- Do not publish from `main`, a branch, or a lightweight tag.
- Do not move or replace an existing tag or published file.
- Do not enable `skip-existing` for the production PyPI upload.
- Do not publish a wheel or sdist different from the artifact validated by the
  build job.
- Do not claim PyPI, Registry, Smithery, signing, or real DipTrace acceptance
  until the corresponding public evidence exists.
