# Governance

## Current repository authority

The GitHub repository is owned by
[`@fireostendere`](https://github.com/fireostendere). No broader maintainer
roster, reviewer group, foundation affiliation, sponsor, or community mandate
is asserted.

Repository administration, branch protection, merge access, and any future
release remain under the GitHub repository owner's control. The repository is
licensed under the Apache License 2.0 (see [`LICENSE`](LICENSE)). Issues and
pull requests may be opened under the contribution and provenance rules in
[`CONTRIBUTING.md`](CONTRIBUTING.md); the owner decides whether a proposed
change is merged.

Contributions follow Developer Certificate of Origin 1.1 as documented in
[`DCO`](DCO) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Decision record

Changes to safety gates, evidence trust, accepted DipTrace conventions,
fixture provenance, release policy, the public MCP API, licensing, or
redistribution must be recorded in reviewable Git history. A green test based
only on synthetic fixtures is not evidence of DipTrace behavior.

No release may bypass a blocker in
[the public-release checklist](docs/PUBLIC_RELEASE_CHECKLIST.md). The
repository owner is responsible for deciding whether a blocker is resolved and
for preserving the evidence behind that decision.

As checked on 2026-08-03 at main SHA
`3f06ffc084154f59a116540694f071c513323215`, `main` is covered by the active GitHub ruleset
documented in [BRANCH_PROTECTION_STATUS.md](docs/compliance/BRANCH_PROTECTION_STATUS.md).
Changes are required to come through pull requests with conversation resolution,
DCO, and the required technical CI checks; force-pushes and branch deletion are
blocked. Required approvals are `0` for the current solo-maintainer mode. The
ruleset is an administrative GitHub setting, not a second reviewer: the owner
retains the administrative ability to change it, and this document does not
claim independent review or a second maintainer. The API also reports strict
up-to-date checks, all three merge methods, and a repository-role pull-request
bypass; those facts are retained in the dated status record and are not
immutability claims.

## Missing governance functions

The repository does not currently provide:

- an independent reviewer or second release approver;
- a succession or repository-recovery policy;
- a conflict-of-interest and recusal process;
- a confidential conduct-enforcement channel; or
- a second person with merge or release authority.

Private vulnerability reporting is enabled through GitHub and published in
[SECURITY.md](SECURITY.md). The remaining items are explicit governance
limitations. A Code of Conduct is not published yet because there is no
verified confidential enforcement channel or enforcement team. Publishing a
fictional contact would make the policy unsafe.

## Governance changes

Any governance expansion must be committed with its effective date and must
name the real GitHub accounts receiving authority. Private contact details
must be tested before they are referenced. Governance text must not imply that
a contributor community, adoption, sponsorship, vendor endorsement, or support
program acceptance exists without dated evidence.
