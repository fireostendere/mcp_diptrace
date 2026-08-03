from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

PACK = Path(__file__).parent / "fixtures" / "diptrace-5.3"


def test_pending_pack_manifest_is_schema_valid_and_has_no_exports() -> None:
    schema = json.loads((PACK / "manifest.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["status"] == "HUMAN_ACTION_REQUIRED"
    assert manifest["accepted_for_trust"] is False
    assert all(item["sha256"] is None for item in manifest["fixtures"])
    assert all(item["created_by"] == "project maintainer" for item in manifest["fixtures"])
    assert all(item["contains_third_party_design"] is False for item in manifest["fixtures"])
    assert all(item["redistribution_basis"] for item in manifest["fixtures"])
    assert not list(PACK.glob("*.xml"))


def test_pack_scenarios_are_small_and_distinct() -> None:
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    files = [item["file"] for item in manifest["fixtures"]]
    scenarios = [item["scenario"] for item in manifest["fixtures"]]
    assert len(files) == len(set(files)) == 8
    assert len(scenarios) == len(set(scenarios))
