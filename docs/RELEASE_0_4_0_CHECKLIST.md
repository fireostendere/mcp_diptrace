# v0.4.0 Release Checklist

Version: `0.4.0`  
Planned tag: `v0.4.0`  
Release class: unsigned development prerelease  
Release manager: `fireostendere` (solo-maintainer exception)

Publication is forbidden while any blocking item below is incomplete or red.

## Source and contract

- [x] Version selected as `0.4.0` without reusing an existing tag/version.
- [x] Public MCP surface remains frozen at 167 tools.
- [x] A1–A8 implementation is behind existing guarded semantic boundaries; no
  speculative global optimizer, push-and-shove or OAuth scope added.
- [ ] Final exact candidate commit frozen after documentation/platform fixes.
- [ ] PR #112 merge tree verified against that candidate.

## Documentation — blocking

- [ ] README reflects v0.4.0 candidate/current platform paths.
- [x] Linux one-command/visible/headless guide exists.
- [x] macOS one-command/visible/headless guide exists.
- [ ] `docs/HEADLESS_GUI.md` covers Windows, Linux/Xvfb and macOS hidden desktop.
- [ ] Roadmap/current-state docs reflect source/package `0.4.0`.
- [ ] Release process/testing/distribution docs describe the multi-platform gates.
- [ ] Changelog is frozen for v0.4.0.
- [x] Candidate release record exists at `docs/releases/v0.4.0.md`.
- [ ] `check_documentation_state.py` and documentation tests pass on final head.
- [ ] `check_release_metadata.py` passes on final head.

Historical v0.3.0/v0.2.x records must remain historical and must not be rewritten
as if current evidence existed at their publication time.

## Windows — blocking

- [ ] Windows installer workflow builds `0.4.0` assets, not `0.3.0` filenames.
- [ ] Standalone frozen server build/smoke passes.
- [ ] Existing bridge build/signature-status smoke passes.
- [ ] Split per-user/admin installer build passes.
- [ ] Install/repair/uninstall and Unicode/space-path lifecycle smoke passes.
- [ ] Portable bundle checksum/audit passes.
- [ ] Frozen MCP stdio `initialize -> tools/list -> capabilities -> read-only`
  smoke passes.
- [ ] Headless Windows bridge/GUI helper checks pass.

Windows binaries remain explicitly unsigned unless a protected signing identity
is actually configured and verified.

## Linux — blocking

- [ ] Fresh Ubuntu 24.04 x86-64 one-command install passes.
- [ ] Official/pinned DipTrace 5.3.0.3 installation under Wine passes.
- [ ] Frozen MCP stdio smoke through installed wrapper passes.
- [ ] Shared-prefix bridge smoke passes.
- [ ] Real Schematic GUI liveness under private Xvfb passes.
- [ ] Headless GUI worker uses private Xvfb and passes native-desktop smoke.
- [ ] Idempotent reinstall/doctor passes.

## macOS — blocking

- [x] Exploratory Apple Silicon and Intel runtime proof passed in run
  `31967736428`.
- [ ] Permanent workflow builds the MCP runtime from the current candidate.
- [ ] Fresh macOS 15 Apple Silicon one-command install passes.
- [ ] Fresh macOS 15 Intel one-command install passes.
- [ ] Official DipTrace 5.3.0.3 DMG hash/version verification passes.
- [ ] Frozen MCP stdio smoke through the bundled Wine prefix passes.
- [ ] Shared-prefix bridge smoke passes.
- [ ] Real Schematic GUI liveness passes.
- [ ] Hidden Win32 desktop worker proves input desktop remains `Default`.
- [ ] Native-worker smoke and automation doctor pass.
- [ ] Idempotent reinstall passes.

The macOS release claim does not include a full native `.dch`/`.dip`
Save/Close/Reopen round-trip until suitable native fixture evidence exists.

## Repository quality — blocking

- [ ] Linux 3.10 and 3.13 tests pass.
- [ ] Linux geometry + coverage passes.
- [ ] Linux no-Shapely fallback passes.
- [ ] macOS Python test/bridge job passes.
- [ ] Windows Python test/bridge job passes.
- [ ] Combined supported-environment coverage gate passes.
- [ ] Ruff and mypy pass.
- [ ] DCO passes.
- [ ] release/privacy/provenance/compliance/event-loop audits pass.
- [ ] public release artifact allowlist audit passes.
- [ ] frozen `tools/list` contract check passes.
- [ ] PyPI wheel/sdist build, audit and clean-install smoke pass.
- [ ] MCPB/registry metadata checks pass when included in v0.4.0 assets.

## Publication — blocking

- [ ] Merge PR #112 only after every applicable pre-release gate is green.
- [ ] Create a new annotated `v0.4.0` tag at the verified exact merge commit.
- [ ] Build/fetch final assets from that tag/commit only.
- [ ] Generate one SHA-256 manifest covering every published asset.
- [ ] Publish GitHub v0.4.0 as an unsigned development prerelease.
- [ ] Publish `diptrace-mcp==0.4.0` through PyPI OIDC Trusted Publishing.
- [ ] Redownload public GitHub/PyPI assets and verify hashes/install/smokes.
- [ ] Fill immutable publication fields in `docs/releases/v0.4.0.md` without
  changing historical releases.

## Stop conditions

Do not publish if a platform gate is red, documentation is stale, a version or
artifact identity is inconsistent, the public tool contract changes
unexpectedly, or evidence would require a stronger claim than the completed
checks support.
