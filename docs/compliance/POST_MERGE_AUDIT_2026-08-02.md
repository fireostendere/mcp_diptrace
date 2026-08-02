# Post-merge security and compliance audit — 2026-08-02

## Scope and exact revisions

- audited branch base/main commit: `f4ea60352a560d03f0cee45d500c186530e6f5f6`;
- PR #40 head preserved in that merge: `209a7ca05a82a9aa129866cdfbb87644728dc09d`;
- audit work is performed on the separate `audit/post-merge-hardening` branch;
- no tag, release, history rewrite, SignPath request, DipTrace request, or
  private-document publication is part of this audit.

## Ruleset and test PR

GitHub API evidence is summarized in
[BRANCH_PROTECTION_STATUS.md](BRANCH_PROTECTION_STATUS.md). The ruleset was
active for the default branch and required pull requests, conversation
resolution, DCO, and nine unique status contexts with zero required approvals.
Deletion and non-fast-forward updates were blocked. The API also reported
strict up-to-date checks and all three merge methods; those differ from the
earlier intended settings and remain an owner decision. Test PR #41 was closed
without merge, contained only `branch-protection-test.txt`, and its remote
branch was absent at the check. The file is absent from main. No complete
status result was returned for the short-lived test head.

## Scanner and inventory results

The sanitized summaries in this document are updated from local or manual
workflow runs. Raw reports are never committed and remain only under the
ignored `.local/open-source-readiness/deep-audit/` directory.

- Secret scan: Gitleaks and detect-secrets scan the current tracked tree and
  all reachable Git objects; `.local/` is not staged or scanned. Findings are
  summarized by rule/plugin and relative path only. A finding is a stop-and-
  rotate event, not an item to suppress broadly.
- Dependency audit: pip-audit checks runtime, geometry, build, PyInstaller,
  and development requirement groups separately. It does not modify
  `pyproject.toml` and does not claim that a clean advisory result proves
  general security.
- License audit: ScanCode, REUSE, pip-licenses, existing SBOM generation, and
  third-party notices are compared. Automated identification is not legal
  clearance; the current dependency inventory and notices retain human-review
  flags, including transitive and PyInstaller content.
- Clean-room build: a fresh clone/worktree must be clean, build wheel and
  sdist, audit the release allowlist, rebuild a wheel from sdist, compare every
  member SHA-256, install only declared runtime dependencies, run CLI help,
  initialize/list tools over MCP stdio, and perform a synthetic read-only XML
  smoke. Archive names and content are checked for ignored/private and extracted
  DipTrace materials, source PDFs, generated spec inventory, and workstation
  paths.
- Windows bundle: this Linux environment cannot execute the Windows bridge or
  PowerShell. The manual workflow builds the current bridge, runs `--help`,
  inventories it with `pyi-archive_viewer`, checks `Get-AuthenticodeSignature`,
  and tests signing-required failure without credentials. The current expected
  state remains unsigned; no EXE is committed.
- Artifact SBOM: Syft is run against wheel, sdist, plugin ZIP, and Windows
  bundle when those artifacts exist. Differences from `pyproject.toml`,
  `dependency-inventory.json`, `sbom.cdx.json`, and
  `THIRD_PARTY_NOTICES.md` are recorded as review items, not silently merged
  into the deterministic project SBOM.

## Findings and limitations

The API verification found two policy/documentation mismatches: strict
up-to-date checks are enabled and all three merge methods are allowed. The
ruleset was not changed automatically. No local Windows/PowerShell run was
possible, so Windows bundle/signature evidence remains pending the manual
workflow. No independent legal, DipTrace-permission, independent-release-
reviewer, conduct-channel, succession/recovery, or full bundled-dependency
clearance claim is made.

## Reproduction

```bash
python scripts/run_deep_audit.py
python scripts/run_dependency_audit.py
reuse lint
scancode --license --copyright --info --package --strip-root \
  --json-pp .local/open-source-readiness/deep-audit/raw/scancode-tree.json .
python scripts/summarize_scancode.py \
  .local/open-source-readiness/deep-audit/raw/scancode-tree.json \
  --output .local/open-source-readiness/deep-audit/scancode-summary.json
python scripts/run_clean_room_audit.py --source /path/to/clean/clone
```

The heavy/manual workflow is
[`deep-compliance-audit.yml`](../../.github/workflows/deep-compliance-audit.yml).
It is intentionally not one of the existing required checks.
