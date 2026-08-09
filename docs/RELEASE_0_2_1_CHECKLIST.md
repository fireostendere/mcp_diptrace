# DipTrace MCP 0.2.1 Release Checklist

This is now a historical release checklist. Version `0.2.1` has already been tagged and published; remaining real-system acceptance is tracked separately and must not be confused with package publication.

## Publication status

- Version: `0.2.1`.
- Annotated tag: `v0.2.1` — **created and immutable**.
- GitHub development prerelease — **published**.
- PyPI package `diptrace-mcp==0.2.1` — **published through Trusted Publishing**.
- Windows installer / portable bundle / MCPB — **published GitHub release assets**.
- Windows signing status: unsigned.
- Release class: alpha/development prerelease.
- Q1 Component Angle real GUI/re-export evidence: `NOT_RUN`.

See `docs/releases/v0.2.1.md` for the immutable tag target, workflow runs, filenames, sizes and SHA-256 values.

## Completed automated publication gates

The release record documents successful candidate CI, Windows build, MCPB/Registry preparation, PyPI distribution validation, verified GitHub prerelease creation and exact-tag PyPI Trusted Publishing.

The repository continues to enforce:

- Ruff and strict Mypy;
- DCO;
- Linux/macOS/Windows test jobs;
- geometry/fallback jobs;
- MCP snapshot and Facade/decomposition contracts;
- architecture, provenance, compliance and release-artifact checks;
- clean Python distribution installation smoke;
- deterministic Windows release-asset generation.

These automated gates are complete for the already-published `v0.2.1`. Do not rerun them as if publication were still pending unless validating a new commit/version.

## Post-publication manual acceptance progress — 2026-08-09

The manual acceptance campaign continued on development commits after the immutable `v0.2.1` tag. These results improve confidence in the current development line; they do **not** retroactively change the bytes contained in the published 0.2.1 release.

The durable campaign recovery point is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md). `docs/ROADMAP.md` remains the authoritative current roadmap.

Completed real-host gates:

- [x] Current real DipTrace PCB open/save/re-export.
- [x] Current real DipTrace Schematic open/save/re-export including authored wires.
- [x] Real Component Library writer open/save/re-export using a real Component Editor seed; native `.eli` reopen, semantic preservation and second-pass idempotence accepted.
- [x] Real Pattern Library writer open/save/re-export using a real Pattern Editor seed; native `.lib` reopen, semantic preservation and second-pass idempotence accepted.
- [x] Generated PCB ratline GUI/save/re-export acceptance after the PR #63/#64 repairs.
- [x] Authored schematic-wire GUI/save/re-export acceptance.
- [x] MASK one-setting-at-a-time semantics.
- [x] PASTE one-setting-at-a-time semantics.

Current blocking point:

- [ ] COURTYARD targeted retest after PR #65. The historical attempt on `main@4ddea7937661afedf9c195af558680c4705bb368` proved that DipTrace preserved `Source/Board/Settings/LineWidth/Courtyard`, while MCP read surfaces failed to expose the changed value. PR #65 is the focused parser repair. Preserve the historical FAIL and create a fresh retest attempt after merge.
- [ ] `Common` semantics. This was intentionally not run after the COURTYARD failure and must not be inferred as complete.

Remaining later manual/external gates:

- [ ] Q1 Component Angle GUI/re-export.
- [ ] Real Codex restart/configuration/`get_capabilities`.
- [ ] Real Claude Desktop restart/configuration/`get_capabilities`.
- [ ] Clean Windows 11 install, repair and uninstall using the applicable release bytes.
- [ ] Elevated Program Files plug-in install while retaining the original user profile.
- [ ] Pre-existing custom-state preservation across install/repair/uninstall.

MASK and PASTE must not be repeated merely because COURTYARD required a parser fix. Likewise, the already accepted PCB, schematic, library-writer and ratline/wire gates are not restart points unless a later code change plausibly affects those exact paths.

Claim-specific optional work includes a future public-redownload smoke when release bytes change, external legal/Novarm review if required for a planned claim/activity, and a real openEMS run if external-solver validation is to be claimed.

Generate and validate evidence worksheets with `scripts/prepare_manual_acceptance.py`. Historical FAIL attempts are evidence and should remain immutable; repairs get fresh retest attempts.

## Native library writer boundary

The real Component Editor and Pattern Editor host-evidence prerequisite that previously blocked confidence in the internal raw-preserving library mutation core is now satisfied on the development line.

This does **not** mean that 0.2.1 suddenly contains public native-library write tools, and it does not silently change the current public MCP contract. Public registration remains a separate future API/product decision requiring explicit review and documentation.

## Fail-closed release rules retained for future versions

- Never publish from an unreviewed branch or movable identity when the release process requires an annotated tag.
- Never move or replace an existing published tag/file.
- Never use `skip-existing` to hide a production publication mismatch.
- Never publish a wheel/sdist different from the artifact that passed validation.
- Never claim signing, production readiness, universal DipTrace compatibility, real-client acceptance or real DipTrace acceptance without the corresponding evidence.

The old pre-publication TODO state is intentionally not preserved as current truth; Git history contains the original checklist if historical reconstruction is needed.
