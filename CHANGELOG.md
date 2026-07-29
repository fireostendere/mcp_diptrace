# Changelog

This file records user-visible project changes. Version `0.1.0` is the first
tagged release; earlier history was never tagged or published.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

## 0.1.0 - 2026-07-30

### Added

- Apache License 2.0 as the project-wide license (`LICENSE`), with the SPDX
  identifier `Apache-2.0` in package and citation metadata.
- Closed-state contribution and governance policies that do not invite
  unlicensed external contributions.
- A license decision matrix and a factual public-release checklist.
- A release process with fail-closed legal, evidence, security, and artifact
  gates.
- GitHub issue forms for bugs, feature requests, and compatibility evidence,
  plus a pull-request review template.
- Citation metadata for the repository's current development state.
- An exact, versioned release-file allowlist and CI audit for Python source
  distributions and wheels.
- Public package metadata for repository, documentation, and issue links,
  plus EDA-focused classifiers without a premature license classifier.

### Fixed

- Full pytest CI regression introduced by the release-artifact validation work.

### Clarified

- The license release blocker is resolved: Apache-2.0 is committed as
  `LICENSE`. Security-channel, contribution-provenance, and signing blockers
  remain open for a fully verified release line.
- No community size, adoption, sponsorship, vendor endorsement, signed binary,
  package-index release, or support-program acceptance is asserted.
- Python wheels intentionally contain the MCP server and eight packaged
  skills, while Windows bridge installation scripts and settings remain
  separate source/release assets.

Version `0.1.0` is published as tag `v0.1.0`; its provenance record is
[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) and the release assets on
GitHub.

[0.1.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.0
