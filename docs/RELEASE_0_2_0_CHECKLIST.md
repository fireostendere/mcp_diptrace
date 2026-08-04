# DipTrace MCP 0.2.0 Release Checklist

## Publication result

- [x] `v0.2.0` published on `2026-08-04` as an unsigned
      alpha/development GitHub prerelease.
- [x] Annotated tag points to
      `31766cb6e667dc24f3e2921decfd65c03eebd271`.
- [x] Exact wheel, source distribution, installer, and portable assets were
      built from the release commit.
- [x] Public files were downloaded again, checksums verified, the public wheel
      installed, and CLI smoke completed.
- [x] Windows executables are explicitly unsigned.
- [x] No PyPI, official MCP Registry, Smithery, or MCPB publication was claimed.

## Automated evidence

- [x] CI run `30946506994` succeeded.
- [x] Windows installer run `30946506419` succeeded.
- [x] Release dry-run `30946506846` succeeded.
- [x] 159-tool MCP contract, 157 public Facade signatures, and 148 explicit
      delegations passed.
- [x] Linux, macOS, Windows, geometry, fallback, Ruff, strict Mypy, DCO,
      event-loop, provenance, artifact, installer, and portable checks passed.

## Manual acceptance not completed

- [ ] Clean Windows 11 install, repair, and uninstall acceptance.
- [ ] Current real DipTrace 5 across PCB, Schematic, Component, and Pattern.
- [ ] Real Codex restart/configuration and `get_capabilities`.
- [ ] Real Claude Desktop restart/configuration and `get_capabilities`.
- [ ] Elevated Program Files plug-in installation while preserving the original
      user profile.
- [ ] Preservation of pre-existing custom-state files.
- [ ] Q1 Component Angle GUI/re-export evidence; status remains `NOT_RUN`.
- [ ] External legal review or Novarm/DipTrace permission.

These unchecked items remain limitations. They must not be converted into
completed evidence or stronger compatibility, signing, production, or
endorsement claims.

## Post-release work

- [x] Synchronise README and installation documentation with the published
      release.
- [x] Disarm the one-shot automatic v0.2.0 publication workflow.
- [x] Prepare reproducible MCPB and registry metadata tooling without publishing
      a new version.
- [ ] Publish MCPB only through a future reviewed immutable release.
- [ ] Submit that future asset to the official MCP Registry and Smithery after
      public-download verification.
