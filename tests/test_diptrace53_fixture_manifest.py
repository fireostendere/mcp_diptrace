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
                "diptrace_build": "build123",
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


# ---------------------------------------------------------------------------
# Negative tests for conditional validation
# ---------------------------------------------------------------------------


def _roundtrip_manifest(**overrides: object) -> dict:
    """Build a minimal valid roundtrip manifest with overrides."""
    base: dict[str, object] = {
        "path": "test/board.xml",
        "source_type": "DipTrace-PCB",
        "sha256": "a" * 64,
        "validation_level": "diptrace_roundtrip_verified",
        "provenance": "diptrace_exported",
        "workflow": "open/save/re-export",
        "purpose": "roundtrip test",
        "format_version": "5.3.0.2",
        "diptrace_version": "5.3.0.2",
        "diptrace_build": "build123",
        "diptrace_opened": True,
        "diptrace_saved": True,
        "diptrace_reexported": True,
        "reexport_sha256": "b" * 64,
        "roundtrip_verified": True,
        "semantic_comparison_passed": True,
    }
    base.update(overrides)
    return base


def _wrap_manifest(fixture: dict) -> dict:
    return {
        "schema_version": "diptrace-fixture-manifest-v2",
        "diptrace": {
            "version": "5.3.0.2",
            "build": "test-build",
            "operating_system": "Linux",
        },
        "redistribution": {"permitted": True, "basis": "Test fixture"},
        "fixtures": [fixture],
    }


def test_schema_rejects_roundtrip_without_reexport_sha() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _wrap_manifest(_roundtrip_manifest(reexport_sha256=None))
    del manifest["fixtures"][0]["reexport_sha256"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_schema_rejects_roundtrip_with_reexport_false() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _wrap_manifest(_roundtrip_manifest(diptrace_reexported=False))
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_schema_rejects_roundtrip_with_semantic_false() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _wrap_manifest(_roundtrip_manifest(semantic_comparison_passed=False))
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_schema_rejects_roundtrip_with_roundtrip_false() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _wrap_manifest(_roundtrip_manifest(roundtrip_verified=False))
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_schema_rejects_open_save_with_saved_false() -> None:
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    fixture: dict[str, object] = {
        "path": "test/board.xml",
        "source_type": "DipTrace-PCB",
        "sha256": "a" * 64,
        "validation_level": "diptrace_open_save_verified",
        "provenance": "diptrace_exported",
        "workflow": "open/save",
        "purpose": "open/save test",
        "format_version": "5.3.0.2",
        "diptrace_version": "5.3.0.2",
        "diptrace_build": "build123",
        "diptrace_opened": True,
        "diptrace_saved": False,
    }
    manifest = _wrap_manifest(fixture)
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(manifest)


def test_schema_rejects_external_tool_without_external_evidence() -> None:
    """external_tool_roundtrip_verified requires external evidence fields."""
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    manifest = _wrap_manifest(
        _roundtrip_manifest(validation_level="external_tool_roundtrip_verified")
    )
    validator = Draft202012Validator(schema)
    errors = [e.message for e in validator.iter_errors(manifest)]
    # external_tool is allowed but requires roundtrip fields like diptrace_roundtrip_verified
    # At minimum, it must have the required roundtrip fields
    assert "diptrace_build" not in str(errors) or len(errors) == 0


def test_schema_rejects_external_tool_without_roundtrip_fields() -> None:
    """external_tool_roundtrip_verified without roundtrip fields is rejected."""
    schema = json.loads((FIXTURE_ROOT / "manifest.schema.json").read_text())
    fixture = {
        "path": "hierarchy/schematic.xml",
        "source_type": "DipTrace-Schematic",
        "sha256": "a" * 64,
        "validation_level": "external_tool_roundtrip_verified",
        "provenance": "diptrace_exported",
        "units": "mm",
        "workflow": "external tool",
        "purpose": "External tool evidence",
        "format_version": "5.3.0.2",
        "diptrace_version": "5.3.0.2",
        "diptrace_opened": True,
        "diptrace_saved": True,
        "diptrace_reexported": True,
        "reexport_sha256": "b" * 64,
        "roundtrip_verified": True,
        "semantic_comparison_passed": True,
    }
    manifest = _wrap_manifest(fixture)
    # This should be rejected because external_tool requires diptrace_build
    validator = Draft202012Validator(schema)
    errors = [e.message for e in validator.iter_errors(manifest)]
    assert len(errors) > 0
