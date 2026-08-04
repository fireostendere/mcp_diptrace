# DipTrace MCP 0.2.0 release checklist

This checklist separates repository automation from actions that require the
repository owner, a real Windows profile, a real DipTrace installation, or
external signing credentials. Do not create tag `v0.2.0` until every blocking
item is complete.

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

## Human release blockers

- [ ] Test install, repair, and uninstall on a clean Windows 11 VM.
- [ ] Test at least one real current DipTrace 5 installation across PCB, Schematic, Component, and Pattern modules.
- [ ] Confirm the installer does not remove pre-existing user files from a custom state location.
- [ ] Test real Codex configuration, restart Codex, and call `get_capabilities`.
- [ ] Test real Claude Desktop configuration, restart Claude, and call `get_capabilities`.
- [ ] Test an elevated plug-in install into Program Files while client configuration remains in the original user profile.
- [ ] Decide whether 0.2.0 is published unsigned or through the configured SignPath contract.
- [ ] Obtain/record any required external legal review; no Novarm endorsement or permission is implied.
- [ ] Keep Q1 component-angle validation marked `NOT_RUN` unless live evidence is captured.

## Final release sequence

1. Merge the reviewed installer PR only after exact-head CI is green.
2. Pull the resulting `main` merge commit and record its SHA.
3. Regenerate compliance outputs bound to the release candidate commit.
4. Run the complete release and clean-room test commands documented in `docs/RELEASE_PROCESS.md`.
5. Build the final assets from the frozen candidate commit.
6. Verify `SHA256SUMS.txt` against every asset from a clean directory.
7. Verify Authenticode on every executable when a signed release is claimed.
8. Create an annotated `v0.2.0` tag only after all preceding checks pass.
9. Publish a GitHub prerelease/development release with the exact audited assets.
10. Download the public assets again and repeat checksum, install, stdio, and uninstall smoke tests.

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
- validated against real DipTrace semantics;
- safe component rotation semantics while Q1 is `NOT_RUN`;
- Novarm/DipTrace endorsement, affiliation, or permission.
