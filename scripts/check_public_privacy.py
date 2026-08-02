#!/usr/bin/env python3
"""Fail if high-confidence private working paths are tracked again."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# These are intentionally explicit and path-focused. They protect private working
# material without treating ordinary words such as "application" or "private" in
# technical prose as a violation.
PRIVATE_PATH_PATTERNS = (
    re.compile(r"(^|/)\.local(/|$)", re.IGNORECASE),
    re.compile(r"(^|/)docs/announcements/", re.IGNORECASE),
    re.compile(
        r"(^|/)(?:private|audit-private|license-audit-private|signing-private)(/|$)",
        re.IGNORECASE,
    ),
    re.compile(r"(^|/)docs/(?:applications|outreach)/private(/|$)", re.IGNORECASE),
    re.compile(
        r"(^|/).*(?:OPENAI.*APPLICATION|APPLICATION_DRAFT|PERMISSION_REQUEST|"
        r"FORUM_ANNOUNCEMENT|FORUM_POST|OUTREACH_DRAFT|SUBMISSION_CONFIRMATION|"
        r"HUMAN_ACTIONS_PRIVATE|DIPTRACE_PERMISSION_REQUEST|SIGNPATH.*ID)(?:[^/]*$)",
        re.IGNORECASE,
    ),
    re.compile(r"(^|/).+\.(?:identity|account)\.json$", re.IGNORECASE),
)

REQUIRED_IGNORED_PATHS = (
    ".local/open-source-readiness/HUMAN_ACTIONS.md",
    ".local/open-source-readiness/openai/APPLICATION_DRAFT.md",
    ".local/open-source-readiness/DIPTRACE_PERMISSION_REQUEST_DRAFT.md",
    "docs/private/operator-notes.md",
    "SIGNPATH_ORGANIZATION_ID.account.json",
    "OPENAI_APPLICATION_DRAFT.md",
    ".local/open-source-readiness/openai/application_draft.md",
    "permission_request.md",
    "forum_post.md",
    "signpath_organization_id.account.json",
)


def matches_private_path(path: str) -> bool:
    """Return whether a repository-relative path is a protected private path."""

    return any(pattern.search(path) for pattern in PRIVATE_PATH_PATTERNS)


def tracked_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def ignored_paths() -> list[str]:
    missing: list[str] = []
    for path in REQUIRED_IGNORED_PATHS:
        completed = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", "--", path],
            cwd=ROOT,
            check=False,
        )
        if completed.returncode != 0:
            missing.append(path)
    return missing


def inspect(
    *, inspected_commit: str | None = None, inspected_date: str | None = None
) -> dict[str, object]:
    commit = inspected_commit or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    checked_date = inspected_date or date.today().isoformat()
    tracked_private = sorted(path for path in tracked_paths() if matches_private_path(path))
    missing_ignores = ignored_paths()
    return {
        "ok": not tracked_private and not missing_ignores,
        "inspected_commit": commit,
        "inspected_date": checked_date,
        "tracked_private_paths": tracked_private,
        "missing_ignore_rules": missing_ignores,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit")
    parser.add_argument("--inspected-date")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = inspect(inspected_commit=args.commit, inspected_date=args.inspected_date)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
