# Release Process

## Current release status

Version `v0.1.2` remains the latest published development-stage release.
Version `0.2.0` is the current source/package version and an unpublished release
candidate.

The 0.2.0 service decomposition and release-preparation pull requests are merged
to `main`:

- PR #48 squash commit:
  `a4c9023cdbc982e5bc8e1867945105c18f49f3f5`;
- PR #49 merge commit:
  `4fdefcd5464d57fa7bef2aa7391eb5b0507798f6`;
- exact PR #49 CI run `30940972328`: success;
- exact PR #49 Windows installer run `30940972331`: success.

The candidate is **not tagged or published** while the blocking items in
[`RELEASE_0_2_0_CHECKLIST.md`](RELEASE_0_2_0_CHECKLIST.md) remain open. Its
candidate record is [`releases/v0.2.0.md`](releases/v0.2.0.md).

CI does not publish to PyPI. Current candidate Windows executables are unsigned.
A release presented as signed, independently reviewed, production-ready, or
universally compatible is prohibited without corresponding evidence.

A development-stage unsigned release may proceed only under the documented
solo-maintainer exception with exact commit identity, artifact hashes, test and
acceptance evidence, limitations, and rollback decision.

## 1. Approve scope and authority

Before changing release metadata or creating a tag:

1. identify the release manager;
2. identify an independent reviewer when one exists, or record the explicit
   solo-maintainer exception;
3. confirm the Apache-2.0 project license and current contribution/provenance
   rules;
4. review dependency, bundled-content, fixture, documentation, and binary
   redistribution status;
5. choose the supported compatibility statement;
6. complete the required real Windows/DipTrace/client acceptance;
7. freeze the exact commit;
8. move user-visible changes from `Unreleased` into the approved version/date;
9. update citation and release documentation to the same immutable identity.

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

For a release that claims Windows and live DipTrace integration, record dated
acceptance from the staged/final assets rather than the source tree.

Minimum 0.2.0 matrix:

- clean Windows 11 install;
- repair/idempotent reinstall;
- uninstall with workspace and user-state preservation;
- a current real DipTrace 5 installation;
- PCB Layout, Schematic Capture, Component Editor, and Pattern Editor profiles;
- real Codex configuration, restart, and `get_capabilities`;
- real Claude Desktop configuration, restart, and `get_capabilities`;
- elevated plug-in installation under Program Files while user configuration
  remains in the original profile;
- at least one fresh PCB and Schematic live apply/cancel/wrong-SHA path;
- GUI/save/re-export confirmation for applied changes;
- proof that cancel/refusal does not reach the host document.

Record exact OS, DipTrace, MCP client, Python/build, installer, and asset hashes.
Do not broaden the compatibility claim beyond the tested matrix.

Q1 Component Angle GUI/re-export validation remains a separate evidence gate.
It must stay `NOT_RUN` unless captured and reviewed.

## 4. Build final assets

Build only from the frozen commit. The intended asset set is:

- `DipTrace-MCP-Setup-0.2.0.exe`;
- `DipTrace-MCP-Portable-0.2.0.zip`;
- `diptrace_mcp-0.2.0-py3-none-any.whl`;
- `diptrace_mcp-0.2.0.tar.gz`;
- `SHA256SUMS.txt`;
- current SBOM, dependency inventory, third-party notices, and provenance
  records.

Inspect:

- source archive, sdist, and wheel contents;
- wheel entry points, packaged skills, schemas, and `RECORD` hashes/sizes;
- bridge, standalone server, configurator, installer, and portable inventory;
- runtime dependencies and notices;
- source-distribution rebuild parity;
- SHA-256 coverage for every final asset;
- Authenticode status for every executable.

A successful build does not establish real DipTrace semantics or a trusted code
signature.

## 5. Signing decision

The default 0.2.0 candidate decision is an explicitly unsigned development
release.

A signed claim is allowed only when:

- a real protected signing identity is configured;
- the protected signing workflow is executed for the final assets;
- every distributed executable verifies;
- the release record contains the signer/verification evidence.

Self-signed, test, or merely configured certificates must not be represented as
trusted signing.

## 6. Stage and verify

Stage the exact final files in a non-public release-manager-controlled channel.
From clean environments:

- verify `SHA256SUMS.txt`;
- install the wheel and run CLI/MCP stdio smoke;
- install and uninstall the Windows installer;
- extract and smoke the portable bundle;
- verify `tools/list` and `get_capabilities`;
- verify packaged skills and schemas;
- run the real acceptance matrix where claimed;
- confirm final asset filenames, sizes, hashes, and unsigned/signed status.

The release record must contain:

- exact commit and tag target;
- acceptance versions and results;
- CI/workflow run IDs;
- final asset names, sizes, and SHA-256 values;
- signing status;
- supported environments and known limitations;
- security/support paths;
- rollback/withdrawal decision.

## 7. Publish

Only after every required gate passes:

1. merge the final release-finalisation PR;
2. verify the merge commit matches the approved release tree;
3. create annotated tag `v0.2.0` from that commit;
4. publish immutable assets and checksums;
5. mark the release as development/prerelease when appropriate;
6. publish notes that distinguish implemented, runtime-available, and real
   DipTrace-verified capabilities;
7. avoid production-ready, signed, universal-compatibility, or endorsement
   claims not supported by evidence.

No automated package-index publication is configured.

## 8. Public-download verification

After publication, download the public files again rather than reusing local
build output.

Repeat:

- SHA-256 verification;
- clean wheel installation and CLI/MCP stdio smoke;
- Windows installer install/repair/uninstall;
- portable-bundle smoke;
- asset inventory and signing-status checks.

Update `docs/releases/v0.2.0.md` with the immutable release URL, tag SHA,
publication date, asset sizes/hashes, and public-download results.

## 9. Post-release and rollback

Monitor the published security and support paths. Never replace bytes under an
existing tag/version.

If a material problem is discovered:

- preserve the tag and original asset bytes;
- mark the release withdrawn when appropriate;
- record affected versions/hashes and required user action;
- publish a corrected version rather than moving the old tag;
- document whether confidentiality, unsafe mutation, installation, or evidence
  claims were affected.

Before publication, a candidate may be abandoned by closing or reverting its
release-finalisation PR. Do not rewrite `main` history or move existing tags.