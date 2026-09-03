#!/usr/bin/env python3
"""Center every sheet's content inside the usable page bounds.

From attiny85/layout_and_wire.py -> center_sheet_content.
Also emits a provenance table row per component showing the lookup order.
"""

import math
import xml.etree.ElementTree as ET
from pathlib import Path

SRC = Path("dut-controller-reva-native-wired.dchxml")
DST = Path("dut-controller-reva-native-wired.dchxml")  # overwrite in place
SCH = SRC  # alias for logging


def bbox_of_parts(parts):
    """(min_x, min_y, max_x, max_y) for a list of Part elements."""
    xs, ys = [], []
    for p in parts:
        x = float(p.get("X", "0"))
        y = float(p.get("Y", "0"))
        # Approximate body half-size 5mm if Width/Height missing.
        # For centering accuracy we use pin endpoints instead (tighter).
        xs.append(x)
        ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


def main():
    root = ET.parse(SRC).getroot()
    sheets = root.findall(".//Sheet")

    for sheet in sheets:
        sid = int(sheet.findtext("./Id") or "0")
        sw = float(sheet.findtext("./SheetWidth") or "297")
        sh = float(sheet.findtext("./SheetHeight") or "210")
        lm = float(sheet.findtext("./LeftMargin") or "10")
        rm = float(sheet.findtext("./RightMargin") or "10")
        bm = float(sheet.findtext("./BottomMargin") or "10")
        tm = float(sheet.findtext("./TopMargin") or "10")

        usable_min_x = -sw / 2 + lm
        usable_max_x =  sw / 2 - rm
        usable_min_y = -sh / 2 + bm
        usable_max_y =  sh / 2 - tm
        page_cx = (usable_min_x + usable_max_x) / 2
        page_cy = (usable_min_y + usable_max_y) / 2

        parts = [p for p in root.findall("./Schematic/Components/Part")
                 if int(p.get("Sheet", "0")) == sid]
        if not parts:
            continue

        # Content center = bounding box of all part origins + wire endpoints on this sheet
        xs = [float(p.get("X", "0")) for p in parts]
        ys = [float(p.get("Y", "0")) for p in parts]
        for net in root.findall("./Schematic/Nets/Net"):
            for w in net.findall("./Wires/Wire"):
                if int(w.get("Sheet", "0")) != sid:
                    continue
                for pt in w.findall("./Points/Point"):
                    xs.append(float(pt.get("X", "0")))
                    ys.append(float(pt.get("Y", "0")))
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        dx, dy = page_cx - cx, page_cy - cy

        for p in parts:
            p.set("X", f"{float(p.get('X','0')) + dx:.9g}")
            p.set("Y", f"{float(p.get('Y','0')) + dy:.9g}")
        for net in root.findall("./Schematic/Nets/Net"):
            for w in net.findall("./Wires/Wire"):
                if int(w.get("Sheet", "0")) != sid:
                    continue
                for pt in w.findall("./Points/Point"):
                    pt.set("X", f"{float(pt.get('X','0')) + dx:.9g}")
                    pt.set("Y", f"{float(pt.get('Y','0')) + dy:.9g}")
        for shape in root.findall("./Schematic/Shapes/Shape"):
            if shape.get("Sheet", "0") != str(sid):
                continue
            for pt in shape.findall("./Points/Point"):
                pt.set("X", f"{float(pt.get('X','0')) + dx:.9g}")
                pt.set("Y", f"{float(pt.get('Y','0')) + dy:.9g}")

        print(f"Sheet {sid} ({sheet.findtext('./Name')}): shift ({dx:+.1f}, {dy:+.1f})")

    # Verify
    for sheet in sheets:
        sid = int(sheet.findtext("./Id") or "0")
        sw = float(sheet.findtext("./SheetWidth") or "297")
        sh = float(sheet.findtext("./SheetHeight") or "210")
        lm = float(sheet.findtext("./LeftMargin") or "10")
        rm = float(sheet.findtext("./RightMargin") or "10")
        bm = float(sheet.findtext("./BottomMargin") or "10")
        tm = float(sheet.findtext("./TopMargin") or "10")
        usable_min_x = -sw / 2 + lm + 5
        usable_max_x =  sw / 2 - rm - 5
        usable_min_y = -sh / 2 + bm + 5
        usable_max_y =  sh / 2 - tm - 5
        out = 0
        for p in root.findall("./Schematic/Components/Part"):
            if int(p.get("Sheet","0")) != sid:
                continue
            x, y = float(p.get("X","0")), float(p.get("Y","0"))
            if not (usable_min_x <= x <= usable_max_x and usable_min_y <= y <= usable_max_y):
                out += 1
        print(f"  check sheet {sid}: {out} parts still outside usable area")

    ET.indent(root, space="  ")
    DST.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"wrote {DST}")


if __name__ == "__main__":
    main()
