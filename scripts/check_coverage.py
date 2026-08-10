#!/usr/bin/env python3
"""Enforce the measured project and safety-critical module coverage floors."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

TOTAL_FLOOR = 85.0
FILE_FLOORS = {
    "src/diptrace_mcp/bridge.py": 64.0,
    "src/diptrace_mcp/xml_document.py": 87.0,
    "src/diptrace_mcp/semantic_compiler.py": 88.0,
    "src/diptrace_mcp/routing_compiler.py": 85.0,
    "src/diptrace_mcp/server_runtime.py": 65.0,
    "src/diptrace_mcp/adapters.py": 70.0,
    "src/diptrace_mcp/sessions.py": 75.0,
    "src/diptrace_mcp/services/evidence.py": 75.0,
    "src/diptrace_mcp/services/transactions.py": 75.0,
    "src/diptrace_mcp/services/semantic_operations.py": 70.0,
    "src/diptrace_mcp/schematic_placement_repair.py": 95.0,
}


class CoverageReportError(ValueError):
    """Raised when coverage.py JSON is missing required numeric fields."""


def load_coverage_report(path: Path) -> dict[str, Any]:
    """Load a coverage.py JSON report with a typed, actionable parse error."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CoverageReportError(f"Cannot read coverage report {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CoverageReportError(f"Coverage report {path} must contain a JSON object")
    return payload


def _summary(report: dict[str, Any], target: str) -> tuple[int, int, float]:
    if target == "TOTAL":
        summary = report.get("totals")
    else:
        files = report.get("files")
        summary = files.get(target, {}).get("summary") if isinstance(files, dict) else None
    if not isinstance(summary, dict):
        raise CoverageReportError(f"Coverage report has no summary for {target}")

    statements = summary.get("num_statements")
    missed = summary.get("missing_lines")
    percent = summary.get("percent_covered")
    if (
        not isinstance(statements, int)
        or isinstance(statements, bool)
        or not isinstance(missed, int)
        or isinstance(missed, bool)
        or not isinstance(percent, (int, float))
        or isinstance(percent, bool)
        or statements < 0
        or missed < 0
        or not math.isfinite(float(percent))
    ):
        raise CoverageReportError(
            f"Coverage summary for {target} requires numeric "
            "num_statements, missing_lines, and percent_covered"
        )
    return statements, missed, float(percent)


def check_coverage(
    report: dict[str, Any],
    *,
    total_floor: float = TOTAL_FLOOR,
    file_floors: dict[str, float] | None = None,
) -> tuple[list[str], list[str]]:
    """Return printable measurements and all threshold failures."""

    measurements: list[str] = []
    failures: list[str] = []
    thresholds = FILE_FLOORS if file_floors is None else file_floors
    for target, floor in [("TOTAL", total_floor), *thresholds.items()]:
        statements, missed, percent = _summary(report, target)
        measurements.append(
            f"{target}: {statements} statements, {missed} missed, "
            f"{percent:.4f}% covered (floor {floor:.1f}%)"
        )
        if percent < floor:
            failures.append(f"{target}: {percent:.4f}% is below the {floor:.1f}% floor")
    return measurements, failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check coverage.py JSON against the committed coverage floors"
    )
    parser.add_argument("report", type=Path, help="coverage.py JSON report")
    args = parser.parse_args()
    try:
        report = load_coverage_report(args.report)
        measurements, failures = check_coverage(report)
    except CoverageReportError as exc:
        print(f"FAIL: {exc}")
        return 1

    for line in measurements:
        print(line)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: total and per-file coverage floors are satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())