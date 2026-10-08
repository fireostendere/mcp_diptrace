from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp import library_adapters
from diptrace_mcp.domain import LibraryPadStyle
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.library_adapters import (
    get_library_item,
    get_library_model,
    query_library_items,
    validate_library,
)
from diptrace_mcp.library_mutation import (
    ComponentGraphicSpec,
    ComponentPartSpec,
    ComponentPinSpec,
    ComponentSpec,
    PatternGraphicSpec,
    PatternPadSpec,
    PatternSpec,
    mutate_component,
    mutate_pattern,
)
from diptrace_mcp.library_mutation_api import LibraryMutationRequest, preview_library_mutation
from diptrace_mcp.pattern_recommendation import (
    PatternFeedbackStore,
    PatternRequirement,
    recommend_patterns,
)
from diptrace_mcp.xml_document import DipTraceDocument, sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> DipTraceDocument:
    path = FIXTURES / name
    return DipTraceDocument.from_bytes(path, path.read_bytes())


def _pattern() -> PatternSpec:
    return PatternSpec(
        name="R_0603",
        style="PatType0",
        unique_name="R_0603_WAVE22",
        refdes="R",
        value="10k",
        manufacturer="Fixture",
        mounting="SMD",
        width_mm=3.2,
        height_mm=1.6,
        orientation_deg=90,
        default_pad_style="SMD_0603",
        pads=[
            PatternPadSpec(xml_id="0", number="1", style="SMD_0603", x_mm=-0.9, y_mm=0),
            PatternPadSpec(xml_id="1", number="2", style="SMD_0603", x_mm=0.9, y_mm=0),
        ],
        graphics=[
            PatternGraphicSpec(
                xml_id="0",
                kind="Line",
                layer="Top Silk",
                line_width_mm=0.15,
                points=[(-1.5, -0.8), (-1.5, 0.8)],
            )
        ],
    )


def _component() -> ComponentSpec:
    return ComponentSpec(
        name="RES_0603",
        parts=[
            ComponentPartSpec(
                name="RES_0603",
                refdes="R",
                value="10k",
                manufacturer="Fixture",
                datasheet="https://example.invalid/r.pdf",
                fields={"MPN": "R-W22", "Tolerance": "1%"},
                pattern_style="PatType0",
                pins=[
                    ComponentPinSpec(
                        xml_id="0",
                        name="A",
                        number="1",
                        pad_id="0",
                        pad_number="1",
                        electrical_type="Passive",
                        x_mm=-1,
                    ),
                    ComponentPinSpec(
                        xml_id="1",
                        name="B",
                        number="2",
                        pad_id="1",
                        pad_number="2",
                        electrical_type="Passive",
                        x_mm=1,
                        orientation_deg=180,
                    ),
                ],
                graphics=[
                    ComponentGraphicSpec(
                        xml_id="0",
                        points=[(-1, 0), (1, 0)],
                    )
                ],
            )
        ],
    )


def test_mutate_pattern_and_component_replace_known_collections() -> None:
    pattern = mutate_pattern(
        _load("pattern_library.xml"),
        _pattern(),
        collision="update",
        replace_pads=True,
        replace_graphics=True,
    )
    mutated_pattern = DipTraceDocument.from_bytes(Path("patterns.lib"), pattern.raw_bytes)
    assert get_library_model(mutated_pattern).patterns[0].name == "R_0603"

    source = _load("component_library.xml")
    root = ET.fromstring(source.raw_bytes)
    component = root.find("./Components/Component")
    assert component is not None
    component.append(ET.fromstring(ET.tostring(component.find("./Part"))))  # type: ignore[arg-type]
    expanded = DipTraceDocument.from_bytes(source.path, ET.tostring(root, encoding="utf-8"))
    result = mutate_component(
        expanded,
        _component(),
        collision="update",
        replace_parts=True,
        replace_pins=True,
        replace_fields=True,
        replace_graphics=True,
    )
    model = get_library_model(DipTraceDocument.from_bytes(source.path, result.raw_bytes))
    assert model.components[0].fields["Tolerance"] == "1%"


def test_library_geometry_validation_api_and_recommendation_paths() -> None:
    document = _load("pattern_library.xml")
    root = ET.fromstring(document.raw_bytes)
    style = root.find("./PadStyles/PadStyle[@Name='SMD_0603']/MainStack")
    assert style is not None
    style.set("Shape", "D-Shape")
    mask = root.find("./PadStyles/PadStyle[@Name='SMD_0603']/MaskPaste")
    assert mask is not None
    mask.set("TopMask", "Tented")
    mask.set("TopPaste", "Segments")
    segments = ET.SubElement(mask, "TopSegments")
    ET.SubElement(segments, "Item", {"X1": "-1", "Y1": "-0.2", "X2": "0", "Y2": "0.2"})
    modified = DipTraceDocument.from_bytes(document.path, ET.tostring(root, encoding="utf-8"))
    model = get_library_model(modified)
    assert model.patterns[0].pads[0].paste_geometry["Top"]
    assert validate_library(model) == []

    request = LibraryMutationRequest(
        action="mutate_pattern",
        expected_sha256=sha256_bytes(document.raw_bytes),
        pattern=_pattern().model_copy(update={"name": "WAVE22_NEW", "style": "WAVE22"}),
    )
    assert preview_library_mutation(document, request).preview.changed
    result = recommend_patterns(
        model.patterns,
        PatternRequirement(
            pad_count=2,
            mounting="surface mount",
            required_pad_numbers=["1", "2"],
            max_width_mm=10,
            max_height_mm=10,
            width_mm=3,
            height_mm=2,
            pitch_mm=1.6,
        ),
    )
    assert result.candidates


def test_pad_geometry_api_component_and_filter_branches() -> None:
    for shape in ("Fiducial", "Oval", "Obround", "D-Shape", "Polygon", "unknown"):
        style = LibraryPadStyle(
            name=shape,
            pad_type="Surface",
            side="Top",
            shape=shape,
            width=1,
            height=2,
            polygon_points=[{"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 0, "y": 1}],
        )
        geometry = library_adapters._pad_geometry(style, 1, 2, 90)
        assert (geometry is not None) == (shape != "unknown")

    component = _load("component_library.xml")
    request = LibraryMutationRequest(
        action="mutate_component",
        expected_sha256=sha256_bytes(component.raw_bytes),
        component=_component(),
        collision="update",
        replace_pins=True,
        replace_fields=True,
        replace_graphics=True,
    )
    assert preview_library_mutation(component, request).preview.changed
    patterns = get_library_model(_load("pattern_library.xml")).patterns
    rejected = recommend_patterns(
        patterns,
        PatternRequirement(
            pad_count=99,
            mounting="through",
            hole_count=99,
            required_pad_numbers=["404"],
            max_width_mm=0.01,
            max_height_mm=0.01,
        ),
    )
    assert rejected.rejected


def test_validation_query_and_request_error_branches(tmp_path: Path) -> None:
    document = _load("pattern_library.xml")
    root = ET.fromstring(document.raw_bytes)
    styles = root.find("./PadStyles")
    assert styles is not None
    styles.append(ET.Element("PadStyle", {"Name": "EMPTY"}))
    pad = root.find("./Patterns/Pattern/Pads/Pad")
    assert pad is not None
    pad.set("Style", "MISSING")
    pad.find("./Number").text = ""  # type: ignore[union-attr]
    broken = DipTraceDocument.from_bytes(document.path, ET.tostring(root, encoding="utf-8"))
    model = get_library_model(broken)
    codes = {item.code for item in validate_library(model)}
    assert {"missing_pad_number", "pad_style_not_found"} <= codes
    assert query_library_items(model, "R_0603")
    assert get_library_item(model, kind="pattern", name="R_0603").name == "R_0603"

    with pytest.raises(ValueError, match="requires component"):
        LibraryMutationRequest(action="mutate_component", expected_sha256="0" * 64)
    with pytest.raises(ValueError, match="requires component_name"):
        LibraryMutationRequest(action="validate_mapping", expected_sha256="0" * 64)
    with pytest.raises(DocumentError, match="limit"):
        recommend_patterns([], PatternRequirement(), limit=0)

    feedback = PatternFeedbackStore(tmp_path / "feedback.jsonl")
    feedback.append(PatternRequirement(pad_count=2), pattern_id="p", decision="accepted")
    assert feedback.read()[0].pattern_id == "p"
