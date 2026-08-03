# Public Release Checklist

## Snapshot status

Audited repository state: 2026-08-03 (main SHA
`3f06ffc084154f59a116540694f071c513323215`).

**Status: v0.1.2 is a verified development-stage release under an explicit solo-maintainer exception.** The repository has an OSI-approved project-wide license (Apache-2.0, committed as `LICENSE`), open DCO 1.1 contribution intake, private vulnerability reporting published as `SECURITY.md`, an active main-branch ruleset, an unsigned-binary disclosure, a completed 2026-07-31 live acceptance matrix, green exact-head CI, and verified public release assets. It still has no verified conduct channel, signed release artifact, dependency/bundled-content legal review, or independent release reviewer, so it must not be represented as independently reviewed, signed, or production-ready.

Checked boxes below describe repository or release facts in the audited state.
Unchecked boxes are blockers for stronger publication, redistribution, governance,
or production-readiness claims; they do not negate the verified alpha/development-
stage status of v0.1.2.

## Legal, ownership, and redistribution

- [x] Accountable copyright holder is identified: the repository owner in
      [GOVERNANCE.md](../GOVERNANCE.md).
- [x] OSI-approved project license is selected and committed: Apache-2.0 as
      `LICENSE`; rationale in [LICENSE_DECISION.md](LICENSE_DECISION.md).
- [x] MIT, Apache-2.0, and MPL-2.0 tradeoffs are documented alongside the
      Apache-2.0 selection record in
      [LICENSE_DECISION.md](LICENSE_DECISION.md).
- [x] DCO 1.1 is published in [`DCO`](../DCO) and contribution provenance
      requirements are documented in [CONTRIBUTING.md](../CONTRIBUTING.md).
- [x] Contribution intake is open under DCO 1.1 and the provenance/privacy
      checks in [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] Dependency and bundled-content licenses are reviewed.
- [ ] Windows bridge and PyInstaller redistribution obligations are reviewed.
- [ ] Wheel-shipped skills and schemas are reviewed.
- [x] Verbatim external specification extracts and source PDFs are absent from
      the current Git tree and release surfaces; no history rewrite was done.
- [ ] Any Novarm/DipTrace redistribution permission is confirmed in writing;
      none is claimed by this repository.
- [x] The replacement factual inventory is project-authored and generated from
      own XML fixtures; it does not claim normative or vendor clearance.
- [ ] Every distributed fixture and evidence artifact has documented
      provenance and redistribution permission.
- [ ] Trademark and non-affiliation wording is approved.

Until the remaining redistribution and review items are complete, do not claim every bundled asset has independent clearance and do not publish a release as independently reviewed, signed, or production-ready. Development-stage publication uses the explicit exception and disclosures described in [RELEASE_PROCESS.md](RELEASE_PROCESS.md).

## Maintainers, governance, and community safety

- [x] Current GitHub repository authority is documented in
      [GOVERNANCE.md](../GOVERNANCE.md).
- [x] The default `main` branch has an active ruleset requiring pull requests,
      conversation resolution, DCO, and nine unique technical CI contexts
      (eleven API status records); force-push and deletion are blocked and
      approvals are `0` for the solo-maintainer mode. The API also reports
      strict up-to-date checks, all three merge methods, and a repository-role
      pull-request bypass. These are external, owner-changeable settings;
      evidence is in
      [BRANCH_PROTECTION_STATUS.md](compliance/BRANCH_PROTECTION_STATUS.md).
- [x] The ruleset was exercised by test PR #41, which was closed without merge;
      its one-file test branch is not present in `main`.
- [ ] Independent merge reviewer and release approver are identified.
- [ ] Repository succession and recovery are documented.
- [x] Private security reporting is enabled (GitHub private vulnerability
      reporting, 2026-07-30) and published in
      [SECURITY.md](../SECURITY.md); channel URL verified anonymously.
- [ ] Confidential conduct enforcement and a backup reviewer are enabled and
      tested.
- [ ] Conflict-of-interest and recusal rules are approved.
- [x] DCO 1.1 and contribution terms are published; no CLA is claimed.
- [x] Bug, feature, and compatibility-evidence issue forms are committed.
- [x] A pull-request template covers scope, tests, provenance, and safety.
- [x] The PR template covers DCO, provenance, AI assistance, security, privacy,
      and data-origin confirmation.

A Code of Conduct is intentionally absent until a real confidential
enforcement channel and responsible people exist. A fictional email address
would not resolve this gate. The vulnerability-reporting policy is published
in [SECURITY.md](../SECURITY.md).

## Product truth and documentation

- [x] README claims distinguish synthetic tests from controlled DipTrace
      evidence.
- [x] Runtime capability discovery is documented as authoritative.
- [x] Missing native library mutation and manufacturing output remain
      explicit.
- [x] Open compatibility questions and human-only experiments are documented.
- [x] Both READMEs state the license and public-release limitations.
- [x] Citation metadata records the Apache-2.0 license and the 0.1.2 release
      date.
- [x] The changelog and release provenance distinguish the withdrawn `0.1.1`
      release from the corrected `0.1.2` development-stage release.
- [ ] Package-index rendering of README links is verified or made independent
      of repository-relative link resolution.
- [x] Windows plug-in settings, installer, and bridge-binary delivery are documented separately from the Python wheel; clean build, four-target install hash checks, and live PCB/Schematic acceptance were completed on 2026-07-31.
- [x] Final installation instructions were tested from the publicly downloaded
      v0.1.2 release artifacts.
- [x] External announcement materials are maintained privately by the
      repository owner; no forum or announcement draft is stored in Git.

## Quality and compatibility

- [x] CI configuration covers Linux, macOS, and Windows.
- [x] CI includes geometry-enabled and no-Shapely Linux jobs.
- [x] CI builds, verifies, and smoke-runs the unsigned Windows bridge
      executable.
- [x] Exact public MCP `tools/list` snapshot is committed and gated.
- [x] Clean-room factual inventory and format coverage have reproducibility
      gates; the inventory is observation data, not a vendor specification.
- [x] Acceptance seed audit fails closed and reports zero accepted seeds.
- [x] Windows DipTrace 5.2.0.4 ↔ WSL MCP live acceptance covers the tested PCB/Schematic apply, cancel, and wrong-SHA matrix, with GUI/save/re-export checks and no phantom path.
- [x] The exact final PR head `759234f209927e3c033e44d63494d3ca3cfae150`
      passed all eight required jobs in CI run `30709466348`; the ordinary merge
      commit preserved that tested release tree.
- [x] Public documentation distinguishes the frozen candidate coverage result
      from the exact-head GitHub CI coverage result.
- [x] The release candidate and publicly downloaded wheel were installed and
      smoke-tested from v0.1.2 artifacts using the procedure in
      [TESTING.md](TESTING.md).
- [ ] Supported Python, OS, DipTrace, transport, and bridge ranges receive an
      independent compatibility approval.
- [x] Known limitations are copied into release notes and any external
      announcements without production-ready or universal-compatibility claims.

## Artifact and supply-chain controls

- [x] CI builds source distributions and wheels from an exact versioned
      allowlist and rejects untracked, private, redirected, special, oversized,
      or unexpected archive members.
- [x] CI checks wheel entry points, eight packaged skills, project URLs,
      archive bounds, and every wheel `RECORD` hash and size.
- [x] A wheel rebuilt from the frozen source distribution was compared with the
      direct release wheel by member set and per-member SHA-256.
- [x] The frozen and publicly downloaded release wheels were installed and
      smoke-tested with only their declared dependencies.
- [x] Windows bridge contents and bundled runtime dependencies were inspected;
      PowerShell `--help`, plug-in ZIP, and all four settings profiles passed.
- [x] `SHA256SUMS.txt` covers all ten v0.1.2 release assets, and a fresh public
      download passed `sha256sum -c`.
- [x] A reviewed unsigned policy is disclosed for the unsigned 0.1.2
      artifacts; no signing identity is configured yet.
- [x] A technical unsigned/signed artifact boundary, verification script, and
      manual protected signing workflow are documented; no SignPath account or
      certificate is configured.
- [ ] Publication accounts have documented multi-factor-authentication and
      recovery owners.
- [ ] Immutable artifact-host retention and recovery policy is documented.
- [x] Tag, wheel, source distribution, binary, plug-in ZIP, checksums, evidence
      files, installation guide, and release notes resolve to version 0.1.2 and
      the documented frozen release provenance. Historical external announcement
      assets are not maintained in the current repository tree.

## Release operation

- [x] Release manager is named in [releases/v0.1.2.md](releases/v0.1.2.md).
- [ ] An independent release reviewer is named.
- [x] Version and frozen merge commit are recorded in
      [releases/v0.1.2.md](releases/v0.1.2.md).
- [x] `CHANGELOG.md` is finalized for the approved version and date.
- [x] Staged and publicly downloaded v0.1.2 artifacts passed clean-environment
      installation and smoke tests.
- [ ] Security and conduct channels have documented ongoing monitoring and
      backup ownership.
- [x] Tag and the ten historical v0.1.2 artifacts are published through the process in
      [RELEASE_PROCESS.md](RELEASE_PROCESS.md).
- [ ] External announcements, if posted, are reviewed privately before
      publication; no repository draft is required or retained.
- [ ] Post-release support and incident processes have documented active owners.

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
a dated, reproducible source is added. Application materials are maintained
privately by the repository owner.
