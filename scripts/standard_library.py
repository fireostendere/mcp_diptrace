#!/usr/bin/env python3
"""Hand-authored standard-library parts (0603/0805 passives, 2.54 mm headers).

Land patterns follow common JLC/IPC-suggested geometries:
- 0603: pads 0.85 x 0.92 mm at x = +/-0.475 mm... use +/-0.5 mm centres,
- 0805: pads 1.0 x 1.15 mm at +/-0.85 mm,
- 2.54 mm pin header: hole 1.0 mm, pad 1.8 mm circle.
Values are instance-level (schematic Part Value), so one style per footprint.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def _mm(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def _pad_style(parent: ET.Element, name: str, w: float, h: float) -> None:
    ps = parent.find("PadStyles")
    assert ps is not None
    st = ET.SubElement(ps, "PadStyle", {"Name": name, "Type": "Surface"})
    ET.SubElement(st, "MainStack", {"Shape": "Rectangle", "Width": _mm(w), "Height": _mm(h), "Corner": "0"})
    ET.SubElement(st, "MaskPaste", {"TopMask": "Open", "BotMask": "Common", "TopPaste": "Common", "BotPaste": "Common"})


def _th_pad_style(parent: ET.Element, name: str, pad_mm: float, hole_mm: float) -> None:
    ps = parent.find("PadStyles")
    st = ET.SubElement(ps, "PadStyle", {"Name": name, "Type": "Through", "Side": "Top"})
    ET.SubElement(st, "MainStack", {"Shape": "Circle", "Width": _mm(pad_mm), "Height": _mm(pad_mm)})
    ET.SubElement(st, "Hole", {"Type": "Drill", "Width": _mm(hole_mm), "Height": _mm(hole_mm)})
    ET.SubElement(st, "MaskPaste", {"TopMask": "Open", "BotMask": "Common", "TopPaste": "Common", "BotPaste": "Common"})


def _pattern(parent: ET.Element, style: str, name: str, width: float, height: float) -> ET.Element:
    pats = parent.find("Patterns")
    pat = ET.SubElement(pats, "Pattern", {"PatternStyle": style, "Id": str(len(pats)), "Mounting": "SMD", "Width": _mm(width), "Height": _mm(height), "Orientation": "0", "LockTypeChange": "Y", "Type": "Standard"})
    ET.SubElement(pat, "Name").text = name
    ET.SubElement(pat, "Name_Description").text = f"Hand-drawn {name} (standard land pattern)"
    ET.SubElement(pat, "Name_Unique").text = style
    ET.SubElement(pat, "Origin", {"X": "0", "Y": "0"})
    return pat


def _add_pads(pat: ET.Element, numbers_xy_style: list[tuple[str, str, float, float]], angle: float = 0.0) -> None:
    pads = ET.SubElement(pat, "Pads")
    for index, (num, style, x, y) in enumerate(numbers_xy_style):
        pad = ET.SubElement(pads, "Pad", {"Id": str(index + 100), "Style": style, "X": _mm(x), "Y": _mm(y), "Angle": str(angle), "Locked": "N", "Side": "Top"})
        ET.SubElement(pad, "Number").text = num


def _rect_shapes(pat: ET.Element, outline: tuple[float, float, float, float], courtyard: tuple[float, float, float, float]) -> None:
    sh = ET.SubElement(pat, "Shapes")
    o = ET.SubElement(sh, "Shape", {"Id": "0", "Type": "Rectangle", "Locked": "N", "Layer": "Top Outline", "LineWidth": "0.05", "AllLayers": "N"})
    pt = ET.SubElement(o, "Points")
    ET.SubElement(pt, "Point", {"X": _mm(outline[0]), "Y": _mm(outline[1])})
    ET.SubElement(pt, "Point", {"X": _mm(outline[2]), "Y": _mm(outline[3])})
    c = ET.SubElement(sh, "Shape", {"Id": "1", "Type": "Rectangle", "Locked": "N", "Layer": "Top Courtyard", "LineWidth": "0.05", "AllLayers": "N"})
    pt = ET.SubElement(c, "Points")
    ET.SubElement(pt, "Point", {"X": _mm(courtyard[0]), "Y": _mm(courtyard[1])})
    ET.SubElement(pt, "Point", {"X": _mm(courtyard[2]), "Y": _mm(courtyard[3])})


def _component(library: ET.Element, style: str, name: str, refdes: str, pattern_style: str, pins: list[tuple[str, str, str, str]], width: float = 5.08, height: float = 2.54) -> None:
    comps = library.find("Components")
    comp = ET.SubElement(comps, "Component", {"Id": str(len(comps)), "ComponentStyle": style})
    part = ET.SubElement(comp, "Part", {"Id": "0", "RefDes": refdes, "PartType": "Normal", "Type": "IC-2 Sides", "Width": _mm(width), "Height": _mm(height), "LockTypeChange": "Y"})
    ET.SubElement(part, "Pattern", {"Style": pattern_style})
    ET.SubElement(part, "Name").text = name
    ET.SubElement(part, "PartName").text = "Part 1"
    ET.SubElement(part, "Origin", {"X": "0", "Y": "0"})
    pins_el = ET.SubElement(part, "Pins")
    for index, (num, nm, x, y) in enumerate(pins):
        left = float(x) < 0
        pin = ET.SubElement(pins_el, "Pin", {"Id": str(index), "X": x, "Y": y, "Locked": "N", "Type": "Default", "ElectricType": "Passive", "Orientation": "0" if left else "180", "PadId": num, "Length": "2.54", "ShowName": "N", "NumXShift": "0", "NumYShift": "0", "NameXShift": "0", "NameYShift": "0", "SignalDelay": "0", "NumOrientation": "0", "NameOrientation": "0"})
        ET.SubElement(pin, "Name").text = nm
        ET.SubElement(pin, "PadNumber").text = num
    shapes = ET.SubElement(part, "Shapes")


def build() -> bytes:
    library = ET.Element("Library", {"Type": "DipTrace-ComponentLibrary", "Name": "DUT-CTRL std", "Hint": "Hand-drawn standard parts", "Version": "5.3.0.3", "Units": "mm"})
    pl = ET.SubElement(library, "Library", {"Type": "DipTrace-PatternLibrary", "Units": "mm"})
    ET.SubElement(pl, "PadStyles")
    ET.SubElement(pl, "Patterns")
    ET.SubElement(library, "Components")

    # Passives -------------------------------------------------------------
    _pad_style(pl, "STD_0603_PAD", 0.85, 0.92)
    _pattern(pl, "STD_R0603", "R_0603", 1.7, 0.92)
    pat = pl.findall("Patterns/Pattern")[0]
    _add_pads(pat, [("1", "STD_0603_PAD", -0.5, 0), ("2", "STD_0603_PAD", 0.5, 0)])
    _rect_shapes(pat, (-0.45, -0.36, 0.45, 0.36), (-1.05, -0.61, 1.05, 0.61))

    _pad_style(pl, "STD_0805_PAD", 1.0, 1.15)
    pat = _pattern(pl, "STD_C0805", "C_0805", 2.2, 1.15)
    _add_pads(pat, [("1", "STD_0805_PAD", -0.85, 0), ("2", "STD_0805_PAD", 0.85, 0)])
    _rect_shapes(pat, (-0.74, -0.62, 0.74, 0.62), (-1.5, -0.73, 1.5, 0.73))

    pat = _pattern(pl, "STD_C0603", "C_0603", 1.7, 0.92)
    _add_pads(pat, [("1", "STD_0603_PAD", -0.5, 0), ("2", "STD_0603_PAD", 0.5, 0)])
    _rect_shapes(pat, (-0.45, -0.36, 0.45, 0.36), (-1.05, -0.61, 1.05, 0.61))

    _component(library, "COMP_R0603", "R_0603", "R", "STD_R0603",
               [("1", "1", "-1.27", "0"), ("2", "2", "1.27", "0")], width=2.54, height=1.27)
    _component(library, "COMP_C0603", "C_0603", "C", "STD_C0603",
               [("1", "1", "-1.27", "0"), ("2", "2", "1.27", "0")], width=2.54, height=1.27)
    _component(library, "COMP_C0805", "C_0805", "C", "STD_C0805",
               [("1", "1", "-1.905", "0"), ("2", "2", "1.905", "0")], width=3.81, height=1.52)

    # 2.54 mm headers (THT) -------------------------------------------------
    _th_pad_style(pl, "STD_TH254", 1.8, 1.0)

    def header(style: str, name: str, cols: int, rows: int) -> None:
        pitch = 2.54
        w = cols * pitch
        h = rows * pitch
        pat = _pattern(pl, style, name, w, h)
        entries = []
        for r in range(rows):
            for c in range(cols):
                number = str(r * cols + c + 1)
                x = -w / 2 + pitch / 2 + c * pitch
                y = h / 2 - pitch / 2 - r * pitch
                entries.append((number, "STD_TH254", x, y))
        _add_pads(pat, entries)
        _rect_shapes(pat, (-w / 2, -h / 2, w / 2, h / 2), (-w / 2 - 0.6, -h / 2 - 0.6, w / 2 + 0.6, h / 2 + 0.6))
        pins = [(num, num, _mm(x), _mm(y)) for num, _, x, y in entries]
        _component(library, style.replace("PAT_", "COMP_"), name, "J", style, pins, width=w, height=h)

    header("PAT_HDR_1X4", "HDR_1x4_P2.54", 4, 1)
    header("PAT_HDR_2X5", "HDR_2x5_P2.54", 5, 2)
    header("PAT_HDR_2X8", "HDR_2x8_P2.54", 8, 2)

    ET.indent(library, space="  ")
    return ET.tostring(library, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    out = Path(".local/reva_lib/std_parts.elixml")
    out.write_bytes(build())
    print(f"wrote {out}")
