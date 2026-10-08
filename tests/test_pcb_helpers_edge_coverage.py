"""Targeted coverage for specctra parse guards, padstack shapes, quality span
measurement and library point replacement."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.library_mutation import _replace_points
from diptrace_mcp.pcb_quality import _component_span
from diptrace_mcp.specctra import _padstack_shape


def _record(stable_id: str, position: dict[str, float] | None) -> ObjectRecord:
    return ObjectRecord(stable_id=stable_id, kind="component", position=position)


# ---------------------------------------------------------------------------
# specctra: parse_ses guard clauses
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# specctra: padstack shape rendering
# ---------------------------------------------------------------------------


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
