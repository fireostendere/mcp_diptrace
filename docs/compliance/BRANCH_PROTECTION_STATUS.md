# Main branch protection status

Checked: 2026-08-02

The checked default branch was `main` at
`f4ea60352a560d03f0cee45d500c186530e6f5f6` (the ordinary merge commit for PR
#40). The active ruleset is named **Protect main** and targets the default
branch through GitHub's `~DEFAULT_BRANCH` ref condition.

## Rules observed through GitHub API

- enforcement is `active`;
- pull requests are required;
- required approving reviews: `0` (solo-maintainer mode);
- required conversation/thread resolution is enabled;
- code-owner, last-push approval, and required reviewer rules are not enabled;
- deletion and non-fast-forward updates are blocked;
- nine unique required status contexts are present:
  `DCO`, `static-analysis`, `test-linux (3.10)`, `test-linux (3.13)`,
  `test-linux geometry + coverage (3.12)`,
  `test-linux no-Shapely fallback (3.12)`, `test-macos`, `test-windows`, and
  `build-windows-bridge`;
- GitHub returned duplicate entries for `test-linux (3.10)` and
  `build-windows-bridge` with and without an integration identifier; they are
  recorded as one context each above and were not changed automatically;
- the API reports `strict_required_status_checks_policy: true`, so branches
  must be up to date before merging. This differs from the earlier intended
  setting and requires an owner decision if that policy is not wanted;
- the API reports all three merge methods (`merge`, `squash`, and `rebase`)
  as allowed. This differs from the earlier ordinary-merge-only expectation
  and requires an owner decision if ordinary merge is the intended policy;
- no bypass actor was exposed in the unauthenticated ruleset response. This
  record therefore does not claim that bypass is impossible or that the
  administrator cannot change the ruleset.

The ruleset was queried with the repository ruleset REST endpoints and checked
against the public PR #41 test record. PR #41 (`test: verify branch protection`)
was closed without merge, had one changed file (`branch-protection-test.txt`),
and its remote head branch was absent at the audit check. The file is absent
from `main`. No status contexts were returned for the short-lived test head,
so this document does not claim that a complete CI run was recorded for PR #41.

Settings link: [GitHub branch rules](https://github.com/fireostendere/mcp_diptrace/settings/rules).

GitHub settings are external state. They are not stored in Git and may be
changed by the repository owner; this file is dated evidence, not an
immutability guarantee.
