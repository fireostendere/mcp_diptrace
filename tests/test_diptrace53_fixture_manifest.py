from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "diptrace_5_3"


def _manifest() -> dict:
    return {
        "schema_version": "diptrace-fixture-manifest-v2",
        "diptrace": {
            "version": "5.3.0.0",
            "build": "example-build",
            "operating_system": "Windows",
        },
        "redistribution": {
            "permitted": True,
            "basis": "Created specifically for this repository.",
        },
        "fixtures": [
            {
                "path": "hierarchy/schematic.xml",
                "source_type": "DipTrace-Schematic",
                "sha256": "a" * 64,
                "validation_level": "diptrace_roundtrip_verified",
                "provenance": "diptrace_exported",
                "units": "mm",
                "workflow": "File > Save As > DipTrace XML",
                "purpose": "Hierarchical schematic parser evidence",
                "format_version": "5.3.0.2",
                "diptrace_version": "5.3.0.2",
                "diptrace_opened": True,
                "diptrace_saved": True,
                "diptrace_reexported": True,
                "reexport_sha256": "b" * 64,
                "roundtrip_verified": True,
                "semantic_comparison_passed": True,
            }
        ],
    }


def test_diptrace53_manifest_schema_and_minimal_manifest() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_manifest())


def test_diptrace53_manifest_requires_redistribution_permission() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _manifest()
    manifest["redistribution"]["permitted"] = False
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_diptrace53_manifest_requires_validation_level() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _manifest()
    del manifest["fixtures"][0]["validation_level"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_diptrace53_manifest_rejects_invalid_validation_level() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _manifest()
    manifest["fixtures"][0]["validation_level"] = "invalid_level"
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_pending_manifest_validates_against_pending_schema() -> None:
    """The real manifest.pending.json must validate against the pending schema."""
    pending_schema = json.loads(
        (FIXTURE_ROOT / "manifest.pending.schema.json").read_text()
    )
    Draft202012Validator.check_schema(pending_schema)
    pending_manifest = json.loads(
        (FIXTURE_ROOT / "power_multilayer" / "manifest.pending.json").read_text()
    )
    Draft202012Validator(pending_schema).validate(pending_manifest)


def test_v2_schema_rejects_pending_manifest() -> None:
    """The v2 schema must NOT accept the pending manifest (different structure)."""
    v2_schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    pending_manifest = json.loads(
        (FIXTURE_ROOT / "power_multilayer" / "manifest.pending.json").read_text()
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(v2_schema).validate(pending_manifest)
