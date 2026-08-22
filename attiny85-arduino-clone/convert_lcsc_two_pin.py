#!/usr/bin/env python3
"""Convert the downloaded two-pin LCSC/EasyEDA parts to DipTrace XML libraries."""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCALE_MM = 0.254
PARTS = {
    "C163461": ("RC0402FR-07511KL", "R", "511k"),
    "C4147": ("0402WGF9102TCE", "R", "91k"),
    "C18221164": ("XFL4015-471MEC", "L", "0.47uH"),
}


def add(parent: ET.Element, tag: str, text: str | None = None, **attrs: object) -> ET.Element:
    node = ET.SubElement(parent, tag, {key.rstrip("_"): str(value) for key, value in attrs.items()})
    node.text = text
    return node


def mm(value: float) -> str:
    return f"{value * SCALE_MM:.6f}".rstrip("0").rstrip(".")


def convert(lcsc: str, mpn: str, refdes: str, value: str) -> Path:
    source = ROOT / "vendor" / f"{lcsc}.json"
    target = ROOT / "vendor" / f"{lcsc}.elixml"
    result = json.loads(source.read_text(encoding="utf-8"))["result"]
    data = result["dataStr"]
    catalog = data["head"]["c_para"]
    package = result["packageDetail"]
    assert result["title"] == catalog["Manufacturer Part"] == mpn
    assert catalog["Supplier Part"] == lcsc

    bbox = data["BBox"]
    center_x = float(bbox["x"]) + float(bbox["width"]) / 2
    center_y = float(bbox["y"]) + float(bbox["height"]) / 2
    pin_re = re.compile(r"^P~show~\d+~(\d+)~([\d.-]+)~([\d.-]+)~")
    wire_re = re.compile(r"M\s*([\d.-]+)\s+([\d.-]+)\s+h\s*([\d.-]+)")
    pins: list[tuple[int, float, float, float]] = []
    for raw in data["shape"]:
        match = pin_re.match(raw)
        if not match:
            continue
        number, outer_x, y = int(match[1]), float(match[2]), float(match[3])
        wire = wire_re.search(raw)
        assert wire
        start_x, dx = float(wire[1]), float(wire[3])
        endpoints = (start_x, start_x + dx)
        body_x = min(endpoints, key=lambda candidate: abs(candidate - center_x))
        pins.append((number, outer_x, y, body_x))
    pins.sort()
    assert [pin[0] for pin in pins] == [1, 2]

    library = ET.Element(
        "Library",
        Type="DipTrace-ComponentLibrary",
        Name=f"LCSC {lcsc}",
        Hint="Converted from downloaded read-only LCSC/EasyEDA catalog data",
        Version="5.3.0.3",
        Units="mm",
    )
    pattern_library = add(library, "Library", Type="DipTrace-PatternLibrary", Units="mm")
    pad_styles = add(pattern_library, "PadStyles")
    patterns = add(pattern_library, "Patterns")

    package_data = package["dataStr"]
    pad_records: list[tuple[int, float, float, float, float, float]] = []
    for raw in package_data["shape"]:
        tokens = raw.split("~")
        if tokens[0] == "PAD":
            assert tokens[1] == "RECT" and tokens[6] == "1"
            pad_records.append(
                (
                    int(tokens[8]),
                    float(tokens[2]),
                    float(tokens[3]),
                    float(tokens[4]),
                    float(tokens[5]),
                    float(tokens[11]),
                )
            )
    pad_records.sort()
    assert [pad[0] for pad in pad_records] == [1, 2]
    style_for_size: dict[tuple[float, float], str] = {}
    for _number, _x, _y, width, height, _angle in pad_records:
        size = (width, height)
        if size in style_for_size:
            continue
        style = f"{lcsc}_PAD_{len(style_for_size)}"
        style_for_size[size] = style
        pad_style = add(pad_styles, "PadStyle", Name=style, Type="Surface")
        add(
            pad_style,
            "MainStack",
            Shape="Rectangle",
            Width=mm(width),
            Height=mm(height),
            Corner="0",
        )
        terminals = add(pad_style, "Terminals")
        add(
            terminals,
            "Terminal",
            Shape="Rectangle",
            X="0",
            Y="0",
            Angle="0",
            Width=mm(width),
            Height=mm(height),
            Corner="0",
        )

    package_bbox = package_data["BBox"]
    pattern = add(
        patterns,
        "Pattern",
        PatternStyle=f"{lcsc}_PATTERN",
        Id="0",
        Mounting="SMD",
        Width=mm(float(package_bbox["width"])),
        Height=mm(float(package_bbox["height"])),
        Orientation="0",
        LockTypeChange="Y",
        Type="LCSC",
    )
    add(pattern, "Name", package["title"])
    add(pattern, "Name_Description", f"LCSC/EasyEDA footprint {lcsc}")
    add(pattern, "Name_Unique", package["title"])
    add(pattern, "Manufacturer", catalog["Manufacturer"])
    add(pattern, "Origin", X="0", Y="0", Cross="Y", Circle="Y", Common="Hide", Courtyard="Show")
    add(pattern, "DefPad", Style=next(iter(style_for_size.values())))
    pads = add(pattern, "Pads")
    footprint_center_x = float(package_data["head"]["x"])
    footprint_center_y = float(package_data["head"]["y"])
    for number, x, y, width, height, angle in pad_records:
        pad = add(
            pads,
            "Pad",
            Id=str(number),
            Style=style_for_size[(width, height)],
            X=mm(x - footprint_center_x),
            Y=mm(footprint_center_y - y),
            Angle=f"{math.radians(angle):.6f}",
            Locked="N",
            Side="Top",
        )
        add(pad, "Number", str(number))
    pattern_shapes = add(pattern, "Shapes")
    for shape_id, layer in enumerate(("Top Outline", "Top Courtyard")):
        shape = add(
            pattern_shapes,
            "Shape",
            Id=str(shape_id),
            Type="Rectangle",
            Locked="N",
            Layer=layer,
            LineWidth="0.05",
            AllLayers="N",
        )
        points = add(shape, "Points")
        add(
            points,
            "Point",
            X=mm(-float(package_bbox["width"]) / 2),
            Y=mm(float(package_bbox["height"]) / 2),
        )
        add(
            points,
            "Point",
            X=mm(float(package_bbox["width"]) / 2),
            Y=mm(-float(package_bbox["height"]) / 2),
        )

    components = add(library, "Components")
    component = add(components, "Component", Id="0", ComponentStyle=lcsc)
    graphic_x: list[float] = []
    graphic_y: list[float] = []
    for raw in data["shape"]:
        tokens = raw.split("~")
        if tokens[0] == "R":
            x, y, width, height = map(float, (tokens[1], tokens[2], tokens[5], tokens[6]))
            graphic_x.extend((x, x + width))
            graphic_y.extend((y, y + height))
        elif raw.startswith("A~"):
            arc = re.search(
                r"M\s*([\d.-]+)\s+([\d.-]+)\s+A\s*([\d.-]+)\s+([\d.-]+).*?([\d.-]+)\s+([\d.-]+)~",
                raw,
            )
            assert arc
            x1, y1, rx, ry, x2, y2 = map(float, arc.groups())
            graphic_x.extend((x1, x2))
            graphic_y.extend((y1 - ry, y1 + ry, y2))
    assert graphic_x and graphic_y
    part = add(
        component,
        "Part",
        Id="0",
        RefDes=refdes,
        PartType="Normal",
        Type="2 Pins",
        Width=mm(max(graphic_x) - min(graphic_x)),
        Height=mm(max(graphic_y) - min(graphic_y)),
        LockTypeChange="Y",
    )
    add(part, "Pattern", Style=f"{lcsc}_PATTERN")
    add(part, "Name", mpn)
    add(part, "PartName", "Part 1")
    add(part, "Origin", X="0", Y="0")
    add(part, "Datasheet", catalog.get("link", ""))
    add(part, "Manufacturer", catalog["Manufacturer"])
    part_pins = add(part, "Pins")
    for pin_id, (number, outer_x, y, body_x) in enumerate(pins):
        left = outer_x < center_x
        pin = add(
            part_pins,
            "Pin",
            Id=str(pin_id),
            X=mm(body_x - center_x),
            Y=mm(center_y - y),
            Locked="N",
            Type="Default",
            ElectricType="Passive",
            Orientation="0" if left else "180",
            PadId=str(number),
            Length=mm(abs(outer_x - body_x)),
            ShowName="N",
            NumXShift="0",
            NumYShift="0",
            NameXShift="0",
            NameYShift="0",
            SignalDelay="0",
            NumOrientation="0",
            NameOrientation="0",
        )
        add(pin, "Name", str(number))
        add(pin, "PadNumber", str(number))
        add(pin, "NameFont", Size="5", FontSizeFloat="5", Width="-2", Scale="1", FontMono="N")
    symbol_shapes = add(part, "Shapes")
    shape_id = 0
    for raw in data["shape"]:
        tokens = raw.split("~")
        if tokens[0] == "R":
            x, y, width, height = map(float, (tokens[1], tokens[2], tokens[5], tokens[6]))
            shape = add(
                symbol_shapes, "Shape", Id=str(shape_id), Type="Rectangle", LineWidth="0.25"
            )
            points = add(shape, "Points")
            add(points, "Point", X=mm(x - center_x), Y=mm(center_y - y))
            add(points, "Point", X=mm(x + width - center_x), Y=mm(center_y - y - height))
            shape_id += 1
        elif raw.startswith("A~"):
            arc = re.search(
                r"M\s*([\d.-]+)\s+([\d.-]+)\s+A\s*([\d.-]+)\s+([\d.-]+).*?([\d.-]+)\s+([\d.-]+)~",
                raw,
            )
            assert arc
            x1, y1, _rx, ry, x2, y2 = map(float, arc.groups())
            shape = add(symbol_shapes, "Shape", Id=str(shape_id), Type="Arc", LineWidth="0.25")
            points = add(shape, "Points")
            add(points, "Point", X=mm(x1 - center_x), Y=mm(center_y - y1))
            add(points, "Point", X=mm((x1 + x2) / 2 - center_x), Y=mm(center_y - (y1 - ry)))
            add(points, "Point", X=mm(x2 - center_x), Y=mm(center_y - y2))
            shape_id += 1
    extra = add(part, "AddFields")
    for key, text in (
        ("MPN", mpn),
        ("LCSC", lcsc),
        ("EasyEDA UUID", result["uuid"]),
        ("EasyEDA Package UUID", package["uuid"]),
        ("Source", "LCSC/EasyEDA downloaded catalog data"),
    ):
        field = add(extra, "AddField", Type="Text")
        add(field, "Name", key)
        add(field, "Text", text)
    ET.indent(library, space="  ")
    target.write_bytes(ET.tostring(library, encoding="utf-8", xml_declaration=True))
    return target


if __name__ == "__main__":
    for part_id, properties in PARTS.items():
        print(convert(part_id, *properties))
