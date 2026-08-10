# Changelog

This file records user-visible project changes. Detailed immutable release records live under `docs/releases/`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

Post-`v0.2.1` development is active on `main` while the next version has not yet been selected. The source/package version remains `0.2.1`; these changes are not part of the already-published `v0.2.1` bytes.

### Added

- intelligent schematic-layout foundation: design intent/reference motifs, bounded multi-candidate placement, non-mutating wire planning, conservative pin geometry, pin-aware joint placement/routing scoring and bounded placement repair;
- PCB Generation A intent/net intelligence and intent-aware placement v2;
- PCB Generation B stackup/PDN/return-path/noise/via context;
- PCB Generation C routing-policy compilation, observed-route checks, copper strategy and bounded placement feedback;
- PCB Generation D bounded whole-board candidate selection and synthetic engineering-trap benchmark catalog;
- internal raw-preserving Component/Pattern Library mutation core with controlled real-editor evidence;
- deterministic cinematic presentation subsystem with UI profiles, affine design-to-client calibration, Windows replay, semantic Schematic/PCB adapters and MP4/GIF recording helpers.

### Changed

- combined supported-environment coverage gate raised to 90% while retaining the 85% geometry-enabled Linux-only floor and selected per-file floors;
- Q1 Component Angle private/manual campaign completed as PASS on the later accepted production checkpoint; immutable release records retain their original historical status;
- Claude Desktop restart explicitly waived for the current campaign without fabricating a PASS;
- documentation synchronized with the published `v0.2.1` state and post-release `main` implementation while preserving dated evidence snapshots.

See `CHANGELOG_NEXT.md` for the detailed development record before the next version is selected.

## 0.2.1 - 2026-08-05

### Added

- deterministic Windows MCPB packaging with a versioned manifest and SHA-256 output;
- official MCP Registry metadata/template and canonical identity `io.github.fireostendere/diptrace-mcp`;
- guarded PyPI Trusted Publishing through GitHub OpenID Connect with no long-lived API token;
- strict wheel/sdist metadata and clean-install smoke checks;
- release checklist/record for the PyPI, MCPB, Registry and Smithery distribution path.

### Changed

- package/fallback version aligned to `0.2.1`;
- installation/distribution documentation aligned with PyPI, MCPB and Registry publication;
- existing unsigned alpha/development and evidence limitations retained.

### Published state

- annotated tag `v0.2.1` points to release merge commit `1d2b7bef256cd43262b566dc2cd4050248d0145d`;
- GitHub development prerelease published with installer, portable bundle, MCPB, wheel, sdist, checksums and provenance files;
- `diptrace-mcp==0.2.1` published to PyPI through the guarded tag-bound Trusted Publishing workflow;
- immutable release record: `docs/releases/v0.2.1.md`.

The release-time Q1 Component Angle status remains `NOT_RUN` in the immutable release record. The later private/manual PASS belongs to a later production checkpoint and does not rewrite release history.

## 0.2.0 - 2026-08-04

### Added

- Windows onedir server, Inno Setup installer, portable bundle and guarded Codex/Claude Desktop configurator;
- typed in-process domain services behind the stable `DipTraceService` Facade;
- central service-to-MCP error boundary with stable public error codes;
- NetClass-aware routing/review-clearance support;
- clean-room factual inventory generation, evidence warnings, SBOM/dependency/provenance records and deterministic release-artifact auditing;
- project-owned AnyIO worker-thread boundary and responsiveness probes for registered tools.

### Changed

- completed the first service-Facade decomposition pass while preserving 159 MCP tools, 157 public service signatures and 148 explicit delegations;
- preserved singleton stores, SHA/policy/atomic-write, session-lease and trust boundaries;
- removed verbatim external reference extracts from public release surfaces;
- hardened installer ownership/rollback/uninstall/state-preservation paths;
- published deterministic coverage-gate metadata from the then-current workflow threshold.

### Validation boundary

The release was an explicitly unsigned alpha/development prerelease. Universal DipTrace compatibility, production readiness, independent review, Novarm/DipTrace endorsement and complete manufacturing sign-off were not claimed. Q1 Component Angle was `NOT_RUN` at this historical point.

## 0.1.2 - 2026-08-01

### Fixed

- synchronized documentation values with generated reports;
- added no-clone release-asset installation guidance;
- corrected MCP snapshot, coverage and format-coverage metadata;
- corrected release provenance while preserving the explicit withdrawal of `0.1.1`.

### Validation

Historical frozen/local coverage was about 85.94%; exact-head GitHub CI was about 85.97%. Those values are release evidence, not the current repository coverage target.

Wheel/sdist audits, clean installation, CLI/MCP stdio smoke, Windows bridge provenance, settings/plugin checks, public checksums and public-download verification passed for the historical release set.

## 0.1.1 - 2026-08-01 [Withdrawn]

This release was withdrawn because public documentation contained stale generated figures and incomplete release-asset installation guidance. It is superseded by `0.1.2`; see `docs/releases/v0.1.1.md`.

### Fixed before withdrawal

- preserved Windows-native live exchange paths and derived WSL mount paths only in memory;
- ignored the intentional stdout-close race used to unblock the Windows output-reader thread after the root process exits.

### Historical validation

Windows DipTrace 5.2.0.4 ↔ WSL MCP live acceptance covered PCB/Schematic apply/cancel/wrong-SHA paths with GUI/save/re-export checks.

## 0.1.0 - 2026-07-30

### Added

- Apache-2.0 project license and citation metadata;
- private vulnerability reporting policy;
- contribution/governance/release-process documentation;
- issue/PR templates for bugs, features, compatibility evidence, provenance/privacy and DCO;
- exact release-file allowlist and Python archive audit;
- initial public package metadata and release assets.

### Fixed

- Windows bridge build environment so the PyInstaller artifact includes required runtime dependencies and smoke-runs in CI.

### Clarified

No community/adoption/sponsorship/vendor endorsement/signed-binary/production-ready claim was made.

[0.2.1]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.1
[0.2.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0
[0.1.2]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.2
[0.1.0]: https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.0
