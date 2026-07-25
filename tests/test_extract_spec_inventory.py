"""Focused tests for the reproducible specification extractor."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from scripts.extract_spec_inventory import (
    _canonical_json,
    _extract_enum_values_from_block,
    _infer_units,
    _parse_attribute_line,
    _parse_spec_pages,
    build_inventory,
)
from scripts.report_format_coverage import main as coverage_main

ROOT = Path(__file__).parents[1]
EXTRACTED_TEXT = ROOT / "reference/diptrace-xml/extracted_text"


def test_glued_attribute_rows_from_pdf_text_are_parsed() -> None:
    assert _parse_attribute_line(
        "Angle RealAngle of the text and picture in radians, counterclockwise."
    ) == (
        "Angle",
        "Real",
        "Angle of the text and picture in radians, counterclockwise.",
    )
    assert _parse_attribute_line("XRealX coordinate of the polygon.") == (
        "X",
        "Real",
        "X coordinate of the polygon.",
    )
    assert _parse_attribute_line("PointerTextText for Type Pointer.") == (
        "PointerText",
        "Text",
        "for Type Pointer.",
    )


def test_enum_rows_do_not_promote_quoted_prose() -> None:
    assert _extract_enum_values_from_block(
        '"Pad";\n"Via" – component via.\nDescription for "Conductor".'
    ) == ["Pad", "Via"]


def test_prose_tag_does_not_reanchor_attribute_owner() -> None:
    elements = _parse_spec_pages(
        [
            """
4.1. Copper pour, <CopperPour>
<CopperPour Id="0" PanelExclude="N">
Id Int Copper pour identifier.
Group Int Group identifier, see
<Groups> section.
"-1" – does not belong to a group.
PanelExclude Bool Do Not Panelize:
"Y" – enabled;
"N" – disabled.
"""
        ],
        "pcb",
        1,
    )

    assert "Groups" not in elements
    assert elements["CopperPour"]["attributes"]["PanelExclude"]["enum"] == [
        "Y",
        "N",
    ]
    assert elements["CopperPour"]["attributes"]["Group"]["enum"] is None


def test_nested_example_keeps_outer_definition_owner() -> None:
    elements = _parse_spec_pages(
        [
            """
4.1. Field, <Field>
<Field Id="0">
<TextLines>
<TextLine>REVISION</TextLine>
</TextLines>
<FontName>Tahoma</FontName>
</Field>
4.1.1. Main field parameters
Id Int Field identifier.
"""
        ],
        "schematic",
        1,
    )

    assert elements["Field"]["attributes"]["Id"]["description"] == (
        "Field identifier."
    )
    assert elements["Field"]["children"] == ["TextLines", "FontName"]
    assert elements["TextLines"]["children"] == ["TextLine"]


def test_scalar_content_is_distinct_from_inline_attribute() -> None:
    elements = _parse_spec_pages(
        [
            """
4.1. Type name and number, <Type>
<Type Index="2">Circular</Type>
Index Int Number of the type.
Text Type name.
"""
        ],
        "pcb",
        1,
    )

    element = elements["Type"]
    assert set(element["attributes"]) == {"Index"}
    assert element["text_content"] == [
        {
            "source_name": "Type",
            "type": "Text",
            "description": "Type name.",
            "enum": None,
            "units": "unknown",
            "omitted_when": None,
            "documents": ["pcb"],
            "pages": [1],
        }
    ]


def test_root_units_prose_and_unit_sentinels() -> None:
    elements = _parse_spec_pages(
        [
            """
2. Information about file, <Source>
<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="inch">
Type="DipTrace-PCB" – file created in DipTrace PCB Layout;
Version="4.3.0.3" – version of the file format;
Units="inch" – Measurement units of dimensions in the file:
mm – millimetres;
inch – inches;
mil – mils.
"""
        ],
        "pcb",
        1,
    )

    assert elements["Source"]["attributes"]["Units"] == {
        "type": "Text",
        "description": (
            "Measurement units of dimensions in the file: "
            "mm – millimetres; inch – inches; mil – mils."
        ),
        "enum": ["mm", "inch", "mil"],
        "units": "document_units",
        "omitted_when": None,
    }
    assert _infer_units("Angle", "Component rotation angle.", "Component") == (
        "unknown"
    )
    assert _infer_units(
        "Angle",
        "Angle of the text and picture in radians, counterclockwise.",
        "Shape",
    ) == "radians"
    assert _infer_units("Orientation", "Table angle, digrees:", "Table") == (
        "degrees"
    )


def test_offline_inventory_generation_is_deterministic() -> None:
    first = build_inventory(EXTRACTED_TEXT)
    second = build_inventory(EXTRACTED_TEXT)
    assert _canonical_json(first) == _canonical_json(second)


def test_coverage_cli_rejects_truncated_inventory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    inventory = build_inventory(EXTRACTED_TEXT)
    truncated = copy.deepcopy(inventory)
    for name, element in truncated["elements"].items():
        if name not in {"Source", "Library", "Component", "Shape", "Table"}:
            element["attributes"].clear()
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(_canonical_json(truncated), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_format_coverage.py",
            "--inventory",
            str(inventory_path),
            "--src",
            str(ROOT / "src/diptrace_mcp"),
            "--out",
            str(tmp_path / "coverage.md"),
            "--check",
        ],
    )

    assert coverage_main() == 1
    assert "expected at least 500 attributes" in capsys.readouterr().err
