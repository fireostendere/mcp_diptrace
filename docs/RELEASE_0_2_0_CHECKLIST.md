# DipTrace MCP 0.2.0 Release Checklist

This checklist separates completed repository automation from actions that
require the repository owner, a real Windows profile, a real DipTrace
installation, signing credentials, or external review.

Do not create tag `v0.2.0` until every blocking item is complete or an explicit
reviewed exception is recorded without weakening the stated evidence limits.

## Current candidate identity

- Version: `0.2.0`.
- Latest published release: `v0.1.2`.
- Publication status: **NOT TAGGED / NOT PUBLISHED**.
- Service-refactor PR: `#48`.
- Reviewed implementation head: `ceafb30725783f66ab83071ed7e98a478ac76618`.
- PR #48 squash commit on `main`:
  `a4c9023cdbc982e5bc8e1867945105c18f49f3f5`.
- Release-preparation PR: `#49`.
- Exact PR #49 head: `946fc121806af532e431fcc1bdad3d85b217cd30`.
- PR #49 merge commit on `main`:
  `4fdefcd5464d57fa7bef2aa7391eb5b0507798f6`.
- Exact PR #49 CI run: `30940972328`, successful.
- Exact PR #49 Windows installer run: `30940972331`, successful.
- Intended publication class: unsigned alpha/development-stage GitHub
  prerelease under the documented solo-maintainer exception.

The merged commit above is the current documentation/release-preparation
baseline. It is not automatically the final release commit; final human
acceptance may require another reviewed release-finalisation PR.

## Automated preparation

- [x] Project and Windows artifact version is `0.2.0`.
- [x] PR #48 is merged with the public MCP contract preserved.
- [x] PR #49 release-candidate documentation is merged.
- [x] The public MCP surface remains 159 tools.
- [x] All 157 public Facade signatures and 148 explicit delegations are checked.
- [x] All 195 Facade methods are covered by the decomposition inventory.
- [x] Persistent write-capability classification includes internal delegation
      and lazy preview-store construction.
- [x] Ruff passes.
- [x] Strict Mypy passes.
- [x] DCO passes.
- [x] Linux Python 3.10/3.12/3.13 tests pass.
- [x] macOS and Windows tests pass.
- [x] Shapely/GEOS and explicit no-Shapely fallback paths pass.
- [x] Public `tools/list` snapshot is regenerated and checked.
- [x] Service-Facade contract and decomposition safety checks pass.
- [x] Event-loop audit covers all registered tools.
- [x] Python wheel/source archives build from the exact allowlist and pass audit.
- [x] Standalone server, bridge, configurator, installer, and portable bundle
      build in the Windows workflow.
- [x] Installer/portable smoke includes frozen stdio, `tools/list`,
      `get_capabilities`, XML, checksums, provenance, and unsigned status.
- [x] State deletion requires matching installation ownership metadata.
- [x] Installer rollback covers plug-in changes when a later configuration step
      fails.
- [x] Signed-required verification covers installer, bridge, server, and
      configurator executables.
- [x] Regular wheel/source stdio remains on the public FastMCP path; the private
      fallback is frozen-only.
- [x] The reviewed implementation head passed `1074 passed, 4 skipped` in the
      geometry-enabled Linux coverage run.
- [x] The reviewed implementation head passed `1062 passed, 16 skipped` on
      Windows.
- [x] Reviewed implementation coverage is `85.9367%`; total and per-file gates
      passed.

## Human release blockers

- [ ] Test install, repair, and uninstall on a clean Windows 11 VM.
- [ ] Test a current real DipTrace 5 installation across PCB, Schematic,
      Component, and Pattern modules.
- [ ] Confirm the installer does not remove pre-existing user files from a
      custom state location.
- [ ] Test real Codex configuration, restart Codex, and call
      `get_capabilities`.
- [ ] Test real Claude Desktop configuration, restart Claude, and call
      `get_capabilities`.
- [ ] Test an elevated plug-in installation under Program Files while MCP client
      configuration remains in the original user profile.
- [ ] Record exact Windows, DipTrace, Codex, and Claude versions/builds used for
      acceptance.
- [ ] Obtain and record any required external legal review. No Novarm/DipTrace
      permission, affiliation, or endorsement is implied.
- [ ] Freeze the exact final release commit after acceptance.
- [ ] Build final release assets from that exact commit.
- [ ] Produce and verify final per-file `SHA256SUMS.txt`.
- [ ] Download the public assets and repeat checksum, install, MCP stdio, and
      uninstall smoke tests after publication.

## Explicit decisions already recorded

- [x] Publish 0.2.0, if approved, as explicitly unsigned development-stage
      software unless a real protected signing run is completed.
- [x] Do not describe CI success or SHA-256 verification as a code signature.
- [x] Keep Q1 Component Angle validation marked `NOT_RUN` unless live evidence
      is captured and independently reviewed.
- [x] Keep the remaining trust-invalidation gaps visible for `plan_apply`,
      `ses_import`, `schematic_to_pcb_sync`, and `live_session_apply`.
- [x] Do not claim universal DipTrace 5.x compatibility, production readiness,
      independent review, native library mutation, or native manufacturing
      output.

## Final release sequence

1. Complete and record the human acceptance matrix.
2. Open a final release-finalisation PR from current `main`.
3. Record the exact candidate commit and acceptance evidence.
4. Move user-visible entries from `Unreleased` into `0.2.0 - <date>` in
   `CHANGELOG.md`.
5. Update `CITATION.cff` to 0.2.0 and the approved release date.
6. Reconcile `README.md`, `README_RU.md`, release records, and installation docs
   with the final immutable state.
7. Regenerate compliance outputs against the exact final commit.
8. Run the complete release and clean-room commands from
   `docs/RELEASE_PROCESS.md`.
9. Build final assets from that exact commit.
10. Verify every entry in `SHA256SUMS.txt` from a clean directory.
11. Verify Authenticode only when a signed release is claimed.
12. Create annotated tag `v0.2.0` from the approved commit.
13. Publish the exact audited assets as a GitHub development/prerelease.
14. Download the public files and repeat checksum/install/stdio/uninstall smoke.
15. Replace candidate placeholders in `docs/releases/v0.2.0.md` with immutable
    tag, asset, date, and public-download evidence.

## Intended release assets

- `DipTrace-MCP-Setup-0.2.0.exe`
- `DipTrace-MCP-Portable-0.2.0.zip`
- `diptrace_mcp-0.2.0-py3-none-any.whl`
- `diptrace_mcp-0.2.0.tar.gz`
- `SHA256SUMS.txt`
- current SBOM
- dependency inventory
- third-party notices
- provenance/release records

## Claims prohibited without additional evidence

- production-ready;
- signed, unless every distributed executable verifies under the approved
  identity;
- independently reviewed;
- universally compatible with DipTrace 5.x;
- validated for every registered tool or XML object;
- safe component-rotation semantics while Q1 is `NOT_RUN`;
- native Component/Pattern Library mutation;
- native Gerber/NC Drill/manufacturing generation;
- Novarm/DipTrace endorsement, affiliation, approval, or redistribution
  permission.