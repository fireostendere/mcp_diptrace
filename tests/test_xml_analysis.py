from __future__ import annotations

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from diptrace_mcp.xml_analysis import analyze_xml_semantics, compare_xml_semantics
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
BASE = (FIXTURES / "pcb.xml").read_bytes()
_SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=16,
)


def _document(raw: bytes) -> DipTraceDocument:
    return DipTraceDocument.from_bytes(FIXTURES / "generated.xml", raw)


def test_xml_semantic_inventory_is_deterministic_on_real_fixture() -> None:
    document = _document(BASE)

    first = analyze_xml_semantics(document)
    second = analyze_xml_semantics(document)

    assert first == second
    assert first.source_type == "DipTrace-PCB"
    assert first.element_count > 1
    assert len(first.semantic_sha256) == 64


@given(first=_SAFE_TEXT, second=_SAFE_TEXT)
def test_semantic_fingerprint_ignores_attribute_order(first: str, second: str) -> None:
    marker = b"</Board>"
    left = f'<UnknownProbe A="{first}" B="{second}" />'.encode()
    right = f'<UnknownProbe B="{second}" A="{first}" />'.encode()
    assert BASE.count(marker) == 1

    first_doc = _document(BASE.replace(marker, left + marker))
    second_doc = _document(BASE.replace(marker, right + marker))

    assert analyze_xml_semantics(first_doc).semantic_sha256 == analyze_xml_semantics(
        second_doc
    ).semantic_sha256
    assert compare_xml_semantics(first_doc, second_doc).semantic_equal is True


@given(value=st.integers(min_value=0, max_value=1_000_000))
def test_semantic_fingerprint_detects_unknown_attribute_changes(value: int) -> None:
    marker = b"</Board>"
    first = _document(BASE.replace(marker, b'<UnknownProbe X="0" />' + marker))
    second = _document(
        BASE.replace(marker, f'<UnknownProbe X="{value + 1}" />'.encode() + marker)
    )

    delta = compare_xml_semantics(first, second)
    assert delta.semantic_equal is False
    assert delta.added_local_records >= 1
    assert delta.removed_local_records >= 1


def test_xml_semantic_delta_reports_known_value_change_without_source_type_drift() -> None:
    assert b"10k" in BASE
    before = _document(BASE)
    after = _document(BASE.replace(b"10k", b"11k", 1))

    delta = compare_xml_semantics(before, after)

    assert delta.source_type_changed is False
    assert delta.root_tag_changed is False
    assert delta.semantic_equal is False
    assert delta.before_sha256 != delta.after_sha256
