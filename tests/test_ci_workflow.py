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
    assert "python -m pytest -q" in commands
    assert "--cov=src/diptrace_mcp" in commands
    assert "--cov-fail-under=84" in commands
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
