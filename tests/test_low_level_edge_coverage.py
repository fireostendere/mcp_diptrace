from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pydantic import BaseModel

import diptrace_mcp.config as config
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import ConfigurationError, DocumentError, PathAccessError
from diptrace_mcp.numeric_inputs import (
    require_finite_number,
    translate_validation_errors,
    xml_integer,
    xml_number,
)
from diptrace_mcp.xml_document import DipTraceDocument


def _document(raw: bytes = b'<Source Type="DipTrace-PCB" Version="5.3" Units="mm"><Board/></Source>') -> DipTraceDocument:
    return DipTraceDocument.from_bytes(Path("synthetic.xml"), raw)


def test_numeric_helpers_translate_invalid_and_nonfinite_values() -> None:
    document = _document()
    invalid_float = ET.Element("Item", Value="not-a-number")
    invalid_int = ET.Element("Item", Count="1.5")

    with pytest.raises(DocumentError, match="Invalid numeric attribute"):
        xml_number(document, invalid_float, "Value")
    with pytest.raises(DocumentError, match="Invalid integer attribute"):
        xml_integer(document, invalid_int, "Count")

    with pytest.raises(DocumentError, match="word offset 7") as exc_info:
        require_finite_number(
            float("inf"),
            context="coverage probe",
            offset=7,
            offset_unit="word",
            details={"source": "test"},
        )
    assert exc_info.value.details["word_offset"] == 7
    assert exc_info.value.details["source"] == "test"


class _PositiveModel(BaseModel):
    value: int


@translate_validation_errors
def _validated(value: object) -> int:
    return _PositiveModel.model_validate({"value": value}).value


def test_validation_translation_uses_document_error_contract() -> None:
    assert _validated(3) == 3
    with pytest.raises(DocumentError, match="Invalid normalized document data at value"):
        _validated("not-an-int")


def test_configuration_helpers_reject_bad_environment_and_outside_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_MAX_SCAN_FILES", "not-an-int")
    with pytest.raises(ConfigurationError, match="must be an integer"):
        config._positive_int("DIPTRACE_MCP_MAX_SCAN_FILES", 500)

    monkeypatch.setenv("DIPTRACE_MCP_MAX_SCAN_FILES", "0")
    with pytest.raises(ConfigurationError, match="greater than zero"):
        config._positive_int("DIPTRACE_MCP_MAX_SCAN_FILES", 500)

    monkeypatch.setenv("DIPTRACE_MCP_POLICY", "unknown")
    with pytest.raises(ConfigurationError, match="must be one of"):
        config._policy_profile()

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    settings = Settings(workspace=root, allowed_roots=(root,), state_dir=tmp_path / "state")

    assert config._is_within(root / "child", root)
    assert not config._is_within(outside, root)
    with pytest.raises(PathAccessError, match="outside allowed roots"):
        settings.resolve_allowed_path(outside)
