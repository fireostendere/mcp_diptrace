from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from diptrace_mcp.errors import DocumentError, EditError
from diptrace_mcp.xml_document import DipTraceDocument, XmlEdit


@dataclass(frozen=True)
class _AdversarialDocument:
    name: str
    payload: bytes
    message: str


def _encoded_document(
    body: str,
    *,
    codec: str,
    declaration: str,
    bom: bytes = b"",
) -> bytes:
    text = (
        f'<?xml version="1.0" encoding="{declaration}"?>'
        f"{body}"
    )
    return bom + text.encode(codec)


_ADVERSARIAL_DOCUMENTS = (
    _AdversarialDocument(
        "bomless_utf32be_external_dtd",
        _encoded_document(
            '<!DOCTYPE Source SYSTEM "file:///definitely-not-read.dtd">'
            '<Source Type="DipTrace-PCB"><Board /></Source>',
            codec="utf-32-be",
            declaration="UTF-32",
        ),
        "DTD and ENTITY declarations are not allowed",
    ),
    _AdversarialDocument(
        "late_utf16le_external_parameter_entity",
        _encoded_document(
            "<!--" + ("padding" * 2_048) + "-->"
            '<!DOCTYPE Source [<!ENTITY % remote SYSTEM "file:///not-read.ent">%remote;]>'
            '<Source Type="DipTrace-PCB"><Board /></Source>',
            codec="utf-16-le",
            declaration="UTF-16",
        ),
        "DTD and ENTITY declarations are not allowed",
    ),
    _AdversarialDocument(
        "declaration_conflicts_with_bom",
        _encoded_document(
            '<Source Type="DipTrace-PCB"><Board /></Source>',
            codec="utf-16-le",
            declaration="UTF-8",
            bom=b"\xff\xfe",
        ),
        "conflicts with the byte-order mark",
    ),
    _AdversarialDocument(
        "non_stream_codec_declaration",
        _encoded_document(
            '<Source Type="DipTrace-PCB"><Board /></Source>',
            codec="utf-8",
            declaration="idna",
        ),
        "Unsupported XML encoding declaration",
    ),
    _AdversarialDocument(
        "truncated_utf16_code_unit",
        _encoded_document(
            '<Source Type="DipTrace-PCB"><Board /></Source>',
            codec="utf-16-be",
            declaration="UTF-16",
        )
        + b"\x00",
        "Invalid XML",
    ),
)


@pytest.mark.parametrize(
    "case",
    _ADVERSARIAL_DOCUMENTS,
    ids=lambda case: case.name,
)
def test_public_loader_fails_closed_on_generated_adversarial_corpus(
    case: _AdversarialDocument,
) -> None:
    """Every synthetic attack is rejected through the public typed contract."""

    with pytest.raises(DocumentError, match=case.message) as caught:
        DipTraceDocument.from_bytes(Path(f"{case.name}.synthetic.xml"), case.payload)

    assert caught.value.payload.code == "schema_parse_error"


@pytest.mark.parametrize(
    "fragment",
    [
        '<!DOCTYPE Injected SYSTEM "file:///definitely-not-read.dtd"><Injected />',
        '<!DOCTYPE Injected [<!ENTITY % p "ignored">%p;]><Injected />',
        '<!ENTITY standalone "ignored"><Injected />',
    ],
    ids=["external_doctype", "parameter_entity", "standalone_entity"],
)
def test_public_edit_rejects_adversarial_fragment_corpus_without_mutating_source(
    fragment: str,
) -> None:
    payload = (
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        b"<Board><Future /></Board></Source>"
    )
    document = DipTraceDocument.from_bytes(Path("fragment-target.synthetic.xml"), payload)

    with pytest.raises(EditError, match="DTD and ENTITY declarations") as caught:
        document.apply_edits(
            [
                XmlEdit(
                    operation="append_xml",
                    xpath="./Board/Future",
                    value=fragment,
                )
            ]
        )

    assert caught.value.payload.code == "schema_write_error"
    assert document.raw_bytes == payload


def test_deep_public_edit_does_not_escape_as_recursion_error() -> None:
    """Deep but small synthetic XML must keep the public edit/error boundary."""

    depth = 1_500
    nested = ("<Node>" * depth) + "<Leaf/>" + ("</Node>" * depth)
    payload = (
        '<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        f"<Board>{nested}</Board></Source>"
    ).encode()
    document = DipTraceDocument.from_bytes(Path("deep.synthetic.xml"), payload)

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_attribute",
                xpath=".//Leaf",
                attribute="Checked",
                value="Y",
            )
        ]
    )

    assert updated == payload.replace(b"<Leaf/>", b'<Leaf Checked="Y"/>')


_EDIT_ENCODINGS = st.sampled_from(
    [
        ("utf-8", "UTF-8", b""),
        ("utf-8", "UTF-8", b"\xef\xbb\xbf"),
        ("utf-16-le", "UTF-16", b""),
        ("utf-16-le", "UTF-16", b"\xff\xfe"),
        ("utf-16-be", "UTF-16", b""),
        ("utf-16-be", "UTF-16", b"\xfe\xff"),
        ("us-ascii", "US-ASCII", b""),
        ("iso-8859-1", "ISO-8859-1", b""),
    ]
)
_VALID_EDIT_TEXT = st.text(
    alphabet=list(" abcXYZ09&<>\"'\t\n\rµΩ°±Кириллица😀"),
    min_size=0,
    max_size=64,
)


def _escaped_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\t", "&#9;")
        .replace("\n", "&#10;")
        .replace("\r", "&#13;")
    )


def _escaped_attribute(value: str, quote: str) -> str:
    escaped = value.replace("&", "&amp;").replace("<", "&lt;")
    escaped = (
        escaped.replace('"', "&quot;")
        if quote == '"'
        else escaped.replace("'", "&apos;")
    )
    return (
        escaped.replace("\t", "&#9;")
        .replace("\n", "&#10;")
        .replace("\r", "&#13;")
    )


@settings(max_examples=100, deadline=None)
@given(value=_VALID_EDIT_TEXT, encoding=_EDIT_ENCODINGS)
def test_set_text_preserves_every_byte_outside_the_target_property(
    value: str,
    encoding: tuple[str, str, bytes],
) -> None:
    codec, declaration, bom = encoding
    before_text = (
        f'<?xml version="1.0" encoding="{declaration}"?>'
        '<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        "<Board><Before Keep='yes'/><Value>ORIGINAL</Value><After Keep='yes'/>"
        "</Board></Source>"
    )
    payload = bom + before_text.encode(codec)
    expected_text = before_text.replace(
        "<Value>ORIGINAL</Value>",
        f"<Value>{_escaped_text(value)}</Value>",
    )
    expected = bom + expected_text.encode(codec, errors="xmlcharrefreplace")
    document = DipTraceDocument.from_bytes(Path("text-property.synthetic.xml"), payload)

    updated, _previews = document.apply_edits(
        [XmlEdit(operation="set_text", xpath="./Board/Value", value=value)]
    )

    assert updated == expected


@settings(max_examples=100, deadline=None)
@given(
    value=_VALID_EDIT_TEXT,
    quote=st.sampled_from(['"', "'"]),
    leading=st.sampled_from([" ", "\t", "\n"]),
    before_equals=st.sampled_from(["", " ", "\t"]),
    after_equals=st.sampled_from(["", " ", "\t"]),
)
def test_set_attribute_preserves_lexical_layout_property(
    value: str,
    quote: str,
    leading: str,
    before_equals: str,
    after_equals: str,
) -> None:
    old_attribute = f"{leading}Target{before_equals}={after_equals}{quote}old{quote}"
    new_attribute = (
        f"{leading}Target{before_equals}={after_equals}{quote}"
        f"{_escaped_attribute(value, quote)}{quote}"
    )
    payload = (
        '<Source Type="DipTrace-PCB"><Board>'
        f"<Future{old_attribute} Keep='yes' />"
        "</Board></Source>"
    ).encode()
    document = DipTraceDocument.from_bytes(
        Path("attribute-property.synthetic.xml"),
        payload,
    )

    updated, _previews = document.apply_edits(
        [
            XmlEdit(
                operation="set_attribute",
                xpath="./Board/Future",
                attribute="Target",
                value=value,
            )
        ]
    )

    assert updated == payload.replace(
        old_attribute.encode(),
        new_attribute.encode(),
    )


_INVALID_XML_CHARACTERS = st.sampled_from(
    [
        *(chr(value) for value in range(0x00, 0x09)),
        "\x0b",
        "\x0c",
        *(chr(value) for value in range(0x0E, 0x20)),
        "\ud800",
        "\udfff",
        "\ufffe",
        "\uffff",
    ]
)


@settings(max_examples=50, deadline=None)
@given(prefix=st.text(alphabet="safe", max_size=12), invalid=_INVALID_XML_CHARACTERS)
def test_every_xml_10_forbidden_character_is_a_typed_write_error_property(
    prefix: str,
    invalid: str,
) -> None:
    payload = (
        b'<Source Type="DipTrace-PCB"><Board><Value>ORIGINAL</Value></Board></Source>'
    )
    document = DipTraceDocument.from_bytes(
        Path("invalid-character-property.synthetic.xml"),
        payload,
    )

    with pytest.raises(EditError, match="XML 1.0-forbidden character") as caught:
        document.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Value",
                    value=prefix + invalid,
                )
            ]
        )

    assert caught.value.payload.code == "schema_write_error"
    assert caught.value.details["character_offset"] == len(prefix)
    assert document.raw_bytes == payload
