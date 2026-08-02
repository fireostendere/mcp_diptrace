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

- Secret scan: Gitleaks 8.30.1 and detect-secrets 1.5.0 both returned zero
  findings for the current tracked tree and all reachable Git blobs. The
  sanitized local summary records the exact file/blob counts; `.local/` was
  not staged or scanned. Findings are summarized by rule/plugin and relative
  path only. A finding is a stop-and-rotate event, not an item to suppress
  broadly.
- Dependency audit: pip-audit 2.10.1 checked runtime, geometry, build,
  PyInstaller, and development groups separately. Runtime, geometry, build,
  and PyInstaller groups were clean. Development has one actionable finding:
  `pytest` 8.4.2 is affected by `PYSEC-2026-1845` (aliases
  `CVE-2025-71176` and `GHSA-6w46-j5rx-g56g`), with fix `9.0.3`. The advisory
  concerns local UNIX temporary-directory handling and is not a runtime or
  wheel dependency finding. No dependency was changed automatically;
  upgrading the development constraint and rerunning the full matrix is a
  HUMAN ACTION REQUIRED decision.
- License audit: REUSE 6.2.0 is not compliant for this tree because many
  project files lack REUSE headers/annotations. ScanCode Toolkit 32.5.0
  found 307 files, 278 without a file-level license expression, and several
  `LicenseRef` expressions around external/reference material. pip-licenses,
  deterministic SBOM generation, and third-party notices remain engineering
  inventories. Automated identification is not legal clearance; no mechanical
  mass-header change was made, and transitive/PyInstaller content remains
  human review.
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
  into the deterministic project SBOM. Syft 1.50.0 found no vendored Python
  dependency components in the wheel or sdist, so all declared dependencies
  appear as `declared_not_observed`; this is expected for a non-vendoring
  package, not proof that dependency review is complete. Windows bundle and
  plugin ZIP scans are deferred to the manual Windows job.

The successful clean-room run used audit-branch source commit
`1f3d79fc4662bcb5f53488a65bd1d3a84594dd41`: direct wheel and sdist built,
allowlist passed, wheel rebuilt from sdist, all 79 wheel members matched by
SHA-256, clean installation passed, and CLI/MCP smoke returned zero. The
sanitized artifacts had 79 wheel members and 303 sdist members; direct wheel
SHA-256 was
`1f2deb2db4f6d0ba53b7f25fd7556f623e7fa0a96daafc800171d1ee5b090994`; the
sdist SHA-256 for that run was
`5f36e685af749e0078f63240311dd37bfbfc83c2789be5680cfaf7817862c786`. Sdist
hashes are intentionally treated as per-build evidence because archive metadata
can change between builds.

## Findings and limitations

The API verification found two policy/documentation mismatches: strict
up-to-date checks are enabled and all three merge methods are allowed. The
ruleset was not changed automatically. The development-only pytest advisory,
REUSE gaps, unresolved ScanCode `LicenseRef` results, and missing local
Windows/PowerShell evidence remain explicit findings. No independent legal,
DipTrace-permission, independent-release-reviewer, conduct-channel,
succession/recovery, or full bundled-dependency clearance claim is made.

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
