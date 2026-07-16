from pathlib import Path

import pytest

from diptrace_mcp.errors import DocumentError, EditError
from diptrace_mcp.xml_document import DipTraceDocument, XmlEdit

FIXTURES = Path(__file__).parent / "fixtures"


def test_guarded_set_text_and_append() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    data, previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value="22k",
            ),
            XmlEdit(
                operation="append_xml",
                xpath="./Board/Components/Component[RefDes='R1']",
                value=(
                    "<AddFields><AddField Type='Text'><Name>MPN</Name>"
                    "<Text>ABC-123</Text></AddField></AddFields>"
                ),
            ),
        ]
    )

    updated = DipTraceDocument.from_bytes(Path("updated.xml"), data)
    assert updated.root.findtext("./Board/Components/Component[RefDes='R1']/Value") == "22k"
    assert updated.root.findtext(
        "./Board/Components/Component[RefDes='R1']/AddFields/AddField/Text"
    ) == "ABC-123"
    assert len(previews) == 2


def test_expected_match_count_prevents_broad_edit() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)

    with pytest.raises(EditError, match="matched 2 elements, expected 1"):
        document.apply_edits(
            [
                XmlEdit(
                    operation="set_attribute",
                    xpath=".//Component",
                    attribute="Locked",
                    value="Y",
                )
            ]
        )


def test_dtd_is_rejected() -> None:
    payload = b'<!DOCTYPE Source [<!ENTITY x "boom">]><Source Type="DipTrace-PCB">&x;</Source>'

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe.xml"), payload)


def test_raw_patch_preserves_bom_declaration_empty_tags_and_unknown_sections() -> None:
    payload = (
        b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?>\r\n'
        b'<Source Type="DipTrace-Schematic" Version="5.3.0.2" Units="inch">\r\n'
        b'<Schematic><Components><Part Id="76"><RefDes>C64</RefDes>\r\n'
        b'<RefDesMarking Show="Common" Align="Common" X="0" Y="0" />\r\n'
        b'<Text/><Unknown Vendor="keep"><Cache/></Unknown>\r\n'
        b'</Part></Components></Schematic></Source>\r\n'
    )
    document = DipTraceDocument.from_bytes(Path("live.xml"), payload)
    replacement = (
        '<RefDesMarking Show="Common" Align="Position" Horz="Center" '
        'Vert="Center" X="0.35" Y="0.4" />'
    )

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="replace_xml",
                xpath="./Schematic/Components/Part[@Id='76']/RefDesMarking",
                value=replacement,
            )
        ]
    )

    expected = payload.replace(
        b'<RefDesMarking Show="Common" Align="Common" X="0" Y="0" />',
        replacement.encode("utf-8"),
    )
    assert updated == expected
    assert updated.startswith(b'\xef\xbb\xbf<?xml version="1.0"')
    assert b"<Text/>" in updated
    assert b'<Unknown Vendor="keep"><Cache/></Unknown>' in updated


def test_raw_patch_operations_change_only_target_spans() -> None:
    payload = (
        b'<Source Type="DipTrace-PCB"><Board Flag="old">'
        b'<Value/><Container/><DeleteMe X="1"/><Keep A="1" />'
        b'</Board></Source>'
    )
    document = DipTraceDocument.from_bytes(Path("board.xml"), payload)

    updated, _previews = document.apply_edits(
        [
            XmlEdit(operation="set_text", xpath="./Board/Value", value="A&B<1>"),
            XmlEdit(
                operation="set_attribute",
                xpath="./Board",
                attribute="Flag",
                value='new "quoted"',
            ),
            XmlEdit(
                operation="append_xml",
                xpath="./Board/Container",
                value="<Child Enabled='Y'/>",
            ),
            XmlEdit(
                operation="remove_attribute",
                xpath="./Board/DeleteMe",
                attribute="X",
            ),
            XmlEdit(operation="delete_element", xpath="./Board/DeleteMe"),
        ]
    )

    assert b"<Value>A&amp;B&lt;1&gt;</Value>" in updated
    assert b'Flag="new &quot;quoted&quot;"' in updated
    assert b"<Container><Child Enabled='Y'/></Container>" in updated
    assert b"DeleteMe" not in updated
    assert updated.endswith(b'<Keep A="1" /></Board></Source>')


def test_raw_patch_repeated_siblings_do_not_change_neighbors() -> None:
    parts = b"".join(
        (
            f'<Part Id="{index}"><RefDes>R{index}</RefDes>'
            '<RefDesMarking Align="Common" X="0" /></Part>\n'
        ).encode()
        for index in range(12)
    )
    payload = (
        b'<Source Type="DipTrace-Schematic"><Schematic><Components>\n'
        + parts
        + b"</Components></Schematic></Source>"
    )
    document = DipTraceDocument.from_bytes(Path("siblings.xml"), payload)

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="replace_xml",
                xpath=f"./Schematic/Components/Part[@Id='{index}']/RefDesMarking",
                value=f'<RefDesMarking Align="Position" X="{index / 10:g}" />',
            )
            for index in (1, 4, 7, 10)
        ]
    )

    assert updated.count(b"<Part Id=") == 12
    assert DipTraceDocument.from_bytes(Path("updated.xml"), updated).source_type == (
        "DipTrace-Schematic"
    )
    for index in (0, 2, 3, 5, 6, 8, 9, 11):
        original = (
            f'<Part Id="{index}"><RefDes>R{index}</RefDes>'
            '<RefDesMarking Align="Common" X="0" /></Part>'
        ).encode()
        assert original in updated
