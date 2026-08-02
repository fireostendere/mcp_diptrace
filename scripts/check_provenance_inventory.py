#!/usr/bin/env python3
"""Validate the public, sanitized provenance inventory."""

from __future__ import annotations

import argparse
import csv
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "docs" / "compliance" / "PROVENANCE_INVENTORY.csv"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REQUIRED_COLUMNS = (
    "inspected_commit",
    "inspected_date",
    "path_or_pattern",
    "category",
    "claimed_source",
    "copyright_owner_if_known",
    "license_or_permission",
    "redistribution_status",
    "included_in_git",
    "included_in_sdist",
    "included_in_wheel",
    "included_in_windows_executable",
    "included_in_release_assets",
    "evidence_reference",
    "human_action_required",
)


def validate_inventory(path: Path = DEFAULT_PATH) -> list[str]:
    errors: list[str] = []
    if not path.is_file() or path.is_symlink():
        return [f"missing or unsafe inventory: {path}"]
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(REQUIRED_COLUMNS):
            return [f"unexpected inventory header: {reader.fieldnames!r}"]
        rows = list(reader)
    if not rows:
        return ["provenance inventory is empty"]

    commits = {row["inspected_commit"] for row in rows}
    dates = {row["inspected_date"] for row in rows}
    if len(commits) != 1 or not COMMIT_RE.fullmatch(next(iter(commits), "")):
        errors.append("all rows must share one 40-character inspected commit")
    if len(dates) != 1 or not DATE_RE.fullmatch(next(iter(dates), "")):
        errors.append("all rows must share one ISO inspected date")
    try:
        date.fromisoformat(next(iter(dates)))
    except (StopIteration, ValueError):
        errors.append("inspected_date is not a calendar date")

    seen: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        path_or_pattern = row["path_or_pattern"]
        if not path_or_pattern or path_or_pattern in seen:
            errors.append(f"line {line_number}: empty or duplicate path_or_pattern")
        seen.add(path_or_pattern)
        if "\\" in path_or_pattern or path_or_pattern.startswith(("/", "~")):
            errors.append(f"line {line_number}: path_or_pattern must be repository-relative")
        if not row["category"] or not row["redistribution_status"]:
            errors.append(f"line {line_number}: category and redistribution status are required")
    if not any(row["human_action_required"].strip().lower() == "yes" for row in rows):
        errors.append("inventory must preserve at least one explicit human action")
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    return parser


def main() -> int:
    args = _parser().parse_args()
    errors = validate_inventory(args.path)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"OK: {args.path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
