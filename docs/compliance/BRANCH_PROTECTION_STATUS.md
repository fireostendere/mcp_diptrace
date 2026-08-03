# Main branch protection status

Checked: 2026-08-03

The checked default branch was `main` at
`3f06ffc084154f59a116540694f071c513323215` (the merge commit for PR #43). The
active ruleset is named **Protect main** (id `20233687`) and targets the default
branch through GitHub's `~DEFAULT_BRANCH` ref condition.

## Rules observed through GitHub API

- enforcement is `active`;
- pull requests are required;
- required approving reviews: `0` (solo-maintainer mode);
- required conversation/thread resolution is enabled;
- code-owner, last-push approval, and required reviewer rules are not enabled;
- deletion and non-fast-forward updates are blocked;
- GitHub returned eleven required-status records, representing nine unique
  contexts:
  `DCO`, `static-analysis`, `test-linux (3.10)`, `test-linux (3.13)`,
  `test-linux geometry + coverage (3.12)`,
  `test-linux no-Shapely fallback (3.12)`, `test-macos`, `test-windows`, and
  `build-windows-bridge`;
- duplicate records for `test-linux (3.10)` and `build-windows-bridge` differ
  only by the GitHub Actions integration identifier; they are recorded as one
  unique context each above and were not changed automatically;
- the API reports `strict_required_status_checks_policy: true`, so branches
  must be up to date before merging;
- the API reports all three merge methods (`merge`, `squash`, and `rebase`)
  as allowed;
- a repository-role bypass actor with id `5` is present for pull requests, and
  the authenticated audit identity reports `current_user_can_bypass:
  pull_requests_only`. This is an observed GitHub setting, not an assertion
  about the human identity behind that role or about immutable administration.

The ruleset was queried read-only with the repository ruleset REST endpoints on
2026-08-03. Classic branch-protection lookup returned no protected-branch
record; the active ruleset is the observed enforcement mechanism. This audit
does not change the ruleset, infer owner intent, or claim that the settings
cannot be changed externally.

Settings link: [GitHub branch rules](https://github.com/fireostendere/mcp_diptrace/settings/rules).

GitHub settings are external state. They are not stored in Git and may be
changed by the repository owner; this file is dated evidence, not an
immutability guarantee.
