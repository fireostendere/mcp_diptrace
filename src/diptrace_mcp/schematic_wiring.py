"""Reusable schematic wiring utilities extracted from proven board builds.

Sources:
  - attiny85-arduino-clone/layout_and_wire.py (1356 lines, textbook-quality)
  - dut-controller-reva scripts/wire_schematic.py (greedy chaining)

Usage:
    from diptrace_mcp.schematic_wiring import (
        SchematicWireBuilder, compute_endpoints, compute_body_boxes
    )
    wb = SchematicWireBuilder(document)
    wb.add_ground_symbols(groups)
    wb.add_net_ports(labels)
    wb.add_wires(specs)
    wb.center_sheets()
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from diptrace_mcp.xml_document import DipTraceDocument


@dataclass(frozen=True)
class Endpoint:
    refdes: str
    pin: int
    sheet: int
    x: float
    y: float
    dx: float
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


def _transform_local(part: ET.Element, x: float, y: float) -> tuple[float, float]:
    ang = math.radians(float(part.get("Angle", "0")))
    return (x * math.cos(ang) - y * math.sin(ang),
            x * math.sin(ang) + y * math.cos(ang))


def compute_endpoints(doc: DipTraceDocument) -> dict[str, list[Endpoint]]:
    """net_name → list of absolute pin endpoints."""
    root = doc.root
    style_map = {c.get("ComponentStyle"): c for c in root.findall("./Library/Components/Component")}
    net_names = {n.get("Id", ""): n.findtext("./Name") or ""
                 for n in root.findall("./Schematic/Nets/Net")}
    result = {v: [] for v in net_names.values()}
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        sheet = int(part.get("Sheet", "0"))
        px, py = float(part.get("X", "0")), float(part.get("Y", "0"))
        lib_comp = style_map.get(part.get("ComponentStyle"))
        if lib_comp is None:
            continue
        lp_all = (lib_comp.find("./Part[@Id='0']") or lib_comp.find("./Part"))
        if lp_all is None:
            continue
        lib_pins = lp_all.findall("./Pins/Pin")
        for idx, pp in enumerate(part.findall("./Pins/Pin")):
            nid = pp.get("NetId", "-1")
            if nid == "-1" or idx >= len(lib_pins):
                continue
            lp = lib_pins[idx]
            ang = math.radians(float(lp.get("Orientation", "0")))
            ddx, ddy = -math.cos(ang), math.sin(ang)
            length = float(lp.get("Length", "0"))
            lx = float(lp.get("X", "0")) + ddx * length
            ly = float(lp.get("Y", "0")) + ddy * length
            ox, oy = _transform_local(part, lx, ly)
            rdx, rdy = _transform_local(part, ddx, ddy)
            result.setdefault(net_names.get(nid, ""), []).append(
                Endpoint(refdes, idx, sheet, px + ox, py + oy, rdx, rdy))
    return result


def compute_body_boxes(doc: DipTraceDocument) -> dict[str, tuple[int, float, float, float, float]]:
    root = doc.root
    style_map = {c.get("ComponentStyle"): c for c in root.findall("./Library/Components/Component")}
    boxes = {}
    for part in root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        lc = style_map.get(part.get("ComponentStyle"))
        if lc is None:
            continue
        lp = lc.find("./Part[@Id='0']") or lc.find("./Part")
        if lp is None:
            continue
        px, py = float(part.get("X", "0")), float(part.get("Y", "0"))
        hw = float(lp.get("Width", "0")) / 2
        hh = float(lp.get("Height", "0")) / 2
        corners = [_transform_local(part, dx, dy) for dx in (-hw, hw) for dy in (-hh, hh)]
        boxes[refdes] = (
            int(part.get("Sheet", "0")),
            px + min(c[0] for c in corners), py + min(c[1] for c in corners),
            px + max(c[0] for c in corners), py + max(c[1] for c in corners),
        )
    return boxes


class SchematicWireBuilder:
    """High-level API to add visual wires to a DipTrace schematic."""

    def __init__(self, document: DipTraceDocument):
        self.doc = document
        self.endpoints = compute_endpoints(document)
        self.bodies = compute_body_boxes(document)
        self._index = {
            (ep.refdes, ep.pin): ep
            for eps in self.endpoints.values() for ep in eps
        }
        self._specs: list[tuple[str, WireSpec]] = []

    def wire(self, net: str, start: tuple[str, int], end: tuple[str, int],
             *waypoints: tuple[float, float]) -> WireSpec:
        a = self._index[start]
        b = self._index[end]
        pts = [(a.x, a.y), *[w for w in waypoints if w != (b.x, b.y)], (b.x, b.y)]
        compact = tuple(p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1])
        spec = WireSpec(net, a.sheet, start[0], start[1], end[0], end[1], compact)
        self._specs.append((net, spec))
        return spec

    def auto_chain(self, net: str, max_len: float = 40.0) -> int:
        """Greedy nearest-neighbour chaining for all same-sheet pins of a net."""
        import random
        random.seed(42)
        eps = [e for e in self.endpoints.get(net, [])]
        if len(eps) < 2:
            return 0
        by_sheet: dict[int, list[Endpoint]] = {}
        for e in eps:
            by_sheet.setdefault(e.sheet, []).append(e)
        count = 0
        for sheet, local in by_sheet.items():
            pool = sorted(local, key=lambda e: (e.x, e.y))
            while len(pool) > 1:
                cur = pool.pop(0)
                best_i, best_d = -1, float("inf")
                for i, c in enumerate(pool):
                    d = math.hypot(c.x - cur.x, c.y - cur.y)
                    if d < best_d:
                        best_i, best_d = i, d
                if best_i < 0 or best_d > max_len:
                    break
                tgt = pool.pop(best_i)
                mids = [(tgt.x, cur.y)] if abs(tgt.y - cur.y) > 0.01 and abs(tgt.x - cur.x) > 0.01 else []
                pts = [(cur.x, cur.y)] + [m for m in mids if m != (tgt.x, tgt.y)] + [(tgt.x, tgt.y)]
                compact = tuple(p for i_, p in enumerate(pts) if i_ == 0 or p != pts[i_ - 1])
                self._specs.append((net, WireSpec(net, sheet, cur.refdes, cur.pin,
                                                   tgt.refdes, tgt.pin, compact)))
                count += 1
        return count

    def commit(self) -> DipTraceDocument:
        """Write all accumulated wires into the XML."""
        root = self.doc.root
        parts_by_ref = {(p_.findtext("./RefDes") or "").casefold(): p_
                        for p_ in root.findall("./Schematic/Components/Part")}
        nets_by_name = {(n.findtext("./Name") or "").casefold(): n
                        for n in root.findall("./Schematic/Nets/Net")}

        def ea(side: int, rd: str | None, pn: int | None):
            if rd and pn is not None:
                part = parts_by_ref.get(rd.casefold())
                pid = part.get("Id", "") if part else "-1"
                return {f"Connected{side}": "Pin", f"Object{side}": pid,
                        f"SubObject{side}": str(pn), f"Bus{side}": "-1"}
            return {f"Connected{side}": "Free", f"Object{side}": "-1",
                    f"SubObject{side}": "-1", f"Bus{side}": "-1"}

        for net_name, spec in self._specs:
            nel = nets_by_name.get(net_name.casefold())
            if nel is None:
                continue
            ws = nel.find("Wires")
            if ws is None:
                ws = ET.SubElement(nel, "Wires")
            w = ET.SubElement(ws, "Wire", {
                "Id": str(len(ws.findall("Wire"))),
                "Sheet": str(spec.sheet),
                **ea(1, spec.start_refdes, spec.start_pin),
                **ea(2, spec.end_refdes, spec.end_pin),
                "HiddenPower": "N", "CanUnhide": "N",
                "Arrows": "None", "Group": "-1", "Selected": "N",
            })
            pe = ET.SubElement(w, "Points")
            prev = None
            for pt in spec.points:
                direction = "-1"
                if prev is not None:
                    direction = "0" if math.isclose(pt[1], prev[1], abs_tol=1e-6) else "1"
                ET.SubElement(pe, "Point",
                              {"X": f"{pt[0]:.9g}", "Y": f"{pt[1]:.9g}", "Dir": direction})
                prev = pt
        return DipTraceDocument.from_bytes(
            self.doc.path,
            ET.tostring(root, encoding="utf-8", xml_declaration=True))
