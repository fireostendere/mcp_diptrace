# Release Process

## Current release status

Version 0.1.0 is the current release, tagged `v0.1.0` with unsigned artifacts;
its provenance record is [releases/v0.1.0.md](releases/v0.1.0.md). CI has no
package-index publication job, and the Windows CI artifact is unsigned.

Publishing is prohibited while any blocking item in
[PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) remains open. The
GitHub repository owner is the only currently documented administrative
authority.

## 1. Approve scope and authority

Before changing a version or creating a tag:

1. identify the release manager and an independent reviewer in the release
   record;
2. identify a working private security channel and conduct-enforcement path;
3. confirm the selected OSI-approved license (Apache-2.0) and finish the
   ownership, dependency, bundled-content, fixture, documentation, and binary
   redistribution audits;
4. select the compatibility statement and supported-version window;
5. freeze the exact commit; and
6. move user-visible entries from `Unreleased` in
   [CHANGELOG.md](../CHANGELOG.md) to the approved version and date.

No announcement may describe unverified DipTrace behavior as verified or
implemented.

## 2. Run quality gates

Use a clean checkout of the frozen commit and run:

```bash
python -m pip install -e ".[dev,geometry]"
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts plugin
python -m mypy --no-incremental src/diptrace_mcp plugin
python scripts/generate_pcb_skills.py --check
python scripts/generate_mcp_tools_snapshot.py --check
python -m hatchling build -d release-dist
python scripts/audit_release_artifacts.py \
  --dist-dir release-dist \
  --check-allowlist
python scripts/extract_spec_inventory.py \
  --sources reference/diptrace-xml/extracted_text \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
python scripts/report_format_coverage.py --check
python scripts/make_probe_pack.py --check
python scripts/ingest_fixtures.py --dry-run --synthetic --json
python scripts/audit_acceptance_seeds.py
```

All required GitHub Actions jobs must pass on the same commit. A missing
platform result cannot be replaced by a local claim.

## 3. Build and inspect

Build only from the frozen commit. Inspect:

- the source archive, Python source distribution, and wheel;
- wheel contents, entry points, packaged skills, and generated schemas;
- the Windows bridge and its runtime dependencies;
- dependency, license, attribution, and notice material; and
- a SHA-256 manifest covering every release artifact.

The committed build hook and release-artifact audit constrain the Python
archives to an exact versioned allowlist. They do not turn a development build
into a release and do not cover the Windows bridge executable. Rebuild the
wheel from the source distribution in the release environment and compare it
with the direct wheel before publication.

The Python wheel contains the MCP server and eight packaged skills. It does
not contain the PowerShell build/installer scripts or DipTrace plug-in settings
needed for complete Windows live-bridge deployment; publish and verify those
as separate release assets.

The Windows bridge is currently unsigned. A public binary must either be
signed by an approved identity or carry an explicit, reviewed unsigned-binary
disclosure. CI success is not a code signature.

## 4. Stage and verify

Stage artifacts in a non-public channel controlled by the release manager.
Install the staged wheel and bridge rather than the source tree. Run CLI,
public MCP `tools/list`, skill-delivery, and headless bridge smoke tests on
supported platforms. Download the staged artifacts and verify their hashes.

The release record must contain the frozen commit, artifact hashes, test
results, approvers, supported environments, known limitations, security
channel, artifact retention policy, and rollback decision.

## 5. Publish

Only after every gate is complete:

1. create the approved tag from the frozen commit;
2. publish immutable artifacts and checksums;
3. verify installation from public artifacts in a clean environment;
4. publish release notes that distinguish implemented, runtime-available, and
   DipTrace-verified capabilities; and
5. publish announcements only after every URL, version, license, checksum,
   support statement, and contact has been verified.

No automated package-index publication is configured by this policy.

## 6. Post-release and rollback

Monitor the published security and support paths. Never replace an immutable
artifact under an existing version. If a release is defective, publish a new
version or withdraw it according to the selected registry policy.

The incident record must state the affected version and hashes, reason,
confidentiality or unsafe-mutation impact, required user action, replacement
version or support status, and disclosure decision.
