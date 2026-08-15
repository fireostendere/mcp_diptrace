from __future__ import annotations

import re
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

    combined = _job_commands(workflow["jobs"]["combined-coverage"])
    assert "coverage report --fail-under=90" in combined


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
    assert "generate_mcp_tools_snapshot.py --check" in commands
    assert "python -m hatchling build -d release-dist" in commands
    assert "audit_release_artifacts.py --dist-dir release-dist --check-allowlist" in commands

    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'extend-exclude = ["plugin/dist"]' in config
    assert 'exclude = ["^plugin/dist/"]' in config

    # The checked directory contains the PyInstaller entry point today; using the
    # directory in CI means future hand-maintained Python files need no CI edit.
    assert (ROOT / "plugin/bridge_entry.py").is_file()


def test_static_analysis_runs_compliance_gates() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    commands = _job_commands(workflow["jobs"]["static-analysis"])

    assert "python scripts/check_public_privacy.py" in commands
    assert "python scripts/check_provenance_inventory.py" in commands
    assert "python scripts/generate_compliance_inventory.py --check" in commands


def test_dco_job_uses_the_actual_pr_head_and_is_not_a_post_merge_gate() -> None:
    workflow_path = ROOT / ".github/workflows/ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    dco = workflow["jobs"]["dco"]
    assert dco["if"] == "${{ github.event_name == 'pull_request' }}"
    dco_checkout = dco["steps"][0]
    assert dco_checkout["with"]["fetch-depth"] == 0
    assert dco_checkout["with"]["ref"] == "${{ github.event.pull_request.head.sha }}"
    command_step = dco["steps"][1]
    assert command_step["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert command_step["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"


def test_all_workflow_actions_are_pinned_to_full_commit_shas() -> None:
    uses_pattern = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
    sha_pattern = re.compile(r"^[^@]+@[0-9a-f]{40}$")
    for workflow_path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        content = workflow_path.read_text(encoding="utf-8")
        actions = uses_pattern.findall(content)
        assert actions, workflow_path
        assert all(sha_pattern.fullmatch(action) for action in actions), workflow_path


def test_windows_installer_workflow_covers_build_smoke_and_audit_jobs() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/windows-installer.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]
    assert set(jobs) == {
        "build-server",
        "build-bridge",
        "build-installer",
        "installer-smoke",
        "artifact-audit",
    }
    installer_commands = _job_commands(jobs["build-installer"])
    smoke_commands = _job_commands(jobs["installer-smoke"])
    audit_commands = _job_commands(jobs["artifact-audit"])
    assert "build_windows_installer.ps1" in installer_commands
    assert "INNO_SETUP_SHA256" in installer_commands
    assert "frozen_server_smoke.py" in smoke_commands
    assert "/REMOVE_STATE" in smoke_commands
    assert "audit_windows_bundle.py" in audit_commands
    assert "Get-AuthenticodeSignature" in audit_commands


def test_pypi_workflow_builds_before_a_minimal_oidc_publish_job() -> None:
    workflow_path = ROOT / ".github/workflows/pypi.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["env"] == {"RELEASE_VERSION": "0.3.0", "RELEASE_TAG": "v0.3.0"}

    build = jobs["build"]
    build_commands = _job_commands(build)
    assert "python -m hatchling build -d dist" in build_commands
    assert "audit_release_artifacts.py --dist-dir dist --check-allowlist" in build_commands
    assert "python -m twine check --strict dist/*" in build_commands
    assert "refs/tags/${RELEASE_TAG}" in build_commands
    assert "git cat-file -t" in build_commands
    assert "diptrace_mcp.__version__" in build_commands

    publish = jobs["publish"]
    assert publish["if"] == (
        "${{ github.event_name == 'workflow_dispatch' && inputs.publish == true }}"
    )
    assert publish["needs"] == "build"
    assert publish["environment"] == {
        "name": "pypi",
        "url": "https://pypi.org/p/diptrace-mcp",
    }
    assert publish["permissions"] == {"contents": "read", "id-token": "write"}
    assert len(publish["steps"]) == 2
    assert publish["steps"][1]["uses"] == (
        "pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b"
    )
    assert "password:" not in workflow_text
    assert "username:" not in workflow_text
