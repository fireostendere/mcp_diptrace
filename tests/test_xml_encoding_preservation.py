from __future__ import annotations

from pathlib import Path

import pytest

import diptrace_mcp.xml_document as xml_document_module
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.errors import DocumentError, EditError
from diptrace_mcp.operations import SetComponentValueOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument, XmlEdit, unified_xml_diff

FIXTURES = Path(__file__).parent / "fixtures"
UNICODE_VALUE = "Резистор µ Ω ° ±"
EDITED_VALUE = "Новый\tµ\nΩ\r° ±"


def _source_text(*, declaration: str = "UTF-8") -> str:
    source = (FIXTURES / "pcb_unicode.xml").read_text(encoding="utf-8")
    return source.replace('encoding="UTF-8"', f'encoding="{declaration}"', 1)


def _encoded_source(codec: str, bom: bytes = b"") -> bytes:
    declaration = {
        "utf-8": "UTF-8",
        "utf-16-le": "UTF-16",
        "utf-16-be": "UTF-16",
        "us-ascii": "US-ASCII",
        "iso-8859-1": "ISO-8859-1",
    }[codec]
    source = _source_text(declaration=declaration)
    if codec in {"us-ascii", "iso-8859-1"}:
        source = source.replace(UNICODE_VALUE, "ASCII value")
        source = source.replace("Кириллица µ Ω ° ±", "ASCII note")
        source = source.replace("Проверка кодировки", "Encoding check")
    return bom + source.encode(codec)


@pytest.mark.parametrize(
    ("codec", "bom"),
    [
        ("utf-8", b""),
        ("utf-8", b"\xef\xbb\xbf"),
        ("utf-16-le", b"\xff\xfe"),
        ("utf-16-be", b"\xfe\xff"),
        ("utf-16-le", b""),
        ("utf-16-be", b""),
        ("us-ascii", b""),
        ("iso-8859-1", b""),
    ],
)
def test_public_loader_records_source_codec_and_exact_bom(codec: str, bom: bytes) -> None:
    payload = _encoded_source(codec, bom)

    document = DipTraceDocument.from_bytes(Path("encoded.xml"), payload)

    assert document.encoding == codec
    assert document.bom == bom
    assert document.raw_bytes == payload


@pytest.mark.parametrize(
    ("codec", "bom"),
    [
        ("utf-8", b""),
        ("utf-8", b"\xef\xbb\xbf"),
        ("utf-16-le", b"\xff\xfe"),
        ("utf-16-be", b"\xfe\xff"),
        ("utf-16-le", b""),
        ("utf-16-be", b""),
    ],
)
def test_raw_text_edit_preserves_every_byte_outside_target_span(
    codec: str,
    bom: bytes,
) -> None:
    payload = _encoded_source(codec, bom)
    document = DipTraceDocument.from_bytes(Path("encoded.xml"), payload)
    original = f"<Value>{UNICODE_VALUE}</Value>".encode(codec)
    escaped_value = "Новый&#9;µ&#10;Ω&#13;° ±"
    replacement = f"<Value>{escaped_value}</Value>".encode(codec)

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value=EDITED_VALUE,
            )
        ]
    )

    assert payload.count(original) == 1
    assert updated == payload.replace(original, replacement)
    assert updated.startswith(bom)


@pytest.mark.parametrize("codec", ["utf-16-le", "utf-16-be"])
def test_explicit_utf16_byte_order_declaration_remains_editable(codec: str) -> None:
    payload = _source_text(declaration=codec.upper()).encode(codec)
    document = DipTraceDocument.from_bytes(Path("explicit-byte-order.xml"), payload)
    original = f"<Value>{UNICODE_VALUE}</Value>".encode(codec)
    replacement = "<Value>Новый Ω</Value>".encode(codec)

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value="Новый Ω",
            )
        ]
    )

    assert document.encoding == codec
    assert updated == payload.replace(original, replacement)


@pytest.mark.parametrize(
    ("codec", "bom"),
    [
        ("utf-8", b"\xef\xbb\xbf"),
        ("utf-16-le", b"\xff\xfe"),
        ("utf-16-be", b"\xfe\xff"),
    ],
)
def test_raw_attribute_and_fragment_use_target_codec(
    codec: str,
    bom: bytes,
) -> None:
    payload = _encoded_source(codec, bom)
    document = DipTraceDocument.from_bytes(Path("encoded.xml"), payload)
    old_start = '<FutureExtension Note="Кириллица µ Ω ° ±">'.encode(codec)
    new_start = '<FutureExtension Note="A&#9;B&#10;C&#13;D Ω">'.encode(codec)
    closing = "</FutureExtension>".encode(codec)
    fragment_text = '<Child Label="Тест µ Ω ° ±" />'
    fragment = fragment_text.encode(codec)
    expected = payload.replace(old_start, new_start)
    expected = expected.replace(closing, fragment + closing)

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_attribute",
                xpath="./Board/FutureExtension",
                attribute="Note",
                value="A\tB\nC\rD Ω",
            ),
            XmlEdit(
                operation="append_xml",
                xpath="./Board/FutureExtension",
                value=fragment_text,
            ),
        ]
    )

    assert updated == expected
    assert updated.startswith(bom)


@pytest.mark.parametrize(
    ("codec", "bom"),
    [
        ("utf-8", b"\xef\xbb\xbf"),
        ("utf-16-le", b"\xff\xfe"),
        ("utf-16-be", b"\xfe\xff"),
    ],
)
def test_semantic_compiler_preserves_codec_bom_and_untouched_bytes(
    codec: str,
    bom: bytes,
) -> None:
    payload = _encoded_source(codec, bom)
    document = DipTraceDocument.from_bytes(Path("encoded.xml"), payload)
    original = f"<Value>{UNICODE_VALUE}</Value>".encode(codec)
    replacement = "<Value>Новый Ω</Value>".encode(codec)

    result = apply_semantic_operations(
        document,
        [
            SetComponentValueOperation(
                selector=QuerySelector(refdes=["R1"]),
                value="Новый Ω",
            )
        ],
    )

    assert result.raw_bytes == payload.replace(original, replacement)
    assert result.document.encoding == codec
    assert result.document.bom == bom


def test_single_byte_source_uses_standard_character_references_for_unicode() -> None:
    payload = _encoded_source("us-ascii")
    document = DipTraceDocument.from_bytes(Path("ascii.xml"), payload)
    original = b"<Value>ASCII value</Value>"
    replacement = b"<Value>&#1058;&#1077;&#1089;&#1090; &#937;</Value>"

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value="Тест Ω",
            )
        ]
    )

    assert updated == payload.replace(original, replacement)


def test_public_apply_edits_rejects_semantically_wrong_raw_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb_unicode.xml", 1_000_000)

    def return_unchanged(
        document: DipTraceDocument,
        index: int,
        edit: XmlEdit,
        matches: list[object],
    ) -> bytes:
        del index, edit, matches
        return document.raw_bytes

    monkeypatch.setattr(xml_document_module, "_apply_raw_edit", return_unchanged)

    with pytest.raises(EditError, match="does not match the requested semantic edit"):
        document.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component[RefDes='R1']/Value",
                    value="Wrong output must not pass",
                )
            ]
        )


def test_public_fragment_parser_rejects_significant_tail() -> None:
    payload = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        b"<Board><Old /></Board></Source>"
    )
    document = DipTraceDocument.from_bytes(Path("fragment-tail.xml"), payload)

    with pytest.raises(EditError, match="exactly one root element"):
        document.apply_edits(
            [
                XmlEdit(
                    operation="replace_xml",
                    xpath="./Board/Old",
                    value="<New />INJECTED",
                )
            ]
        )


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        ("<New />INJECTED", "exactly one root element"),
        ("<?mcp hidden?><New />", "exactly one root element"),
        ("<!--outside--><New />", "exactly one root element"),
        ("<New><?mcp hidden?></New>", "processing instructions"),
    ],
)
def test_public_append_fragment_rejects_content_outside_or_invisible_to_semantic_gate(
    fragment: str,
    message: str,
) -> None:
    payload = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        b"<Board><Box /></Board></Source>"
    )
    document = DipTraceDocument.from_bytes(Path("append-fragment.xml"), payload)

    with pytest.raises(EditError, match=message):
        document.apply_edits(
            [
                XmlEdit(
                    operation="append_xml",
                    xpath="./Board/Box",
                    value=fragment,
                )
            ]
        )


@pytest.mark.parametrize(
    "edit",
    [
        XmlEdit(
            operation="append_xml",
            xpath="./Board/Box",
            value="<New>\ud800</New>",
        ),
        XmlEdit(
            operation="set_text",
            xpath="./Board/Box",
            value="\ud800",
        ),
        XmlEdit(
            operation="set_attribute",
            xpath="./Board/Box",
            attribute="Label",
            value="\x01",
        ),
    ],
)
def test_public_edits_reject_xml_forbidden_characters_with_write_error(
    edit: XmlEdit,
) -> None:
    payload = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        b"<Board><Box /></Board></Source>"
    )
    document = DipTraceDocument.from_bytes(Path("invalid-character.xml"), payload)

    with pytest.raises(EditError, match="XML 1.0-forbidden character") as caught:
        document.apply_edits([edit])

    assert caught.value.payload.code == "schema_write_error"
    assert caught.value.details["code_point"] in {"U+0001", "U+D800"}
    assert isinstance(caught.value.details["character_offset"], int)


def test_utf16_diff_is_decoded_with_the_source_codec() -> None:
    payload = _encoded_source("utf-16-le", b"\xff\xfe")
    document = DipTraceDocument.from_bytes(Path("encoded.xml"), payload)
    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[RefDes='R1']/Value",
                value="Новый Ω",
            )
        ]
    )

    diff = unified_xml_diff(payload, updated)

    assert f"-        <Value>{UNICODE_VALUE}</Value>" in diff
    assert "+        <Value>Новый Ω</Value>" in diff
    assert "\x00" not in diff
    assert "\ufffd" not in diff


@pytest.mark.parametrize(
    "payload",
    [
        _source_text(declaration="cp037").encode("utf-8"),
        b"\xff\xfe\x00\x00" + _source_text(declaration="UTF-32").encode("utf-32-le"),
        b"\x00\x00\xfe\xff" + _source_text(declaration="UTF-32").encode("utf-32-be"),
    ],
)
def test_unsupported_clean_encoding_fails_closed_with_typed_error(payload: bytes) -> None:
    with pytest.raises(DocumentError):
        DipTraceDocument.from_bytes(Path("unsupported.xml"), payload)
