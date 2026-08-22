#!/usr/bin/env python3
"""Convert the downloaded LCSC/EasyEDA C2845237 symbol and footprint to DipTrace XML."""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "vendor" / "C2845237.json"
TARGET = ROOT / "vendor" / "C2845237.elixml"
SCALE_MM = 0.254


def add(parent: ET.Element, tag: str, text: str | None = None, **attrs: object) -> ET.Element:
    node = ET.SubElement(parent, tag, {key.rstrip("_"): str(value) for key, value in attrs.items()})
    node.text = text
    return node


def mm(value: float) -> str:
    return f"{value * SCALE_MM:.6f}".rstrip("0").rstrip(".")


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    result = payload["result"]
    data = result["dataStr"]
    fields = data["head"]["c_para"]
    package = result["packageDetail"]
    assert result["title"] == fields["Manufacturer Part"] == "TPS63802DLAR"
    assert fields["Supplier Part"] == "C2845237"
    assert package["title"] == "VSON-10_L3.0-W2.0-P0.50-TL"

    shapes = data["shape"]
    rectangle = next(item for item in shapes if item.startswith("R~")).split("~")
    body_x, body_y, body_w, body_h = map(
        float, (rectangle[1], rectangle[2], rectangle[5], rectangle[6])
    )
    center_x, center_y = body_x + body_w / 2, body_y + body_h / 2

    pin_re = re.compile(r"^P~show~0~(\d+)~([\d.]+)~([\d.]+)~")
    pins: list[tuple[int, str, float, float]] = []
    for raw in shapes:
        match = pin_re.match(raw)
        if not match:
            continue
        number, pin_x, pin_y = int(match[1]), float(match[2]), float(match[3])
        labels = []
        for section in raw.split("^^")[1:]:
            tokens = section.split("~")
            if len(tokens) > 4 and tokens[0] == "1" and not tokens[4].isdigit():
                labels.append(tokens[4])
        assert len(labels) == 1
        pins.append((number, labels[0], pin_x, pin_y))
    pins.sort()
    assert [(number, name) for number, name, *_ in pins] == [
        (1, "EN"),
        (2, "MODE"),
        (3, "AGND"),
        (4, "FB"),
        (5, "PG"),
        (6, "VOUT"),
        (7, "L2"),
        (8, "GND"),
        (9, "L1"),
        (10, "VIN"),
    ]

    library = ET.Element(
        "Library",
        Type="DipTrace-ComponentLibrary",
        Name="LCSC C2845237",
        Hint="Converted from the downloaded read-only LCSC/EasyEDA component",
        Version="5.3.0.3",
        Units="mm",
    )
    pattern_library = add(library, "Library", Type="DipTrace-PatternLibrary", Units="mm")
    pad_styles = add(pattern_library, "PadStyles")
    patterns = add(pattern_library, "Patterns")

    package_shapes = package["dataStr"]["shape"]
    pad_records: list[tuple[int, float, float, float, float, float]] = []
    for raw in package_shapes:
        tokens = raw.split("~")
        if tokens[0] != "PAD":
            continue
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
    assert [item[0] for item in pad_records] == list(range(1, 11))

    style_for_size: dict[tuple[float, float], str] = {}
    for _number, _x, _y, width, height, _angle in pad_records:
        size = (width, height)
        if size in style_for_size:
            continue
        style = f"C2845237_PAD_{len(style_for_size)}"
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

    bbox = package["dataStr"]["BBox"]
    pattern = add(
        patterns,
        "Pattern",
        PatternStyle="C2845237_PATTERN",
        Id="0",
        Mounting="SMD",
        Width=mm(float(bbox["width"])),
        Height=mm(float(bbox["height"])),
        Orientation="0",
        LockTypeChange="Y",
        Type="LCSC",
    )
    add(pattern, "Name", package["title"])
    add(pattern, "Name_Description", "LCSC/EasyEDA footprint C2845237")
    add(pattern, "Name_Unique", package["title"])
    add(pattern, "Manufacturer", "Texas Instruments")
    add(pattern, "Origin", X="0", Y="0", Cross="Y", Circle="Y", Common="Hide", Courtyard="Show")
    add(pattern, "DefPad", Style=next(iter(style_for_size.values())))
    pads = add(pattern, "Pads")
    footprint_center_x = float(package["dataStr"]["head"]["x"])
    footprint_center_y = float(package["dataStr"]["head"]["y"])
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
    shape_id = 0
    body = add(
        pattern_shapes,
        "Shape",
        Id=str(shape_id),
        Type="Rectangle",
        Locked="N",
        Layer="Top Outline",
        LineWidth="0.05",
        AllLayers="N",
    )
    shape_id += 1
    points = add(body, "Points")
    add(points, "Point", X="-1", Y="1.5")
    add(points, "Point", X="1", Y="-1.5")
    for raw in package_shapes:
        tokens = raw.split("~")
        if tokens[0] != "TRACK" or tokens[2] != "3":
            continue
        coords = [float(value) for value in tokens[4].split()]
        silk = add(
            pattern_shapes,
            "Shape",
            Id=str(shape_id),
            Type="Polyline",
            Locked="N",
            Layer="Top Silk",
            LineWidth=mm(float(tokens[1])),
            AllLayers="N",
        )
        shape_id += 1
        points = add(silk, "Points")
        for x, y in zip(coords[::2], coords[1::2], strict=True):
            add(points, "Point", X=mm(x - footprint_center_x), Y=mm(footprint_center_y - y))
    courtyard = add(
        pattern_shapes,
        "Shape",
        Id=str(shape_id),
        Type="Rectangle",
        Locked="N",
        Layer="Top Courtyard",
        LineWidth="0.05",
        AllLayers="N",
    )
    points = add(courtyard, "Points")
    add(points, "Point", X=mm(-float(bbox["width"]) / 2), Y=mm(float(bbox["height"]) / 2))
    add(points, "Point", X=mm(float(bbox["width"]) / 2), Y=mm(-float(bbox["height"]) / 2))

    components = add(library, "Components")
    component = add(components, "Component", Id="0", ComponentStyle="C2845237")
    part = add(
        component,
        "Part",
        Id="0",
        RefDes="U",
        PartType="Normal",
        Type="IC-2 Sides",
        Width=mm(body_w),
        Height=mm(body_h),
        LockTypeChange="Y",
    )
    add(part, "Pattern", Style="C2845237_PATTERN")
    add(part, "Name", "TPS63802DLAR")
    add(part, "PartName", "Part 1")
    add(part, "Origin", X="0", Y="0")
    add(part, "Datasheet", "https://www.ti.com/lit/ds/symlink/tps63802.pdf")
    add(part, "Manufacturer", "Texas Instruments")
    diptrace_pins = add(part, "Pins")
    electric = {
        "EN": "Input",
        "MODE": "Input",
        "AGND": "Power",
        "FB": "Input",
        "PG": "Output",
        "VOUT": "Power",
        "L2": "Passive",
        "GND": "Power",
        "L1": "Passive",
        "VIN": "Power",
    }
    for pin_id, (number, name, x, y) in enumerate(pins):
        left = x < center_x
        pin = add(
            diptrace_pins,
            "Pin",
            Id=str(pin_id),
            X=mm((body_x if left else body_x + body_w) - center_x),
            Y=mm(center_y - y),
            Locked="N",
            Type="Default",
            ElectricType=electric[name],
            Orientation="0" if left else "180",
            PadId=str(number),
            Length=mm(abs(x - (body_x if left else body_x + body_w))),
            ShowName="Y",
            NumXShift="0",
            NumYShift="0",
            NameXShift="0",
            NameYShift="0",
            SignalDelay="0",
            NumOrientation="0",
            NameOrientation="0",
        )
        add(pin, "Name", name)
        add(pin, "PadNumber", str(number))
        add(pin, "NameFont", Size="5", FontSizeFloat="5", Width="-2", Scale="1", FontMono="N")
    symbol_shapes = add(part, "Shapes")
    symbol = add(symbol_shapes, "Shape", Id="0", Type="Rectangle", LineWidth="0.25")
    points = add(symbol, "Points")
    add(points, "Point", X=mm(-body_w / 2), Y=mm(body_h / 2))
    add(points, "Point", X=mm(body_w / 2), Y=mm(-body_h / 2))
    extra = add(part, "AddFields")
    for key, value in (
        ("MPN", "TPS63802DLAR"),
        ("LCSC", "C2845237"),
        ("EasyEDA UUID", result["uuid"]),
        ("EasyEDA Package UUID", package["uuid"]),
        ("Source", "LCSC/EasyEDA downloaded catalog data"),
    ):
        field = add(extra, "AddField", Type="Text")
        add(field, "Name", key)
        add(field, "Text", value)

    ET.indent(library, space="  ")
    TARGET.write_bytes(ET.tostring(library, encoding="utf-8", xml_declaration=True))
    print(TARGET)


if __name__ == "__main__":
    main()
