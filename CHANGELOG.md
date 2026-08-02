# Changelog

## Unreleased

- disclose pending live component-angle evidence and expose structured evidence warnings;
- resolve routing and trace-to-trace review clearances from board defaults plus affected NetClasses;
- add a centralized service-to-MCP error boundary with stable public error codes and safe details;
- remove verbatim external reference extracts and source-derived inventory from public surfaces;
- add a clean-room factual inventory generator and a pending DipTrace 5.3 fixture-pack manifest;
- document the remaining live-evidence, provenance, and partial-clearance limitations.

This file records user-visible project changes. Version `0.1.0` was the first
tagged release; the withdrawn `0.1.1` release and the corrected `0.1.2`
development release are retained as separate historical records.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

### Documentation

- Activated and verified the main-branch GitHub ruleset; pull requests require
  DCO plus the eight technical CI contexts.
- Completed a post-merge security and compliance audit of the current tree and
  reachable Git history.
- Added reproducible deep secret-scanning, dependency-audit, and clean-room
  audit tools; their raw reports remain owner-private.
- Finalized the post-publication `v0.1.2` provenance with the immutable release
  commit, exact-head CI run, public asset inventory, checksum verification, and
  public-download smoke results.
- Distinguished the frozen candidate coverage measurement from the exact-head
  GitHub CI coverage measurement.
- Reconciled the public release checklist with the verification work that was
  completed during publication.
- Opened contribution intake under DCO 1.1, added provenance/privacy checks,
  and added reproducible dependency, SBOM, and signing-preparation records.
- Removed forum-announcement drafts from the public tree; external announcement
  materials are maintained privately by the repository owner.

## 0.1.2 - 2026-08-01

### Fixed

- Synchronized documentation values with the exact generated reports.
- Added release-asset installation instructions for a no-clone setup.
- Corrected MCP snapshot, coverage, and format-coverage metadata.
- Corrected release provenance and preserved the explicit revert of 0.1.1.

### Documentation

- Added the release installation guide.
- Added the withdrawn `v0.1.1` record and the `v0.1.2` release record.

### Validation

- Frozen candidate/local run: Python 3.12.3, Shapely 2.1.2, GEOS 3.13.1,
  991 passed, 4 skipped, 16,922 statements, 2,379 missed, and 85.941378%
  total coverage.
- Exact-head GitHub CI run `30709466348`: all eight required Linux, macOS,
  Windows, geometry, fallback, static-analysis, generated-artifact, and native
  bridge jobs passed; its Python 3.12.13 coverage result was 991 passed,
  4 skipped, 16,922 statements, 2,375 missed, and 85.9650% total.
- Wheel/sdist audit, direct-wheel versus sdist-rebuilt-wheel comparison,
  clean-wheel installation, CLI and MCP stdio smoke, exact-CI Windows bridge
  provenance, plug-in ZIP/settings validation, checksums, and public-download
  verification passed.
- All ten expected GitHub Release assets were present exactly once, and the
  publicly downloaded files passed `sha256sum -c SHA256SUMS.txt`.

## 0.1.1 - 2026-08-01 [Withdrawn]

This release was withdrawn because public documentation contained stale
generated figures and incomplete release-asset installation guidance. No claim
that a critical runtime vulnerability existed is made. It is superseded by
`0.1.2`; see [the withdrawal record](docs/releases/v0.1.1.md).

### Fixed

- Preserve Windows-native live exchange paths in session metadata and derive WSL
  drive-mount paths only in memory, preventing false `applied` results against a
  phantom `C:\\mnt\\c\\...` target.
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
