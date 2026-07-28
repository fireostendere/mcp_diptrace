from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_coverage import CoverageReportError, check_coverage, load_coverage_report


def _report(
    *,
    total_percent: float = 84.1,
    file_percent: float = 88.1,
) -> dict[str, object]:
    summary = {
        "num_statements": 100,
        "missing_lines": 12,
        "percent_covered": file_percent,
    }
    return {
        "totals": {
            "num_statements": 200,
            "missing_lines": 31,
            "percent_covered": total_percent,
        },
        "files": {"src/diptrace_mcp/example.py": {"summary": summary}},
    }


def test_check_coverage_accepts_report_at_floors_and_reports_counts() -> None:
    measurements, failures = check_coverage(
        _report(total_percent=84.0, file_percent=88.0),
        total_floor=84.0,
        file_floors={"src/diptrace_mcp/example.py": 88.0},
    )

    assert failures == []
    assert measurements == [
        "TOTAL: 200 statements, 31 missed, 84.0000% covered (floor 84.0%)",
        (
            "src/diptrace_mcp/example.py: 100 statements, 12 missed, "
            "88.0000% covered (floor 88.0%)"
        ),
    ]


def test_check_coverage_reports_total_and_per_file_regressions() -> None:
    _, failures = check_coverage(
        _report(total_percent=83.999, file_percent=87.999),
        total_floor=84.0,
        file_floors={"src/diptrace_mcp/example.py": 88.0},
    )

    assert failures == [
        "TOTAL: 83.9990% is below the 84.0% floor",
        "src/diptrace_mcp/example.py: 87.9990% is below the 88.0% floor",
    ]


def test_check_coverage_rejects_missing_file_summary() -> None:
    with pytest.raises(CoverageReportError, match="has no summary"):
        check_coverage(
            _report(),
            file_floors={"src/diptrace_mcp/missing.py": 1.0},
        )


def test_check_coverage_rejects_non_finite_percent() -> None:
    with pytest.raises(CoverageReportError, match="requires numeric"):
        check_coverage(
            _report(total_percent=float("nan")),
            file_floors={},
        )


def test_load_coverage_report_rejects_invalid_json(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text("{broken", encoding="utf-8")

    with pytest.raises(CoverageReportError, match="Cannot read coverage report"):
        load_coverage_report(report)


def test_load_coverage_report_reads_json_object(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps(_report()), encoding="utf-8")

    assert load_coverage_report(report)["totals"] == _report()["totals"]
