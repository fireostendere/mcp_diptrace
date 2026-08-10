from __future__ import annotations

import importlib
import importlib.metadata
import runpy
from pathlib import Path

import pytest

import diptrace_mcp
import diptrace_mcp.server_runtime as server_runtime
from scripts.generate_coverage_badge import read_coverage_gate, render_badge

ROOT = Path(__file__).resolve().parents[1]


def test_coverage_badge_matches_the_enforced_ci_gate() -> None:
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    badge = ROOT / "docs" / "badges" / "coverage.svg"

    threshold = read_coverage_gate(workflow)

    assert threshold == "90"
    assert badge.read_text(encoding="utf-8") == render_badge(threshold)


def test_readme_publishes_ci_and_coverage_badges() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "actions/workflows/ci.yml/badge.svg?branch=main" in text
    assert "docs/badges/coverage.svg" in text


def test_package_version_falls_back_when_distribution_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_version(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("diptrace-mcp")

    with monkeypatch.context() as patch:
        patch.setattr(importlib.metadata, "version", missing_version)
        reloaded = importlib.reload(diptrace_mcp)
        assert reloaded.__version__ == "0.2.1"

    importlib.reload(diptrace_mcp)


def test_module_entrypoints_delegate_to_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str] | None] = []
    monkeypatch.setattr(server_runtime, "main", lambda argv=None: calls.append(argv))

    runpy.run_module("diptrace_mcp.__main__", run_name="__main__")
    runpy.run_module("diptrace_mcp.frozen_server", run_name="__main__")
    runpy.run_module("diptrace_mcp.server", run_name="__main__")

    assert calls == [None, None, None]
