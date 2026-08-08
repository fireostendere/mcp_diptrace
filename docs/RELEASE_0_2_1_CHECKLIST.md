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

## Remaining manual acceptance

The following are intentionally **not** marked complete by CI or publication:

- clean Windows 11 install, repair and uninstall;
- current real DipTrace PCB open/save/re-export;
- current real DipTrace Schematic open/save/re-export including authored wires;
- current real Component Library writer open/save/re-export;
- current real Pattern Library writer open/save/re-export;
- generated-ratline GUI/save/re-export evidence;
- mask/paste/courtyard/`Common` one-setting-at-a-time exports;
- Q1 Component Angle GUI/re-export;
- real Codex restart/configuration/`get_capabilities`;
- real Claude Desktop restart/configuration/`get_capabilities`;
- elevated Program Files plug-in install while retaining the original user profile;
- pre-existing custom-state preservation.

Claim-specific optional work includes a future public-redownload smoke when release bytes change, external legal/Novarm review if required for a planned claim/activity, and a real openEMS run if external-solver validation is to be claimed.

Generate and validate the evidence worksheet with `scripts/prepare_manual_acceptance.py`; `docs/ROADMAP.md` is the authoritative current roadmap.

## Fail-closed release rules retained for future versions

- Never publish from an unreviewed branch or movable identity when the release process requires an annotated tag.
- Never move or replace an existing published tag/file.
- Never use `skip-existing` to hide a production publication mismatch.
- Never publish a wheel/sdist different from the artifact that passed validation.
- Never claim signing, production readiness, universal DipTrace compatibility, real-client acceptance or real DipTrace acceptance without the corresponding evidence.

The old pre-publication TODO state is intentionally not preserved as current truth; Git history contains the original checklist if historical reconstruction is needed.
