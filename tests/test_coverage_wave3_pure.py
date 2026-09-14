"""Targeted coverage for specctra parse guards, padstack shapes, quality span
measurement and library point replacement."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.library_mutation import _replace_points
from diptrace_mcp.pcb_quality import _component_span
from diptrace_mcp.specctra import _padstack_shape, parse_ses


def _record(stable_id: str, position: dict[str, float] | None) -> ObjectRecord:
    return ObjectRecord(stable_id=stable_id, kind="component", position=position)


# ---------------------------------------------------------------------------
# specctra: parse_ses guard clauses
# ---------------------------------------------------------------------------


def test_parse_ses_rejects_oversized_payload() -> None:
    with pytest.raises(DocumentError, match="exceeds"):
        parse_ses(b"(session x)", max_bytes=4)


def test_parse_ses_rejects_non_utf8_payload() -> None:
    with pytest.raises(DocumentError, match="UTF-8"):
        parse_ses(b"(session \xff\xfe bad)")


def test_parse_ses_requires_exactly_one_session_scope() -> None:
    with pytest.raises(DocumentError, match="exactly one session scope"):
        parse_ses(b"(session a) (session b)")
    with pytest.raises(DocumentError, match="exactly one session scope"):
        parse_ses(b"token")


def test_parse_ses_rejects_non_session_root() -> None:
    with pytest.raises(DocumentError, match="not a session file"):
        parse_ses(b"(design x)")


def test_parse_ses_requires_routes_scope() -> None:
    with pytest.raises(DocumentError, match="no routes scope"):
        parse_ses(b"(session board.ses)")


def test_parse_ses_requires_resolution() -> None:
    with pytest.raises(DocumentError, match="no valid resolution"):
        parse_ses(b"(session board.ses (routes (network_out x)))")


def test_parse_ses_rejects_unsupported_resolution_unit() -> None:
    with pytest.raises(DocumentError, match="Unsupported SES resolution unit"):
        parse_ses(b"(session board.ses (routes (resolution furlong 1000)))")


# ---------------------------------------------------------------------------
# specctra: padstack shape rendering
# ---------------------------------------------------------------------------


def test_padstack_shape_rect_uses_half_extents() -> None:
    text = _padstack_shape(
        layer="Top", shape="rect", width=2.0, height=1.0, resolution=1000
    )

    assert text.startswith("(shape (rect \"Top\"")
    assert "-500" in text and "500" in text


def test_padstack_shape_square_renders_circle() -> None:
    text = _padstack_shape(
        layer="Top", shape="round", width=1.5, height=1.5, resolution=1000
    )

    assert text.startswith("(shape (circle \"Top\"")


def test_padstack_shape_wide_renders_horizontal_path() -> None:
    text = _padstack_shape(
        layer="Top", shape="oval", width=3.0, height=1.0, resolution=1000
    )

    assert text.startswith("(shape (path \"Top\"")
    # Horizontal runway: start.x < 0 < end.x, y centered.
    assert "-1000" in text and "1000" in text


def test_padstack_shape_tall_renders_vertical_path() -> None:
    text = _padstack_shape(
        layer="Bottom", shape="oval", width=1.0, height=3.0, resolution=1000
    )

    assert text.startswith("(shape (path \"Bottom\"")


# ---------------------------------------------------------------------------
# pcb_quality: component span
# ---------------------------------------------------------------------------


def test_component_span_measures_furthest_positions() -> None:
    components = {
        "component_0123456789abcde0": _record(
            "component_0123456789abcde0", {"x": 0.0, "y": 0.0}
        ),
        "component_0123456789abcde1": _record(
            "component_0123456789abcde1", {"x": 3.0, "y": 4.0}
        ),
    }

    span = _component_span(list(components), components)

    assert span == pytest.approx(5.0)


def test_component_span_is_zero_without_two_positions() -> None:
    present = _record("component_0123456789abcde0", {"x": 1.0, "y": 1.0})
    unplaced = _record("component_0123456789abcde1", None)

    assert _component_span([], {}) == 0.0
    single = ["component_0123456789abcde0"]
    assert _component_span(single, {"component_0123456789abcde0": present}) == 0.0
    assert (
        _component_span(
            ["component_0123456789abcde0", "component_0123456789abcde1"],
            {
                "component_0123456789abcde0": present,
                "component_0123456789abcde1": unplaced,
            },
        )
        == 0.0
    )


# ---------------------------------------------------------------------------
# library_mutation: point replacement
# ---------------------------------------------------------------------------


def test_replace_points_rebuilds_only_on_change() -> None:
    container = ET.Element("Points")
    ET.SubElement(container, "Item", {"X": "1.0", "Y": "2.0"})

    assert _replace_points(container, [(0.0, 0.0), (2.54, 0.0)]) is True
    items = container.findall("./Item")
    assert len(items) == 2

    written = [(item.get("X"), item.get("Y")) for item in items]
    assert _replace_points(container, [(0.0, 0.0), (2.54, 0.0)]) is False
    assert written == [(item.get("X"), item.get("Y")) for item in container.findall("./Item")]


def test_replace_points_removes_point_children_too() -> None:
    container = ET.Element("Points")
    ET.SubElement(container, "Point", {"X": "9.0", "Y": "9.0"})

    assert _replace_points(container, [(1.0, 1.0)]) is True
    assert [child.tag for child in container] == ["Item"]
