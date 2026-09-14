from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from diptrace_mcp.provenance import (
    BomLine,
    export_bom,
    set_bom_fields,
    write_provenance_markdown,
)
from diptrace_mcp.xml_document import DipTraceDocument


def _schematic_xml(parts: str) -> bytes:
    return (
        b'<Source Type="DipTrace-Schematic">'
        b"<Schematic><Components>" + parts.encode() + b"</Components></Schematic>"
        b"</Source>"
    )


def _part(
    refdes: str,
    value: str = "10k",
    pattern_style: str = "R0402",
    mpn: str = "",
    manufacturer: str = "",
    lcsc: str = "",
    datasheet: str = "",
) -> str:
    fields = ""
    if mpn:
        fields += f'<AddField><Name>MPN</Name><Text>{mpn}</Text></AddField>'
    if manufacturer:
        fields += (
            f"<AddField><Name>Manufacturer</Name>"
            f"<Text>{manufacturer}</Text></AddField>"
        )
    if lcsc:
        fields += f'<AddField><Name>LCSC</Name><Text>{lcsc}</Text></AddField>'
    if datasheet:
        fields += (
            f"<AddField><Name>Datasheet</Name>"
            f"<Text>{datasheet}</Text></AddField>"
        )
    af = f"<AddFields>{fields}</AddFields>" if fields else "<AddFields/>"
    return (
        f'<Part Id="{refdes}"><RefDes>{refdes}</RefDes>'
        f"<Value>{value}</Value>{af}"
        f'<Pattern Style="{pattern_style}"/>'
        f"</Part>"
    )


def _write_schematic(tmp_path: Path, parts: str, name: str = "sch.xml") -> Path:
    p = tmp_path / name
    p.write_bytes(_schematic_xml(parts))
    return p


def test_export_bom_groups_by_key_identity(tmp_path: Path) -> None:
    parts = (
        _part("R1", "10k", "R0402", mpn="RC0402FR-0710KL", manufacturer="Yageo")
        + _part("R2", "10k", "R0402", mpn="RC0402FR-0710KL", manufacturer="Yageo")
        + _part("R3", "4k7", "R0402", mpn="RC0402FR-074K7L", manufacturer="Yageo")
    )
    path = _write_schematic(tmp_path, parts)
    lines = export_bom(path)
    assert len(lines) == 2
    r10k = [bom for bom in lines if bom.value == "10k"][0]
    assert sorted(r10k.refdes) == ["R1", "R2"]
    assert r10k.mpn == "RC0402FR-0710KL"
    r4k7 = [bom for bom in lines if bom.value == "4k7"][0]
    assert r4k7.refdes == ["R3"]


def test_export_bom_skips_power_symbols(tmp_path: Path) -> None:
    parts = (
        _part("R1", "10k", mpn="MPN1")
        + _part("PSG1", "VCC", mpn="")
        + _part("PWR1", "3V3", mpn="")
        + _part("NPI1", "NC", mpn="")
        + _part("NPO1", "NC", mpn="")
    )
    path = _write_schematic(tmp_path, parts)
    lines = export_bom(path)
    assert len(lines) == 1
    assert lines[0].refdes == ["R1"]


def test_export_bom_merges_same_key_extends_refdes(tmp_path: Path) -> None:
    parts = (
        _part("C1", "100nF", "C0402", mpn="GRM155R71C104KA88D")
        + _part("C2", "100nF", "C0402", mpn="GRM155R71C104KA88D")
        + _part("C3", "100nF", "C0402", mpn="GRM155R71C104KA88D")
    )
    path = _write_schematic(tmp_path, parts)
    lines = export_bom(path)
    assert len(lines) == 1
    assert sorted(lines[0].refdes) == ["C1", "C2", "C3"]


def test_export_bom_sorted_by_mpn(tmp_path: Path) -> None:
    parts = (
        _part("R2", "1k", mpn="ZZZ_MPN")
        + _part("R1", "10k", mpn="AAA_MPN")
    )
    path = _write_schematic(tmp_path, parts)
    lines = export_bom(path)
    assert lines[0].mpn == "AAA_MPN"
    assert lines[1].mpn == "ZZZ_MPN"


def test_export_bom_empty_schematic(tmp_path: Path) -> None:
    path = _write_schematic(tmp_path, "")
    lines = export_bom(path)
    assert lines == []


def test_write_provenance_markdown(tmp_path: Path) -> None:
    out = tmp_path / "prov.md"
    lines = [
        BomLine(
            refdes=["R1", "R2"], value="10k", pattern="R0402",
            mpn="RC0402FR-0710KL", manufacturer="Yageo",
            lcsc="C25741", datasheet="https://example.com/ds.pdf",
        ),
        BomLine(
            refdes=["C1"], value="100nF", pattern="C0402",
            mpn="GRM155R71C104KA88D", manufacturer="Murata",
            lcsc="C307331", datasheet="",
        ),
    ]
    write_provenance_markdown(lines, out)
    text = out.read_text(encoding="utf-8")
    assert "# Component provenance" in text
    assert "RC0402FR-0710KL" in text
    assert "R1, R2" in text
    assert "GRM155R71C104KA88D" in text
    assert "| RefDes |" in text


def test_write_provenance_markdown_empty(tmp_path: Path) -> None:
    out = tmp_path / "prov_empty.md"
    write_provenance_markdown([], out)
    text = out.read_text(encoding="utf-8")
    assert "# Component provenance" in text
    assert "| RefDes |" in text


def test_set_bom_fields_dry_run(tmp_path: Path) -> None:
    parts = _part("R1", "10k", mpn="OLD_MPN")
    path = _write_schematic(tmp_path, parts)
    mock_doc = DipTraceDocument.from_bytes(path, path.read_bytes())
    mock_compiled = MagicMock()
    mock_compiled.document = mock_doc
    mock_apply = MagicMock(return_value=mock_compiled)
    monkeypatch_mod = pytest.importorskip("diptrace_mcp.domain")
    orig_qs = monkeypatch_mod.QuerySelector
    import diptrace_mcp.domain as dom_mod
    import diptrace_mcp.operations as ops_mod
    import diptrace_mcp.semantic_compiler as sc_mod
    dom_mod.QuerySelector = MagicMock(return_value="mock_qs")
    orig_set_component_properties = ops_mod.SetComponentPropertiesOperation
    ops_mod.SetComponentPropertiesOperation = MagicMock(return_value="mock_op")
    orig_apply = sc_mod.apply_semantic_operations
    sc_mod.apply_semantic_operations = mock_apply
    try:
        result = set_bom_fields(
            path, {"R1": {"MPN": "NEW_MPN"}}, dry_run=True,
        )
    finally:
        dom_mod.QuerySelector = orig_qs
        ops_mod.SetComponentPropertiesOperation = orig_set_component_properties
        sc_mod.apply_semantic_operations = orig_apply
    assert result["updated"] == 1
    assert "sha256" in result


def test_set_bom_fields_writes_file(tmp_path: Path) -> None:
    parts = _part("R1", "10k")
    path = _write_schematic(tmp_path, parts)
    original = path.read_bytes()
    mock_doc = DipTraceDocument.from_bytes(path, original)
    mock_compiled = MagicMock()
    mock_compiled.document = mock_doc
    mock_apply = MagicMock(return_value=mock_compiled)
    import diptrace_mcp.domain as dom_mod
    import diptrace_mcp.operations as ops_mod
    import diptrace_mcp.semantic_compiler as sc_mod
    orig_qs = dom_mod.QuerySelector
    orig_op = ops_mod.SetComponentPropertiesOperation
    orig_apply = sc_mod.apply_semantic_operations
    dom_mod.QuerySelector = MagicMock(return_value="qs")
    ops_mod.SetComponentPropertiesOperation = MagicMock(return_value="op")
    sc_mod.apply_semantic_operations = mock_apply
    try:
        result = set_bom_fields(
            path, {"R1": {"MPN": "NEW"}}, dry_run=False,
        )
    finally:
        dom_mod.QuerySelector = orig_qs
        ops_mod.SetComponentPropertiesOperation = orig_op
        sc_mod.apply_semantic_operations = orig_apply
    assert result["updated"] == 1
    assert path.read_bytes() == mock_doc.raw_bytes
