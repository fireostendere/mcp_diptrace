#!/usr/bin/env python3
"""Render staged DipTrace PCB XML files into a boundary-fit cinematic.

House style: black background, yellow board, dark top copper, bright pads,
green RefDes silk, gray component outlines, purple board outline. The frame
fits the purple board outline with ~10% margin and stays stable across
frames; the final frame is also written as a standalone PNG at 2x scale.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BOARD_W = 42.2
BOARD_H = 13.9
MARGIN = 0.10  # fraction of the larger board dimension
PX_PER_MM = 26  # final-frame resolution
COPPER = (52, 44, 28)
BOARD_FILL = (255, 255, 96)
PAD = (255, 255, 128)
DRILL = (25, 22, 15)
SILK_GREEN = (0, 190, 60)
SILK_GRAY = (168, 168, 168)
OUTLINE = (168, 64, 208)
VIA_RING = (255, 255, 128)


def _float(value: str | None) -> float:
    return float(value) if value else 0.0


def _parse(path: Path) -> dict:
    s = path.read_text(encoding="utf-8", errors="replace")
    out: dict = {"components": [], "traces": [], "vias": [], "pads": [],
                 "shapes": [], "pours": []}
    # nets by id
    nets: dict[str, str] = {}
    for m in re.finditer(r'<Net Id="(\d+)"[^>]*>\s*<Name>([^<]+)</Name>', s):
        nets[m.group(1)] = m.group(2)
    # components + pads
    comp_re = (r'<Component [^>]*PatternStyle="(PatType\d+)"'
               r'[^>]*? X="([-\d.e]+)" Y="([-\d.e]+)"([^>]*)>')
    for cm in re.finditer(comp_re, s):
        tail = cm.group(4)
        am = re.search(r'Angle="([-\d.e]+)"', tail)
        i = cm.end()
        refm = re.search(r'<RefDes>(\w+)</RefDes>', s[i:i + 500])
        if not refm:
            continue
        out["components"].append({
            "ref": refm.group(1), "pat": cm.group(1),
            "x": float(cm.group(2)), "y": float(cm.group(3)),
            "a": float(am.group(1)) if am else 0.0,
        })
    # patterns: shapes + pads per style
    pats = {}
    for m in re.finditer(r'<Pattern PatternStyle="(PatType\d+)"[^>]*>.*?</Pattern>', s, re.S):
        style = m.group(1)
        blk = m.group(0)
        pad_re = r'<Pad Id="(\d+)"[^>]*X="([-\d.e]+)" Y="([-\d.e]+)"'
        pads = [(str(n), float(a), float(b)) for n, a, b in re.findall(pad_re, blk)]
        shapes = []
        shape_re = (r'<Shape Id="\d+" Type="(\w+)"[^>]*Layer="([^"]+)"'
                    r'[^>]*>\s*<Points>(.*?)</Points>')
        for sm in re.finditer(shape_re, blk, re.S):
            pt_re = r'X="([-\d.e]+)" Y="([-\d.e]+)"'
            pts = [(float(a), float(b)) for a, b in re.findall(pt_re, sm.group(3))]
            shapes.append((sm.group(2), sm.group(1), pts))
        pats[style] = {"pads": pads, "shapes": shapes}
    # pad styles: name -> (w, h)
    padstyles = {}
    ps_re = (r'<PadStyle Name="(\w+)"[^>]*>\s*<MainStack Shape="Rectangle"'
             r' Width="([\d.e]+)" Height="([\d.e]+)"')
    for pm in re.finditer(ps_re, s):
        padstyles[pm.group(1)] = (float(pm.group(2)), float(pm.group(3)))
    out["pats"] = pats
    out["padstyles"] = padstyles
    # component -> pattern style + pad style
    for c in out["components"]:
        m = re.search(rf'<Component [^>]*PatternStyle="{c["pat"]}"[^>]*?>', s)
        # DefPad per pattern
        pm = re.search(rf'<Pattern PatternStyle="{c["pat"]}".*?<DefPad Style="(\w+)"', s, re.S)
        c["padstyle"] = pm.group(1) if pm else "PadT19"
    # traces (per net, with per-point widths)
    for nm in re.finditer(r'<Net Id="(\d+)"[^>]*>\s*<Name>([^<]+)</Name>.*?</Net>', s, re.S):
        net_name = nm.group(2)
        for tm in re.finditer(r'<Trace\b.*?</Trace>', nm.group(0), re.S):
            pt_re = (r'<Point Id="\d+" X="([-\d.e]+)" Y="([-\d.e]+)"'
                     r' Lay="\d*"[^>]*?(?:Width="([\d.e]+)")?[^>]*>')
            pts = [(_float(a), _float(b), _float(w)) for a, b, w in re.findall(pt_re, tm.group(0))]
            if len(pts) >= 2:
                out["traces"].append({"net": net_name, "pts": pts,
                                      "layer": "top" if 'Lay="0"' in tm.group(0) else "bottom"})
    # vias (Type=Via components)
    for vm in re.finditer(r'<Component [^>]*Type="Via"[^>]*X="([-\d.e]+)" Y="([-\d.e]+)"[^>]*>', s):
        out["vias"].append((float(vm.group(1)), float(vm.group(2))))
    # copper shapes on Top
    cs_re = (r'<Shape Id="\d+" Type="Rectangle"[^>]*Layer="Signal/Plane"'
             r'[^>]*NetId="(\d+)"[^>]*>\s*<Points>(.*?)</Points>')
    for sm in re.finditer(cs_re, s, re.S):
        pt_re = r'X="([-\d.e]+)" Y="([-\d.e]+)"'
        pts = [(_float(a), _float(b)) for a, b in re.findall(pt_re, sm.group(2))]
        if len(pts) == 2:
            out["shapes"].append({"net": nets.get(sm.group(1), "?"), "pts": pts})
    # pours (outline only; fill rendered as solid same-net copper)
    pour_re = r'<CopperPour\b[^>]*NetId="(\d+)"[^>]*Lay="0"[^>]*>(.*?)</CopperPour>'
    for pm in re.finditer(pour_re, s, re.S):
        pt_re = r'<Point X="([-\d.e]+)" Y="([-\d.e]+)"'
        pts = [(_float(a), _float(b)) for a, b in re.findall(pt_re, pm.group(2))]
        if len(pts) >= 3:
            out["pours"].append({"net": nets.get(pm.group(1), "?"), "pts": pts})
    return out


def _rot(c: dict, px: float, py: float) -> tuple[float, float]:
    ca, sa = math.cos(c["a"]), math.sin(c["a"])
    return (c["x"] + px * ca - py * sa, c["y"] + px * sa + py * ca)


def render(data: dict, out_path: Path, scale: int = 1, final: bool = False) -> None:
    ppp = PX_PER_MM * scale
    margin_mm = max(BOARD_W, BOARD_H) * MARGIN
    W = int((BOARD_W + 2 * margin_mm) * ppp)
    H = int((BOARD_H + 2 * margin_mm) * ppp)

    def T(x: float, y: float) -> tuple[float, float]:
        return ((x + margin_mm) * ppp, (BOARD_H + margin_mm - y) * ppp)

    img = Image.new("RGB", (W, H), (8, 8, 8))
    dr = ImageDraw.Draw(img)
    # board (yellow = masked GND pour, DipTrace print style)
    dr.rectangle([*T(0, BOARD_H), *T(BOARD_W, 0)], fill=BOARD_FILL)

    def poly(c: dict, pts, close=False):
        return [T(*_rot(c, x, y)) for x, y in pts]

    # solid GND copper shapes (dark against the yellow board)
    for sh in data["shapes"]:
        if sh["net"] != "GND" or len(sh["pts"]) != 2:
            continue
        (x1, y1), (x2, y2) = sh["pts"]
        dr.rectangle([*T(min(x1, x2), max(y1, y2)), *T(max(x1, x2), min(y1, y2))], fill=COPPER)
    # traces: bottom first, then top
    for layer in ("bottom", "top"):
        for tr in data["traces"]:
            if tr["layer"] != layer or tr["net"] == "GND" and layer == "bottom":
                continue
            pts = tr["pts"]
            for (ax, ay, aw), (bx, by, bw) in zip(pts, pts[1:], strict=False):
                wa = aw or bw or 0.25
                wb = bw or aw or 0.25
                color = COPPER if layer == "top" else (34, 30, 22)
                dr.line([T(ax, ay), T(bx, by)], fill=color, width=max(1, int(wa * ppp)))
                dr.ellipse([*T(ax - wa / 2, ay + wa / 2),
                            *T(ax + wa / 2, ay - wa / 2)], fill=color)
                dr.ellipse([*T(bx - wb / 2, by + wb / 2),
                            *T(bx + wb / 2, by - wb / 2)], fill=color)
    # component pads + outlines
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, int(1.1 * ppp))
    except Exception:
        font = ImageFont.load_default()
    for c in data["components"]:
        pw, ph = data["padstyles"].get(c["padstyle"], (0.6, 0.6))
        for _num, px, py in data["pats"][c["pat"]]["pads"]:
            bx, by = _rot(c, px, py)
            half_w = (pw / 2) if abs(c["a"]) < 0.1 else (ph / 2)
            half_h = (ph / 2) if abs(c["a"]) < 0.1 else (pw / 2)
            dr.rectangle([*T(bx - half_w, by + half_h), *T(bx + half_w, by - half_h)], fill=PAD)
        for layer, _styp, pts in data["pats"][c["pat"]]["shapes"]:
            coords = poly(c, pts, close=True)
            if layer == "Top Outline" and len(coords) >= 2:
                if len(coords) == 2:  # Rectangle: 2 diagonal corners
                    (ax, ay), (bx, by) = coords
                    dr.rectangle([min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)],
                                 fill=None, outline=SILK_GRAY, width=max(1, int(0.1 * ppp)))
                else:
                    dr.line(coords + [coords[0]], fill=SILK_GRAY, width=max(1, int(0.1 * ppp)))
            elif layer == "Top Silk" and len(coords) >= 2:
                dr.line(coords, fill=SILK_GRAY, width=max(1, int(0.12 * ppp)))
        # refdes
        tx, ty = T(c["x"], c["y"] - 2.2)
        dr.text((tx, ty), c["ref"], font=font, fill=SILK_GREEN, anchor="mm")
    # vias on top
    for vx, vy in data["vias"]:
        r = 0.3 * ppp
        cx, cy = T(vx, vy)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=VIA_RING)
        dr.ellipse([cx - 0.55 * r, cy - 0.55 * r, cx + 0.55 * r, cy + 0.55 * r], fill=DRILL)
    # purple board outline
    dr.rectangle([*T(0, BOARD_H), *T(BOARD_W, 0)], outline=OUTLINE, width=max(2, int(0.12 * ppp)))

    img.save(out_path)


def main() -> int:
    stage_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    # Construction order of the build stages (build_pcb.py ATTINY_STAGE_DIR).
    order = [
        "01_manual",
        "02_TPS_FB", "02_TPS_PG", "02_CP2102_VBUS", "02_VBUS",
        "02_USB_D-", "02_USB_Dp", "02_p3V3",
        "02_PB1_MISO", "02_PB0_MOSI", "02_PB2_SCK", "02_RESET",
        "02_CP2102_RXD", "02_CP2102_TXD", "02_CP2102_DTR", "02_GND",
        "90_pours", "99_final",
    ]
    rank = {name: i for i, name in enumerate(order)}
    stages = sorted(
        (p for p in stage_dir.glob("*.dipxml")),
        key=lambda p: rank.get(p.stem, len(rank)),
    )
    if not stages:
        print("no stages", file=sys.stderr)
        return 1
    frames = []
    for i, stage in enumerate(stages):
        data = _parse(stage)
        frame = out_dir / f"frame_{i:02d}_{stage.stem}.png"
        render(data, frame)
        frames.append((frame, stage.stem))
        print(f"{frame.name}: {len(data['components'])} comps, "
              f"{len(data['traces'])} traces", flush=True)
    # final PNG at 2x
    data = _parse(stages[-1])
    render(data, out_dir / "attiny85-arduino-clone-pcb.png", scale=2, final=True)
    # GIF: hold the first frame, 0.9s per stage, hold the final for 2.5s
    from PIL import Image as PILImage
    imgs = [PILImage.open(f) for f, _ in frames]
    durations = [1500] + [900] * (len(imgs) - 2) + [2500]
    imgs[0].save(out_dir / "attiny85-arduino-clone-pcb.gif", save_all=True,
                 append_images=imgs[1:], duration=durations, loop=0, optimize=True)
    # MP4 via imageio-ffmpeg
    try:
        import imageio.v2 as imageio
        import numpy as np
        with imageio.get_writer(out_dir / "attiny85-arduino-clone-pcb.mp4", fps=2, codec="libx264",
                                quality=8, macro_block_size=1) as w:
            for img in imgs:
                w.append_data(np.asarray(img))
            for _ in range(5):
                w.append_data(np.asarray(imgs[-1]))
    except Exception as exc:
        print(f"mp4 skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
