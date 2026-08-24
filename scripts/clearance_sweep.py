"""Precise geometric clearance sweep of the built board (shapely).

Mirrors the native DipTrace DRC categories so build-side fixes are targeted:
via/pad, drill/pad, trace/trace, trace/pad, outline/trace, silk/pad.
Foreign-net pairs only; same-net copper is legal overlap.

Usage:
    PYTHONPATH=src python scripts/clearance_sweep.py [board.dipxml] [--clearance 0.13]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shapely.geometry import LineString, Point as ShPoint, Polygon, box  # noqa: E402

from diptrace_mcp.adapters import build_snapshot  # noqa: E402
from diptrace_mcp.xml_document import DipTraceDocument  # noqa: E402


def _pad_shape(pad) -> Polygon | None:
    if pad.geometry is not None:
        try:
            return Polygon(pad.geometry)
        except Exception:
            pass
    bb = pad.bbox
    if bb is None:
        return None
    return box(bb["min_x"], bb["min_y"], bb["max_x"], bb["max_y"])


def _via_shape(via) -> Polygon | None:
    if via.geometry is not None:
        try:
            return Polygon(via.geometry)
        except Exception:
            pass
    style = via.attributes.get("via_style") or {}
    diameter = style.get("diameter_mm") if isinstance(style, dict) else None
    radius = (float(diameter) if diameter else 0.6) / 2.0
    return ShPoint(via.position["x"], via.position["y"]).buffer(radius)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", nargs="?",
                        default="attiny85-arduino-clone/attiny85-arduino-clone-pcb.dipxml")
    parser.add_argument("--clearance", type=float, default=0.13)
    args = parser.parse_args()

    doc = DipTraceDocument.load(Path(args.board), max_bytes=20_000_000)
    snap = build_snapshot(doc)
    b = snap.board
    assert b is not None
    nets_by_id = {i: net.name for i, net in enumerate(b.nets)}
    comps = {c.stable_id: c.refdes for c in b.components}

    def net_name(record) -> str | None:
        raw = record.net_id
        try:
            return nets_by_id.get(int(raw))
        except (TypeError, ValueError):
            return None

    pads = [
        (f"{comps.get(p.parent_id, '?')}.{p.label}", net_name(p), _pad_shape(p))
        for p in b.pads
    ]
    pads = [entry for entry in pads if entry[2] is not None]
    vias = [
        (f"via({v.position['x']:.2f},{v.position['y']:.2f})", net_name(v), _via_shape(v))
        for v in b.vias
    ]
    vias = [entry for entry in vias if entry[2] is not None]

    traces: list[tuple[str, str | None, object, str]] = []
    for t in b.traces:
        pts = t.attributes.get("points") or []
        widths = t.attributes.get("segment_widths_mm") or []
        layers = t.attributes.get("segment_layers") or []
        tname = f"{net_name(t)}:{t.stable_id[-6:]}"
        for i in range(len(pts) - 1):
            width = float(widths[i]) if i < len(widths) else float(t.width or 0.25)
            layer = layers[i] if i < len(layers) else str(t.layer or "")
            shape = LineString(
                [(pts[i]["x"], pts[i]["y"]), (pts[i + 1]["x"], pts[i + 1]["y"])]
            ).buffer(width / 2.0)
            traces.append((f"{tname}[{i}]", net_name(t), shape, layer))

    findings: list[str] = []

    for vname, vnet, vshape in vias:
        for pname, pnet, pshape in pads:
            if vnet and pnet and vnet == pnet:
                continue
            gap = vshape.distance(pshape)
            if gap < args.clearance:
                findings.append(f"via/pad: {vname} <-> {pname} gap={gap:.4f}")

    for h in b.holes:
        diameter = h.attributes.get("diameter")
        radius = (float(diameter) if diameter else 0.8) / 2.0
        hshape = ShPoint(h.position["x"], h.position["y"]).buffer(radius)
        for pname, _pnet, pshape in pads:
            gap = hshape.distance(pshape)
            if gap < args.clearance:
                findings.append(
                    f"drill/pad: drill({h.position['x']:.2f},{h.position['y']:.2f}) "
                    f"<-> {pname} gap={gap:.4f}"
                )

    for i, (tname, tnet, tshape, tlayer) in enumerate(traces):
        for tname2, tnet2, tshape2, tlayer2 in traces[i + 1:]:
            if tlayer != tlayer2:
                continue
            if tnet and tnet2 and tnet == tnet2:
                continue
            gap = tshape.distance(tshape2)
            if gap < args.clearance:
                findings.append(f"trace/trace: {tname} <-> {tname2} gap={gap:.4f}")

    for tname, tnet, tshape, _layer in traces:
        for pname, pnet, pshape in pads:
            if tnet and pnet and tnet == pnet:
                continue
            gap = tshape.distance(pshape)
            if gap < args.clearance:
                findings.append(f"trace/pad: {tname} <-> {pname} gap={gap:.4f}")

    outline = b.outline
    if outline is not None:
        ring = LineString([(p["x"], p["y"]) for p in outline["points"]])
        for tname, _tnet, tshape, _layer in traces:
            gap = tshape.distance(ring)
            if gap < args.clearance:
                findings.append(f"outline/trace: {tname} gap={gap:.4f}")

    for t in b.texts:
        if "Silk" not in (t.layer or ""):
            continue
        if (t.attributes.get("Show") or "Show") == "Hide":
            continue
        bb = t.bbox
        if bb is None:
            continue
        tshape = box(bb["min_x"], bb["min_y"], bb["max_x"], bb["max_y"])
        for pname, _pnet, pshape in pads:
            if tshape.distance(pshape) < args.clearance:
                label = str(t.attributes.get("Text") or t.attributes.get("text") or "?")
                findings.append(f"silk/pad: '{label}' <-> {pname}")

    print(f"findings: {len(findings)}")
    for line in findings:
        print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
