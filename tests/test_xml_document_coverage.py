from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.errors import DocumentError, EditError
from diptrace_mcp.xml_document import (
    DipTraceDocument,
    RawTreeSnapshot,
    XmlEdit,
    _apply_replacements,
    _decode_xml_fragment,
    _detect_xml_encoding,
    _encode_xml_fragment,
    _open_self_closing_tag,
    _remove_raw_attribute,
    _require_valid_xml_characters,
    _set_raw_attribute,
    parse_xml_definition,
    reject_forbidden_xml_declarations,
    unified_xml_diff,
    unified_xml_diff_preview,
    write_with_backup,
)

# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------

def test_detect_encoding_unsupported_declaration() -> None:
    payload = b'<?xml version="1.0" encoding="koi8-r"?><Source Type="DipTrace-PCB"/>'
    with pytest.raises(DocumentError, match="Unsupported XML encoding"):
        DipTraceDocument.from_bytes(Path("x.xml"), payload)


def test_detect_encoding_utf16_without_bom() -> None:
    payload = b'<?xml version="1.0" encoding="utf-16"?><Source Type="DipTrace-PCB"/>'
    with pytest.raises(DocumentError, match="requires a BOM"):
        DipTraceDocument.from_bytes(Path("x.xml"), payload)


def test_detect_encoding_utf32_without_bom() -> None:
    payload = b'<?xml version="1.0" encoding="utf-32"?><Source Type="DipTrace-PCB"/>'
    with pytest.raises(DocumentError, match="requires a BOM"):
        DipTraceDocument.from_bytes(Path("x.xml"), payload)


def test_detect_encoding_bom_conflict_with_declaration() -> None:
    utf16le_bom = b"\xff\xfe"
    body = '<?xml version="1.0" encoding="utf-8"?><Source Type="DipTrace-PCB"/>'.encode(
        "utf-16-le"
    )
    payload = utf16le_bom + body
    with pytest.raises(DocumentError, match="conflicts"):
        DipTraceDocument.from_bytes(Path("x.xml"), payload)


def test_detect_encoding_signature_utf16le_with_declaration() -> None:
    # UTF-16-LE with XML declaration byte signature
    body = '<?xml version="1.0"?><Source Type="DipTrace-PCB"/>'.encode("utf-16-le")
    enc = _detect_xml_encoding(body)
    assert enc.codec == "utf-16-le"


def test_detect_encoding_signature_utf16be_with_declaration() -> None:
    # UTF-16-BE with XML declaration byte signature
    body = '<?xml version="1.0"?><Source Type="DipTrace-PCB"/>'.encode("utf-16-be")
    enc = _detect_xml_encoding(body)
    assert enc.codec == "utf-16-be"


# ---------------------------------------------------------------------------
# _encode/_decode_xml_fragment error paths
# ---------------------------------------------------------------------------

def test_encode_xml_fragment_bad_codec() -> None:
    with pytest.raises(EditError, match="Cannot encode"):
        _encode_xml_fragment("hello", "nonexistent-codec-xyz")


def test_decode_xml_fragment_bad_codec() -> None:
    with pytest.raises(EditError, match="Cannot decode"):
        _decode_xml_fragment(b"hello", "nonexistent-codec-xyz")


# ---------------------------------------------------------------------------
# parse_xml_definition
# ---------------------------------------------------------------------------

def test_parse_xml_definition_valid() -> None:
    result = parse_xml_definition("<Pad Shape='Circle' X='0' Y='0'/>")
    assert result.tag == "Pad"


def test_parse_xml_definition_rejects_dtd() -> None:
    with pytest.raises(EditError, match="forbidden"):
        parse_xml_definition("<!DOCTYPE x [<!ENTITY a 'b'>]><Pad Shape='Circle'/>")


def test_parse_xml_definition_rejects_invalid_xml() -> None:
    with pytest.raises(EditError, match="Invalid embedded"):
        parse_xml_definition("<Pad><unclosed>")


# ---------------------------------------------------------------------------
# reject_forbidden_xml_declarations — string input path
# ---------------------------------------------------------------------------

def test_reject_forbidden_xml_string_dtd() -> None:
    with pytest.raises(EditError, match="not allowed"):
        reject_forbidden_xml_declarations(
            "<!DOCTYPE x><Pad/>",
            error_type=EditError,
            context="fragment",
        )


def test_reject_forbidden_xml_pattern_definition() -> None:
    with pytest.raises(EditError, match="forbidden"):
        reject_forbidden_xml_declarations(
            "<!ENTITY a 'b'>",
            error_type=EditError,
            context="pattern_definition",
        )


# ---------------------------------------------------------------------------
# from_bytes validation errors
# ---------------------------------------------------------------------------

def test_from_bytes_non_diptrace_root() -> None:
    with pytest.raises(DocumentError, match="Expected a DipTrace"):
        DipTraceDocument.from_bytes(Path("x.xml"), b"<html/>")


def test_from_bytes_empty_type() -> None:
    with pytest.raises(DocumentError, match="Unsupported DipTrace XML type"):
        DipTraceDocument.from_bytes(Path("x.xml"), b"<Source/>")


def test_from_bytes_unknown_type() -> None:
    with pytest.raises(DocumentError, match="Unsupported DipTrace XML type"):
        DipTraceDocument.from_bytes(Path("x.xml"), b"<Source Type='Other'/>")


# ---------------------------------------------------------------------------
# DipTraceDocument.load errors
# ---------------------------------------------------------------------------

def test_load_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(DocumentError, match="Cannot stat"):
        DipTraceDocument.load(tmp_path / "missing.xml", 10_000_000)


def test_load_too_large(tmp_path: Path) -> None:
    big = tmp_path / "big.xml"
    big.write_bytes(b"<Source Type='DipTrace-PCB'/>" + b"x" * 1000)
    with pytest.raises(DocumentError, match="larger than"):
        DipTraceDocument.load(big, 10)


# ---------------------------------------------------------------------------
# kind property branches
# ---------------------------------------------------------------------------

def test_kind_component_library() -> None:
    doc = DipTraceDocument.from_bytes(
        Path("x.xml"),
        b"<Library Type='DipTrace-ComponentLibrary'/>",
    )
    assert doc.kind == "component_library"


def test_kind_pattern_library() -> None:
    doc = DipTraceDocument.from_bytes(
        Path("x.xml"),
        b"<Library Type='DipTrace-PatternLibrary'/>",
    )
    assert doc.kind == "pattern_library"


def test_kind_generic() -> None:
    doc = DipTraceDocument.from_bytes(
        Path("x.xml"), b"<Source Type='DipTrace-Unknown'/>"
    )
    assert doc.kind == "generic"


# ---------------------------------------------------------------------------
# container property branches
# ---------------------------------------------------------------------------

def test_container_generic_returns_root() -> None:
    doc = DipTraceDocument.from_bytes(
        Path("x.xml"), b"<Source Type='DipTrace-Other'><Child/></Source>"
    )
    assert doc.container.tag == "Source"


def test_container_missing_section() -> None:
    doc = DipTraceDocument.from_bytes(
        Path("x.xml"), b"<Source Type='DipTrace-PCB'/>"
    )
    with pytest.raises(DocumentError, match="Missing main section"):
        _ = doc.container


# ---------------------------------------------------------------------------
# _normalize_xpath branches (instance method on DipTraceDocument)
# ---------------------------------------------------------------------------

PCB_PAYLOAD = (
    b"<Source Type='DipTrace-PCB'><Board>"
    b"<Components><Component RefDes='R1'><Value>10k</Value>"
    b"</Component></Components></Board></Source>"
)


def _pcb_doc() -> DipTraceDocument:
    return DipTraceDocument.from_bytes(Path("pcb.xml"), PCB_PAYLOAD)


def test_normalize_xpath_empty_raises() -> None:
    doc = _pcb_doc()
    with pytest.raises(EditError, match="XPath cannot be empty"):
        doc._normalize_xpath("   ")


def test_normalize_xpath_too_long_raises() -> None:
    doc = _pcb_doc()
    with pytest.raises(EditError, match="longer than 512"):
        doc._normalize_xpath("." * 513)


def test_normalize_xpath_absolute_source() -> None:
    doc = _pcb_doc()
    assert doc._normalize_xpath("/Source/Board") == "./Board"


def test_normalize_xpath_relative_source() -> None:
    doc = _pcb_doc()
    assert doc._normalize_xpath("Source/Board") == "./Board"


def test_normalize_xpath_double_slash() -> None:
    doc = _pcb_doc()
    assert doc._normalize_xpath("//Component") == ".//Component"


def test_normalize_xpath_absolute_non_source_raises() -> None:
    doc = _pcb_doc()
    with pytest.raises(EditError, match="Absolute XPath"):
        doc._normalize_xpath("/Board")


def test_normalize_xpath_bare_element() -> None:
    doc = _pcb_doc()
    assert doc._normalize_xpath("Board") == "./Board"


def test_normalize_xpath_dot() -> None:
    doc = _pcb_doc()
    assert doc._normalize_xpath(".") == "."


# ---------------------------------------------------------------------------
# findall
# ---------------------------------------------------------------------------

def test_findall_dot_returns_root() -> None:
    doc = _pcb_doc()
    result = doc.findall(".")
    assert len(result) == 1
    assert result[0].tag == "Source"


def test_findall_invalid_xpath_raises() -> None:
    doc = _pcb_doc()
    # Invalid XPath syntax raises TypeError from ElementPath
    with pytest.raises((EditError, TypeError)):
        doc.findall(".//Component[invalid")


# ---------------------------------------------------------------------------
# xml_fragments limit
# ---------------------------------------------------------------------------

def test_xml_fragments_exceeds_limit() -> None:
    parts = "".join(f"<C Id='{i}'/>" for i in range(30))
    doc = DipTraceDocument.from_bytes(
        Path("x.xml"),
        f"<Source Type='DipTrace-PCB'><Board>{parts}</Board></Source>".encode(),
    )
    with pytest.raises(DocumentError, match="limit"):
        doc.xml_fragments("./Board/C", max_matches=10)


# ---------------------------------------------------------------------------
# apply_edits edge cases
# ---------------------------------------------------------------------------

def test_apply_edits_empty_raises() -> None:
    doc = _pcb_doc()
    with pytest.raises(EditError, match="At least one"):
        doc.apply_edits([])


def test_apply_edits_zero_expected_matches_raises() -> None:
    doc = _pcb_doc()
    with pytest.raises(EditError, match="expected_matches"):
        doc.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component/Value",
                    value="x",
                    expected_matches=0,
                )
            ]
        )


# ---------------------------------------------------------------------------
# _set_raw_attribute / _remove_raw_attribute
# ---------------------------------------------------------------------------

def test_set_raw_attribute_invalid_name() -> None:
    with pytest.raises(EditError, match="Invalid XML attribute name"):
        _set_raw_attribute(b"<Pad />", "bad name!", "val", "utf-8")


def test_set_raw_attribute_new_attribute() -> None:
    result = _set_raw_attribute(b"<Pad Shape='Circle'/>", "Enabled", "Y", "utf-8")
    assert b"Enabled=" in result


def test_remove_raw_attribute_missing() -> None:
    with pytest.raises(EditError, match="missing"):
        _remove_raw_attribute(b"<Pad Shape='Circle'/>", "Enabled", "utf-8")


def test_remove_raw_attribute_invalid_name() -> None:
    with pytest.raises(EditError, match="Invalid XML attribute name"):
        _remove_raw_attribute(b"<Pad />", "bad name!", "utf-8")


# ---------------------------------------------------------------------------
# _require_valid_xml_characters
# ---------------------------------------------------------------------------

def test_require_valid_xml_characters_null() -> None:
    with pytest.raises(EditError, match="forbidden"):
        _require_valid_xml_characters("bad\x00text", "test")


def test_require_valid_xml_characters_surrogate() -> None:
    with pytest.raises(EditError, match="forbidden"):
        _require_valid_xml_characters("bad\ud800text", "test")


# ---------------------------------------------------------------------------
# _apply_replacements errors
# ---------------------------------------------------------------------------

def test_apply_replacements_outside_document() -> None:
    with pytest.raises(EditError, match="outside"):
        _apply_replacements(b"data", [(100, 200, b"x")])


def test_apply_replacements_overlapping() -> None:
    with pytest.raises(EditError, match="Overlapping"):
        _apply_replacements(b"abcdef", [(0, 4, b"X"), (2, 5, b"Y")])


# ---------------------------------------------------------------------------
# _open_self_closing_tag
# ---------------------------------------------------------------------------

def test_open_self_closing_tag() -> None:
    result = _open_self_closing_tag(b"<Pad Shape='Circle'/>", "utf-8")
    assert result == b"<Pad Shape='Circle'>"


# ---------------------------------------------------------------------------
# _scan_start_tag_end — unterminated tag
# ---------------------------------------------------------------------------

def test_raw_element_spans_unterminated_tag() -> None:
    bad = b"<Source Type='DipTrace-PCB'><Board <Child/></Board></Source>"
    # Malformed XML raises DocumentError from _parse_root
    with pytest.raises(DocumentError, match="Invalid XML"):
        DipTraceDocument.from_bytes(Path("x.xml"), bad)


# ---------------------------------------------------------------------------
# unified_xml_diff_preview
# ---------------------------------------------------------------------------

def test_unified_xml_diff_preview_invalid_limits() -> None:
    before = b"<Source/>"
    after = b"<Source/>"
    with pytest.raises(ValueError, match="max_lines"):
        unified_xml_diff_preview(before, after, max_lines=0)
    with pytest.raises(ValueError, match="max_characters"):
        unified_xml_diff_preview(before, after, max_characters=5)


def test_unified_xml_diff_preview_truncation_by_lines() -> None:
    before_lines = "\n".join(f"<L{i}/>" for i in range(50))
    after_lines = "\n".join(f"<L{i}/>" for i in range(50, 100))
    before = f"<Source>{before_lines}</Source>".encode()
    after = f"<Source>{after_lines}</Source>".encode()
    rendered, meta = unified_xml_diff_preview(before, after, max_lines=10)
    assert meta["truncated"] is True
    assert meta["total_line_count"] > 10


def test_unified_xml_diff_preview_truncation_by_characters() -> None:
    before = b"<Source><A>" + b"x" * 500 + b"</A></Source>"
    after = b"<Source><A>" + b"y" * 500 + b"</A></Source>"
    rendered, meta = unified_xml_diff_preview(before, after, max_characters=100)
    assert meta["truncated"] is True


def test_unified_xml_diff_wrapper() -> None:
    before = b"<Source><A/></Source>"
    after = b"<Source><B/></Source>"
    result = unified_xml_diff(before, after)
    assert "-<A/>" in result or "-  <A/>" in result or "<A/>" in result


def test_unified_xml_diff_identical() -> None:
    data = b"<Source><A/></Source>"
    result = unified_xml_diff(data, data)
    assert result == ""


# ---------------------------------------------------------------------------
# write_with_backup
# ---------------------------------------------------------------------------

def test_write_with_backup_rejects_plain_path(tmp_path: Path) -> None:
    with pytest.raises(EditError, match="backup"):
        write_with_backup(
            tmp_path / "out.xml",
            b"<Source/>",
            tmp_path,
        )


# ---------------------------------------------------------------------------
# RawTreeSnapshot.compile — root identity check
# ---------------------------------------------------------------------------

def test_raw_tree_snapshot_compile_root_identity() -> None:
    doc = DipTraceDocument.from_bytes(Path("pcb.xml"), PCB_PAYLOAD)
    snapshot = RawTreeSnapshot.capture(doc)
    other_root = ET.fromstring(b"<Other/>")
    with pytest.raises(EditError, match="replaced the XML root"):
        snapshot.compile(other_root, Path("pcb.xml"))
