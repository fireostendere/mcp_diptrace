# Changelog

This file records user-visible project changes. Version `0.1.0` was the first
tagged release; the withdrawn `0.1.1` release and the corrected `0.1.2`
development release are retained as separate historical records.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

No unreleased user-visible changes are recorded.

## 0.1.2 - 2026-08-01

### Fixed

- Synchronized documentation values with the exact generated reports.
- Added release-asset installation instructions for a no-clone setup.
- Corrected MCP snapshot, coverage, and format-coverage metadata.
- Corrected release provenance and preserved the explicit revert of 0.1.1.

### Documentation

- Added Russian and English forum announcements.
- Added the release installation guide.
- Added the withdrawn `v0.1.1` record and the `v0.1.2` release record.

### Validation

- Fresh Python 3.12.3/Shapely 2.1.2/GEOS 3.13.1 run: 991 passed, 4 skipped;
  total coverage 85.941378% (16,922 statements, 2,379 missed).
- The required Linux, macOS, Windows, geometry, fallback, static-analysis,
  generated-artifact, and native-bridge matrix is the merge gate for the exact
  final PR head.
- Wheel, sdist, clean-wheel, direct-wheel/sdist-rebuilt-wheel, bridge, plugin,
  and public-download verification are required before publication.

## 0.1.1 - 2026-08-01 [Withdrawn]

This release was withdrawn because public documentation contained stale
generated figures and incomplete release-asset installation guidance. No claim
that a critical runtime vulnerability existed is made. It is superseded by
`0.1.2`; see [the withdrawal record](docs/releases/v0.1.1.md).

### Fixed

- Preserve Windows-native live exchange paths in session metadata and derive WSL
  drive-mount paths only in memory, preventing false `applied` results against a
  phantom `C:\mnt\c\...` target.
- Ignore the intentional stdout-close race used to unblock a Windows output-reader
  thread after the root process exits while a descendant inherited the pipe.

### Validation

- Completed Windows DipTrace 5.2.0.4 ↔ WSL MCP live acceptance for PCB and
  Schematic apply/cancel/wrong-SHA paths, including GUI checks, independent
  save/re-export comparisons, path invariants, and connectivity/count preservation.
- Added focused unit coverage for non-WSL Windows-path refusal, relative WSL mount
  roots, POSIX-path refusal on Windows, and invalid path-platform metadata.

### Documentation

- Reconciled English and Russian readiness, testing, architecture, compatibility,
  usage, roadmap, and release-policy documentation with the 2026-07-31 evidence.
- Added a dated code-review record and live-acceptance record.

## 0.1.0 - 2026-07-30

### Added

- Apache License 2.0 as the project-wide license (`LICENSE`), with the SPDX
  identifier `Apache-2.0` in package and citation metadata.
- Private vulnerability reporting through GitHub, published as `SECURITY.md`.
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
- Windows bridge executables are now built in an environment that contains the
  project runtime dependencies; the previous PyInstaller-only environment
  produced a bridge that failed at startup with `ModuleNotFoundError`. CI now
  smoke-runs the built executable with `--help`.

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
