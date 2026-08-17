# Changelog

## 0.4.0 - 2026-08-16

Version `0.4.0` is the current published unsigned development release.

### Publication

- Published as annotated tag `v0.4.0` with GitHub release ID `371451484`.
- Published `diptrace-mcp==0.4.0` to PyPI through OIDC Trusted Publishing; both
  wheel and source distribution returned `200 OK` and received attestations.
- Published Windows per-user installer, administrator plug-in installer,
  portable bundle and `SHA256SUMS.txt`; a v0.4.0 MCPB was not attached.
- Linux/macOS release installation is bootstrapped from the immutable v0.4.0
  installer scripts rather than from moving `main`.

### Added

- A1-A8 roadmap closure: bounded transport regression, guarded whole-board PCB
  plan/apply, provider-neutral reviewer evaluation, source-bound rule ingestion,
  topology-preserving schematic reroute, confidence-gated rotation candidates,
  source-bound bounded physics estimates, and deterministic evidence campaigns.
- One-command Linux installation with real DipTrace GUI under Wine and private-Xvfb
  headless automation.
- One-command macOS installation using the official DipTrace.app bundled Wine
  runtime, with visible GUI and hidden-Win32-desktop automation on Apple Silicon
  and Intel.
- Permanent Linux/macOS clean-install release gates.

### Changed

- Public MCP contract remains frozen at 167 tools.
- Current project-level manual evidence remains 12 of 12 blocking gates PASS across
  accepted checkpoints; the later Claude Desktop restart PASS remains separate-
  machine evidence from a machine where Codex was not installed.
- Release documentation separates exact host/runtime evidence from stronger native
  project-roundtrip or universal-compatibility claims.

## 0.3.0 - 2026-08-16

Version `0.3.0` is a published unsigned development prerelease following the
immutable `v0.2.1` release.

### Added

- Intelligent schematic-layout foundation: design intent/reference motifs,
  bounded multi-candidate placement, conservative pin geometry, non-mutating
  wire planning, pin-aware joint placement/routing scoring, bounded placement
  repair, and selective atomic affected-net reroute.
- PCB Generations A-D: engineering intent/placement, physical/PDN/return-path
  context, engineering-aware routing policy, and bounded whole-board candidate
  selection with a synthetic benchmark catalog.
- Internal raw-preserving Component/Pattern Library mutation core with
  controlled real-editor evidence; public native-library write registration
  remains a separate API decision.
- Cinematic DipTrace presentation subsystem with UI profiles, affine
  design-to-client calibration, semantic Schematic/PCB replay adapters, Windows
  playback, and MP4/GIF recording helpers.
- Optional Windows headless GUI worker using an isolated Win32 desktop for
  bounded native open/save/close operations without physical-input fallback.
- Compact PCB authoring defaults: smallest compatible standard connector
  preference, explicit-net Top/Bottom pours, four-spoke thermal intent,
  distributed GND stitching and obstacle-aware silkscreen cleanup.
- Matching 25×12 mm I²C PCB source and board-framed MP4/GIF demonstration.

### Changed

- Combined supported-environment coverage remains gated at 90% while the
  geometry-enabled Linux full-suite job retains its separate 85% floor.
- Q1 Component Angle was completed as PASS in the later private/manual
  DipTrace PCB Layout 5.3.0.3 campaign; immutable release-time evidence retains
  its original historical status.
- The accepted manual matrix is complete at 12 of 12 blocking gates PASS across
  its recorded checkpoints. Claude Desktop restart and custom-state preservation
  are operator-confirmed PASS from a separate machine; their earlier
  WAIVED/pending states remain historical only.
- Evergreen documentation records the transition from `v0.2.1` to published
  `v0.3.0` without rewriting dated release, acceptance or compliance snapshots.
- The operator accepted the current repository PCB/Schematic examples and both
  GIF/MP4 outputs in the current DipTrace configuration on 2026-08-16.

See `CHANGELOG_NEXT.md` for the detailed `v0.3.0` release record.

## 0.2.1 - 2026-08-05

### Added

- Deterministic Windows MCPB packaging with a versioned manifest, reproducible
  archive layout, and sibling SHA-256 file.
- Official MCP Registry metadata template and concrete `server.json` generator
  for the immutable `v0.2.1` MCPB asset.
- Focused MCPB and Registry metadata tests and distribution documentation for
  the official Registry, Smithery, and awesome-mcp-servers.
- Guarded PyPI Trusted Publishing through GitHub OpenID Connect with a minimal
  tag-bound publish job and no long-lived API token.
- Strict wheel and source-distribution metadata checks plus clean installation
  and CLI smoke for both Python artifacts.
- Candidate release checklist and release record for the PyPI, MCPB, Registry,
  and Smithery publication sequence.

### Changed

- Bumped the Python package and fallback version to `0.2.1`.
- Synchronized English/Russian README, release records, and installation
  instructions with the new package and distribution route.
- Added the canonical ownership marker
  `io.github.fireostendere/diptrace-mcp`.
- Removed the completed one-shot automatic v0.2.0 publication trigger and
  restored the signing workflow to manual preparation only.
- Kept the existing unsigned alpha/development and evidence limitations explicit
  across all new distribution channels.

### Publication boundary

- Existing `v0.2.0` tags and assets remain immutable.
- PyPI publication is permitted only from annotated tag `v0.2.1` through the
  protected `pypi` environment and `.github/workflows/pypi.yml`.
- The GitHub Release, PyPI project, MCP Registry version, and Smithery entry are
  not created by the release-preparation pull request itself.

## 0.2.0 - 2026-08-04

### Added

- Windows onedir server, Inno Setup installer, portable bundle, and guarded
  Codex/Claude Desktop configurator.
- Typed in-process domain services for document reads, BOM and component
  metadata, review, discovery, exports, jobs, external adapters, routing,
  placement, semantic operations, synchronization, XML writes, scaffolding,
  transactions, evidence, and live sessions.
- Central service-to-MCP error boundary with stable public error codes and
  bounded safe details.
- NetClass-aware routing and trace-to-trace review-clearance resolution with
  structured partial-review and skip reporting.
- Clean-room factual inventory generation, pending current-version fixture
  manifests, evidence warnings, SBOM, dependency inventory, provenance records,
  and deterministic release-artifact auditing.
- Project-owned AnyIO worker-thread boundary and connected responsiveness probes
  for all registered MCP tools.

### Changed

- Completed the first service-Facade decomposition pass while preserving the
  159-tool MCP surface, all 157 public `DipTraceService` signatures, and 148
  explicit delegations.
- Preserved singleton store ownership, stable error contracts,
  SHA/policy/atomic-write boundaries, live-session leases, and the server-owned
  thread-offload boundary.
- Removed verbatim external reference extracts and source-derived inventory from
  public surfaces.
- Hardened installer ownership, compensating plug-in rollback, uninstall/state
  preservation, portable paths, final-asset checksums, and executable-signature
  gates.
- Published CI status and deterministic coverage-gate metadata generated from
  the enforced workflow threshold.

### Validation and limitations

- Exact PR #48 implementation head passed CI run `30933874564`, Windows
  installer run `30933874350`, `1074 passed, 4 skipped` on the geometry-enabled
  Linux coverage job, and `1062 passed, 16 skipped` on Windows.
- Exact PR #49 release-preparation head passed CI run `30940972328` and Windows
  installer run `30940972331` across Linux 3.10/3.12/3.13, macOS, Windows,
  geometry, fallback, static analysis, DCO, MCP contract, decomposition,
  provenance, and artifact audits.
- The release is an explicitly unsigned alpha/development prerelease. SHA-256
  checks establish byte identity, not publisher trust.
- Universal DipTrace 5.x compatibility, production readiness, independent
  review, Novarm/DipTrace endorsement, and complete manufacturing sign-off are
  not claimed.
- Q1 Component Angle GUI/re-export evidence remains `NOT_RUN`; runtime
  `get_capabilities` remains authoritative for each installation and document.

This file records user-visible project changes. Version `0.1.0` was the first
tagged release; the withdrawn `0.1.1` release and the corrected `0.1.2`
development release are retained as separate historical records.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.2 - 2026-08-01

### Fixed

- Synchronized documentation values with the exact generated reports.
- Added release-asset installation instructions for a no-clone setup.
- Corrected MCP snapshot, coverage, and format-coverage metadata.
- Corrected release provenance and preserved the explicit revert of 0.1.1.

### Documentation

- Added the release installation guide.
- Added the withdrawn `v0.1.1` record and the `v0.1.2` release record.
- Activated and verified the main-branch GitHub ruleset; pull requests require
  DCO plus nine unique technical CI contexts.
- Completed a post-merge security and compliance audit of the current tree and
  reachable Git history.
- Added reproducible deep secret-scanning, dependency-audit, and clean-room
  audit tools; raw reports remain owner-private.
- Finalized the post-publication `v0.1.2` provenance with the immutable release
  commit, exact-head CI run, public asset inventory, checksum verification, and
  public-download smoke results.
- Opened contribution intake under DCO 1.1 and added provenance/privacy checks.

### Validation

- Frozen candidate/local run: Python 3.12.3, Shapely 2.1.2, GEOS 3.13.1,
  991 passed, 4 skipped, 16,922 statements, 2,379 missed, and 85.941378%
  total coverage.
- Exact-head GitHub CI run `30709466348`: all required Linux, macOS, Windows,
  geometry, fallback, static-analysis, generated-artifact, and native bridge
  jobs passed; its Python 3.12.13 coverage result was 991 passed, 4 skipped,
  16,922 statements, 2,375 missed, and 85.9650% total.
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
  save/re-export comparisons, path invariants, and connectivity/count
  preservation.
- Added focused unit coverage for non-WSL Windows-path refusal, relative WSL
  mount roots, POSIX-path refusal on Windows, and invalid path-platform metadata.

### Documentation

- Reconciled English and Russian readiness, testing, architecture,
  compatibility, usage, roadmap, and release-policy documentation with the
  2026-07-31 evidence.
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
- Public package metadata for repository, documentation, and issue links, plus
  EDA-focused classifiers without a premature license classifier.

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
- Python wheels intentionally contain the MCP server and eight packaged skills,
  while Windows bridge installation scripts and settings remain separate
  source/release assets.

Version `0.1.0` is published as tag `v0.1.0`; its provenance record is
[docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) and the release assets on
GitHub.

[0.2.1]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.1
[0.2.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0
[0.1.2]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.2
[0.1.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.0
