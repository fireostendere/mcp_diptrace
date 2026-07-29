# Public Release Checklist

## Snapshot status

Audited repository state: 2026-07-30.

**Status: blocked.** The repository has an OSI-approved project-wide license
(Apache-2.0, committed as `LICENSE`) and a published 0.1.0 development-stage
release with an unsigned-binary disclosure, but no verified private security
or conduct channel, approved contribution terms, signed release artifact, or
independent release reviewer.

Checked boxes below describe repository facts in the audited state. Unchecked
boxes are release blockers, not publication claims.

## Legal, ownership, and redistribution

- [x] Accountable copyright holder is identified: the repository owner in
      [GOVERNANCE.md](../GOVERNANCE.md).
- [x] OSI-approved project license is selected and committed: Apache-2.0 as
      `LICENSE`; rationale in [LICENSE_DECISION.md](LICENSE_DECISION.md).
- [x] MIT, Apache-2.0, and MPL-2.0 tradeoffs are documented alongside the
      Apache-2.0 selection record in
      [LICENSE_DECISION.md](LICENSE_DECISION.md).
- [ ] Contribution provenance mechanism is approved.
- [ ] Dependency and bundled-content licenses are reviewed.
- [ ] Windows bridge and PyInstaller redistribution obligations are reviewed.
- [ ] Wheel-shipped skills and schemas are reviewed.
- [ ] Extracted specification text and generated inventory are approved for
      redistribution.
- [ ] Every distributed fixture and evidence artifact has documented
      provenance and redistribution permission.
- [ ] Trademark and non-affiliation wording is approved.

Until these items are complete, do not call the repository open source and do
not publish a package or binary release.

## Maintainers, governance, and community safety

- [x] Current GitHub repository authority is documented in
      [GOVERNANCE.md](../GOVERNANCE.md).
- [ ] Independent merge reviewer and release approver are identified.
- [ ] Repository succession and recovery are documented.
- [ ] Private security reporting is enabled and tested.
- [ ] Confidential conduct enforcement and a backup reviewer are enabled and
      tested.
- [ ] Conflict-of-interest and recusal rules are approved.
- [ ] Contribution intake is opened after license selection.
- [ ] DCO, CLA, or other contribution terms are published.
- [x] Bug, feature, and compatibility-evidence issue forms are committed.
- [x] A pull-request template covers scope, tests, provenance, and safety.

A Code of Conduct and vulnerability-reporting policy are intentionally absent
until real confidential channels and responsible people exist. A fictional
email address or unverified private-report URL would not resolve these gates.

## Product truth and documentation

- [x] README claims distinguish synthetic tests from controlled DipTrace
      evidence.
- [x] Runtime capability discovery is documented as authoritative.
- [x] Missing native library mutation and manufacturing output remain
      explicit.
- [x] Open compatibility questions and human-only experiments are documented.
- [x] Both READMEs state the license and public-release blocker.
- [x] Citation metadata records the Apache-2.0 license and the 0.1.0 release
      date.
- [x] The changelog does not present development version `0.1.0` as released.
- [ ] Package-index rendering of README links is verified or made independent
      of repository-relative link resolution.
- [ ] Windows plug-in settings, installer, and bridge-binary delivery are
      documented and tested separately from the Python wheel.
- [ ] Final installation instructions are tested from release artifacts.
- [ ] Announcement text is reviewed only after public URLs and license exist.

## Quality and compatibility

- [x] CI configuration covers Linux, macOS, and Windows.
- [x] CI includes geometry-enabled and no-Shapely Linux jobs.
- [x] CI builds and checks a non-empty unsigned Windows bridge.
- [x] Exact public MCP `tools/list` snapshot is committed and gated.
- [x] Specification inventory and format coverage have reproducibility gates.
- [x] Acceptance seed audit fails closed and reports zero accepted seeds.
- [ ] Release commit passes every required CI job.
- [ ] Coverage figures in public docs are regenerated from the release commit.
- [x] Release candidate is installed and smoke-tested from built artifacts
      (procedure in [TESTING.md](TESTING.md)).
- [ ] Supported Python, OS, DipTrace, transport, and bridge ranges are
      approved.
- [ ] Known limitations are copied into release notes without overclaiming.

## Artifact and supply-chain controls

- [x] CI builds source distributions and wheels from an exact versioned
      allowlist and rejects untracked, private, redirected, special, oversized,
      or unexpected archive members.
- [x] CI checks wheel entry points, eight packaged skills, project URLs,
      archive bounds, and every wheel `RECORD` hash and size.
- [x] A wheel rebuilt from the frozen source distribution is compared with the
      direct release wheel in the release environment.
- [x] The frozen release wheel is installed and smoke-tested with only its
      declared dependencies.
- [ ] Windows bridge contents and runtime dependencies are inspected.
- [x] Artifact SHA-256 manifest is generated (`SHA256SUMS.txt` release asset;
      see [releases/v0.1.0.md](releases/v0.1.0.md)).
- [x] A reviewed unsigned policy is disclosed for the unsigned 0.1.0
      artifacts; no signing identity is configured yet.
- [ ] Publication accounts have multi-factor authentication and recovery
      owners.
- [ ] Immutable artifact host and retention policy are documented.
- [ ] Tag, archive, wheel, binary, checksums, and release notes resolve to the
      same commit and version.

## Release operation

- [ ] Release manager and independent reviewer are named in the release record.
- [x] Version and frozen commit are approved (recorded in
      [releases/v0.1.0.md](releases/v0.1.0.md)).
- [x] `CHANGELOG.md` is finalized for the approved version and date.
- [x] Staged artifacts pass clean-environment installation and smoke tests.
- [ ] Security and conduct channels are monitored.
- [ ] Tag and artifacts are published through
      [RELEASE_PROCESS.md](RELEASE_PROCESS.md).
- [ ] English and Russian announcements are posted only after final public URLs
      are verified.
- [ ] Post-release support and incident processes are active.

## Explicit non-evidence

The repository does not currently provide verified facts about:

- community size, users, production deployments, downloads, stars, dependents,
  or adoption;
- sponsorship, funding, foundation membership, vendor endorsement, or formal
  partnership;
- acceptance into an open-source or infrastructure-support program;
- package-index publication or a signed public binary; or
- comprehensive DipTrace 5.3 writer compatibility.

Announcements and program applications must keep these values unknown unless
a dated, reproducible source is added.
