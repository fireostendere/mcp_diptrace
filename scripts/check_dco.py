#!/usr/bin/env python3
"""Check DCO 1.1 sign-offs on commits in a review range."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_DCO_LINE = re.compile(
    r"^Signed-off-by:\s+[^<\n]+<[^<>\s@]+@[^<>\s]+>\s*$", re.MULTILINE
)
_ZERO_SHA = "0" * 40


def has_dco_signoff(message: str) -> bool:
    """Return whether *message* contains a valid DCO sign-off line."""

    return _DCO_LINE.search(message) is not None


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _commit_ids(base: str | None, head: str | None, commit: str | None) -> list[str]:
    if commit:
        return [commit]
    if not base or not head:
        raise ValueError("provide --commit or both --base and --head")
    if head == _ZERO_SHA:
        raise ValueError("head SHA is the all-zero GitHub event placeholder")
    if base == _ZERO_SHA:
        output = _git("rev-list", "--topo-order", "--reverse", head)
        return [line for line in output.splitlines() if line]
    output = _git("rev-list", "--topo-order", "--reverse", f"{base}..{head}")
    return [line for line in output.splitlines() if line]


def check_range(
    *, base: str | None = None, head: str | None = None, commit: str | None = None
) -> list[dict[str, str]]:
    """Return commit records missing a DCO sign-off."""

    missing: list[dict[str, str]] = []
    for sha in _commit_ids(base, head, commit):
        message = _git("show", "-s", "--format=%B", sha)
        if not has_dco_signoff(message):
            subject = _git("show", "-s", "--format=%s", sha).strip()
            missing.append({"sha": sha, "subject": subject})
    return missing


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--commit")
    selector.add_argument("--base")
    parser.add_argument("--head")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.base and not args.head:
        raise SystemExit("--head is required with --base")
    missing = check_range(base=args.base, head=args.head, commit=args.commit)
    print(json.dumps({"ok": not missing, "missing": missing}, indent=2, sort_keys=True))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
