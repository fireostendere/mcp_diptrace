from __future__ import annotations

import xml.parsers.expat as expat
from pathlib import Path

import pytest

from diptrace_mcp import xml_document as xml
from diptrace_mcp.errors import DocumentError, EditError


def test_xml_encoding_rare_declaration_paths() -> None:
    assert xml._declaration_from_prefix(b"\xff", "utf-8", b"") is None
    assert xml._declaration_from_prefix(b"x", "missing-codec", b"") is None
    assert xml._declaration_matches_codec("utf-8-sig", "utf-8")

    unsupported = b"\xff\xfe" + '<?xml version="1.0" encoding="koi8-r"?><Source/>'.encode(
        "utf-16-le"
    )
    with pytest.raises(DocumentError, match="Unsupported"):
        xml._detect_xml_encoding(unsupported)
    signature = '<?xml version="1.0" encoding="koi8-r"?><Source/>'.encode("utf-16-le")
    with pytest.raises(DocumentError, match="Unsupported"):
        xml._detect_xml_encoding(signature)
    conflict = '<?xml version="1.0" encoding="utf-16-be"?><Source/>'.encode("utf-16-le")
    with pytest.raises(DocumentError, match="conflicts"):
        xml._detect_xml_encoding(conflict)
    with pytest.raises(DocumentError, match="ASCII codec"):
        xml._detect_xml_encoding(b'<?xml version="1.0" encoding="\xff"?><Source/>')
    assert xml._encoding_candidates(b'<?xml encoding="\xff"?>') == ()


@pytest.mark.parametrize("callback", ["doctype", "entity", "external"])
def test_xml_expat_callbacks_reject_declarations(
    callback: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Parser:
        StartDoctypeDeclHandler = None
        EntityDeclHandler = None
        ExternalEntityRefHandler = None

        def Parse(self, _data: bytes, _final: bool) -> None:
            if callback == "doctype":
                self.StartDoctypeDeclHandler("x", None, None, 0)
            elif callback == "entity":
                self.EntityDeclHandler("x", 0, None, None, None, None, None)
            else:
                self.ExternalEntityRefHandler("x", None, None, None)

    monkeypatch.setattr(xml.expat, "ParserCreate", lambda *_args: Parser())
    with pytest.raises(EditError, match="not allowed"):
        xml.reject_forbidden_xml_declarations(
            b"<Source/>", error_type=EditError, context="fragment"
        )


def test_xml_load_offsets_xpath_and_fragment_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "board.xml"
    path.write_bytes(b'<Source Type="DipTrace-PCB"><Board/></Source>')
    document = xml.DipTraceDocument.load(path, 1_000)

    with pytest.raises(EditError, match="Unsupported XPath"):
        document.findall(".//A[foo()]/")
    with pytest.raises(EditError, match="self-closing"):
        xml._open_self_closing_tag(b"<Pad>", "utf-8")
    with pytest.raises(EditError):
        xml._parse_fragment(0, "<broken>")
    with pytest.raises(EditError):
        xml._parse_root_fragment(b"<broken>")

    class BrokenParser:
        CurrentByteIndex = 0
        StartElementHandler = None

        def Parse(self, _data: bytes, _final: bool) -> None:
            raise expat.ExpatError("bad")

    monkeypatch.setattr(xml.expat, "ParserCreate", lambda *_args: BrokenParser())
    assert document.element_byte_offset(document.root) is None

    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _self: (_ for _ in ()).throw(OSError("denied")),
    )
    with pytest.raises(DocumentError, match="Cannot read"):
        xml.DipTraceDocument.load(path, 1_000)
