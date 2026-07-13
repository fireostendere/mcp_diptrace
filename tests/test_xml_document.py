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
