from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.errors import Sha256MismatchError
from diptrace_mcp.library_mutation import PatternPadSpec, PatternSpec
from diptrace_mcp.library_mutation_api import (
    LibraryMutationRequest,
    preview_library_mutation,
)
from diptrace_mcp.xml_document import DipTraceDocument, sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def _document(name: str) -> DipTraceDocument:
    path = FIXTURES / name
    return DipTraceDocument.from_bytes(path, path.read_bytes())


def _pattern() -> PatternSpec:
    return PatternSpec(
        name="API_PATTERN",
        style="PatTypeApiPattern",
        mounting="SMD",
        default_pad_style="SMD_0603",
        pads=[
            PatternPadSpec(
                xml_id="0",
                number="1",
                style="SMD_0603",
                x_mm=0.0,
                y_mm=0.0,
            )
        ],
    )


def test_library_preview_contract_is_sha_bound_and_not_publicly_registered() -> None:
    document = _document("pattern_library.xml")
    request = LibraryMutationRequest(
        action="mutate_pattern",
        expected_sha256=sha256_bytes(document.raw_bytes),
        pattern=_pattern(),
    )

    execution = preview_library_mutation(document, request)

    assert execution.preview.changed is True
    assert execution.preview.public_registration is False
    assert execution.preview.source_sha256 == sha256_bytes(document.raw_bytes)
    assert execution.preview.result_sha256 == sha256_bytes(execution.raw_bytes)
    assert execution.preview.semantic_delta.semantic_equal is False
    assert execution.preview.changed_ids == ["pattern:API_PATTERN"]
    assert document.raw_bytes != execution.raw_bytes


def test_library_preview_contract_refuses_stale_expected_sha() -> None:
    document = _document("pattern_library.xml")
    request = LibraryMutationRequest(
        action="mutate_pattern",
        expected_sha256="0" * 64,
        pattern=_pattern(),
    )

    with pytest.raises(Sha256MismatchError):
        preview_library_mutation(document, request)


def test_library_mapping_validation_is_read_only() -> None:
    document = _document("component_library.xml")
    request = LibraryMutationRequest(
        action="validate_mapping",
        expected_sha256=sha256_bytes(document.raw_bytes),
        component_name="RES_0603",
    )

    execution = preview_library_mutation(document, request)

    assert execution.preview.changed is False
    assert execution.preview.semantic_delta.semantic_equal is True
    assert execution.raw_bytes == document.raw_bytes
    assert execution.preview.mapping_errors == []


def test_library_request_rejects_cross_action_payloads() -> None:
    document = _document("pattern_library.xml")
    with pytest.raises(ValueError, match="fields for another action"):
        LibraryMutationRequest(
            action="mutate_pattern",
            expected_sha256=sha256_bytes(document.raw_bytes),
            pattern=_pattern(),
            component_name="unexpected",
        )
