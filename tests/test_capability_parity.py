from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import Settings
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _assert_same_mapping_keys(
    without_document: dict[str, Any],
    with_document: dict[str, Any],
    *,
    path: str = "capabilities",
) -> None:
    assert without_document.keys() == with_document.keys(), path
    for key in without_document:
        left = without_document[key]
        right = with_document[key]
        if isinstance(left, dict) and isinstance(right, dict):
            _assert_same_mapping_keys(left, right, path=f"{path}.{key}")


@pytest.mark.parametrize(
    "fixture",
    sorted(FIXTURES.glob("*.xml")),
    ids=lambda path: path.name,
)
def test_capability_key_sets_match_with_and_without_document(fixture: Path) -> None:
    document = DipTraceDocument.load(fixture, 10_000_000)

    without_document = get_capabilities().model_dump()
    with_document = get_capabilities(document).model_dump()

    _assert_same_mapping_keys(without_document, with_document)


def test_capability_names_are_canonical_across_contexts() -> None:
    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)

    without_document = get_capabilities().read_capabilities
    with_document = get_capabilities(pcb).read_capabilities

    assert without_document.keys() == with_document.keys()
    assert "library_models" in without_document
    assert "library_model" not in without_document
    assert {"document_info", "get_object", "xml_fragments"} <= without_document.keys()


def test_document_capabilities_include_resolved_document_trust(tmp_path: Path) -> None:
    board = tmp_path / "board.xml"
    board.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )

    trust = service.get_capabilities("board.xml")["trust_model"]["document"]

    assert trust["sha256"]
    assert trust["validation_level"] == "synthetic_parser_only"
    assert trust["trust_authority"] == "no_sidecar"
    assert trust["requires_diptrace_verification"] is True
