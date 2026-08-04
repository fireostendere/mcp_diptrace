# DipTrace MCP 0.2.0 Release Checklist

This checklist separates completed repository automation from actions requiring
a real Windows profile, current DipTrace installation, external clients,
signing credentials, or independent review.

## Publication decision

- Version: `0.2.0`.
- Release manager: [@fireostendere](https://github.com/fireostendere), repository
  owner.
- Approval date: `2026-08-04`.
- Publication class: **unsigned alpha/development GitHub prerelease**.
- Independent reviewer: none.
- PyPI publication: not configured and not planned for this release.
- Signing claim: prohibited; all Windows executables remain explicitly unsigned.

The repository owner explicitly approved publication under the documented
solo-maintainer exception while the manual acceptance items below remain open.
Those items are not represented as completed. They are release limitations and
must remain visible in the release notes, release record, README, and runtime
capability reporting.

## Reviewed lineage

- Service-refactor PR: `#48`.
- Reviewed implementation head:
  `ceafb30725783f66ab83071ed7e98a478ac76618`.
- PR #48 squash commit:
  `a4c9023cdbc982e5bc8e1867945105c18f49f3f5`.
- Release-preparation PR: `#49`.
- Exact PR #49 head:
  `946fc121806af532e431fcc1bdad3d85b217cd30`.
- PR #49 merge commit:
  `4fdefcd5464d57fa7bef2aa7391eb5b0507798f6`.
- Documentation-synchronisation PR: `#50`.
- PR #50 merge commit:
  `9c31fe51b31e5aece66b085021d4cf2a6171ce31`.
- Exact PR #49 CI run: `30940972328`, successful.
- Exact PR #49 Windows installer run: `30940972331`, successful.
- Exact PR #50 CI run: `30945046315`, successful.
- Exact PR #50 Windows installer run: `30945046584`, successful.

The final release-finalisation PR must pass its complete exact-head matrix. Its
merged commit becomes the immutable annotated-tag target.

## Completed automated preparation

- [x] Project/package version is `0.2.0`.
- [x] Public MCP surface remains 159 tools.
- [x] All 157 public Facade signatures and 148 explicit delegations are checked.
- [x] All 195 Facade methods are covered by the decomposition inventory.
- [x] Persistent-write classification includes internal delegation and lazy
      preview-store construction.
- [x] Ruff, strict Mypy, and DCO pass.
- [x] Linux Python 3.10/3.12/3.13, macOS, and Windows tests pass.
- [x] Shapely/GEOS and explicit no-Shapely fallback paths pass.
- [x] Public `tools/list`, service-Facade contract, decomposition safety, and
      event-loop audits pass.
- [x] Python wheel/source archives build from the exact allowlist and pass audit.
- [x] Standalone server, bridge, configurator, installer, and portable bundle
      build in Windows CI.
- [x] Installer ownership, rollback, state preservation, checksums, unsigned
      verification, frozen stdio, XML, and provenance paths are covered by CI.
- [x] Reviewed implementation head passed `1074 passed, 4 skipped` at
      `85.9367%` geometry-enabled Linux coverage.
- [x] Reviewed implementation head passed `1062 passed, 16 skipped` on Windows.
- [x] Changelog and citation metadata are finalised for `0.2.0` dated
      `2026-08-04`.
- [x] A guarded publication workflow builds exact `0.2.0` assets, creates an
      annotated tag, publishes a prerelease, redownloads all public assets,
      verifies `SHA256SUMS.txt`, installs the public wheel, and runs CLI smoke.

## Manual acceptance not completed

- [ ] Clean Windows 11 install, repair, and uninstall acceptance.
- [ ] Current real DipTrace 5 across PCB, Schematic, Component, and Pattern
      modules.
- [ ] Preservation of pre-existing files in a custom state location.
- [ ] Real Codex configuration, restart, and `get_capabilities`.
- [ ] Real Claude Desktop configuration, restart, and `get_capabilities`.
- [ ] Elevated Program Files plug-in installation while client configuration
      remains in the original user profile.
- [ ] Exact Windows, DipTrace, Codex, and Claude versions/builds for the above
      acceptance matrix.
- [ ] Any required external legal review or Novarm/DipTrace permission.
- [ ] Q1 Component Angle GUI/re-export evidence; status remains `NOT_RUN`.

These unchecked items prohibit stronger claims but do not block the explicitly
approved unsigned prerelease. They must not be silently converted into passes.

## Final automated sequence

1. Merge the release-finalisation PR only after exact-head CI and exact
   `0.2.0` release-asset builds pass.
2. Build wheel, source distribution, standalone server, bridge, configurator,
   installer, and portable bundle from the merged commit.
3. Smoke the exact installer and portable bundle.
4. Assemble the release files and deterministic per-file `SHA256SUMS.txt`.
5. Create annotated tag `v0.2.0` at the exact merged commit.
6. Publish the files as an explicitly unsigned GitHub prerelease.
7. Redownload the public assets, verify all checksums, install the public wheel,
   and run `diptrace-mcp --help`.
8. Reconcile public documentation with the immutable tag, release URL, asset
   hashes, and verification result in a post-release PR.

## Release assets

- `DipTrace-MCP-Setup-0.2.0.exe`
- `DipTrace-MCP-Portable-0.2.0.zip`
- `diptrace_mcp-0.2.0-py3-none-any.whl`
- `diptrace_mcp-0.2.0.tar.gz`
- `SHA256SUMS.txt`
- SBOM
- dependency inventory
- third-party notices
- provenance inventory
- Windows bundle inventory
- release record
- Apache-2.0 license

## Claims prohibited without additional evidence

- production-ready;
- signed or trusted-publisher verified;
- independently reviewed;
- universally compatible with DipTrace 5.x;
- validated for every registered tool or XML object;
- safe component-rotation semantics while Q1 is `NOT_RUN`;
- native Component/Pattern Library mutation;
- native Gerber/NC Drill/manufacturing generation;
- Novarm/DipTrace endorsement, affiliation, approval, or redistribution
  permission;
- complete manufacturing, fabrication, assembly, or regulatory sign-off.
