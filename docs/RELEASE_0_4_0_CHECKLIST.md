# v0.4.0 Release Checklist

Version: `0.4.0`
Tag: `v0.4.0`
Release class: published unsigned development release
Release manager: `fireostendere` (solo-maintainer exception)

## Source and contract

- [x] Version `0.4.0` selected without reusing an existing tag/version.
- [x] Public MCP surface remained frozen at 167 tools.
- [x] A1-A8 implementation stayed behind existing guarded semantic boundaries.
- [x] Exact cross-platform candidate frozen at `72750d195e204cf0c11c04d71364055ca7634c6b`.
- [x] Release tag target frozen at `b4c0132283ff16a0bca81567df6704d1f6a73c7f`.

## Documentation and repository quality

- [x] README, roadmap, platform, testing, release and distribution docs synchronized.
- [x] Linux and macOS one-command/visible/headless guides exist.
- [x] Changelog and v0.4.0 release record exist.
- [x] `check_documentation_state.py` and release metadata checks passed on the candidate.
- [x] Linux 3.10/3.13, Linux geometry/fallback, macOS and Windows test jobs passed.
- [x] Combined supported-environment coverage, Ruff, Mypy and DCO passed.
- [x] Release/privacy/provenance/compliance/event-loop/artifact audits passed.
- [x] Frozen 167-tool public contract check passed.
- [x] PyPI wheel/sdist build, audit and clean-install smoke passed.
- [x] MCPB/registry preparation passed as validation-only evidence.

## Platform gates

- [x] Windows split installer/portable build and lifecycle smoke passed (run `31974338063`).
- [x] Ubuntu 24.04 x86-64 one-command install, Wine/DipTrace GUI, bridge, private-Xvfb
  headless worker and idempotent reinstall passed (run `31974338096`).
- [x] macOS 15 Apple Silicon and Intel clean install, official DMG verification,
  bundled Wine, bridge, real GUI, hidden desktop/doctor and idempotent reinstall
  passed (run `31974338039`).
- [x] Repository CI passed on the exact candidate (run `31974338117`).

## Publication

- [x] Created immutable annotated `v0.4.0` tag object
  `3794c32c7d94456aec2ed358326e953e21e3fa21`.
- [x] Tag points to exact release target `b4c0132283ff16a0bca81567df6704d1f6a73c7f`.
- [x] GitHub release `v0.4.0` published (release ID `371451484`, workflow
  `31976705266`).
- [x] Published per-user installer, administrator plug-in installer, portable ZIP
  and one `SHA256SUMS.txt`; recorded final sizes/hashes.
- [x] Published `diptrace-mcp==0.4.0` through PyPI OIDC Trusted Publishing
  (workflow `31976705280`).
- [x] PyPI returned HTTP `200 OK` for wheel and sdist and generated attestations.
- [x] GitHub API release metadata confirms uploaded asset digests.
- [ ] Independent public-byte redownload plus reinstall/smoke from a separate
  network path is not yet recorded.
- [x] Immutable publication fields are filled in `docs/releases/v0.4.0.md`.

## Publication boundary

No v0.4.0 MCPB was attached to the public release. Preparation-only MCPB evidence
must not be promoted to a published-asset claim. Existing `v0.4.0` GitHub/PyPI
bytes are immutable; corrections require a new version.
