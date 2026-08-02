from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import scripts.check_dco as check_dco
from scripts.check_dco import has_dco_signoff
from scripts.check_provenance_inventory import validate_inventory
from scripts.check_public_privacy import (
    REQUIRED_IGNORED_PATHS,
    inspect,
    matches_private_path,
)

ROOT = Path(__file__).resolve().parents[1]


def test_dco_checker_accepts_and_rejects_signoff_lines() -> None:
    assert has_dco_signoff("subject\n\nSigned-off-by: Contributor <contributor@example.com>\n")
    assert not has_dco_signoff("subject\n\nReviewed-by: Contributor <contributor@example.com>\n")
    assert not has_dco_signoff("subject\n\nSigned-off-by: no-email\n")


def test_dco_range_keeps_merge_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_git(*args: str) -> str:
        calls.append(args)
        if args[0] == "rev-list":
            return "merge-sha\nleaf-sha\n"
        if args[-1] == "merge-sha":
            return "Merge commit\n"
        return "Leaf commit\nSigned-off-by: Person <person@example.com>\n"

    monkeypatch.setattr(check_dco, "_git", fake_git)
    missing = check_dco.check_range(base="base-sha", head="head-sha")

    assert missing == [{"sha": "merge-sha", "subject": "Merge commit"}]
    assert ("rev-list", "--topo-order", "--reverse", "base-sha..head-sha") in calls


def test_private_path_deny_list_is_explicit_without_generic_word_matches() -> None:
    assert matches_private_path("docs/announcements/v0.1.2-forum-en.md")
    assert matches_private_path(".local/open-source-readiness/HUMAN_ACTIONS.md")
    assert matches_private_path("OPENAI_APPLICATION_DRAFT.md")
    assert not matches_private_path("docs/RELEASE_PROCESS.md")
    assert not matches_private_path("docs/EVIDENCE_CAPTURE.md")


def test_current_tree_has_no_private_paths_and_required_paths_are_ignored() -> None:
    report = inspect(
        inspected_commit="e57422e545c6b94aefe52c044c64d72a74a8c373",
        inspected_date="2026-08-02",
    )
    assert report["tracked_private_paths"] == []
    assert report["missing_ignore_rules"] == []
    assert REQUIRED_IGNORED_PATHS


def test_provenance_inventory_is_sanitized_and_bound() -> None:
    assert validate_inventory() == []
    text = (ROOT / "docs/compliance/PROVENANCE_INVENTORY.csv").read_text(encoding="utf-8")
    assert "/home/" not in text
    assert "\\Users\\" not in text
    assert "SIGNPATH_API_TOKEN" not in text


def test_generated_inventory_and_sbom_are_bound_to_same_commit_and_date() -> None:
    inventory = json.loads(
        (ROOT / "docs/compliance/dependency-inventory.json").read_text(encoding="utf-8")
    )
    sbom = json.loads((ROOT / "docs/compliance/sbom.cdx.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", inventory["inspected_commit"])
    assert inventory["inspected_date"] == "2026-08-02"
    properties = {item["name"]: item["value"] for item in sbom["metadata"]["properties"]}
    assert properties["diptrace-mcp:inspected-commit"] == inventory["inspected_commit"]
    assert properties["diptrace-mcp:inspection-date"] == inventory["inspected_date"]
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"


def test_contribution_and_pr_policies_are_consistent() -> None:
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    governance = (ROOT / "GOVERNANCE.md").read_text(encoding="utf-8")
    template = (ROOT / ".github/pull_request_template.md").read_text(encoding="utf-8")
    assert "git commit -s" in contributing
    assert "AI assistance" in contributing
    assert "provenance" in contributing
    assert "personal data" in contributing
    assert "DCO 1.1" in governance or "DCO" in governance
    assert "Signed-off-by" in template
    assert "AI assistance" in template
    assert "privacy" in template.lower()


def test_signing_material_has_no_real_account_values_and_keeps_unsigned_mode_explicit() -> None:
    signing = (ROOT / "docs/SIGNING.md").read_text(encoding="utf-8")
    verifier = (ROOT / "plugin/verify_signature.ps1").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/windows-signing.yml").read_text(encoding="utf-8")
    assert "SIGNPATH_ORGANIZATION_ID" in signing
    assert "SIGNING_REQUIRED" in signing
    assert "Get-AuthenticodeSignature" in verifier
    assert "signtool verify /pa /v" in verifier
    assert "HUMAN ACTION REQUIRED" in workflow
    assert "api.openai.com" not in signing
    assert "SIGNING_REQUIRED" in verifier
    assert "expected signer subject is required" in verifier.lower()
    assert "Require a protected ref for signing" in workflow
    package_script = (ROOT / "plugin/package_plugin.ps1").read_text(encoding="utf-8")
    assert '-LiteralPath (Join-Path $PluginDir "settings\\*.settings.xml")' not in package_script
