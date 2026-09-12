#!/usr/bin/env python3
"""Normalize all coordinates in the Rev.A schematic to fit within A4 usable area.

Reads dut-controller-reva-native-wired.dchxml, shifts each sheet's content
(components + wires + shapes) to center in [-138..+138] x [-95..+95].
Writes dut-controller-reva-normalized.dchxml.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

SRC = Path("dut-controller-reva-native-wired.dchxml")
DST = Path("dut-controller-reva-normalized.dchxml")

SHEET_W, SHEET_H = 297.0, 210.0
MARGIN = 10.0
USABLE_MIN_X = -SHEET_W/2 + MARGIN
USABLE_MAX_X =  SHEET_W/2 - MARGIN
USABLE_MIN_Y = -SHEET_H/2 + MARGIN
USABLE_MAX_Y =  SHEET_H/2 - MARGIN
GRID = 2.54


def snap(v: float) -> float:
    return round(v / GRID) * GRID


def main():
    tree = ET.parse(SRC)
    root = tree.getroot()

    sheets = root.findall(".//Sheet")
    print(f"Sheets found: {len(sheets)}")

    for sheet in sheets:
        sid = int(sheet.findtext("Id", "0"))  # Id is a child element
        name = sheet.findtext("Name", "?")

        # Collect parts on this sheet
        parts = [p for p in root.findall("./Schematic/Components/Part")
                 if int(p.get("Sheet", "0")) == sid]
        if not parts:
            continue

        # Bounding box from PARTS ONLY
        part_xs = [float(p.get("X", "0")) for p in parts]
        part_ys = [float(p.get("Y", "0")) for p in parts]
        content_cx = (min(part_xs) + max(part_xs)) / 2
        content_cy = (min(part_ys) + max(part_ys)) / 2
        target_cx = (USABLE_MIN_X + USABLE_MAX_X) / 2
        target_cy = (USABLE_MIN_Y + USABLE_MAX_Y) / 2
        dx = target_cx - content_cx
        dy = target_cy - content_cy

        # Shift parts
        for p in parts:
            nx = snap(float(p.get("X", "0")) + dx)
            ny = snap(float(p.get("Y", "0")) + dy)
            p.set("X", f"{nx:.2f}")
            p.set("Y", f"{ny:.2f}")

        # Collect and shift wire endpoints on this sheet
        wire_points = []
        for net in root.findall("./Schematic/Nets/Net"):
            for w in net.findall("./Wires/Wire"):
                if int(w.get("Sheet", "0")) != sid:
                    continue
                for pt in w.findall("./Points/Point"):
                    wire_points.append(pt)
        for pt in wire_points:
            nx = snap(float(pt.get("X", "0")) + dx)
            ny = snap(float(pt.get("Y", "0")) + dy)
            pt.set("X", f"{nx:.2f}")
            pt.set("Y", f"{ny:.2f}")

        # Collect and shift shape points on this sheet
        shape_points = []
        for shape in root.findall("./Schematic/Shapes/Shape"):
            if shape.get("Sheet", "0") != str(sid):
                continue
            for pt in shape.findall("./Points/Point"):
                shape_points.append(pt)
        for pt in shape_points:
            nx = snap(float(pt.get("X", "0")) + dx)
            ny = snap(float(pt.get("Y", "0")) + dy)
            pt.set("X", f"{nx:.2f}")
            pt.set("Y", f"{ny:.2f}")

        # Verify
        new_xs = [float(p.get("X")) for p in parts]
        new_ys = [float(p.get("Y")) for p in parts]
        out_x = sum(1 for x in new_xs if x < USABLE_MIN_X or x > USABLE_MAX_X)
        out_y = sum(1 for y in new_ys if y < USABLE_MIN_Y or y > USABLE_MAX_Y)
        print(f"  Sheet {sid} ({name}): shift ({dx:+.0f},{dy:+.0f})  "
              f"{len(parts)} parts, {len(wire_points)} wire pts  "
              f"outside: X={out_x} Y={out_y}")

    ET.indent(root, space="  ")
    DST.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"\nwrote {DST}")
    print(f"ABS: {DST.resolve()}")


if __name__ == "__main__":
    main()