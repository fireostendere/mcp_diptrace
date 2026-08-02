from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "diptrace_5_3"


def test_future_accepted_manifest_schema_is_valid_but_has_no_current_claim() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["diptrace"]["properties"]["version"]["pattern"] == r"^5\.3(?:\.|$)"


def test_pending_manifest_validates_and_is_not_real_evidence() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.pending.schema.json").read_text())
    manifest = json.loads(
        (FIXTURE_ROOT / "power_multilayer" / "manifest.pending.json").read_text()
    )

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["validation_level"] == "synthetic_operation_fixture"
    assert manifest["diptrace"]["version_used_for_final_exports"] is None
    assert manifest["diptrace"]["build"] is None
    assert manifest["diptrace_opened"] is False
    assert manifest["diptrace_reexported"] is False
    assert all(
        artifact["validation_level"] in {"synthetic_parser_only", "synthetic_operation_fixture"}
        for artifact in manifest["artifacts"]
    )


def test_no_accepted_diptrace53_fixture_bytes_are_committed() -> None:
    accepted_root = FIXTURE_ROOT / "acceptance"
    assert not accepted_root.exists()
    assert not list(FIXTURE_ROOT.rglob("manifest.json"))
