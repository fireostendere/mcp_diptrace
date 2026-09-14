"""Tests for diptrace_mcp.pcb_build_kit module."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.pcb_build_kit import (
    dump_stage,
    inject_markings_preset,
    inject_route_keepout,
    make_intent,
    placement_from_dict,
    renumber_merged_pads,
    strip_schematic_to_physical,
    tie_renumbered_pads_to_gnd,
)
from diptrace_mcp.xml_document import DipTraceDocument

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schematic_xml(parts: str = "", nets: str = "") -> bytes:
    return (
        b'<Source Type="DipTrace-Schematic">'
        b"<Schematic>"
        b"<Components>" + parts.encode() + b"</Components>"
        b"<Nets>" + nets.encode() + b"</Nets>"
        b"</Schematic></Source>"
    )


def _part(refdes: str, component_id: str = "0") -> str:
    return (
        f'<Part Id="{component_id}">'
        f"<RefDes>{refdes}</RefDes>"
        f"<Value>10k</Value>"
        f'<Pattern Style="R0402"/>'
        f"</Part>"
    )


def _pcb_xml(has_settings: bool = True) -> bytes:
    settings = "<Settings/>" if has_settings else ""
    return (
        b'<Source Type="DipTrace-PCB">'
        b"<Board>"
        + settings.encode()
        + b"<BoardOutline><Points>"
        b'<Point X="0" Y="0"/><Point X="50" Y="0"/>'
        b'<Point X="50" Y="30"/><Point X="0" Y="30"/>'
        b"</Points></BoardOutline>"
        b"<Shapes/>"
        b"<Components/>"
        b"</Board></Source>"
    )


def _pcb_with_components_xml() -> bytes:
    return (
        b'<Source Type="DipTrace-PCB">'
        b"<Board>"
        b"<Settings/>"
        b"<BoardOutline><Points>"
        b'<Point X="0" Y="0"/><Point X="50" Y="0"/>'
        b'<Point X="50" Y="30"/><Point X="0" Y="30"/>'
        b"</Points></BoardOutline>"
        b"<Components>"
        b'<Component Id="1" RefDes="U1" X="10" Y="10"/>'
        b"</Components>"
        b"<Nets>"
        b'<Net Id="0"><Name>GND</Name><Pads/></Net>'
        b"</Nets>"
        b"<Shapes/>"
        b"</Board></Source>"
    )


# ---------------------------------------------------------------------------
# strip_schematic_to_physical
# ---------------------------------------------------------------------------

def test_strip_removes_power_symbols_by_prefix() -> None:
    parts = (
        _part("R1", "0")
        + _part("PSG1", "1")
        + _part("PWR1", "2")
        + _part("NPI1", "3")
        + _part("NPO1", "4")
    )
    nets = (
        '<Net Id="0"><Name>VCC</Name><Pins>'
        '<Item Part="0"/><Item Part="1"/>'
        '</Pins><Wires><Wire Id="0"/></Wires></Net>'
    )
    doc = DipTraceDocument.from_bytes(Path("s.dch"), _schematic_xml(parts, nets))
    result = strip_schematic_to_physical(doc)
    refdes_set = {
        p.findtext("./RefDes")
        for p in result.root.findall("./Schematic/Components/Part")
    }
    assert "R1" in refdes_set
    assert refdes_set & {"PSG1", "PWR1", "NPI1", "NPO1"} == set()


def test_strip_keep_refdes_filter() -> None:
    parts = _part("R1", "0") + _part("R2", "1") + _part("C1", "2")
    doc = DipTraceDocument.from_bytes(
        Path("s.dch"), _schematic_xml(parts)
    )
    result = strip_schematic_to_physical(doc, keep_refdes={"R1", "C1"})
    refdes_set = {
        p.findtext("./RefDes")
        for p in result.root.findall("./Schematic/Components/Part")
    }
    assert refdes_set == {"R1", "C1"}


def test_strip_cleans_net_pins_and_wires() -> None:
    parts = _part("R1", "0") + _part("PSG1", "1")
    nets = (
        '<Net Id="0"><Name>VCC</Name><Pins>'
        '<Item Part="0"/><Item Part="1"/>'
        '</Pins><Wires><Wire Id="0"/></Wires></Net>'
    )
    doc = DipTraceDocument.from_bytes(Path("s.dch"), _schematic_xml(parts, nets))
    result = strip_schematic_to_physical(doc)
    vcc_net = next(
        n for n in result.root.findall("./Schematic/Nets/Net")
        if n.findtext("./Name") == "VCC"
    )
    pin_items = vcc_net.findall("./Pins/Item")
    assert len(pin_items) == 1
    assert pin_items[0].get("Part") == "0"
    wires = vcc_net.findall("./Wires/Wire")
    assert len(wires) == 0


def test_strip_empty_schematic() -> None:
    doc = DipTraceDocument.from_bytes(Path("s.dch"), _schematic_xml(""))
    result = strip_schematic_to_physical(doc)
    assert result.root is not None


# ---------------------------------------------------------------------------
# renumber_merged_pads
# ---------------------------------------------------------------------------

def test_renumber_merged_pads() -> None:
    xml = (
        '<Source Type="DipTrace-PCB">'
        '<Library><Library>'
        '<PadStyles/><Patterns>'
        '<Pattern PatternStyle="SPECIAL">'
        '<Pads>'
        '<Pad><Number>1</Number></Pad>'
        '<Pad><Number>2</Number></Pad>'
        '<Pad><Number>6@</Number></Pad>'
        '<Pad><Number>6@</Number></Pad>'
        '</Pads>'
        '</Pattern>'
        '</Patterns></Library></Library>'
        '<Board><Settings/></Board>'
        '</Source>'
    )
    root = ET.fromstring(xml)
    renumber_merged_pads(root, "SPECIAL")
    pads = root.findall(".//Pattern[@PatternStyle='SPECIAL']/Pads/Pad")
    numbers = [p.findtext("./Number") for p in pads]
    assert numbers == ["1", "2", "3", "4"]


def test_renumber_no_matching_pattern() -> None:
    xml = (
        '<Source Type="DipTrace-PCB">'
        '<Library><Library>'
        '<PadStyles/><Patterns>'
        '<Pattern PatternStyle="OTHER">'
        '<Pads><Pad><Number>1</Number></Pad></Pads>'
        '</Pattern>'
        '</Patterns></Library></Library>'
        '<Board><Settings/></Board>'
        '</Source>'
    )
    root = ET.fromstring(xml)
    renumber_merged_pads(root, "SPECIAL")
    pads = root.findall(".//Pattern[@PatternStyle='OTHER']/Pads/Pad")
    assert pads[0].findtext("./Number") == "1"


def test_renumber_no_at_suffix() -> None:
    xml = (
        '<Source Type="DipTrace-PCB">'
        '<Library><Library>'
        '<PadStyles/><Patterns>'
        '<Pattern PatternStyle="SP">'
        '<Pads>'
        '<Pad><Number>1</Number></Pad>'
        '<Pad><Number>2</Number></Pad>'
        '</Pads>'
        '</Pattern>'
        '</Patterns></Library></Library>'
        '<Board><Settings/></Board>'
        '</Source>'
    )
    root = ET.fromstring(xml)
    renumber_merged_pads(root, "SP")
    pads = root.findall(".//Pattern[@PatternStyle='SP']/Pads/Pad")
    numbers = [p.findtext("./Number") for p in pads]
    assert numbers == ["1", "2"]


# ---------------------------------------------------------------------------
# tie_renumbered_pads_to_gnd
# ---------------------------------------------------------------------------

def test_tie_renumbered_pads_to_gnd() -> None:
    xml = (
        '<Source Type="DipTrace-PCB">'
        '<Board>'
        '<Settings/>'
        '<Components>'
        '<Component Id="42"><RefDes>J1</RefDes></Component>'
        '</Components>'
        '<Nets>'
        '<Net Id="0"><Name>GND</Name><Pads/></Net>'
        '</Nets>'
        '</Board>'
        '</Source>'
    )
    doc = DipTraceDocument.from_bytes(Path("p.dip"), xml.encode())
    result = tie_renumbered_pads_to_gnd(doc, "J1", ["7", "8"])
    gnd_net = next(
        n for n in result.root.findall(".//Nets/Net")
        if n.findtext("Name") == "GND"
    )
    items = gnd_net.findall("./Pads/Item")
    assert len(items) == 2
    assert items[0].get("Comp") == "42"
    assert items[0].get("Pad") == "7"
    assert items[1].get("Pad") == "8"


# ---------------------------------------------------------------------------
# make_intent
# ---------------------------------------------------------------------------

def test_make_intent_empty() -> None:
    intent = make_intent()
    assert intent.components == []
    assert intent.nets == []


def test_make_intent_ground_nets() -> None:
    intent = make_intent(ground_nets=["GND", "AGND"])
    assert len(intent.nets) == 2
    gnd = intent.nets[0]
    assert gnd.selector == "GND"
    assert "ground" in gnd.roles
    assert gnd.constraints.trace_width_mm == 0.5
    assert gnd.constraints.max_vias == 0


def test_make_intent_power_nets() -> None:
    intent = make_intent(power_nets=[("VCC", 1.0), ("3V3", 0.5)])
    assert len(intent.nets) == 2
    vcc = intent.nets[0]
    assert vcc.selector == "VCC"
    assert "power" in vcc.roles
    assert vcc.constraints.trace_width_mm == 1.0
    assert vcc.constraints.max_vias == 2


def test_make_intent_switching_and_analog() -> None:
    intent = make_intent(
        switching_nodes=["SW"], analog_nets=["AN1"],
    )
    assert len(intent.nets) == 2
    sw = intent.nets[0]
    assert "switching_node" in sw.roles
    assert sw.constraints.trace_width_mm == 0.45
    an = intent.nets[1]
    assert "analog" in an.roles
    assert an.constraints.trace_width_mm == 0.25


def test_make_intent_connectors() -> None:
    intent = make_intent(connectors=["J1", "J2"])
    assert len(intent.components) == 2
    assert intent.components[0].selector == "J1"
    assert intent.components[0].mechanical_anchor is True


# ---------------------------------------------------------------------------
# inject_route_keepout
# ---------------------------------------------------------------------------

def test_inject_route_keepout() -> None:
    doc = DipTraceDocument.from_bytes(Path("p.dip"), _pcb_xml())
    result = inject_route_keepout(doc, 1.0, 2.0, 3.0, 4.0)
    shape = result.root.find("./Board/Shapes/Shape")
    assert shape is not None
    assert shape.get("Type") == "Rectangle"
    assert shape.get("Layer") == "Route Keepout"
    pts = shape.findall("./Points/Point")
    assert len(pts) == 2
    assert pts[0].get("X") == "1"
    assert pts[1].get("Y") == "4"


def test_inject_route_keepout_no_board_raises() -> None:
    xml = b'<Source Type="DipTrace-PCB"><Library/></Source>'
    doc = DipTraceDocument.from_bytes(Path("p.dip"), xml)
    with pytest.raises(ValueError, match="no Board"):
        inject_route_keepout(doc, 0, 0, 1, 1)


def test_inject_route_keepout_custom_layer() -> None:
    doc = DipTraceDocument.from_bytes(Path("p.dip"), _pcb_xml())
    result = inject_route_keepout(
        doc, 0, 0, 5, 5, layer="Component Keepout"
    )
    shape = result.root.find("./Board/Shapes/Shape")
    assert shape is not None
    assert shape.get("Layer") == "Component Keepout"


# ---------------------------------------------------------------------------
# dump_stage
# ---------------------------------------------------------------------------

def test_dump_stage(tmp_path: Path) -> None:
    doc = DipTraceDocument.from_bytes(Path("p.dip"), _pcb_xml())
    stage_dir = tmp_path / "stage"
    result = dump_stage(doc, stage_dir, "step1")
    assert result.exists()
    assert result.name == "step1.dipxml"
    assert result.read_bytes() == doc.raw_bytes


def test_dump_stage_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = DipTraceDocument.from_bytes(Path("p.dip"), _pcb_xml())
    env_dir = tmp_path / "env_stage"
    monkeypatch.setenv("ATTINY_STAGE_DIR", str(env_dir))
    result = dump_stage(doc, tmp_path / "unused", "step2")
    assert result.parent == env_dir
    assert result.name == "step2.dipxml"


# ---------------------------------------------------------------------------
# inject_markings_preset
# ---------------------------------------------------------------------------

def test_inject_markings_preset() -> None:
    doc = DipTraceDocument.from_bytes(Path("p.dip"), _pcb_xml())
    result = inject_markings_preset(
        doc, silk_align="Center", font_mm="1.5"
    )
    markings = result.root.find("./Board/Settings/Markings")
    assert markings is not None
    assert markings.findtext("./CompRotate") == "N"
    assert markings.findtext("./FontVector") == "Y"
    assert markings.findtext("./FontSize") == "1.5"
    refdes = markings.find("./RefDesGlobal")
    assert refdes is not None
    assert refdes.get("SilkAlign") == "Center"


def test_inject_markings_preset_no_settings_raises() -> None:
    xml = b'<Source Type="DipTrace-PCB"><Board><Shapes/></Board></Source>'
    doc = DipTraceDocument.from_bytes(Path("p.dip"), xml)
    with pytest.raises(ValueError, match="no Board/Settings"):
        inject_markings_preset(doc)


def test_inject_markings_preset_empty_font() -> None:
    doc = DipTraceDocument.from_bytes(Path("p.dip"), _pcb_xml())
    result = inject_markings_preset(doc, silk_align="", font_mm="")
    markings = result.root.find("./Board/Settings/Markings")
    assert markings is not None
    assert markings.find("./FontVector") is None
    assert markings.find("./RefDesGlobal") is None


# ---------------------------------------------------------------------------
# placement_from_dict
# ---------------------------------------------------------------------------

def test_placement_from_dict_basic() -> None:
    result = placement_from_dict({"R1": (1.0, 2.0), "C1": (3.0, 4.0)})
    assert result["R1"] == {"x": 1.0, "y": 2.0, "rot": 0.0}
    assert result["C1"] == {"x": 3.0, "y": 4.0, "rot": 0.0}


def test_placement_from_dict_with_rotations() -> None:
    result = placement_from_dict(
        {"U1": (10.0, 20.0)}, rotations={"U1": 90.0}
    )
    assert result["U1"]["rot"] == 90.0


def test_placement_from_dict_empty() -> None:
    result = placement_from_dict({})
    assert result == {}
