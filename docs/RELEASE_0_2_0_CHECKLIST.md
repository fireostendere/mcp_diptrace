# DipTrace MCP 0.2.0 release checklist

This checklist separates repository automation from actions that require the
repository owner, a real Windows profile, a real DipTrace installation, or
external signing credentials. Do not create tag `v0.2.0` until every blocking
item below is complete or an explicit reviewed exception is recorded without
weakening the stated evidence limits.

## Current candidate

- Release branch: `release/v0.2.0`.
- Reviewed feature/refactor merge: PR #48, squash commit
  `a4c9023cdbc982e5bc8e1867945105c18f49f3f5`.
- Reviewed source head: `ceafb30725783f66ab83071ed7e98a478ac76618`.
- Exact-head CI: run `30933874564`, successful.
- Exact-head Windows installer workflow: run `30933874350`, successful.
- Candidate artifacts from the Windows workflow remain unsigned.
- Publication status: **NOT TAGGED / NOT PUBLISHED**.

## Automated preparation

- [x] Project and Windows artifact version is `0.2.0`.
- [x] Standalone server, bridge, configurator, installer, and portable bundle are built in CI.
- [x] Portable helper uses the real packaged bridge/configurator paths.
- [x] Final installer and portable ZIP have an external `SHA256SUMS.txt`.
- [x] State deletion requires a matching installation manifest and ownership marker.
- [x] Installer rolls back DipTrace plug-in files when later client configuration fails.
- [x] Signed-required verification covers installer, bridge, server, and configurator executables.
- [x] Frozen skill files use directory destinations without duplicated filenames.
- [x] Regular wheel/source stdio continues through the public FastMCP path; the private fallback is frozen-only.
- [x] The 159-tool public MCP surface is unchanged by the service-facade decomposition.
- [x] All 157 public Facade signatures and 148 explicit delegations are checked from a committed manifest.
- [x] The exact reviewed head passed `1074 passed, 4 skipped` on the full Linux coverage run.
- [x] The exact reviewed head passed `1062 passed, 16 skipped` on Windows.
- [x] Exact-head coverage is `85.9367%`; the total and per-file gates passed.
- [x] PR #48 is merged without changing the public MCP contract or documented safety boundaries.

## Human release blockers

- [ ] Test install, repair, and uninstall on a clean Windows 11 VM.
- [ ] Test at least one real current DipTrace 5 installation across PCB, Schematic, Component, and Pattern modules.
- [ ] Confirm the installer does not remove pre-existing user files from a custom state location.
- [ ] Test real Codex configuration, restart Codex, and call `get_capabilities`.
- [ ] Test real Claude Desktop configuration, restart Claude, and call `get_capabilities`.
- [ ] Test an elevated plug-in install into Program Files while client configuration remains in the original user profile.
- [x] Publish 0.2.0, if approved, as an explicitly unsigned development-stage release; no signed claim is permitted.
- [ ] Obtain/record any required external legal review; no Novarm endorsement or permission is implied.
- [x] Keep Q1 component-angle validation marked `NOT_RUN` unless live evidence is captured.

## Final release sequence

1. Complete the human release blockers above and record dated evidence.
2. Freeze the exact release-candidate commit and record its SHA.
3. Regenerate compliance outputs bound to that candidate commit.
4. Run the complete release and clean-room test commands documented in `docs/RELEASE_PROCESS.md`.
5. Build the final assets from the frozen candidate commit.
6. Verify `SHA256SUMS.txt` against every asset from a clean directory.
7. Verify Authenticode on every executable only when a signed release is claimed.
8. Create an annotated `v0.2.0` tag only after all preceding checks pass.
9. Publish a GitHub prerelease/development release with the exact audited assets.
10. Download the public assets again and repeat checksum, install, stdio, and uninstall smoke tests.
11. Reconcile `README.md`, `README_RU.md`, `CITATION.cff`, `CHANGELOG.md`, and `docs/releases/v0.2.0.md` with the immutable published commit and public asset hashes.

## Required release assets

- `DipTrace-MCP-Setup-0.2.0.exe`
- `DipTrace-MCP-Portable-0.2.0.zip`
- `diptrace_mcp-0.2.0-py3-none-any.whl`
- `diptrace_mcp-0.2.0.tar.gz`
- `SHA256SUMS.txt`
- current SBOM, dependency inventory, notices, and provenance records

## Claims that remain prohibited without evidence

- production-ready;
- signed, unless all executable signatures verify;
- validated against real DipTrace semantics beyond the dated acceptance records;
- safe component rotation semantics while Q1 is `NOT_RUN`;
- universal DipTrace-version compatibility;
- Novarm/DipTrace endorsement, affiliation, or permission.
