from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _job_commands(job: dict[str, Any]) -> str:
    return "\n".join(
        str(step.get("run", ""))
        for step in job["steps"]
        if isinstance(step, dict)
    )


def test_linux_geometry_job_runs_exact_backend_and_coverage_gates() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["test-linux-geometry-and-coverage"]
    commands = _job_commands(job)

    assert 'python -m pip install -e ".[dev,geometry]"' in commands
    assert "verify_geometry_backend.py --expect shapely_geos" in commands
    assert "python scripts/smoke_bridge_headless.py" in commands
    assert "python -m pytest -q" in commands
    assert "--cov=src/diptrace_mcp" in commands
    assert "--cov-fail-under=85" in commands
    assert "check_coverage.py coverage.json" in commands


def test_linux_fallback_job_proves_shapely_absent_and_runs_fallback_tests() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["test-linux-no-shapely-fallback"]
    commands = _job_commands(job)

    assert 'python -m pip install -e ".[dev]"' in commands
    assert "pip uninstall -y shapely" in commands
    assert "find_spec('shapely') is None" in commands
    assert "verify_geometry_backend.py --expect pure_python" in commands
    assert "tests/test_geometry.py" in commands
    assert "tests/test_copper_pour_obstacles.py" in commands


def test_windows_job_runs_real_headless_bridge_handshake() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    commands = _job_commands(workflow["jobs"]["test-windows"])

    assert "python scripts/smoke_bridge_headless.py" in commands


def test_static_analysis_covers_plugin_python_but_excludes_generated_dist() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    commands = _job_commands(workflow["jobs"]["static-analysis"])

    assert "python -m ruff check --no-cache src tests benchmarks scripts plugin" in commands
    assert "python -m mypy --no-incremental src/diptrace_mcp plugin" in commands
    assert "measure_mcp_surface.py" in commands
    assert "--baseline-bytes 121335" in commands
    assert "--max-growth-percent 15" in commands

    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'extend-exclude = ["plugin/dist"]' in config
    assert 'exclude = ["^plugin/dist/"]' in config

    # The checked directory contains the PyInstaller entry point today; using the
    # directory in CI means future hand-maintained Python files need no CI edit.
    assert (ROOT / "plugin/bridge_entry.py").is_file()
