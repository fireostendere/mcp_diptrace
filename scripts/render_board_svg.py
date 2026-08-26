#!/usr/bin/env python3
"""Render the Rev.A PCB to standalone SVG previews (Top / Bottom).

No external deps: parses dut-controller-reva-pcb.dipxml directly.
Output: dut-controller-reva-pcb-top.svg / -bottom.svg / preview.html
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "dut-controller-reva-pcb.dipxml"
SCALE = 12          # px per mm
MARGIN = 3          # mm

TOP_COPPER = "#cc2222"
BOT_COPPER = "#2255cc"
PAD_TOP = "#ff5533"
PAD_BOT = "#5588ff"
PAD_THT = "#22aa44"
POUR_TOP_FILL = "#cc222218"
POUR_BOT_FILL = "#2255cc18"
BODY_STROKE = "#888"


def fmt(v: float) -> str:
    return f"{v:.2f}"


def load(root):
    board = root.find("./Board")
    outline = [tuple(map(float, p_.attrib["X"].split()) ) for p_ in []]  # placeholder
    pts = [(float(p_.get("X")), float(p_.get("Y"))) for p_ in board.find("./BoardOutline/Points")]
    # patterns & pad styles
    patterns = {}
    for pat in root.iter("Pattern"):
        style = pat.get("PatternStyle")
        pads = []
        for pd_ in pat.findall("./Pads/Pad"):
            stl = pd_.get("Style")
            pads.append({
                "id": pd_.get("Id"),
                "x": float(pd_.get("X", "0")),
                "y": float(pd_.get("Y", "0")),
                "through": False,
                "w": 0.6, "h": 0.6, "shape": "Circle",
            })
        shapes = {"outline": None, "courtyard": None}
        for sh in pat.findall("./Shapes/Shape"):
            layer = sh.get("Layer", "")
            pts2 = [(float(p_.get("X")), float(p_.get("Y")))
                    for p_ in sh.find("./Points")] if sh.find("./Points") is not None else []
            if "Courtyard" in layer and pts2:
                xs = [p_[0] for p_ in pts2]; ys = [p_[1] for p_ in pts2]
                shapes["courtyard"] = (min(xs), min(ys), max(xs), max(ys))
        patterns[style] = {"pads": pads, **shapes}
    for ps in root.iter("PadStyle"):
        name = ps.get("Name")
        ms = ps.find("./MainStack")
        if ms is None:
            continue
        through = ps.get("Type") == "Through"
        for pat in patterns.values():
            for pd_ in pat["pads"]:
                pass
    # attach pad geometry via style lookup dict
    styles = {}
    for ps in root.iter("PadStyle"):
        ms = ps.find("./MainStack")
        if ms is None:
            continue
        styles[ps.get("Name")] = {
            "w": float(ms.get("Width", "0.6")),
            "h": float(ms.get("Height", "0.6")),
            "shape": ms.get("Shape", "Rectangle"),
            "through": ps.get("Type") == "Through",
        }
    for pat in patterns.values():
        for pd_ in pat["pads"]:
            st = styles.get(pd_.get("_style_placeholder", ""), None)
    # second pass with real style names stored during first parse
    return board, pts, patterns, styles


def main() -> None:
    root = ET.parse(BOARD).getroot()
    board_el = root.find("./Board")

    # --- patterns with real pad styles ------------------------------------
    styles = {}
    for ps in root.iter("PadStyle"):
        ms = ps.find("./MainStack")
        if ms is not None:
            styles[ps.get("Name")] = {
                "w": float(ms.get("Width", "0.6")),
                "h": float(ms.get("Height", "0.6")),
                "shape": ms.get("Shape", "Rectangle"),
                "through": ps.get("Type") == "Through",
            }
    patterns = {}
    for pat in root.iter("Pattern"):
        style = pat.get("PatternStyle")
        pads = []
        for pd_ in pat.findall("./Pads/Pad"):
            st = styles.get(pd_.get("Style"), {})
            pads.append({
                "id": pd_.get("Id"),
                "x": float(pd_.get("X", "0")),
                "y": float(pd_.get("Y", "0")),
                "w": st.get("w", 0.6),
                "h": st.get("h", 0.6),
                "ellipse": st.get("shape") in ("Ellipse", "Circle"),
                "through": st.get("through", False),
                "number": (pd_.findtext("./Number") or "").strip(),
            })
        courtyard = None
        for sh in pat.findall("./Shapes/Shape"):
            if "Courtyard" in (sh.get("Layer") or "") and sh.find("./Points") is not None:
                cs = [(float(p_.get("X")), float(p_.get("Y"))) for p_ in sh.find("./Points")]
                xs = [c[0] for c in cs]; ys = [c[1] for c in cs]
                courtyard = (min(xs), min(ys), max(xs), max(ys))
        patterns[style] = {"pads": pads, "courtyard": courtyard}

    # --- components ---------------------------------------------------------
    comps = []
    for c in board_el.find("./Components"):
        refdes = c.findtext("./RefDes") or ""
        style = c.get("PatternStyle")
        comps.append({
            "refdes": refdes,
            "x": float(c.get("X", "0")),
            "y": float(c.get("Y", "0")),
            "ang": math.degrees(float(c.get("Angle", "0"))),
            "side": c.get("Side", "Top"),
            "pat": patterns.get(style, {"pads": [], "courtyard": None}),
            "pads": {pd_.get("Id"): (pd_.findtext("./Number") or "").strip()
                     for pd_ in c.findall("./Pads/Pad")},
        })

    # --- nets: traces & pour polygons ---------------------------------------
    traces = []      # (net, lay, width, [(x,y)...])
    vias = []        # (x, y)
    for net in board_el.findall("./Nets/Net"):
        name = net.findtext("./Name") or ""
        for tr in net.find("./Traces") or []:
            run_lay, run_w, run_pts = None, None, []
            for p_ in tr.find("./Points"):
                lay = int(p_.get("Lay", "0"))
                w = float(p_.get("Width", "0.25"))
                xy = (float(p_.get("X")), float(p_.get("Y")))
                if p_.get("ViaStyle", "-1") not in ("-1", None):
                    vias.append(xy)
                if run_lay is None:
                    run_lay, run_w = lay, w
                elif lay != run_lay or w != run_w:
                    if len(run_pts) >= 2:
                        traces.append((name, run_lay, run_w, run_pts))
                    run_lay, run_w = lay, w
                    run_pts = [run_pts[-1]] if run_pts else []
                run_pts.append(xy)
            if len(run_pts) >= 2:
                traces.append((name, run_lay, run_w, run_pts))

    pours = []       # (lay, [(x,y)...])
    for pour in board_el.findall("./CopperPours/CopperPour"):
        lay = int(pour.get("Lay", "0"))
        pts = [(float(p_.get("X")), float(p_.get("Y")))
               for p_ in pour.find("./Points")]
        if len(pts) >= 3:
            pours.append((lay, pts))

    outline = [(float(p_.get("X")), float(p_.get("Y")))
               for p_ in board_el.find("./BoardOutline/Points")]

    xs = [p[0] for p in outline]; ys = [p[1] for p in outline]
    min_x, min_y = min(xs) - MARGIN, min(ys) - MARGIN
    W, H = (max(xs) - min_x + MARGIN), (max(ys) - min_y + MARGIN)

    def T(x, y, mirror=False):
        px = (x - min_x) * SCALE
        py = (y - min_y) * SCALE
        if mirror:
            px = W * SCALE - px
        return px, py

    def emit(side: str, path: Path) -> None:
        mirror = side == "Bottom"
        s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*SCALE:.0f}" '
             f'height="{H*SCALE:.0f}" viewBox="0 0 {W*SCALE:.0f} {H*SCALE:.0f}">',
             f'<rect width="100%" height="100%" fill="#111"/>',
             f'<g transform="translate({MARGIN*SCALE:.0f},{MARGIN*SCALE:.0f})">']
        # local helper inside translated frame
        def t(x, y):
            px, py = T(x, y, mirror)
            return px - MARGIN*SCALE, py - MARGIN*SCALE

        o = " ".join(f"{fmt(px)},{fmt(py)}" for px, py in (t(*p) for p in outline))
        s.append(f'<polygon points="{o}" fill="#1a1a1a" stroke="#e0e0e0" stroke-width="2"/>')

        lay_idx = 1 if mirror else 0
        pour_fill = POUR_BOT_FILL if mirror else POUR_TOP_FILL
        for ply, pts_p in pours:
            if ply != lay_idx:
                continue
            o = " ".join(f"{fmt(px)},{fmt(py)}" for px, py in (t(*p) for p in pts_p))
            s.append(f'<polygon points="{o}" fill="{pour_fill}" stroke="none"/>')

        copper = BOT_COPPER if mirror else TOP_COPPER
        for _net, lay, w, pts_t in traces:
            if lay != lay_idx:
                continue
            d = " ".join(f"{fmt(px)},{fmt(py)}" for px, py in (t(*p) for p in pts_t))
            s.append(f'<polyline points="{d}" fill="none" stroke="{copper}" '
                     f'stroke-width="{w*SCALE:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')

        # pads & bodies
        for c in comps:
            bottom_side = (c["side"] == "Bottom")
            visible = bottom_side == mirror
            a = math.radians(c["ang"])
            ca, sa = math.cos(a), math.sin(a)
            def xf(px_, py_, flip_local=False):
                lx, ly = px_, py_
                if bottom_side:
                    lx = -lx          # bottom-side footprint mirrors X
                rx = lx * ca - ly * sa
                ry = lx * sa + ly * ca
                return t(c["x"] + rx, c["y"] + ry)
            for pd_ in c["pat"]["pads"]:
                number = c["pads"].get(pd_["id"], "")
                px, py = xf(pd_["x"], pd_["y"])
                if pd_["through"]:
                    color, r = PAD_THT, max(pd_["w"], pd_["h"]) / 2
                    s.append(f'<circle cx="{fmt(px)}" cy="{fmt(py)}" r="{fmt(r*SCALE)}" fill="{color}"/>')
                    continue
                show = visible or pd_["through"]
                if not show:
                    continue
                color = PAD_BOT if bottom_side else PAD_TOP
                half_w, half_h = pd_["w"] / 2, pd_["h"] / 2
                if pd_["ellipse"]:
                    s.append(f'<circle cx="{fmt(px)}" cy="{fmt(py)}" '
                             f'r="{fmt(max(half_w, half_h)*SCALE)}" fill="{color}"/>')
                else:
                    ang = c["ang"] + (math.pi if bottom_side else 0)
                    s.append(f'<rect x="{fmt(px-half_w*SCALE)}" y="{fmt(py-half_h*SCALE)}" '
                             f'width="{fmt(pd_["w"]*SCALE)}" height="{fmt(pd_["h"]*SCALE)}" '
                             f'fill="{color}" transform="rotate({math.degrees(ang):.2f},'
                             f'{fmt(px)},{fmt(py)})"/>')
            cy_box = c["pat"].get("courtyard")
            if cy_box and visible:
                x0, y0, x1, y1 = cy_box
                pa = t(c["x"] + x0, c["y"] + y0)
                pb = t(c["x"] + x1, c["y"] + y1)
                s.append(f'<rect x="{fmt(min(pa[0],pb[0]))}" y="{fmt(min(pa[1],pb[1]))}" '
                         f'width="{fmt(abs(pb[0]-pa[0]))}" height="{fmt(abs(pb[1]-pa[1]))}" '
                         f'fill="none" stroke="{BODY_STROKE}" stroke-width="1" opacity="0.7"/>')
                cx, cy = t(c["x"], c["y"])
                label = f'{c["refdes"]}'
                s.append(f'<text x="{fmt(cx)}" y="{fmt(cy)}" font-size="11" fill="#fff" '
                         f'text-anchor="middle" dominant-baseline="middle" '
                         f'transform="rotate({0 if not mirror else 180},{fmt(cx)},{fmt(cy)})">{label}</text>')

        for vx, vy in vias:
            px, py = t(vx, vy)
            s.append(f'<circle cx="{fmt(px)}" cy="{fmt(py)}" r="{fmt(0.45*SCALE)}" '
                     f'fill="none" stroke="#dddddd" stroke-width="2"/>')

        s.append(f'<text x="10" y="20" font-size="16" fill="#fff">{path.stem}</text>')
        s.append("</g></svg>")
        path.write_text("\n".join(s), encoding="utf-8")
        print(f"wrote {path} ({path.stat().st_size//1024} KB)")

    emit("Top", ROOT / "dut-controller-reva-pcb-top.svg")
    emit("Bottom", ROOT / "dut-controller-reva-pcb-bottom.svg")

    html = f'''<!doctype html><html><head><meta charset="utf-8">
<title>DUT Controller Rev.A preview</title>
<style>body{{background:#000;color:#eee;font-family:sans-serif;margin:0;padding:10px}}
img{{max-width:100%;border:1px solid #444;margin-bottom:10px}}</style></head><body>
<h2>Top</h2><img src="dut-controller-reva-pcb-top.svg">
<h2>Bottom (mirrored)</h2><img src="dut-controller-reva-pcb-bottom.svg">
</body></html>'''
    (ROOT / "dut-controller-reva-preview.html").write_text(html, encoding="utf-8")
    print("wrote dut-controller-reva-preview.html")


if __name__ == "__main__":
    main()
