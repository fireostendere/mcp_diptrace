from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.errors import EditError
from diptrace_mcp.library_mutation import (
    ComponentPartSpec,
    ComponentPinSpec,
    ComponentSpec,
    PatternGraphicSpec,
    PatternPadSpec,
    PatternSpec,
    attach_pattern,
    mutate_component,
    mutate_pattern,
    validate_explicit_pin_pad_mapping,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _document(name: str) -> DipTraceDocument:
    path = FIXTURES / name
    return DipTraceDocument.from_bytes(path, path.read_bytes())


def _new_pattern() -> PatternSpec:
    return PatternSpec(
        name="QFN_4_SYNTH",
        style="PatTypeSyntheticQfn4",
        unique_name="QFN_4_SYNTH_UNIQUE",
        refdes="U",
        mounting="SMD",
        width_mm=3.0,
        height_mm=3.0,
        default_pad_style="SMD_0603",
        pads=[
            PatternPadSpec(xml_id="0", number="1", style="SMD_0603", x_mm=-1.0, y_mm=-1.0),
            PatternPadSpec(xml_id="1", number="2", style="SMD_0603", x_mm=1.0, y_mm=-1.0),
            PatternPadSpec(xml_id="2", number="3", style="SMD_0603", x_mm=1.0, y_mm=1.0),
            PatternPadSpec(xml_id="3", number="4", style="SMD_0603", x_mm=-1.0, y_mm=1.0),
        ],
        graphics=[
            PatternGraphicSpec(
                xml_id="0",
                layer="Top Silk",
                points=[(-1.4, -1.4), (1.4, -1.4), (1.4, 1.4), (-1.4, 1.4)],
            )
        ],
    )


def test_create_pattern_is_raw_preserving_and_idempotent() -> None:
    document = _document("pattern_library.xml")
    unknown = b'<FuturePatternData Preserve="Y" />'
    assert unknown in document.raw_bytes

    first = mutate_pattern(document, _new_pattern())
    assert first.changed is True
    assert unknown in first.raw_bytes
    assert b"QFN_4_SYNTH" in first.raw_bytes

    reparsed = DipTraceDocument.from_bytes(document.path, first.raw_bytes)
    second = mutate_pattern(reparsed, _new_pattern(), collision="update")
    assert second.changed is False
    assert second.raw_bytes == first.raw_bytes


def test_pattern_update_replaces_only_known_pad_children() -> None:
    document = _document("pattern_library.xml")
    existing = PatternSpec(
        name="R_0603",
        style="PatType0",
        unique_name="R_0603_GOLDEN",
        refdes="R",
        mounting="SMD",
        width_mm=3.2,
        height_mm=1.6,
        default_pad_style="SMD_0603",
        pads=[
            PatternPadSpec(xml_id="0", number="1", style="SMD_0603", x_mm=-0.9, y_mm=0.0),
        ],
    )
    result = mutate_pattern(document, existing, collision="update", replace_pads=True)
    assert b'<FuturePatternData Preserve="Y" />' in result.raw_bytes
    reparsed = DipTraceDocument.from_bytes(document.path, result.raw_bytes)
    pattern = next(
        item
        for item in reparsed.root.findall("./Patterns/Pattern")
        if item.findtext("./Name") == "R_0603"
    )
    pads = pattern.findall("./Pads/Pad")
    assert len(pads) == 1
    assert pads[0].get("X") == "-0.9"


def test_pattern_collision_is_explicit() -> None:
    document = _document("pattern_library.xml")
    with pytest.raises(EditError, match="already exists"):
        mutate_pattern(
            document,
            PatternSpec(name="R_0603", style="PatType0", mounting="SMD"),
        )


def _new_component() -> ComponentSpec:
    return ComponentSpec(
        name="SYNTH_IC",
        parts=[
            ComponentPartSpec(
                name="SYNTH_IC",
                refdes="U",
                value="SYNTH",
                manufacturer="Fixture Inc",
                datasheet="https://example.invalid/synth.pdf",
                fields={"MPN": "SYNTH-4", "Description": "synthetic fixture"},
                pattern_style="PatType0",
                pins=[
                    ComponentPinSpec(
                        xml_id="0",
                        name="A",
                        number="1",
                        pad_id="0",
                        pad_number="1",
                        electrical_type="Passive",
                        x_mm=-1.0,
                    ),
                    ComponentPinSpec(
                        xml_id="1",
                        name="B",
                        number="2",
                        pad_id="1",
                        pad_number="2",
                        electrical_type="Passive",
                        x_mm=1.0,
                        orientation_deg=180.0,
                    ),
                ],
            )
        ],
    )


def test_create_component_preserves_unknown_library_xml_and_mapping() -> None:
    document = _document("component_library.xml")
    unknown = b'<FutureComponentData Preserve="Y" />'
    assert unknown in document.raw_bytes

    result = mutate_component(document, _new_component())
    assert result.changed is True
    assert unknown in result.raw_bytes
    reparsed = DipTraceDocument.from_bytes(document.path, result.raw_bytes)
    assert validate_explicit_pin_pad_mapping(reparsed, "SYNTH_IC") == []

    second = mutate_component(reparsed, _new_component(), collision="update")
    assert second.changed is False
    assert second.raw_bytes == result.raw_bytes


def test_attach_pattern_is_idempotent_and_validated() -> None:
    document = _document("component_library.xml")
    first = attach_pattern(document, "RES_0603", "PatType0")
    assert first.changed is False
    assert first.raw_bytes == document.raw_bytes

    with pytest.raises(EditError, match="not present"):
        attach_pattern(document, "RES_0603", "NO_SUCH_PATTERN")


def test_pin_mapping_requires_id_and_number_together() -> None:
    with pytest.raises(ValueError, match="supplied together"):
        ComponentPinSpec(
            xml_id="0",
            number="1",
            pad_id="0",
        )
