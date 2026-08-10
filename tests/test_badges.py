from __future__ import annotations

from pathlib import Path

from scripts.generate_coverage_badge import read_coverage_gate, render_badge

ROOT = Path(__file__).resolve().parents[1]


def test_coverage_badge_matches_the_enforced_ci_gate() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    badge = ROOT / "docs" / "badges" / "coverage.svg"

    threshold = read_coverage_gate(workflow)

    assert threshold == "85"
    assert badge.read_text(encoding="utf-8") == render_badge(threshold)


def test_readme_publishes_ci_and_coverage_badges() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "actions/workflows/ci.yml/badge.svg?branch=main" in text
    assert "docs/badges/coverage.svg" in text
