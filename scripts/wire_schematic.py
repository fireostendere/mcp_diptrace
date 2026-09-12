#!/usr/bin/env python3
"""Add visual wires and net labels to a DipTrace schematic.

Extracted from attiny85-arduino-clone/layout_and_wire.py. Computes pin
endpoint positions from library data, generates L-shaped wire paths between
connected pins on the same sheet, and appends them to the XML.

Usage:
    PYTHONPATH=src python scripts/wire_schematic.py <input.dchxml> [--max-wire-len 30]

For each net, pins on the same sheet are connected with orthogonal wires.
Pins on different sheets get net labels instead (cross-sheet connectivity).
"""

from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diptrace_mcp.xml_document import DipTraceDocument  # noqa: E402


@dataclass(frozen=True)
class Endpoint:
    refdes: str
    pin: int
    sheet: int
    x: float
    y: float
    dx: float  # direction the pin stub points (unit vector)
    dy: float


@dataclass(frozen=True)
class WireSpec:
    net: str
    sheet: int
    start_refdes: str | None
    start_pin: int | None
    end_refdes: str | None
    end_pin: int | None
    points: tuple[tuple[float, float], ...]


def _transform_local(part_el: ET.Element, x: float, y: float) -> tuple[float, float]:
    angle = math.radians(float(part_el.get("Angle", "0")))
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    rx = x * cos_a - y * sin_a
    ry = x * sin_a + y * cos_a
    return rx, ry


def compute_endpoints(doc: DipTraceDocument) -> dict[str, list[Endpoint]]:
    """Map net name → list of absolute pin endpoint positions."""
    root = doc.root
    style_by_name = {
        c.get("ComponentStyle"): c
        for c in root.findall("./Library/Components/Component")
    }
    net_id_to_name = {
        n.get("Id", ""): n.findtext("./Name") or ""
        for n in root.findall("./Schematic/Nets/Net")
    }
    result: dict[str, list[Endpoint]] = {v: [] for v in net_id_to_name.values()}

    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        sheet = int(part.get("Sheet", "0"))
        px, py = float(part.get("X", "0")), float(part.get("Y", "0"))
        comp_style = part.get("ComponentStyle")
        lib_comp = style_by_name.get(comp_style)
        if lib_comp is None:
            continue
        lib_part = lib_comp.find("./Part[@Id='0']")
        if lib_part is None:
            continue
        lib_pins = lib_part.findall("./Pins/Pin")
        for idx, placed_pin in enumerate(part.findall("./Pins/Pin")):
            net_id = placed_pin.get("NetId", "-1")
            if net_id == "-1":
                continue
            if idx >= len(lib_pins):
                continue
            lp = lib_pins[idx]
            ang = math.radians(float(lp.get("Orientation", "0")))
            dx_dir = -math.cos(ang)
            dy_dir = math.sin(ang)
            length = float(lp.get("Length", "0"))
            lx = float(lp.get("X", "0")) + dx_dir * length
            ly = float(lp.get("Y", "0")) + dy_dir * length
            ox, oy = _transform_local(part, lx, ly)
            rdx, rdy = _transform_local(part, dx_dir, dy_dir)
            net_name = net_id_to_name.get(net_id, "")
            result.setdefault(net_name, []).append(
                Endpoint(refdes, idx, sheet,
                         px + ox, py + oy, rdx, rdy)
            )
    return result


def compute_body_boxes(doc: DipTraceDocument) -> dict[str, tuple[int, float, float, float, float]]:
    """refdes → (sheet, min_x, min_y, max_x, max_y)."""
    root = doc.root
    style_by_name = {
        c.get("ComponentStyle"): c
        for c in root.findall("./Library/Components/Component")
    }
    boxes = {}
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        sheet = int(part.get("Sheet", "0"))
        px, py = float(part.get("X", "0")), float(part.get("Y", "0"))
        lib_comp = style_by_name.get(part.get("ComponentStyle"))
        if lib_comp is None:
            continue
        lib_part = lib_comp.find("./Part[@Id='0']")
        if lib_part is None:
            continue
        hw = float(lib_part.get("Width", "0")) / 2
        hh = float(lib_part.get("Height", "0")) / 2
        corners = [_transform_local(part, dx, dy)
                   for dx in (-hw, hw) for dy in (-hh, hh)]
        boxes[refdes] = (
            sheet,
            px + min(c[0] for c in corners),
            py + min(c[1] for c in corners),
            px + max(c[0] for c in corners),
            py + max(c[1] for c in corners),
        )
    return boxes


def _l_path(a: tuple[float, float], b: tuple[float, float],
            first: str = "h") -> list[tuple[float, float]]:
    """L-shaped path from a to b (horizontal-first or vertical-first)."""
    mx, my = b
    if first == "h":
        return [(mx, a[1]), b]
    return [(a[0], my), b]


def route_net(endpoints: list[Endpoint],
              bodies: dict[str, tuple[int, float, float, float, float]],
              sheet: int,
              max_wire_len: float = 50.0) -> list[WireSpec]:
    """Connect same-sheet endpoints of one net with L-shaped wires.

    Uses minimum-spanning-tree-like greedy nearest-neighbour chaining.
    Cross-sheet endpoints are skipped (caller should add net labels).
    """
    local = [e for e in endpoints if e.sheet == sheet]
    if len(local) < 2:
        return []

    specs: list[WireSpec] = []
    remaining = list(local)

    # Start with the first endpoint, greedily connect nearest.
    current = remaining.pop(0)
    while remaining:
        best_idx, best_dist, best_target = -1, float("inf"), None
        for i, candidate in enumerate(remaining):
            d = math.hypot(candidate.x - current.x, candidate.y - current.y)
            if d < best_dist:
                best_dist = d
                best_idx = i
                best_target = candidate
        if best_dist > max_wire_len or best_target is None:
            break

        mid_pts = _l_path((current.x, current.y), (best_target.x, best_target.y))
        pts = [(current.x, current.y)] + [p for p in mid_pts if p != (best_target.x, best_target.y)] + [(best_target.x, best_target.y)]
        # Deduplicate consecutive identical points
        compact = tuple(p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1])
        specs.append(WireSpec(
            net="",  # filled by caller
            sheet=sheet,
            start_refdes=current.refdes,
            start_pin=current.pin,
            end_refdes=best_target.refdes,
            end_pin=best_target.pin,
            points=compact,
        ))
        current = best_target
        remaining.pop(best_idx)

    return specs


def append_wires_to_xml(doc: DipTraceDocument,
                        all_specs: list[tuple[str, WireSpec]]) -> DipTraceDocument:
    """Write WireSpec objects into the schematic XML as visible Wire elements."""
    root = doc.root
    parts_by_ref = {}
    for p_ in root.findall("./Schematic/Components/Part"):
        parts_by_ref[(p_.findtext("./RefDes") or "").casefold()] = p_
    nets_by_name = {}
    for n in root.findall("./Schematic/Nets/Net"):
        nets_by_name[(n.findtext("./Name") or "").casefold()] = n

    def endpoint_attrs(side: int, refdes: str | None, pin: int | None) -> dict[str, str]:
        if refdes is not None and pin is not None:
            part = parts_by_ref.get(refdes.casefold())
            pid = part.get("Id", "") if part is not None else "-1"
            return {f"Connected{side}": "Pin", f"Object{side}": pid,
                    f"SubObject{side}": str(pin), f"Bus{side}": "-1"}
        return {f"Connected{side}": "Free", f"Object{side}": "-1",
                f"SubObject{side}": "-1", f"Bus{side}": "-1"}

    added = 0
    for net_name, spec in all_specs:
        net_el = nets_by_name.get(net_name.casefold())
        if net_el is None:
            continue
        wires_el = net_el.find("Wires")
        if wires_el is None:
            wires_el = ET.SubElement(net_el, "Wires")
        wire_el = ET.SubElement(wires_el, "Wire", {
            "Id": str(len(wires_el.findall("Wire"))),
            "Sheet": str(spec.sheet),
            **endpoint_attrs(1, spec.start_refdes, spec.start_pin),
            **endpoint_attrs(2, spec.end_refdes, spec.end_pin),
            "HiddenPower": "N", "CanUnhide": "N",
            "Arrows": "None", "Group": "-1", "Selected": "N",
        })
        pts_el = ET.SubElement(wire_el, "Points")
        prev = None
        for pt in spec.points:
            direction = "-1"
            if prev is not None:
                direction = "0" if math.isclose(pt[1], prev[1], abs_tol=1e-6) else "1"
            ET.SubElement(pts_el, "Point",
                          {"X": f"{pt[0]:.9g}", "Y": f"{pt[1]:.9g}", "Dir": direction})
            prev = pt
        added += 1

    return DipTraceDocument.from_bytes(
        doc.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Add visual wires to schematic")
    parser.add_argument("input", type=Path)
    parser.add_argument("--max-wire-len", type=float, default=40.0,
                        help="Max wire length in mm (default 40)")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    input_path = args.input.resolve()
    output_path = (args.output or input_path).resolve()

    doc = DipTraceDocument.load(input_path, 128 * 1024 * 1024)
    endpoints = compute_endpoints(doc)
    bodies = compute_body_boxes(doc)

    # Discover sheets that have components
    sheets = set()
    for p_ in doc.root.findall("./Schematic/Components/Part"):
        sheets.add(int(p_.get("Sheet", "0")))

    all_specs: list[tuple[str, WireSpec]] = []
    total_wires = 0
    total_skipped_nets = 0

    for net_name, eps in sorted(endpoints.items()):
        if not eps or net_name.startswith(("PSG", "PWR", "NPI", "NPO")):
            continue
        for sheet in sorted(sheets):
            specs = route_net(eps, bodies, sheet, args.max_wire_len)
            for s in specs:
                all_specs.append((net_name, s))
                total_wires += 1
        # count nets where some pins are cross-sheet (no wire possible)
        sheets_with_pins = {e.sheet for e in eps}
        if len(sheets_with_pins) > 1:
            total_skipped_nets += 1

    print(f"wires generated: {total_wires}")
    print(f"nets spanning multiple sheets (need labels): {total_skipped_nets}")

    if all_specs:
        doc = append_wires_to_xml(doc, all_specs)
        output_path.write_bytes(doc.raw_bytes)
        print(f"wrote {output_path}")
    else:
        print("no wires needed")


if __name__ == "__main__":
    main()
