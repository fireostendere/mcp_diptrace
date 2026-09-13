"""Tests for diptrace_mcp.pipeline module."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp import pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schematic_xml(extra_parts: str = "") -> bytes:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Source Type="DipTrace-Schematic" Units="mm">
  <Library Type="DipTrace-ComponentLibrary">
    <Library>
      <PadStyles><PadStyle Id="0"><Name>Default</Name></PadStyle></PadStyles>
      <Patterns><Pattern PatternStyle="0"><Name>Def</Name></Pattern></Patterns>
    </Library>
    <Components>
      <Component ComponentStyle="R0402" RefDes="R" PartType="Normal">
        <Part Id="0"><Name>R</Name><Pins>
          <Pin Id="1" ElectricType="Passive"/>
          <Pin Id="2" ElectricType="Passive"/>
        </Pins></Part>
      </Component>
    </Components>
  </Library>
  <Schematic>
    <Components>
      <Part Id="0" ComponentStyle="R0402" Sheet="0" X="10" Y="20">
        <RefDes>R1</RefDes><Name>REQ_C1</Name>
        <Pins><Pin NetId="0"/><Pin NetId="1"/></Pins>
      </Part>
      {extra_parts}
    </Components>
    <Nets>
      <Net Id="0"><Name>VCC</Name><Pins/><Wires/></Net>
      <Net Id="1"><Name>GND</Name><Pins/><Wires/></Net>
    </Nets>
  </Schematic>
</Source>'''.encode()


def _pcb_xml(
    extra_traces: str = "",
    extra_pours: str = "",
) -> bytes:
    outline = (
        '<Point X="0" Y="0"/>'
        '<Point X="50" Y="0"/>'
        '<Point X="50" Y="30"/>'
        '<Point X="0" Y="30"/>'
    )
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Source Type="DipTrace-PCB" Units="mm">
  <Board>
    <Settings/>
    <BoardOutline><Points>{outline}</Points></BoardOutline>
    <Components>
      <Component Id="0" RefDes="U1" X="10" Y="10"/>
    </Components>
    <Nets>
      <Net Id="0"><Name>VCC</Name>
        <Traces>
          <Trace>
            <Points>
              <Point X="5" Y="5" Lay="0" Width="0.3"/>
              <Point X="15" Y="5" Lay="0" Width="0.3"/>
              <Point X="15" Y="15" Lay="0" Width="0.3"/>
            </Points>
          </Trace>
          {extra_traces}
        </Traces>
      </Net>
    </Nets>
    <CopperPours>
      {extra_pours}
    </CopperPours>
    <Shapes/>
    <Ratlines/>
  </Board>
  <Library>
    <Library>
      <PadStyles><PadStyle Id="0"><Name>Default</Name></PadStyle></PadStyles>
      <Patterns><Pattern PatternStyle="0"><Name>Def</Name></Pattern></Patterns>
    </Library>
    <Components/>
  </Library>
</Source>'''.encode()


# ---------------------------------------------------------------------------
# _detect_kind
# ---------------------------------------------------------------------------

class TestDetectKind:
    def test_schematic(self, tmp_path: Path) -> None:
        p = tmp_path / "s.dch"
        p.write_bytes(_schematic_xml())
        assert pipeline._detect_kind(p) == "schematic"

    def test_pcb(self, tmp_path: Path) -> None:
        p = tmp_path / "b.dip"
        p.write_bytes(_pcb_xml())
        assert pipeline._detect_kind(p) == "pcb"

    def test_unknown(self, tmp_path: Path) -> None:
        p = tmp_path / "x.xml"
        p.write_text(
            '<?xml version="1.0"?>'
            '<Source Type="DipTrace-Other"><Library/></Source>'
        )
        assert pipeline._detect_kind(p) == "unknown"


# ---------------------------------------------------------------------------
# nativeize_document
# ---------------------------------------------------------------------------

class TestNativeizeDocument:
    def test_schematic_graft(self, tmp_path: Path) -> None:
        src = tmp_path / "gen.dch"
        src.write_bytes(_schematic_xml())
        tpl = tmp_path / "tpl.dch"
        tpl.write_bytes(_schematic_xml())
        out = tmp_path / "out.dch"

        result = pipeline.nativeize_document(str(src), str(tpl), str(out))
        assert result["ok"] is True
        assert result["kind"] == "schematic"
        assert out.exists()
        root = ET.fromstring(out.read_bytes())
        assert root.get("Units") == "mm"
        lib = root.find("./Library")
        assert lib is not None
        assert lib.get("Units") == "mm"

    def test_pcb_graft(self, tmp_path: Path) -> None:
        src = tmp_path / "gen.dip"
        src.write_bytes(_pcb_xml())
        tpl = tmp_path / "tpl.dip"
        tpl.write_bytes(_pcb_xml())
        out = tmp_path / "out.dip"

        result = pipeline.nativeize_document(str(src), str(tpl), str(out))
        assert result["ok"] is True
        assert result["kind"] == "pcb"
        assert out.exists()
        root = ET.fromstring(out.read_bytes())
        assert root.get("Units") == "mm"

    def test_kind_mismatch_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "s.dch"
        src.write_bytes(_schematic_xml())
        tpl = tmp_path / "b.dip"
        tpl.write_bytes(_pcb_xml())
        out = tmp_path / "out.dch"

        with pytest.raises(ValueError, match="Kind mismatch"):
            pipeline.nativeize_document(str(src), str(tpl), str(out))


# ---------------------------------------------------------------------------
# render_board_svg
# ---------------------------------------------------------------------------

class TestRenderBoardSvg:
    def test_basic_render(self, tmp_path: Path) -> None:
        pcb_file = tmp_path / "board.dip"
        pcb_file.write_bytes(_pcb_xml())
        out_dir = tmp_path / "svgs"

        result = pipeline.render_board_svg(str(pcb_file), str(out_dir))
        assert result["ok"] is True
        assert len(result["files"]) == 2
        for fp in result["files"]:
            assert fp.endswith(".svg")
            content = Path(fp).read_text(encoding="utf-8")
            assert "<svg" in content
            assert "board" in content.lower() or "Top" in content \
                or "Bottom" in content

    def test_no_board_element(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.xml"
        p.write_text(
            '<?xml version="1.0"?>'
            '<Source Type="DipTrace-PCB"><Library/></Source>'
        )
        result = pipeline.render_board_svg(str(p), str(tmp_path / "out"))
        assert result["ok"] is False
        assert "No Board" in result["error"]

    def test_empty_outline(self, tmp_path: Path) -> None:
        p = tmp_path / "empty_outline.dip"
        xml = (
            '<?xml version="1.0"?>'
            '<Source Type="DipTrace-PCB"><Board>'
            '<BoardOutline><Points/></BoardOutline>'
            '<Nets/><CopperPours/><Shapes/><Ratlines/>'
            '</Board></Source>'
        )
        p.write_text(xml)
        result = pipeline.render_board_svg(str(p), str(tmp_path / "out"))
        assert result["ok"] is False
        assert "Empty outline" in result["error"]

    def test_missing_outline_points(self, tmp_path: Path) -> None:
        p = tmp_path / "no_outline.dip"
        xml = (
            '<?xml version="1.0"?>'
            '<Source Type="DipTrace-PCB"><Board>'
            '<BoardOutline/>'
            '<Nets/><CopperPours/><Shapes/><Ratlines/>'
            '</Board></Source>'
        )
        p.write_text(xml)
        result = pipeline.render_board_svg(str(p), str(tmp_path / "out"))
        assert result["ok"] is False
        assert "No BoardOutline" in result["error"]

    def test_traces_with_via_and_layer_switch(self, tmp_path: Path) -> None:
        extra = (
            '<Trace><Points>'
            '<Point X="1" Y="1" Lay="0" Width="0.25"/>'
            '<Point X="5" Y="1" Lay="0" Width="0.25" ViaStyle="0"/>'
            '<Point X="5" Y="10" Lay="1" Width="0.25"/>'
            '<Point X="20" Y="10" Lay="1" Width="0.25"/>'
            '</Points></Trace>'
        )
        pcb_file = tmp_path / "board2.dip"
        pcb_file.write_bytes(_pcb_xml(extra_traces=extra))
        result = pipeline.render_board_svg(
            str(pcb_file), str(tmp_path / "out")
        )
        assert result["ok"] is True

    def test_with_copper_pours(self, tmp_path: Path) -> None:
        pour = (
            '<CopperPour Lay="0"><Points>'
            '<Point X="2" Y="2"/>'
            '<Point X="48" Y="2"/>'
            '<Point X="48" Y="28"/>'
            '</Points></CopperPour>'
        )
        pcb_file = tmp_path / "pours.dip"
        pcb_file.write_bytes(_pcb_xml(extra_pours=pour))
        result = pipeline.render_board_svg(
            str(pcb_file), str(tmp_path / "out")
        )
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# lcsc_fetch
# ---------------------------------------------------------------------------

class TestLcscFetch:
    def _easyeda_payload(self) -> dict[str, Any]:
        return {
            "result": {
                "title": "STM32F103C8T6",
                "packageDetail": {
                    "title": "LQFP-48",
                    "dataStr": {
                        "shape": [
                            "PAD~1~", "PAD~2~",
                            "PAD,3~",
                        ],
                    },
                },
                "dataStr": {
                    "shape": [
                        "P~pin1~", "P~pin2~",
                        "LINE~something~",
                    ],
                },
            },
        }

    def test_direct_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = self._easyeda_payload()
        product_html = (
            '<a href="https://www.lcsc.com/product-detail/C88888.html">'
            'component_svgs/prod/aabbccdd11223344aabbccdd11223344</a>'
            '"pdfUrl":"https://datasheet.lcsc.com/test.pdf"'
        )
        out_dir = tmp_path / "lcsc_out"

        def fake_curl(url: str) -> str:
            if "product-detail" in url:
                return product_html
            if "easyeda.com/api/components" in url:
                return json.dumps(payload)
            return ""

        monkeypatch.setattr(pipeline, "_curl", fake_curl)
        monkeypatch.setattr(pipeline, "_download", lambda u, d: None)

        result = pipeline.lcsc_fetch("C88888", str(out_dir))
        assert result["code"] == "C88888"
        assert result["mpn"] == "STM32F103C8T6"
        assert result["package"] == "LQFP-48"
        assert result["pins"] == 2
        assert result["pads"] == 3
        assert (out_dir / "C88888.json").exists()

    def test_mpn_resolution_via_duckduckgo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._easyeda_payload()
        ddg_html = (
            'something lcsc.com/product-detail/C123456.html more stuff'
        )
        product_html = (
            'component_svgs/prod/aaaabbbbccccdddd1111222233334444'
        )

        def fake_curl(url: str) -> str:
            if "duckduckgo" in url:
                return ddg_html
            if "product-detail" in url:
                return product_html
            if "easyeda.com" in url:
                return json.dumps(payload)
            return ""

        monkeypatch.setattr(pipeline, "_curl", fake_curl)
        monkeypatch.setattr(pipeline, "_download", lambda u, d: None)

        result = pipeline.lcsc_fetch("STM32F103", str(tmp_path / "o"))
        assert result["code"] == "C123456"

    def test_mpn_fallback_to_jlc_search(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._easyeda_payload()
        product_html = "component_svgs/prod/" + "a" * 32

        def fake_curl(url: str) -> str:
            if "duckduckgo" in url:
                return "no results here"
            if "product-detail" in url:
                return product_html
            if "easyeda.com" in url:
                return json.dumps(payload)
            return ""

        monkeypatch.setattr(pipeline, "_curl", fake_curl)
        monkeypatch.setattr(pipeline, "_download", lambda u, d: None)
        monkeypatch.setattr(
            pipeline, "_jlc_search", lambda q: "C99999"
        )

        result = pipeline.lcsc_fetch("MYMPN", str(tmp_path / "o"))
        assert result["code"] == "C99999"

    def test_cannot_resolve_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(pipeline, "_curl", lambda url: "nothing useful")
        monkeypatch.setattr(pipeline, "_jlc_search", lambda q: None)

        with pytest.raises(ValueError, match="Cannot resolve"):
            pipeline.lcsc_fetch("UNKNOWN_PART", str(tmp_path / "o"))

    def test_no_combined_document_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        product_html = (
            'component_svgs/prod/' + "a" * 32
        )

        def fake_curl(url: str) -> str:
            if "product-detail" in url:
                return product_html
            if "easyeda.com" in url:
                return '{"result": {"noPackageDetail": true}}'
            return ""

        monkeypatch.setattr(pipeline, "_curl", fake_curl)
        monkeypatch.setattr(pipeline, "_download", lambda u, d: None)

        with pytest.raises(ValueError, match="no combined"):
            pipeline.lcsc_fetch("C12345", str(tmp_path / "o"))

    def test_datasheet_not_downloaded_when_no_pdf(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = self._easyeda_payload()
        product_html = 'component_svgs/prod/' + "b" * 32

        def fake_curl(url: str) -> str:
            if "product-detail" in url:
                return product_html
            if "easyeda.com" in url:
                return json.dumps(payload)
            return ""

        downloads: list[str] = []
        monkeypatch.setattr(pipeline, "_curl", fake_curl)
        monkeypatch.setattr(
            pipeline, "_download", lambda u, d: downloads.append(u)
        )

        result = pipeline.lcsc_fetch("C55555", str(tmp_path / "o"))
        assert result["datasheet"] is None
        assert len(downloads) == 0

    def test_bad_json_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If first UUID returns bad JSON, loop continues to next."""
        payload = self._easyeda_payload()
        product_html = (
            'component_svgs/prod/' + "a" * 32
            + ' component_svgs/prod/' + "b" * 32
        )
        calls = {"n": 0}

        def fake_curl(url: str) -> str:
            if "product-detail" in url:
                return product_html
            if "easyeda.com" in url:
                calls["n"] += 1
                if calls["n"] == 1:
                    return "NOT JSON"
                return json.dumps(payload)
            return ""

        monkeypatch.setattr(pipeline, "_curl", fake_curl)
        monkeypatch.setattr(pipeline, "_download", lambda u, d: None)

        result = pipeline.lcsc_fetch("C77777", str(tmp_path / "o"))
        assert result["code"] == "C77777"
