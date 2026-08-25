#!/usr/bin/env python3
"""Generic LCSC/EasyEDA -> DipTrace Component Library (.elixml) converter.

Input: vendor/<code>.json files produced by fetch_component.py
(.agents/skills/easyeda-lcsc-sourcing). Output: standalone
DipTrace-ComponentLibrary XML fragments loadable by
diptrace_mcp.services.builtin_library._component_definitions.

EasyEDA geometry units are 10 mil (0.254 mm); Y grows upward, DipTrace Y
grows downward. Symbol graphics are reduced to the body rectangle plus named
pins (house rule: electrical correctness first, decoration later).
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SCALE_MM = 0.254


@dataclass(frozen=True)
class SymbolPin:
    number: str
    name: str
    x_mm: float  # absolute EasyEDA mm
    y_mm: float


@dataclass(frozen=True)
class FootprintPad:
    number: str
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    angle_deg: float
    hole_mm: float  # >0 => through-hole


def _mm(value: float) -> str:
    out = f"{value:.4f}".rstrip("0").rstrip(".")
    return out if out else "0"


def _pin_label(raw: str, number: str) -> str:
    """Extract the visible name from a P~ record's ^^ sections."""
    candidates: list[str] = []
    for section in raw.split("^^")[1:]:
        tokens = section.split("~")
        if len(tokens) < 6:
            continue
        value = tokens[4]
        if not value or value.isdigit():
            continue
        if tokens[5] in ("start", "end"):
            candidates.append(value)
    return candidates[0] if candidates else number


def _merged_pad_remap(
    pins: list[SymbolPin], pad_numbers: set[str]
) -> dict[str, str]:
    """Map symbol pin ids onto merged pads like ``A1B12`` (USB-C VBUS/GND).

    Returns {pin_number: merged_pad_number} for pins whose own id is not a
    physical pad but is contained inside one merged pad name.
    """
    import re

    merged_parts: dict[str, set[str]] = {}
    for number in pad_numbers:
        parts = set(re.findall(r"[A-Z]+\d+", number))
        if len(parts) > 1:
            merged_parts[number] = parts
    remap: dict[str, str] = {}
    for pin in pins:
        if pin.number in pad_numbers:
            continue
        for pad_number, parts in merged_parts.items():
            if pin.number in parts:
                remap[pin.number] = pad_number
                break
    return remap


def parse_symbol(
    result: dict,
) -> tuple[tuple[float, float, float, float], list[SymbolPin]]:
    """Return (body x,y,w,h in EasyEDA units) and parsed pins.

    Preferred input is an ``R~`` body rectangle. Symbols without one (small
    discretes drawn from polylines) get a bounding-box body synthesised from
    PL/PG graphics.
    """
    shapes = result["dataStr"]["shape"]
    rect = next((t.split("~") for t in shapes if t.startswith("R~")), None)
    if rect is not None:
        bx, by, bw, bh = float(rect[1]), float(rect[2]), float(rect[5]), float(rect[6])
    else:
        xs: list[float] = []
        ys: list[float] = []
        for raw in shapes:
            head = raw.split("~")[0]
            if head not in ("PL", "PG"):
                continue
            coords = raw.split("~")[1].split()
            values = [float(v) for v in coords]
            xs.extend(values[0::2])
            ys.extend(values[1::2])
        if not xs:
            raise ValueError("symbol has neither R~ body nor PL/PG graphics")
        bx, by = min(xs), min(ys)
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)

    pins: list[SymbolPin] = []
    for raw in shapes:
        if not raw.startswith("P~show~"):
            continue
        head = raw.split("^^")[0].split("~")
        number, px, py = head[3], float(head[4]), float(head[5])
        pins.append(SymbolPin(number, _pin_label(raw, number), px, py))
    if not pins:
        raise ValueError("symbol has no P~ pins")
    return (bx, by, bw, bh), pins


def parse_package(result: dict) -> tuple[list[FootprintPad], float, float]:
    """Return pads plus footprint origin (head x/y in EasyEDA units)."""
    pkg = result["packageDetail"]
    cx, cy = float(pkg["dataStr"]["head"]["x"]), float(pkg["dataStr"]["head"]["y"])
    pads: list[FootprintPad] = []
    for raw in pkg["dataStr"]["shape"]:
        tokens = raw.split("~")
        if tokens[0] != "PAD":
            continue
        shape, x, y, w, h = tokens[1], float(tokens[2]), float(tokens[3]), float(tokens[4]), float(tokens[5])
        if shape == "POLY":
            # Approximate custom polygons by their declared bounding box.
            pts = [float(v) for v in tokens[10].split()] if len(tokens) > 10 and tokens[10] else []
            if len(pts) >= 4:
                xs, ys = pts[0::2], pts[1::2]
                x, y = min(xs), max(ys)
                w, h = max(xs) - min(xs), max(ys) - min(ys)
            shape = "RECT"
        if shape not in ("RECT", "POLYGON", "OVAL", "CIRCLE", "ELLIPSE"):
            continue
        if shape in ("OVAL", "ELLIPSE"):
            w, h = max(w, h), min(w, h)
        if shape == "CIRCLE":
            h = w
        hole_r = float(tokens[9]) if len(tokens) > 9 and tokens[9] else 0.0
        angle = float(tokens[11]) if len(tokens) > 11 and tokens[11] else 0.0
        pads.append(
            FootprintPad(
                number=tokens[8],
                x_mm=(x - cx) * SCALE_MM,
                y_mm=(cy - y) * SCALE_MM,
                w_mm=w * SCALE_MM,
                h_mm=h * SCALE_MM,
                angle_deg=math.radians(angle),
                hole_mm=hole_r * SCALE_MM * 2,
            )
        )
    if not pads:
        raise ValueError("package has no PAD records")
    # DipTrace sync requires unique pad numbers per component; EasyEDA repeats
    # one number across thermal-pad grids (ESP32-S3-MINI "61" x9). Merge each
    # duplicated group into a single pad covering their union bounding box.
    groups: dict[str, list[FootprintPad]] = {}
    order: list[str] = []
    for pad in sorted(pads, key=lambda p: p.number):
        if pad.number not in groups:
            groups[pad.number] = []
            order.append(pad.number)
        groups[pad.number].append(pad)
    merged: list[FootprintPad] = []
    for number in order:
        members = groups[number]
        if len(members) == 1:
            merged.append(members[0])
            continue
        xs0 = [m.x_mm - m.w_mm / 2 for m in members]
        xs1 = [m.x_mm + m.w_mm / 2 for m in members]
        ys0 = [m.y_mm - m.h_mm / 2 for m in members]
        ys1 = [m.y_mm + m.h_mm / 2 for m in members]
        x0, x1 = min(xs0), max(xs1)
        y0, y1 = min(ys0), max(ys1)
        base = members[0]
        merged.append(
            FootprintPad(
                number=number,
                x_mm=(x0 + x1) / 2,
                y_mm=(y0 + y1) / 2,
                w_mm=x1 - x0,
                h_mm=y1 - y0,
                angle_deg=0.0,
                hole_mm=base.hole_mm,
            )
        )
    return merged, cx, cy


def _electric_type(name: str) -> str:
    upper = name.upper()
    if any(k in upper for k in ("GND", "VSS", "VDD", "VCC", "VBUS", "VIN", "VOUT", "3V3", "5V", "1V8", "2V5", "VREF", "EP", "ANT")):
        return "Power"
    if upper.startswith(("IO", "GPIO", "P")) and any(ch.isdigit() for ch in upper):
        return "Bidirectional"
    if any(k in upper for k in ("D+", "D-", "TX", "RX", "SDA", "SCL", "MOSI", "MISO", "USB")):
        return "Bidirectional"
    if any(k in upper for k in ("EN", "OE", "CE", "CS", "RST", "SHDN", "INT", "FLT", "PG", "ILIM")):
        return "Input"
    return "Passive"


def build_elixml(
    *,
    mpn: str,
    manufacturer: str,
    datasheet_url: str,
    lcsc_code: str,
    refdes_prefix: str = "U",
) -> str:
    """Build one combined library document for vendor/<code>.json."""
    source = json.loads(Path(f"vendor/{lcsc_code}.json").read_text(encoding="utf-8"))
    result = source["result"]
    (bx, by, bw, bh), pins = parse_symbol(result)
    pads, _, _ = parse_package(result)
    remap = _merged_pad_remap(pins, {p.number for p in pads})

    # DipTrace sync maps schematic pins to PCB pads POSITIONALLY
    # (pin index -> pad_numbers[index]), so the embedded pattern must list its
    # pads in exactly the symbol's pin order. Unmatched extra pads keep their
    # relative order at the end.
    desired = [remap.get(pin.number, pin.number) for pin in pins]
    rank = {num: i for i, num in enumerate(desired)}
    pads = sorted(
        enumerate(pads),
        key=lambda t: (rank.get(t[1].number, len(desired) + t[0]), t[0]),
    )
    pads = [pad for _i, pad in pads]

    center_x, center_y = bx + bw / 2, by + bh / 2

    library = ET.Element(
        "Library",
        {
            "Type": "DipTrace-ComponentLibrary",
            "Name": f"LCSC {lcsc_code}",
            "Hint": f"Converted from downloaded LCSC/EasyEDA catalog data ({mpn})",
            "Version": "5.3.0.3",
            "Units": "mm",
        },
    )
    pattern_library = ET.SubElement(library, "Library", {"Type": "DipTrace-PatternLibrary", "Units": "mm"})
    pad_styles = ET.SubElement(pattern_library, "PadStyles")
    patterns = ET.SubElement(pattern_library, "Patterns")

    style_for_size: dict[tuple[float, float, bool], str] = {}
    for pad in pads:
        through = pad.hole_mm > 0
        size = (round(pad.w_mm, 3), round(pad.h_mm, 3), through)
        if size in style_for_size:
            continue
        style_name = f"{lcsc_code}_PAD_{len(style_for_size)}"
        style_for_size[size] = style_name
        attrs = {"Name": style_name, "Type": "Through" if through else "Surface"}
        if through:
            attrs["Side"] = "Top"
        style = ET.SubElement(pad_styles, "PadStyle", attrs)
        ET.SubElement(
            style,
            "MainStack",
            {"Shape": "Ellipse" if through else "Rectangle", "Width": _mm(pad.w_mm), "Height": _mm(pad.h_mm), "Corner": "0"},
        )
        if through:
            ET.SubElement(style, "Hole", {"Type": "Drill", "Width": _mm(pad.hole_mm), "Height": _mm(pad.hole_mm)})
        ET.SubElement(
            style,
            "MaskPaste",
            {"TopMask": "Open" if not through else "Common", "BotMask": "Common", "TopPaste": "Segments" if not through else "Common", "BotPaste": "Common"},
        )

    bbox_w = max(abs(p.x_mm) + p.w_mm / 2 for p in pads) * 2
    bbox_h = max(abs(p.y_mm) + p.h_mm / 2 for p in pads) * 2
    pattern = ET.SubElement(
        patterns,
        "Pattern",
        {
            "PatternStyle": f"{lcsc_code}_PATTERN",
            "Id": "0",
            "Mounting": "Through" if any(p.hole_mm for p in pads) else "SMD",
            "Width": _mm(bbox_w),
            "Height": _mm(bbox_h),
            "Orientation": "0",
            "LockTypeChange": "Y",
            "Type": "LCSC",
        },
    )
    ET.SubElement(pattern, "Name").text = result["packageDetail"].get("title", mpn)
    ET.SubElement(pattern, "Name_Description").text = f"LCSC/EasyEDA footprint {lcsc_code}"
    ET.SubElement(pattern, "Name_Unique").text = f"{mpn}_{lcsc_code}"
    ET.SubElement(pattern, "Manufacturer").text = manufacturer
    ET.SubElement(pattern, "Origin", {"X": "0", "Y": "0"})
    ET.SubElement(pattern, "DefPad", {"Style": next(iter(style_for_size.values()))})
    pads_el = ET.SubElement(pattern, "Pads")
    for index, pad in enumerate(pads):
        pad_el = ET.SubElement(
            pads_el,
            "Pad",
            {
                "Id": str(index),
                "Style": style_for_size[(round(pad.w_mm, 3), round(pad.h_mm, 3), pad.hole_mm > 0)],
                "X": _mm(pad.x_mm),
                "Y": _mm(pad.y_mm),
                "Angle": f"{pad.angle_deg:.6f}",
                "Locked": "N",
                "Side": "Top",
            },
        )
        ET.SubElement(pad_el, "Number").text = pad.number

    shapes_el = ET.SubElement(pattern, "Shapes")
    outline = ET.SubElement(shapes_el, "Shape", {"Id": "0", "Type": "Rectangle", "Locked": "N", "Layer": "Top Outline", "LineWidth": "0.05", "AllLayers": "N"})
    pts = ET.SubElement(outline, "Points")
    ET.SubElement(pts, "Point", {"X": _mm(-bbox_w / 2 + 0.2), "Y": _mm(-bbox_h / 2 + 0.2)})
    ET.SubElement(pts, "Point", {"X": _mm(bbox_w / 2 - 0.2), "Y": _mm(bbox_h / 2 - 0.2)})
    courtyard = ET.SubElement(shapes_el, "Shape", {"Id": "1", "Type": "Rectangle", "Locked": "N", "Layer": "Top Courtyard", "LineWidth": "0.05", "AllLayers": "N"})
    pts = ET.SubElement(courtyard, "Points")
    ET.SubElement(pts, "Point", {"X": _mm(-bbox_w / 2 - 0.25), "Y": _mm(-bbox_h / 2 - 0.25)})
    ET.SubElement(pts, "Point", {"X": _mm(bbox_w / 2 + 0.25), "Y": _mm(bbox_h / 2 + 0.25)})

    components = ET.SubElement(library, "Components")
    component = ET.SubElement(components, "Component", {"Id": "0", "ComponentStyle": f"{lcsc_code}"})
    part = ET.SubElement(
        component,
        "Part",
        {"Id": "0", "RefDes": refdes_prefix, "PartType": "Normal", "Type": "IC-2 Sides", "Width": _mm(bw * SCALE_MM), "Height": _mm(bh * SCALE_MM), "LockTypeChange": "Y"},
    )
    ET.SubElement(part, "Pattern", {"Style": f"{lcsc_code}_PATTERN"})
    ET.SubElement(part, "Name").text = mpn
    ET.SubElement(part, "PartName").text = "Part 1"
    ET.SubElement(part, "Origin", {"X": "0", "Y": "0"})
    ET.SubElement(part, "Datasheet").text = datasheet_url
    ET.SubElement(part, "Manufacturer").text = manufacturer
    pins_el = ET.SubElement(part, "Pins")
    for index, pin in enumerate(pins):
        px, py = pin.x_mm / SCALE_MM, pin.y_mm / SCALE_MM
        distances = {
            "left": abs(px - bx),
            "right": abs(px - (bx + bw)),
            "bottom": abs(py - by),
            "top": abs(py - (by + bh)),
        }
        side = min(distances, key=lambda k: (distances[k], ["left", "right", "bottom", "top"].index(k)))
        edge = {
            "left": (bx, py, "0"),
            "right": (bx + bw, py, "180"),
            "top": (px, by + bh, "90"),
            "bottom": (px, by, "270"),
        }[side]
        edge_x, edge_y, orientation = edge
        length_units = math.hypot(px - edge_x, py - edge_y)
        pin_el = ET.SubElement(
            pins_el,
            "Pin",
            {
                "Id": str(index),
                "X": _mm((edge_x - center_x) * SCALE_MM),
                "Y": _mm((center_y - edge_y) * SCALE_MM),
                "Locked": "N",
                "Type": "Default",
                "ElectricType": _electric_type(pin.name),
                "Orientation": orientation,
                "PadId": pin.number,
                "Length": _mm(length_units * SCALE_MM),
                "ShowName": "Y",
                "NumXShift": "0",
                "NumYShift": "0",
                "NameXShift": "0",
                "NameYShift": "0",
                "SignalDelay": "0",
                "NumOrientation": "0",
                "NameOrientation": "0",
            },
        )
        ET.SubElement(pin_el, "Name").text = pin.name
        ET.SubElement(pin_el, "PadNumber").text = remap.get(pin.number, pin.number)
        ET.SubElement(pin_el, "NameFont", {"Size": "5", "FontSizeFloat": "5", "Width": "-2", "Scale": "1", "FontMono": "N"})
    symbol_shapes = ET.SubElement(part, "Shapes")
    body = ET.SubElement(symbol_shapes, "Shape", {"Id": "0", "Type": "Rectangle", "LineWidth": "0.25"})
    pts = ET.SubElement(body, "Points")
    ET.SubElement(pts, "Point", {"X": _mm(-bw * SCALE_MM / 2), "Y": _mm(bh * SCALE_MM / 2)})
    ET.SubElement(pts, "Point", {"X": _mm(bw * SCALE_MM / 2), "Y": _mm(-bh * SCALE_MM / 2)})
    extra = ET.SubElement(part, "AddFields")
    for key, value in (("MPN", mpn), ("LCSC", lcsc_code), ("Source", "LCSC/EasyEDA downloaded catalog data")):
        field = ET.SubElement(extra, "AddField", {"Type": "Text"})
        ET.SubElement(field, "Name").text = key
        ET.SubElement(field, "Text").text = value

    # DipTrace's synthetic-sync resolves pad references by numeric Id
    # fallback; alphanumeric pad numbers (USB-C "A1B12") cannot round-trip.
    # Renumber such components sequentially in symbol-pin order and record an
    # alias table next to the .elixml so builders can translate net tables.
    import json as _json

    alias: dict[str, str] = {}
    if any(not pad.number.isdigit() for pad in pads):
        for index, pad in enumerate(pads):
            alias[pad.number] = str(index + 1)
        for pad_el, pad in zip(pads_el.findall("Pad"), pads):
            num = pad_el.find("Number")
            if num is not None:
                num.text = alias.get(pad.number, pad.number)
        for pin_el, pin in zip(pins_el.findall("Pin"), pins):
            pn = pin_el.find("PadNumber")
            if pn is not None:
                pn.text = alias.get(remap.get(pin.number, pin.number),
                                    remap.get(pin.number, pin.number))
        Path(f".local/reva_lib/{lcsc_code}.alias.json").write_text(
            _json.dumps(alias, indent=1), encoding="utf-8"
        )

    ET.indent(library, space="  ")
    return ET.tostring(library, encoding="unicode")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=".local/reva_lib", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path("vendor/reva_manifest.json").read_text(encoding="utf-8"))
    for entry in manifest:
        xml = build_elixml(**entry)
        target = args.out / f"{entry['lcsc_code']}.elixml"
        target.write_text(xml, encoding="utf-8")
        print(f"{target} ({entry['mpn']})")


if __name__ == "__main__":
    main()
