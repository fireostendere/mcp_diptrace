#!/usr/bin/env python3
"""Extract Rev.A part placements from the build script, normalize to visible A4 area.

Reads build_dut_controller_reva.py, extracts all b.part() calls + for-loop parts,
centers each sheet's content in usable area [-138..+138] x [-95..+95].
Writes dut_controller_rev_a_corrected.json for MCP consumption.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

USABLE_X = (-138.0, 138.0)
USABLE_Y = (-95.0, 95.0)
GRID = 2.54


def grid_snap(x: float, y: float) -> tuple[float, float]:
    return (round(x / GRID) * GRID, round(y / GRID) * GRID)


# Library resolution: lib_raw substring → (lib_name, source)
LIB_RESOLVE = [
    ("C2980299", "C2980299", "lcsc"), ("C130085", "C130085", "lcsc"),
    ("C55136", "C55136", "lcsc"), ("C2653870", "C2653870", "lcsc"),
    ("C11133", "C11133", "lcsc"), ("C7843", "C7843", "lcsc"),
    ("C129516", "C129516", "lcsc"), ("C161747", "C161747", "lcsc"),
    ("C7519", "C7519", "lcsc"), ("C83574", "C83574", "lcsc"),
    ("C10758", "C10758", "lcsc"), ("C123820", "C123820", "lcsc"),
    ("C108176", "C108176", "lcsc"), ("C14643", "C14643", "lcsc"),
    ("C910842", "C910842", "lcsc"), ("C146332", "C146332", "lcsc"),
    ("C15127", "C15127", "lcsc"), ("C84104", "C84104", "lcsc"),
    ("C165948", "C165948", "lcsc"), ("C698206", "C698206", "lcsc"),
    ("C8465", "C8465", "lcsc"), ("C68608", "C68608", "lcsc"),
    ("C20802", "C20802", "lcsc"), ("C318884", "C318884", "lcsc"),
    ("C2286", "C2286", "lcsc"),
    ("COMP_R0603", "R_0603", "builtin"), ("COMP_C0603", "C_0603", "builtin"),
    ("COMP_C0805", "C_0805", "builtin"), ("COMP_HDR_2X5", "HDR-2x5", "builtin"),
    ("COMP_HDR_2X8", "HDR-2x8", "builtin"), ("COMP_HDR_1X4", "HDR-1x4", "builtin"),
    # Variable names from build script: R = std_parts COMP_R0603, C06 = std_parts COMP_C0603, etc.
    ("C06", "C_0603", "builtin"), ("C08", "C_0805", "builtin"),
    ("R", "R_0603", "builtin"),
    ("STD", "builtin", "builtin"),  # STD = "std_parts"
]


def resolve_lib(lib_raw: str) -> tuple[str, str]:
    # Exact match first (for variable names like R, C06, C08)
    exact = {"R": ("R_0603", "builtin"), "C06": ("C_0603", "builtin"),
             "C08": ("C_0805", "builtin"), "STD": ("builtin", "builtin")}
    if lib_raw in exact:
        return exact[lib_raw]
    # Substring match for catalog IDs
    for needle, name, source in LIB_RESOLVE:
        if needle in lib_raw:
            return name, source
    return lib_raw, "unknown"


def parse_parts(script_path: str) -> list[dict]:
    text = Path(script_path).read_text()
    parts = []

    # Track sheet variable assignments: find "s = N" lines
    lines = text.split("\n")
    current_sheet = 1
    sheet_at_line = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r'^s\s*=\s*\d+\s*$', stripped):
            current_sheet = int(re.search(r'\d+', stripped).group())
        sheet_at_line[i] = current_sheet

    # Parse explicit b.part() calls
    pat = r'b\.part\(([^,]+),\s*"([^"]+)",\s*"([^"]+)",\s*s,\s*([\d.]+),\s*([\d.]+)\)'
    for m in re.finditer(pat, text):
        lib_raw = m.group(1).strip()
        refdes = m.group(2)
        value = m.group(3)
        x, y = float(m.group(4)), float(m.group(5))
        line_num = text[:m.start()].count("\n")
        sheet = sheet_at_line.get(line_num, 1)
        lib, source = resolve_lib(lib_raw)
        parts.append({"refdes": refdes, "value": value, "sheet": sheet,
                       "x_orig": x, "y_orig": y, "lib": lib, "source": source})

    # For-loop generated parts (K1-K8, R36-R43, R49-R60, D15-D26, RSER1-8, R26-R35)
    for i in range(8):
        x = 78.0 + (i % 4) * 17.0
        y = 78.0 + (i // 4) * 15.0
        parts += [
            {"refdes": f"K{i+1}", "value": "TLP176A", "sheet": 5,
             "x_orig": x, "y_orig": y, "lib": "C146332", "source": "lcsc"},
            {"refdes": f"R{36+i}", "value": "390R", "sheet": 5,
             "x_orig": x+6, "y_orig": y, "lib": "R_0603", "source": "builtin"},
        ]
    for i in range(6):
        y = 104.0 + i * 8.0
        parts += [
            {"refdes": f"R{49+i*2}", "value": "15k", "sheet": 6,
             "x_orig": 40.0, "y_orig": y, "lib": "R_0603", "source": "builtin"},
            {"refdes": f"R{50+i*2}", "value": "10k", "sheet": 6,
             "x_orig": 47.0, "y_orig": y, "lib": "R_0603", "source": "builtin"},
            {"refdes": f"C{10+i}", "value": "1nF", "sheet": 6,
             "x_orig": 54.0, "y_orig": y, "lib": "C_0603", "source": "builtin"},
        ]
        if i < 4:
            parts.append({"refdes": f"D{15+i}", "value": "clamp", "sheet": 6,
                           "x_orig": 61.0, "y_orig": y, "lib": "C83574", "source": "lcsc"})
    for i in range(8):
        x = 92.0 + (i % 4) * 16.0
        y = 156.0 + (i // 4) * 12.0
        parts += [
            {"refdes": f"RSER{i+1}", "value": "100R", "sheet": 6,
             "x_orig": x, "y_orig": y, "lib": "R_0603", "source": "builtin"},
            {"refdes": f"D{19+i}", "value": "clamp", "sheet": 6,
             "x_orig": x+6, "y_orig": y, "lib": "C83574", "source": "lcsc"},
        ]
    for ref, y in [("R26", 94), ("R27", 98), ("R28", 148), ("R29", 152)]:
        parts.append({"refdes": ref, "value": "10k sink", "sheet": 4,
                       "x_orig": 86.0, "y_orig": y, "lib": "R_0603", "source": "builtin"})
    for ref, y in [("R30", 80), ("R31", 84), ("R32", 88), ("R33", 134), ("R34", 138), ("R35", 142)]:
        parts.append({"refdes": ref, "value": "100k ctrl PD", "sheet": 4,
                       "x_orig": 46.0, "y_orig": y, "lib": "R_0603", "source": "builtin"})
    return parts


def normalize(parts: list[dict]) -> list[dict]:
    by_sheet: dict[int, list[dict]] = {}
    for p in parts:
        by_sheet.setdefault(p["sheet"], []).append(p)

    for sheet, sp in by_sheet.items():
        xs = [p["x_orig"] for p in sp]
        ys = [p["y_orig"] for p in sp]
        dx = 0 - (min(xs) + max(xs)) / 2
        dy = 0 - (min(ys) + max(ys)) / 2
        for p in sp:
            nx, ny = grid_snap(p["x_orig"] + dx, p["y_orig"] + dy)
            p["x"] = max(USABLE_X[0]+5, min(USABLE_X[1]-5, nx))
            p["y"] = max(USABLE_Y[0]+5, min(USABLE_Y[1]-5, ny))
    return parts


def main():
    parts = parse_parts("scripts/build_dut_controller_reva.py")
    from collections import Counter
    print(f"Parsed {len(parts)} parts")
    print(f"  Sources: {dict(Counter(p['source'] for p in parts))}")
    for s in sorted(set(p['sheet'] for p in parts)):
        print(f"  Sheet {s}: {sum(1 for p in parts if p['sheet']==s)} parts")

    parts = normalize(parts)
    out = sum(1 for p in parts if not (USABLE_X[0] <= p['x'] <= USABLE_X[1] and USABLE_Y[0] <= p['y'] <= USABLE_Y[1]))
    print(f"After normalize: {len(parts)} parts, {out} outside usable area")
    for s in sorted(set(p['sheet'] for p in parts)):
        sp = [p for p in parts if p['sheet']==s]
        xs, ys = [p['x'] for p in sp], [p['y'] for p in sp]
        print(f"  Sheet {s}: {len(sp)}  X=[{min(xs):.0f}..{max(xs):.0f}]  Y=[{min(ys):.0f}..{max(ys):.0f}]")

    Path("dut_controller_rev_a_corrected.json").write_text(json.dumps(parts, indent=2))
    print("\nwrote dut_controller_rev_a_corrected.json")


if __name__ == "__main__":
    main()
