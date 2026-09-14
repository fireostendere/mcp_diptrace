"""Tests for diptrace_mcp.schematic_wiring module."""

from __future__ import annotations

import math
from pathlib import Path

from diptrace_mcp.schematic_wiring import (
    SchematicWireBuilder,
    WireSpec,
    _transform_local,
    compute_body_boxes,
    compute_endpoints,
)
from diptrace_mcp.xml_document import DipTraceDocument

# ---------------------------------------------------------------------------
# Minimal schematic XML with two resistors
# ---------------------------------------------------------------------------

_RESISTOR_STYLE = (
    '<Component ComponentStyle="R">'
    '<Part Id="0" RefDes="R" Width="10" Height="4">'
    '<Name>Resistor</Name>'
    '<Pins>'
    '<Pin Id="0" X="-2.5" Y="0" Orientation="0" Length="2.5"/>'
    '<Pin Id="1" X="2.5" Y="0" Orientation="180" Length="2.5"/>'
    '</Pins>'
    '</Part>'
    '</Component>'
)


def _doc(
    *,
    r1_x: float = 10.0,
    r1_y: float = 20.0,
    r2_x: float = 30.0,
    r2_y: float = 20.0,
    angle: float = 0.0,
) -> DipTraceDocument:
    r1_pin0_net = "VCC"
    r1_pin1_net = "SIG"
    r2_pin1_net = "GND"
    angle_attr = f' Angle="{angle}"' if angle else ""
    xml = (
        '<Source Type="DipTrace-Schematic">'
        "<Library>"
        "<Components>" + _RESISTOR_STYLE + "</Components>"
        "</Library>"
        "<Schematic>"
        "<Components>"
        f'<Part Id="1" ComponentStyle="R" Sheet="0"'
        f' X="{r1_x}" Y="{r1_y}"{angle_attr}>'
        "<RefDes>R1</RefDes>"
        f'<Pins><Pin NetId="0"/><Pin NetId="1"/></Pins>'
        "</Part>"
        f'<Part Id="2" ComponentStyle="R" Sheet="0"'
        f' X="{r2_x}" Y="{r2_y}"{angle_attr}>'
        "<RefDes>R2</RefDes>"
        f'<Pins><Pin NetId="1"/><Pin NetId="2"/></Pins>'
        "</Part>"
        "</Components>"
        "<Nets>"
        f'<Net Id="0"><Name>{r1_pin0_net}</Name></Net>'
        f'<Net Id="1"><Name>{r1_pin1_net}</Name><Wires/></Net>'
        f'<Net Id="2"><Name>{r2_pin1_net}</Name></Net>'
        "</Nets>"
        "</Schematic>"
        "</Source>"
    )
    return DipTraceDocument.from_bytes(Path("test.dch"), xml.encode())


# ---------------------------------------------------------------------------
# _transform_local
# ---------------------------------------------------------------------------

def test_transform_local_no_rotation() -> None:
    doc = _doc()
    part = doc.root.findall("./Schematic/Components/Part")[0]
    part.set("Angle", "0")
    result = _transform_local(part, 3.0, 4.0)
    assert math.isclose(result[0], 3.0, abs_tol=1e-9)
    assert math.isclose(result[1], 4.0, abs_tol=1e-9)


def test_transform_local_90_degrees() -> None:
    xml = (
        '<Source Type="DipTrace-Schematic">'
        '<Library><Components/></Library>'
        '<Schematic><Components>'
        '<Part Id="0" X="0" Y="0" Angle="90">'
        '<RefDes>U1</RefDes><Pins/></Part>'
        '</Components></Schematic></Source>'
    )
    doc = DipTraceDocument.from_bytes(Path("t.dch"), xml.encode())
    part = doc.root.findall("./Schematic/Components/Part")[0]
    result = _transform_local(part, 1.0, 0.0)
    assert math.isclose(result[0], 0.0, abs_tol=1e-9)
    assert math.isclose(result[1], 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# compute_endpoints
# ---------------------------------------------------------------------------

def test_compute_endpoints_basic() -> None:
    doc = _doc()
    eps = compute_endpoints(doc)
    assert "SIG" in eps
    sig_eps = eps["SIG"]
    assert len(sig_eps) == 2
    r1_pin1 = next(
        e for e in sig_eps if e.refdes == "R1" and e.pin == 1
    )
    r2_pin0 = next(
        e for e in sig_eps if e.refdes == "R2" and e.pin == 0
    )
    assert math.isclose(r1_pin1.x, 15.0, abs_tol=0.01)
    assert math.isclose(r1_pin1.y, 20.0, abs_tol=0.01)
    assert math.isclose(r2_pin0.x, 25.0, abs_tol=0.01)
    assert math.isclose(r2_pin0.y, 20.0, abs_tol=0.01)


def test_compute_endpoints_empty_schematic() -> None:
    xml = (
        '<Source Type="DipTrace-Schematic">'
        '<Library><Components/></Library>'
        '<Schematic><Components/>'
        '<Nets><Net Id="0"><Name>NET0</Name></Net></Nets>'
        '</Schematic></Source>'
    )
    doc = DipTraceDocument.from_bytes(Path("e.dch"), xml.encode())
    eps = compute_endpoints(doc)
    assert "NET0" in eps
    assert eps["NET0"] == []


def test_compute_endpoints_missing_style() -> None:
    """Part with no matching ComponentStyle is skipped."""
    xml = (
        '<Source Type="DipTrace-Schematic">'
        '<Library><Components/></Library>'
        '<Schematic><Components>'
        '<Part Id="99" ComponentStyle="NonExistent" X="5" Y="5">'
        '<RefDes>U99</RefDes>'
        '<Pins><Pin NetId="0"/></Pins>'
        '</Part>'
        '</Components>'
        '<Nets><Net Id="0"><Name>VCC</Name></Net></Nets>'
        '</Schematic></Source>'
    )
    doc = DipTraceDocument.from_bytes(Path("m.dch"), xml.encode())
    eps = compute_endpoints(doc)
    assert "VCC" in eps
    assert eps["VCC"] == []


# ---------------------------------------------------------------------------
# compute_body_boxes
# ---------------------------------------------------------------------------

def test_compute_body_boxes_basic() -> None:
    doc = _doc()
    boxes = compute_body_boxes(doc)
    assert "R1" in boxes
    assert "R2" in boxes
    sheet, x0, y0, x1, y1 = boxes["R1"]
    assert sheet == 0
    assert math.isclose(x0, 5.0, abs_tol=0.1)
    assert math.isclose(y0, 18.0, abs_tol=0.1)
    assert math.isclose(x1, 15.0, abs_tol=0.1)
    assert math.isclose(y1, 22.0, abs_tol=0.1)


def test_compute_body_boxes_missing_style() -> None:
    xml = (
        '<Source Type="DipTrace-Schematic">'
        '<Library><Components/></Library>'
        '<Schematic><Components>'
        '<Part Id="1" ComponentStyle="Missing" X="0" Y="0">'
        '<RefDes>U1</RefDes><Pins/></Part>'
        '</Components><Nets/></Schematic></Source>'
    )
    doc = DipTraceDocument.from_bytes(Path("b.dch"), xml.encode())
    boxes = compute_body_boxes(doc)
    assert boxes == {}


# ---------------------------------------------------------------------------
# SchematicWireBuilder
# ---------------------------------------------------------------------------

def test_wire_builder_creates_spec() -> None:
    doc = _doc()
    wb = SchematicWireBuilder(doc)
    spec = wb.wire("SIG", ("R1", 1), ("R2", 0))
    assert isinstance(spec, WireSpec)
    assert spec.net == "SIG"
    assert spec.sheet == 0
    assert spec.start_refdes == "R1"
    assert spec.start_pin == 1
    assert spec.end_refdes == "R2"
    assert spec.end_pin == 0
    assert len(spec.points) >= 2
    assert math.isclose(spec.points[0][0], 15.0, abs_tol=0.1)
    assert math.isclose(spec.points[-1][0], 25.0, abs_tol=0.1)


def test_wire_builder_auto_chain() -> None:
    doc = _doc()
    wb = SchematicWireBuilder(doc)
    count = wb.auto_chain("SIG", max_len=40.0)
    assert count == 1
    assert len(wb._specs) == 1
    spec = wb._specs[0][1]
    assert spec.start_refdes in ("R1", "R2")
    assert spec.end_refdes in ("R1", "R2")


def test_wire_builder_auto_chain_too_few() -> None:
    xml = (
        '<Source Type="DipTrace-Schematic">'
        "<Library><Components>" + _RESISTOR_STYLE + "</Components></Library>"
        "<Schematic><Components>"
        '<Part Id="1" ComponentStyle="R" Sheet="0" X="0" Y="0">'
        "<RefDes>R1</RefDes>"
        '<Pins><Pin NetId="0"/><Pin NetId="1"/></Pins>'
        "</Part>"
        "</Components>"
        '<Nets><Net Id="0"><Name>VCC</Name></Net>'
        '<Net Id="1"><Name>SIG</Name></Net></Nets>'
        "</Schematic></Source>"
    )
    doc = DipTraceDocument.from_bytes(Path("one.dch"), xml.encode())
    wb = SchematicWireBuilder(doc)
    count = wb.auto_chain("SIG")
    assert count == 0


def test_wire_builder_auto_chain_beyond_max_len() -> None:
    doc = _doc(r1_x=0.0, r2_x=200.0)
    wb = SchematicWireBuilder(doc)
    count = wb.auto_chain("SIG", max_len=5.0)
    assert count == 0


def test_wire_builder_commit_writes_wires() -> None:
    doc = _doc()
    wb = SchematicWireBuilder(doc)
    wb.wire("SIG", ("R1", 1), ("R2", 0))
    new_doc = wb.commit()
    assert isinstance(new_doc, DipTraceDocument)
    sig_net = next(
        n for n in new_doc.root.findall("./Schematic/Nets/Net")
        if n.findtext("./Name") == "SIG"
    )
    wires = sig_net.findall("./Wires/Wire")
    assert len(wires) == 1
    w = wires[0]
    assert w.get("Connected1") == "Pin"
    assert w.get("Connected2") == "Pin"
    pts = w.findall("./Points/Point")
    assert len(pts) >= 2
    assert pts[0].get("Dir") == "-1"


def test_wire_builder_commit_skips_missing_net() -> None:
    doc = _doc()
    wb = SchematicWireBuilder(doc)
    wb._specs.append(
        ("NONEXISTENT", WireSpec(
            net="NONEXISTENT", sheet=0,
            start_refdes="R1", start_pin=0,
            end_refdes="R2", end_pin=0,
            points=((0.0, 0.0), (1.0, 1.0)),
        ))
    )
    new_doc = wb.commit()
    nets = [
        n for n in new_doc.root.findall("./Schematic/Nets/Net")
        if n.findtext("./Name") == "NONEXISTENT"
    ]
    assert nets == []


def test_wire_builder_commit_free_endpoints() -> None:
    doc = _doc()
    wb = SchematicWireBuilder(doc)
    wb._specs.append(
        ("SIG", WireSpec(
            net="SIG", sheet=0,
            start_refdes=None, start_pin=None,
            end_refdes=None, end_pin=None,
            points=((1.0, 2.0), (3.0, 4.0)),
        ))
    )
    new_doc = wb.commit()
    sig_net = next(
        n for n in new_doc.root.findall("./Schematic/Nets/Net")
        if n.findtext("./Name") == "SIG"
    )
    free_wires = [
        w for w in sig_net.findall("./Wires/Wire")
        if w.get("Connected1") == "Free" and w.get("Connected2") == "Free"
    ]
    assert len(free_wires) == 1
