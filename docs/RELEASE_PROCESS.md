# Release Process

## Current release status

Version 0.1.2 is the current development-stage release line, with unsigned
artifacts and provenance in [releases/v0.1.2.md](releases/v0.1.2.md). The
previous `v0.1.1` release is explicitly withdrawn in
[releases/v0.1.1.md](releases/v0.1.1.md). CI has no package-index publication
job, and the Windows CI artifact is unsigned.

A release presented as independently reviewed, signed, or production-ready is prohibited while the corresponding blocking items in [PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md) remain open. A development-stage unsigned release may proceed only through an explicit solo-maintainer exception recorded with its limitations, artifact hashes, test evidence, and rollback decision. The GitHub repository owner is the only currently documented administrative authority.

Contribution intake uses the DCO 1.1 and provenance requirements in
[`CONTRIBUTING.md`](../CONTRIBUTING.md). External announcement, grant, and
application materials are maintained outside Git. They must not be copied into
release records, source archives, or release assets.

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

For a correction release, use one temporary release branch and one pull
request. Preserve the original release commit with an explicit Git revert;
do not rewrite `main`, move the old tag, or replace old release assets. Merge
the PR only after every required job passes for that exact PR head.

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
  --sources tests/fixtures \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
python scripts/report_format_coverage.py --check
python scripts/make_probe_pack.py --check
python scripts/ingest_fixtures.py --dry-run --synthetic --json
python scripts/audit_acceptance_seeds.py
python scripts/measure_mcp_surface.py --baseline-bytes 121335 --max-growth-percent 15
python scripts/verify_geometry_backend.py --expect shapely_geos
python scripts/smoke_bridge_headless.py
```

All required GitHub Actions jobs must pass on the same commit. A missing platform result cannot be replaced by a local claim. When release notes claim live PCB or Schematic integration, attach a dated acceptance record for the exact server/bridge baseline and clearly separate local host evidence from public CI.

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

The reference-document extraction bundles and generated specification inventory
are engineering inputs with unresolved redistribution status. They are kept
out of future source archives and wheels until a human confirms a redistribution
basis; the local regeneration command remains available to an operator with
legitimate source documents.

The Python wheel contains the MCP server and eight packaged skills. It does
not contain the PowerShell build/installer scripts or DipTrace plug-in settings
needed for complete Windows live-bridge deployment; publish and verify those
as separate release assets.

The Windows development asset set additionally contains
`DipTrace-MCP-Setup-<version>.exe` and
`DipTrace-MCP-Portable-<version>.zip`. The installer is the primary user asset;
the ZIP is a no-Python fallback. Both are built from the staged onedir server,
the existing bridge pipeline, the four settings profiles, and the standalone
configurator. The installer does not fetch runtime code. Its writable state is
outside the installed application, and its uninstaller preserves workspaces,
backups, logs, client-config backups, and state by default.

The current bundle build includes Shapely/GEOS only when the exact Windows
geometry smoke passes. A successful installer build does not establish live
DipTrace semantics, Q1 rotation validation, universal DipTrace-version
support, or permission/endorsement from Novarm.

The Windows bridge is currently unsigned. A public binary must either be
signed by an approved identity or carry an explicit, reviewed unsigned-binary
disclosure. CI success is not a code signature.

The same rule applies to the server executable and installer. The unsigned
development path calculates SHA-256 values and records
`unsigned-until-verified`; `SIGNING_REQUIRED=true` must fail closed and verify
Authenticode after signing. No test certificate, self-made certificate, or
SignPath request may be represented as a trusted signature.

## 4. Stage and verify

Stage artifacts in a non-public channel controlled by the release manager.
Install the staged wheel and bridge rather than the source tree. Run CLI, public MCP `tools/list`, skill-delivery, and headless bridge smoke tests on supported platforms. For a release that claims Windows live integration, run fresh-session PCB and Schematic apply/cancel/wrong-SHA acceptance, verify GUI/save/re-export behavior for applied changes, and prove cancelled/refused changes do not reach the host document. Download the staged artifacts and verify their hashes.

The release record must contain the frozen commit, artifact hashes, test
results, approvers, supported environments, known limitations, security
channel, artifact retention policy, and rollback decision.

For Windows, also retain the exact workflow run, Python version, pinned
PyInstaller/constraint file, Inno Setup compiler version and package SHA-256,
portable inventory/checksum report, installer size, server cold-start and MCP
initialize timings, Authenticode status, SBOM, and sanitized provenance
inventory. Unknown timings or missing native Windows results remain blockers
for stronger claims.

## 5. Publish

Only after every gate is complete:

1. create the approved annotated tag from the exact merge commit;
2. publish immutable artifacts and checksums;
3. download the published artifacts again and verify installation from those
   public files in a clean environment;
4. publish release notes that distinguish implemented, runtime-available, and
   DipTrace-verified capabilities; and
5. publish any external announcement only after every URL, version, license,
   checksum, support statement, and contact has been verified privately.

No automated package-index publication is configured by this policy.

## 6. Post-release and rollback

Monitor the published security and support paths. Never replace an immutable
artifact under an existing version. If a release is defective, publish a new
version or withdraw it according to the selected registry policy.

The incident record must state the affected version and hashes, reason,
confidentiality or unsafe-mutation impact, required user action, replacement
version or support status, and disclosure decision.
