from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.run_clean_room_audit import _safe_output as safe_clean_output
from scripts.run_deep_audit import DEFAULT_OUTPUT
from scripts.run_deep_audit import _safe_output as safe_deep_output
from scripts.run_dependency_audit import _groups

ROOT = Path(__file__).resolve().parents[1]


def test_raw_audit_output_is_confined_to_ignored_private_tree() -> None:
    assert safe_deep_output(DEFAULT_OUTPUT) == DEFAULT_OUTPUT.resolve()
    with pytest.raises(ValueError):
        safe_deep_output(ROOT / "docs")
    with pytest.raises(ValueError):
        safe_clean_output(ROOT / "release-dist")


def test_secret_allowlist_is_only_the_narrow_ignored_private_path() -> None:
    config = (ROOT / "scripts/gitleaks.toml").read_text(encoding="utf-8")
    assert "useDefault = true" in config
    assert "\\.local" in config
    assert "regexes" not in config
    assert "regex =" not in config
    assert "secret =" not in config


def test_deep_workflow_is_manual_read_only_and_does_not_use_secrets() -> None:
    workflow_path = ROOT / ".github/workflows/deep-compliance-audit.yml"
    text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in text
    assert "secrets." not in text
    uses = re.findall(r"^\s*- uses:\s*([^\s#]+)", text, re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses)


def test_dependency_audit_groups_follow_pyproject_and_include_bridge() -> None:
    import scripts.run_dependency_audit as dependency_audit

    project = dependency_audit.tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    groups = _groups(project)
    assert groups["runtime"] == project["project"]["dependencies"]
    assert any(value.lower().startswith("shapely") for value in groups["geometry"])
    assert any(value.lower().startswith("pyinstaller") for value in groups["pyinstaller"])
    assert groups["development"]


def test_audit_docs_do_not_publish_workstation_or_ruleset_identifiers() -> None:
    paths = (
        ROOT / "docs/compliance/BRANCH_PROTECTION_STATUS.md",
        ROOT / "docs/compliance/POST_MERGE_AUDIT_2026-08-02.md",
        ROOT / "docs/compliance/WINDOWS_BUNDLE_INVENTORY.md",
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "/mnt/c/Users/" not in text
    assert str(Path.home()).replace("\\", "/") not in text
    assert not re.search(r"\b\d{15,}\b", text)
