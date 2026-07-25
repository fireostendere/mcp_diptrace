from pathlib import Path

import pytest

from diptrace_mcp.errors import DocumentError, EditError
from diptrace_mcp.xml_document import DipTraceDocument, RawTreeSnapshot, XmlEdit

FIXTURES = Path(__file__).parent / "fixtures"
ENTITY_BOMB = (
    '<!DOCTYPE Source [<!ENTITY a "AAAAAAAAAA">'
    '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
    '<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
)
ENTITY_BODY = (
    '<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
    "<X>&c;</X></Source>"
)


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


def test_utf16_be_bom_dtd_is_rejected() -> None:
    text = '<!DOCTYPE Source [<!ENTITY x "boom">]><Source Type="DipTrace-PCB">&x;</Source>'
    payload = b"\xfe\xff" + text.encode("utf-16-be")

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-utf16-be.xml"), payload)


def test_utf16_le_bom_entity_is_rejected() -> None:
    text = '<Source Type="DipTrace-PCB"><!ENTITY x "boom"></Source>'
    payload = b"\xff\xfe" + text.encode("utf-16-le")

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-utf16-le.xml"), payload)


def test_utf32_be_bom_dtd_is_rejected() -> None:
    text = '<!DOCTYPE Source><Source Type="DipTrace-PCB"/>'
    payload = b"\x00\x00\xfe\xff" + text.encode("utf-32-be")

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-utf32-be.xml"), payload)


def test_utf32_le_bom_entity_is_rejected() -> None:
    text = '<Source Type="DipTrace-PCB"><!ENTITY x "boom"/></Source>'
    payload = b"\xff\xfe\x00\x00" + text.encode("utf-32-le")

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-utf32-le.xml"), payload)


def test_utf16_be_without_bom_dtd_is_rejected() -> None:
    text = '<?xml version="1.0" encoding="UTF-16"?>' + ENTITY_BOMB + ENTITY_BODY
    payload = text.encode("utf-16-be")

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-utf16-be-no-bom.xml"), payload)


@pytest.mark.parametrize(
    "comment",
    ['encoding="utf-16"', 'encoding="cp037"', 'encoding="idna"'],
)
def test_encoding_name_in_comment_cannot_bypass_guard(comment: str) -> None:
    text = f'<?xml version="1.0"?><!--{comment}-->{ENTITY_BOMB}{ENTITY_BODY}'

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-comment.xml"), text.encode())


def test_doctype_after_large_comment_is_rejected() -> None:
    text = (
        '<?xml version="1.0"?><!-- '
        + ("P" * 70_000)
        + f" -->{ENTITY_BOMB}{ENTITY_BODY}"
    )

    with pytest.raises(DocumentError, match="DTD and ENTITY"):
        DipTraceDocument.from_bytes(Path("unsafe-late-doctype.xml"), text.encode())


@pytest.mark.parametrize(
    ("bom", "encoding"),
    [(b"\xfe\xff", "utf-16-be"), (b"\xff\xfe", "utf-16-le")],
)
def test_clean_utf16_fixture_loads(bom: bytes, encoding: str) -> None:
    text = (FIXTURES / "pcb.xml").read_text(encoding="utf-8")
    text = text.replace('encoding="UTF-8"', 'encoding="UTF-16"', 1)
    payload = bom + text.encode(encoding)

    document = DipTraceDocument.from_bytes(Path("clean-utf16.xml"), payload)

    assert document.source_type == "DipTrace-PCB"


def test_apply_edits_rejects_entity_declaration_in_fragment() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)

    with pytest.raises(
        EditError,
        match="DTD and ENTITY declarations are not allowed in XML fragments",
    ):
        document.apply_edits(
            [
                XmlEdit(
                    operation="append_xml",
                    xpath="./Board",
                    value=(
                        '<!DOCTYPE Child [<!ENTITY x "boom">]>'
                        "<Child>&x;</Child>"
                    ),
                )
            ]
        )


def test_raw_span_guard_preserves_write_error_contract() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    document.raw_bytes = (
        b'<!DOCTYPE Source [<!ENTITY x "boom">]>'
        b'<Source Type="DipTrace-PCB"><Board>&x;</Board></Source>'
    )

    with pytest.raises(
        EditError,
        match=r"^DTD and ENTITY declarations are not allowed$",
    ):
        RawTreeSnapshot.capture(document)


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
