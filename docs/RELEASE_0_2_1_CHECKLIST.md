# DipTrace MCP 0.2.1 Release Checklist

This is a historical release checklist. Version `0.2.1` has already been tagged and published; later development-line acceptance improves confidence in current code but does **not** retroactively change the published 0.2.1 bytes.

## Publication status

- Version: `0.2.1`.
- Annotated tag: `v0.2.1` — **created and immutable**.
- GitHub development prerelease — **published**.
- PyPI package `diptrace-mcp==0.2.1` — **published through Trusted Publishing**.
- Windows installer / portable bundle / MCPB — **published GitHub release assets**.
- Windows signing status: unsigned.
- Release class: alpha/development prerelease.

See `docs/releases/v0.2.1.md` for the immutable release record, workflow runs, filenames, sizes and SHA-256 values.

## Completed automated publication gates

The published release completed its automated CI/build/distribution checks. Do not rerun those as if publication were still pending unless validating a new commit/version.

The repository continues to enforce:

- Ruff and strict Mypy;
- DCO;
- Linux/macOS/Windows test jobs;
- geometry/fallback jobs;
- MCP snapshot and Facade/decomposition contracts;
- architecture, provenance, compliance and release-artifact checks;
- clean Python distribution installation smoke;
- deterministic Windows release-asset generation.

## Post-publication manual acceptance progress — updated 2026-08-10

The current accepted production-code candidate for the development-line manual campaign is:

`main@0bb09b4b3af40a5a3d1a875fab885430a2d251ba`

The durable campaign recovery point is [MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md](MANUAL_ACCEPTANCE_CHECKPOINT_2026-08-09.md), updated on 2026-08-10. `docs/ROADMAP.md` remains the authoritative current roadmap.

Completed blocking real-host / real-client gates:

- [x] Current real DipTrace PCB open/save/re-export.
- [x] Current real DipTrace Schematic open/save/re-export including authored wires.
- [x] Real Component Library writer open/save/re-export; native `.eli` reopen, semantic preservation and second-pass idempotence accepted.
- [x] Real Pattern Library writer open/save/re-export; native `.lib` reopen, semantic preservation and second-pass idempotence accepted.
- [x] Generated PCB ratline GUI/save/re-export acceptance.
- [x] Authored schematic-wire GUI/save/re-export acceptance.
- [x] MASK one-setting-at-a-time semantics.
- [x] PASTE one-setting-at-a-time semantics.
- [x] COURTYARD targeted retest after PR #65.
- [x] `Common` versus explicit override semantics.
- [x] Q1 Component Angle GUI/re-export acceptance.
- [x] Real Codex Desktop restart/configuration/`get_capabilities` acceptance.

The composite `diptrace_mask_paste_courtyard_common_semantics` gate is PASS. The historical COURTYARD FAIL remains immutable evidence.

Q1 manual acceptance established real DipTrace angle semantics on the development candidate: radians for 90/180/270 degrees, 360-to-0 GUI normalization, and expected bottom-side mirror canonicalization. The private/manual PASS does not by itself alter any separately source-controlled public evidence warning or redistribute private source artifacts.

Codex restart acceptance used Codex Desktop `26.803.5235.0`; both restarts exposed 159 tools and returned identical `get_capabilities` evidence. Production code remained unchanged.

Overall blocking manual progress is now **8 of 12 gates complete**.

## Intentional pause before remaining lifecycle gates

The formal next gate is still:

- [ ] `claude_desktop_real_client_restart`.

It has not been run.

The project is intentionally pausing the formal client/Windows lifecycle sequence here to validate core product quality first: current post-Ponytail schematic authoring/readability in real DipTrace.

This separate validation should build small real circuits and inspect electrical correctness, component placement, wire routing, text/label collisions, junction clarity and native save/reopen/re-export behavior. It must not be treated as a substitute for the remaining formal gates.

Remaining blocking formal gates after the pause:

- [ ] Real Claude Desktop restart/configuration/`get_capabilities`.
- [ ] Clean Windows 11 install, repair and uninstall using the applicable release bytes.
- [ ] Elevated Program Files plug-in install while retaining the original user profile.
- [ ] Pre-existing custom-state preservation across install/repair/uninstall.

Claim-specific optional work remains a future public-redownload smoke when release bytes change, external legal/Novarm review when required for a planned claim/activity, and a real openEMS run only if external-solver validation is claimed.

Do not repeat historical PASS gates merely because a stronger schematic-quality validation is now being added. A new reproducible schematic authoring problem should become its own focused regression/repair case.

## Native library writer boundary

Real Component Editor and Pattern Editor host evidence exists for the internal raw-preserving library mutation core.

This does **not** mean that 0.2.1 contains public native-library write tools and does not silently change the public MCP contract. Public registration remains a separate future API/product decision.

## Fail-closed release rules retained for future versions

- Never publish from an unreviewed branch or movable identity when the release process requires an annotated tag.
- Never move or replace an existing published tag/file.
- Never use `skip-existing` to hide a production publication mismatch.
- Never publish a wheel/sdist different from the artifact that passed validation.
- Never claim signing, production readiness, universal DipTrace compatibility, real-client acceptance or real DipTrace acceptance without corresponding evidence.

Git history contains the original pre-publication checklist state if historical reconstruction is needed.
