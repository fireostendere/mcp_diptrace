# Release Process

## Current release status

Version `v0.2.0` is the latest published unsigned alpha/development prerelease.
Its annotated tag points to
`31766cb6e667dc24f3e2921decfd65c03eebd271`; the immutable record is
[`releases/v0.2.0.md`](releases/v0.2.0.md).

The project is not published to PyPI, the official MCP Registry, or Smithery.
Version 0.2.0 contains no MCPB asset. MCPB and `server.json` tooling is
preparation for a future version only; existing tags and release files must
never be replaced.

Windows executables remain unsigned. CI and SHA-256 establish tested behaviour
and byte identity, not trusted publisher signing, universal compatibility,
independent review, or production readiness.

The one-shot automatic v0.2.0 publication path has been removed. Future releases
require a new reviewed finalisation PR and an explicit publication action.

## 1. Approve scope and authority

Before changing release metadata or creating a tag:

1. identify the release manager;
2. identify an independent reviewer when one exists, or record an explicit
   solo-maintainer exception;
3. confirm licensing, contribution, provenance, dependency, bundled-content,
   fixture, and binary-redistribution status;
4. choose the exact supported compatibility statement;
5. complete the real Windows/DipTrace/client acceptance required by that claim;
6. freeze one exact candidate commit;
7. move approved user-visible changes from `Unreleased` to a dated version;
8. update citation, installation, and release documentation to the same
   immutable identity.

Do not claim Novarm/DipTrace endorsement, affiliation, approval, or permission
without explicit evidence.

## 2. Run repository quality gates

Use a clean checkout of the exact candidate commit:

```bash
python -m pip install -e '.[dev,geometry]'
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
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
```

All required GitHub Actions jobs must pass on the same pull-request head. A
missing platform result cannot be replaced by a local assertion.

Current public contract expectations are:

- 159 MCP tools;
- 142,746 canonical snapshot bytes;
- MCP snapshot SHA-256
  `073f53681306fd13c5f3f29d61baed9a83fc9eb5c1ed14883846005a39d812db`;
- 157 public Facade methods;
- 148 explicit delegations.

## 3. Complete real acceptance

For a release claiming Windows and live DipTrace integration, record dated
acceptance from staged/final assets rather than the source tree.

Minimum matrix:

- clean Windows 11 install, repair/idempotent reinstall, and uninstall;
- workspace and pre-existing user-state preservation;
- a current real DipTrace 5 installation;
- PCB Layout, Schematic Capture, Component Editor, and Pattern Editor profiles;
- real Codex configuration, restart, and `get_capabilities`;
- real Claude Desktop configuration, restart, and `get_capabilities`;
- elevated plug-in installation under Program Files while client configuration
  remains in the original user profile;
- fresh PCB and Schematic live apply/cancel/wrong-SHA paths;
- GUI/save/re-export confirmation for applied changes;
- proof that cancel/refusal does not reach the host document.

Record exact OS, DipTrace, MCP client, Python/build, installer, and asset hashes.
Do not broaden the compatibility claim beyond the tested matrix.

Q1 Component Angle GUI/re-export validation remains a separate evidence gate and
must stay `NOT_RUN` unless captured and reviewed.

## 4. Build final assets

Build only from the frozen commit. Inspect:

- source archive, sdist, and wheel contents;
- wheel entry points, packaged skills, schemas, and `RECORD` hashes/sizes;
- bridge, standalone server, configurator, installer, and portable inventory;
- MCPB manifest/archive contents when MCPB is part of the new version;
- runtime dependencies, notices, SBOM, and provenance;
- source-distribution rebuild parity;
- SHA-256 coverage for every final asset;
- Authenticode status for every executable.

A successful build does not establish real DipTrace semantics or a trusted code
signature.

## 5. Signing decision

A signed claim is allowed only when:

- a real protected signing identity is configured;
- the protected signing workflow is executed for the final assets;
- every distributed executable verifies;
- the release record contains signer and verification evidence.

Self-signed, test, or merely configured certificates must not be represented as
trusted signing. Otherwise publish only with an explicit unsigned-development
statement.

## 6. Stage and verify

Stage the exact final files in a non-public release-manager-controlled channel.
From clean environments:

- verify `SHA256SUMS.txt`;
- install the wheel and run CLI/MCP stdio smoke;
- install and uninstall the Windows installer;
- extract and smoke the portable bundle;
- inspect and smoke the MCPB when included;
- verify `tools/list`, `get_capabilities`, packaged skills, and schemas;
- run the real acceptance matrix where claimed;
- confirm filenames, sizes, hashes, and unsigned/signed status.

The release record must contain the exact commit/tag target, acceptance versions
and results, workflow run IDs, final asset inventory and hashes, signing status,
supported environments, known limitations, security/support paths, and rollback
or withdrawal decision.

## 7. Publish

Only after the approved gates pass:

1. merge the final release-finalisation PR;
2. verify the merge commit matches the approved tree;
3. create a new annotated tag from that exact commit;
4. publish immutable assets and checksums;
5. mark the release as development/prerelease when appropriate;
6. publish notes distinguishing implemented, runtime-available, and real
   DipTrace-verified capabilities;
7. avoid unsupported production, signing, compatibility, or endorsement claims.

No automatic package-index or registry publication is configured. Publishing to
PyPI, the official MCP Registry, Smithery, or another directory is a separate
explicit action after public asset verification.

## 8. Public-download verification

After publication, download public files again rather than reusing local build
output. Repeat checksum, wheel installation, CLI/MCP stdio, Windows installer,
portable, and any MCPB verification. Record the immutable release URL, tag SHA,
publication date, asset sizes/hashes, and public-download results.

For a future MCPB release, generate concrete `server.json` only from the public
MCPB URL and its verified SHA-256. Revalidate the current Registry and Smithery
schemas and CLIs at publication time.

## 9. Post-release and rollback

Monitor published security and support paths. Never replace bytes under an
existing tag or version.

If a material problem is discovered:

- preserve the tag and original asset bytes;
- mark the release withdrawn when appropriate;
- record affected versions/hashes and required user action;
- publish a corrected version rather than moving the old tag;
- document whether confidentiality, unsafe mutation, installation, or evidence
  claims were affected.

Before publication, abandon a candidate by closing or reverting its
release-finalisation PR. Do not rewrite `main` history or move existing tags.
