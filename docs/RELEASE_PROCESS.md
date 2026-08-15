# Release Process

## Current release status

Version `v0.2.1` is the current published unsigned alpha/development prerelease.

Immutable/current published identities:

- annotated tag: `v0.2.1`;
- exact tag target / release merge commit: `1d2b7bef256cd43262b566dc2cd4050248d0145d`;
- GitHub prerelease: `v0.2.1`;
- PyPI package: `diptrace-mcp==0.2.1`;
- Windows installer: `DipTrace-MCP-Setup-0.2.1.exe`;
- portable bundle: `DipTrace-MCP-Portable-0.2.1.zip`;
- Windows MCPB: `DipTrace-MCP-0.2.1-windows.mcpb`;
- registry identity: `io.github.fireostendere/diptrace-mcp`.

The immutable release record is [releases/v0.2.1.md](releases/v0.2.1.md). The old `v0.2.0` tag/assets also remain immutable.

Development on `main` after `v0.2.1` is tracked in `CHANGELOG_NEXT.md` until the next version is selected. Do not describe post-release `main` features as if they were already present in the published `v0.2.1` bytes.

Windows executables remain unsigned. CI, SHA-256, PyPI Trusted Publishing and package attestations can establish tested behaviour, byte identity and publication provenance; they do not establish Authenticode trust, universal compatibility, independent review or production readiness.

## Historical release evidence versus current manual evidence

The `v0.2.1` release record correctly says Q1 Component Angle was `NOT_RUN` for that immutable release candidate.

A later private/manual campaign on the accepted production checkpoint completed Q1 as PASS. That later observation does not rewrite the historical release record or automatically upgrade `v0.2.1` artifact claims.

The accepted project-level manual matrix later reached 12 of 12 blocking gates PASS across its recorded checkpoints. `claude_desktop_real_client_restart` and `custom_state_preservation`, which were previously WAIVED/pending, are operator-confirmed PASS from a separate machine. That later evidence remains exact-checkpoint evidence and does not retroactively change the immutable `v0.2.1` release record.

## 1. Select and freeze the next version

Before changing release metadata or creating a new tag:

1. select the new version;
2. identify the release manager;
3. identify an independent reviewer when one exists, or record the explicit solo-maintainer exception;
4. define the exact compatibility/evidence claim;
5. complete real Windows/DipTrace/client acceptance required by that claim;
6. freeze one exact candidate commit;
7. move approved user-visible entries from `CHANGELOG_NEXT.md` / `CHANGELOG.md` into the dated release section;
8. update package, citation, installation, distribution and release-record metadata to the same immutable identity.

Never move an existing tag or replace published release/PyPI bytes.

## 2. Run repository quality gates

Use a clean checkout of the exact candidate. Typical repository checks include:

```bash
python -m pip install -e '.[dev,geometry]'
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/sync_skill_scripts.py --check
python scripts/generate_pcb_skills.py --check
python scripts/generate_mcp_tools_snapshot.py --check
python scripts/check_service_facade_contract.py --check
python scripts/validate_service_decomposition.py --check
python scripts/audit_event_loop.py --json
python scripts/generate_coverage_badge.py --check
python scripts/extract_spec_inventory.py \
  --sources tests/fixtures \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
python scripts/report_format_coverage.py --check
python scripts/make_probe_pack.py --check
python scripts/ingest_fixtures.py --dry-run --synthetic --json
python scripts/audit_acceptance_seeds.py
rm -rf release-dist
python -m hatchling build -d release-dist
python scripts/audit_release_artifacts.py \
  --dist-dir release-dist \
  --check-allowlist
python -m twine check --strict release-dist/*
```

The exact `.github/workflows/*.yml` definitions at the candidate commit are authoritative.

Current contract expectations on `main` are:

- 167 MCP tools;
- 90% combined supported-environment coverage floor;
- 85% geometry-enabled Linux-only coverage floor plus per-file floors.

If the public contract intentionally changes, update its generated snapshot and documentation in the same reviewed change.

## 3. Decide what real acceptance is required

Real acceptance must be claim-specific and exact-version/exact-candidate bound.

For a release claiming Windows/live DipTrace/client integration, consider:

- clean Windows install, repair/idempotent reinstall and uninstall;
- workspace/pre-existing state preservation;
- a current real DipTrace 5 installation;
- PCB, Schematic, Component Editor and Pattern Editor paths actually claimed;
- real MCP client configuration/restart and `get_capabilities`;
- elevated plug-in installation while preserving the original user-profile client configuration;
- live apply/cancel/wrong-SHA paths;
- GUI/save/reopen/re-export confirmation for affected edits;
- proof that cancel/refusal does not mutate the host exchange document.

Do not broaden the published compatibility statement beyond the completed matrix.

The current project's 12-gate manual matrix is complete for its recorded checkpoints. A future release does not inherit those PASS results automatically: rerun only the gates affected by changed production code/artifacts or required by the new release claim, plus reasonable adjacent smoke coverage.

## 4. Build final assets from the frozen commit

Build and inspect only from the exact approved candidate/tag:

- source archive, sdist and wheel;
- packaged skills/schemas/metadata and wheel `RECORD` hashes/sizes;
- bridge, standalone server, configurator, installer and portable bundle;
- MCPB when part of the version;
- SBOM, dependency/notice/provenance inventories;
- source-distribution installation parity;
- SHA-256 coverage for every final asset;
- Authenticode status for Windows executables.

A successful build does not establish real DipTrace semantics or trusted code signing.

## 5. Signing decision

A trusted signed claim is allowed only when a real protected signing identity is configured and the final distributed executables verify under the documented signing workflow.

Self-signed/test certificates or merely configured signing infrastructure must not be represented as trusted publisher signing. PyPI Trusted Publishing is also not an Authenticode substitute.

If no protected signing identity exists, publish only with the explicit unsigned-development statement.

## 6. Stage and verify final bytes

Before public publication:

- verify `SHA256SUMS.txt`;
- install wheel and sdist and run CLI/MCP stdio smoke;
- run strict package metadata checks;
- install/uninstall the Windows installer;
- extract/smoke the portable bundle;
- inspect/smoke MCPB when included;
- verify `tools/list`, `get_capabilities`, packaged skills and schemas;
- perform the real acceptance matrix needed for the intended claims;
- record filenames, sizes, hashes and unsigned/signed status.

The release record must identify exact commit/tag target, acceptance versions/results, workflow runs, final asset inventory/hashes, signing status, supported environments, limitations and rollback/withdrawal decision.

## 7. Publish GitHub assets

Only after the reviewed gates pass:

1. merge the release-finalisation PR;
2. verify the merge tree matches the approved candidate;
3. create a **new** annotated tag at that exact commit;
4. build/fetch the immutable final assets and checksums from the tag-bound workflow;
5. publish them as the appropriate development/prerelease class;
6. publish notes that distinguish implemented, runtime-available and real-DipTrace-verified capabilities.

Never reuse or move `v0.2.1` or any older tag.

## 8. Verify public downloads

Redownload public files instead of reusing local/CI copies. Repeat checksum, wheel/sdist installation, CLI/MCP stdio, Windows installer, portable and MCPB verification as appropriate.

Record the immutable release URL/tag SHA, publication date, public asset sizes/hashes and public-download results.

## 9. Publish to PyPI

PyPI publication remains a separate explicit action and must use GitHub OIDC Trusted Publishing from the exact authorized tag/workflow/environment identity.

Current authorized identity:

```text
PyPI project:       diptrace-mcp
GitHub owner:       fireostendere
Repository:         mcp_diptrace
Workflow filename:  pypi.yml
Environment:        pypi
```

The build job and publish job stay separated. The publish job receives only already validated wheel/sdist artifacts and requires only the minimal permissions needed for OIDC publication.

After publication, verify the exact public version, hashes, project links, README rendering, publisher identity and attestations. Do not use `skip-existing` to hide a version collision.

## 10. Registry / directory metadata

Registry/Smithery/directory metadata must reference immutable public artifacts, not transient CI files.

For a future MCPB version:

1. publish and redownload the MCPB;
2. verify its SHA-256;
3. generate concrete metadata from that public URL/hash;
4. validate against the then-current registry/tooling schema;
5. publish and record the returned immutable identity.

Directory publication does not strengthen compatibility/evidence claims.

## 11. Post-release and rollback

Published tags, GitHub assets, PyPI versions and registry identities are immutable.

If a material problem is found:

- preserve original bytes and identities;
- document affected versions/hashes and required user action;
- withdraw/yank only where appropriate;
- publish a corrected new version;
- record whether confidentiality, unsafe mutation, installation or evidence claims were affected.

Before publication, abandon a candidate through ordinary reviewed branch/PR history. Do not rewrite `main` history merely to hide a failed candidate.
