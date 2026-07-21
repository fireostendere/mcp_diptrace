import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.domain import QueryRequest, QuerySelector
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_capabilities_distinguish_tested_and_documented_format_versions() -> None:
    capabilities = get_capabilities()

    assert capabilities.source_types["tested_versions"] == {
        "DipTrace-PCB": ["4.3.0.3"],
        "DipTrace-Schematic": ["4.3.0.3"],
        "DipTrace-ComponentLibrary": ["4.3.0.1"],
        "DipTrace-PatternLibrary": ["4.3.0.1"],
    }
    assert capabilities.source_types["documented_versions"][
        "DipTrace-PatternLibrary"
    ] == ["4.3.0.1", "5.3.0.0"]
    assert (
        capabilities.source_types["compatibility_policy"]
        == "feature_detected_preserve_unknown"
    )


def test_normalized_board_and_schematic_models() -> None:
    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)

    pcb_snapshot = build_snapshot(pcb)
    schematic_snapshot = build_snapshot(schematic)

    assert pcb_snapshot.board is not None
    assert pcb_snapshot.board.outline["point_count"] == 4
    assert pcb_snapshot.board.traces[0].attributes["length_mm"] == 10.0
    assert pcb_snapshot.info.compatibility["roundtrip"] == "partial"
    assert "traces_and_vias" in pcb_snapshot.info.compatibility["writable_objects"]
    assert not any(
        "not implemented yet" in item
        for item in pcb_snapshot.info.compatibility["limitations"]
    )
    assert schematic_snapshot.schematic is not None
    assert schematic_snapshot.schematic.erc["attributes"]["CheckPinType"] == "Y"

    query = QueryRequest(selector=QuerySelector(refdes=["R1"]), limit=10)
    pcb_results = pcb_snapshot.query(query)
    assert pcb_results.total >= 1
    assert pcb_results.items[0].refdes == "R1"

    caps = get_capabilities(pcb)
    assert caps.read_capabilities["board_model"] is True
    assert caps.write_capabilities["transactions"] is True


def test_unknown_format_version_uses_feature_detection_and_preserves_unknown_xml() -> None:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    root.set("Version", "99.0.experimental")
    modified = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    snapshot = build_snapshot(modified)
    compatibility = snapshot.info.compatibility
    assert compatibility["format_version"] == "99.0.experimental"
    assert (
        compatibility["version_policy"]
        == "feature_detection_with_unknown_field_preservation"
    )
    assert compatibility["default_omission_tolerant"] is True
    assert compatibility["detected_features"] == {
        "explicit_via_style_spans": False,
        "documented_via_size_fields": False,
        "observed_via_size_aliases": True,
    }
    assert modified.serialize().find(b"FutureExtension") >= 0


def test_pcb_embedded_pattern_library_drives_exact_pad_geometry() -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes()
    marker = b'<Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm" />'
    embedded = b"""<Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm">
    <PadStyles><PadStyle Name="SMD" Type="Surface" Side="Top">
      <MainStack Shape="Rectangle" Width="1" Height="0.8" />
    </PadStyle></PadStyles>
    <Patterns>
      <Pattern PatternStyle="PatType0"><Name>RES_0603</Name><DefPad Style="SMD" />
        <Pads>
          <Pad Id="0" Style="SMD" X="0" Y="-1"><Number>1</Number></Pad>
          <Pad Id="1" Style="SMD" X="0" Y="0"><Number>2</Number></Pad>
        </Pads>
      </Pattern>
      <Pattern PatternStyle="PatType1"><Name>TEST_MCU</Name><DefPad Style="SMD" />
        <Pads>
          <Pad Id="0" Style="SMD" X="0" Y="-1"><Number>1</Number></Pad>
          <Pad Id="1" Style="SMD" X="0" Y="0"><Number>2</Number></Pad>
        </Pads>
      </Pattern>
    </Patterns><UnknownCacheData Keep="Y" />
  </Library>"""
    document = DipTraceDocument.from_bytes(
        FIXTURES / "embedded-pcb.xml", raw.replace(marker, embedded)
    )

    snapshot = build_snapshot(document)

    assert snapshot.board is not None
    assert len(snapshot.board.patterns) == 2
    assert len(snapshot.board.pad_styles) == 1
    r1 = next(item for item in snapshot.board.components if item.refdes == "R1")
    r1_pads = sorted(
        (snapshot.get_object(item) for item in r1.relationships["pads"]),
        key=lambda item: item.label or "",
    )
    assert [item.position for item in r1_pads] == [
        {"x": 10.0, "y": 9.0},
        {"x": 10.0, "y": 10.0},
    ]
    assert all(item.bbox is not None for item in r1_pads)
    assert all(item.geometry_source == "embedded-pattern-library" for item in r1_pads)
    assert r1.geometry_source == "embedded-pattern-library"


def test_nested_52_pattern_cache_and_legacy_testpoint_are_normalized() -> None:
    document = DipTraceDocument.from_bytes(
        FIXTURES / "nested-cache-pcb.xml",
        b"""<?xml version="1.0" encoding="UTF-8"?>
<Source Type="DipTrace-PCB" Version="5.2.0.4" Units="mm">
  <Library Type="DipTrace-ComponentLibrary" Version="5.2.0.4" Units="mm">
    <Library Type="DipTrace-PatternLibrary" Version="5.2.0.4" Units="mm">
      <PadStyles>
        <PadStyle Name="Unused" Type="Through" HoleType="Round" Hole="-0.3333">
          <MainStack Shape="Ellipse" Width="0" Height="0" />
        </PadStyle>
        <PadStyle Name="SMD" Type="Surface" Side="Top">
          <MainStack Shape="Polygon" Width="1" Height="1">
            <Points>
              <Point X="-0.5" Y="-0.5"/><Point X="0.5" Y="-0.5"/>
              <Point X="0.5" Y="0.5"/><Point X="-0.5" Y="0.5"/>
            </Points>
          </MainStack>
        </PadStyle>
      </PadStyles>
      <Patterns>
        <Pattern PatternStyle="Connector" Width="10" Height="4">
          <Name>CONNECTOR</Name><DefPad Style="SMD"/>
          <Pads><Pad Id="1" X="0" Y="0"><Number>1</Number></Pad></Pads>
          <Shapes><Shape Type="Polygon" Layer="Top Courtyard">
            <Points>
              <Point X="-5" Y="-2"/><Point X="5" Y="-2"/>
              <Point X="5" Y="2"/><Point X="-5" Y="2"/>
            </Points>
          </Shape></Shapes>
        </Pattern>
        <Pattern PatternStyle="Probe" Width="1.86" Height="1.86">
          <Name>TP_1.00MM</Name><DefPad Style="SMD"/>
          <Pads><Pad Id="1" X="0" Y="0"><Number>TP</Number></Pad></Pads>
          <Shapes><Shape Type="Obround" Layer="Top Courtyard">
            <Points><Point X="-0.93" Y="0.93"/><Point X="0.93" Y="-0.93"/></Points>
          </Shape></Shapes>
        </Pattern>
      </Patterns>
    </Library>
  </Library>
  <Board>
    <BoardOutline><Points>
      <Point X="0" Y="0"/><Point X="20" Y="0"/>
      <Point X="20" Y="20"/><Point X="0" Y="20"/>
    </Points></BoardOutline>
    <Components>
      <Component Id="1" PatternStyle="Connector" X="10" Y="10" Side="Top">
        <RefDes>J1</RefDes><Name>CONNECTOR</Name><Pads><Pad Id="1" NetId="0"/></Pads>
      </Component>
      <Component Id="2" PatternStyle="Probe" X="15" Y="10" Side="Top">
        <RefDes>TP_SIGNAL</RefDes><Name>TP_1.00MM</Name><Pads><Pad Id="1" NetId="0"/></Pads>
      </Component>
    </Components>
    <Nets><Net Id="0"><Name>SIGNAL</Name><Pads>
      <Item Comp="1" Pad="1"/><Item Comp="2" Pad="1"/>
    </Pads></Net></Nets>
  </Board>
</Source>""",
    )

    snapshot = build_snapshot(document)

    assert snapshot.board is not None
    assert len(snapshot.board.patterns) == 2
    assert len(snapshot.board.pad_styles) == 2
    assert snapshot.board.pad_styles[0].hole_width is None
    connector = next(item for item in snapshot.board.components if item.refdes == "J1")
    assert connector.bbox == {"min_x": 5.0, "min_y": 8.0, "max_x": 15.0, "max_y": 12.0}
    assert connector.geometry_source == "embedded-pattern-library"
    assert [item.refdes for item in snapshot.board.testpoints] == ["TP_SIGNAL"]
    testpoint = snapshot.board.testpoints[0]
    assert testpoint.bbox == {
        "min_x": 14.07,
        "min_y": 9.07,
        "max_x": 15.93,
        "max_y": 10.93,
    }
    polygon_pad = snapshot.board.patterns[0].pads[0]
    assert polygon_pad.geometry is not None
    assert polygon_pad.geometry.kind == "polygon"
    assert len(polygon_pad.geometry.points) == 4
