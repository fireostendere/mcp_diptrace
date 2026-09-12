"""High-level DUT-controller / generic board build pipeline.

Each function is self-contained and takes explicit paths + parameters.
They wrap logic proven in scripts/lcsc_library.py, scripts/nativeize_reva.py,
scripts/render_board_svg.py and the Rev.A builder.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 1. LCSC/EasyEDA component sourcing
# ---------------------------------------------------------------------------

def lcsc_fetch(mpn_or_code: str, output_dir: str) -> dict[str, Any]:
    """Resolve MPN → LCSC code → download component JSON + datasheet PDF."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    query = mpn_or_code.strip()

    # resolve MPN -> LCSC code
    if not re.fullmatch(r"C[0-9]{4,8}", query):
        html = _curl(f"https://html.duckduckgo.com/html/?q={query}+lcsc+product-detail")
        m = re.search(r"lcsc\.com/product-detail/(C[0-9]{5,8})\.html", html)
        if m:
            code = m.group(1)
        else:
            code = _jlc_search(query) or ""
            if not code:
                raise ValueError(f"Cannot resolve {query!r} to an LCSC code")
    else:
        code = query

    # product page -> uuids
    html = _curl(f"https://www.lcsc.com/product-detail/{code}.html")
    uuids = list(dict.fromkeys(re.findall(r"component_svgs/prod/([a-f0-9]{32})", html)))
    pdf_m = re.search(r'"pdfUrl":"(https://datasheet\.lcsc\.com/[^"]+)"', html)

    # EasyEDA API: pick combined doc (has packageDetail)
    payload = None
    for uuid in uuids:
        raw = _curl(f"https://easyeda.com/api/components/{uuid}")
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        r = d.get("result") or {}
        if r.get("packageDetail"):
            payload = d
            break
        time.sleep(0.3)
    if payload is None:
        raise ValueError(f"{code}: no combined EasyEDA document found")

    json_path = out / f"{code}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    pdf_path = None
    if pdf_m:
        pdf_path = out / f"{code}.pdf"
        _download(pdf_m.group(1), pdf_path)

    result = payload["result"]
    pin_count = sum(1 for s in result["dataStr"]["shape"] if s.startswith("P~"))
    pad_count = sum(
        1 for s in result["packageDetail"]["dataStr"]["shape"]
        if s.startswith("PAD") or s.startswith("PAD,")
    )
    return {
        "code": code,
        "mpn": result.get("title"),
        "package": result["packageDetail"].get("title"),
        "pins": pin_count,
        "pads": pad_count,
        "json": str(json_path),
        "datasheet": str(pdf_path) if pdf_path else None,
    }


def _curl(url: str) -> str:
    r = subprocess.run(
        ["curl", "-sS", "-L", "-m", "40", "-A", "Mozilla/5.0", "--", url],
        capture_output=True,
        text=True,
        check=True,
    )
    return r.stdout


def _download(url: str, dest: Path) -> None:
    subprocess.run(
        ["curl", "-sS", "-L", "-m", "60", "-A", "Mozilla/5.0", "-o", str(dest), "--", url],
        check=True,
    )


def _jlc_search(query: str) -> str | None:
    body = json.dumps({"keyword": query, "currentPage": 1, "pageSize": 3})
    try:
        raw = subprocess.run(
            [
                "curl", "-sS", "-m", "25", "-X", "POST",
                "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",
                "-H", "Content-Type: application/json", "-d", body,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        items = json.loads(raw.stdout)["data"]["componentPageInfo"]["list"] or []
        for it in items:
            model = str(it.get("componentModelEn") or "").upper()
            if model == query.upper():
                val = it.get("componentCode")
                return str(val) if val is not None else None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 2. Nativeize: transplant generated content into a native template
# ---------------------------------------------------------------------------

def nativeize_document(input_path: str, template_path: str, output_path: str) -> dict[str, Any]:
    """Transplant generated content into a DipTrace-native template so the
    real editor parses it without hanging."""

    src = Path(input_path).resolve()
    tpl_p = Path(template_path).resolve()
    dst = Path(output_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    kind = _detect_kind(src)
    tkind = _detect_kind(tpl_p)
    if kind != tkind:
        raise ValueError(f"Kind mismatch: input={kind}, template={tkind}")

    tpl = ET.parse(tpl_p).getroot()
    mine = ET.parse(src).getroot()

    if kind == "schematic":
        _graft_schematic(tpl, mine)
    elif kind == "pcb":
        _graft_pcb(tpl, mine)
    else:
        raise ValueError(f"Unsupported kind: {kind}")

    # Force mm units so injected coordinates are interpreted correctly.
    tpl.set("Units", "mm")
    lib = tpl.find("./Library")
    if lib is not None:
        lib.set("Units", "mm")
        sub = lib.find("./Library")
        if sub is not None:
            sub.set("Units", "mm")

    ET.indent(tpl, space="  ")
    dst.write_bytes(ET.tostring(tpl, encoding="utf-8", xml_declaration=True))
    return {
        "ok": True,
        "input": str(src),
        "template": str(tpl_p),
        "output": str(dst),
        "kind": kind,
    }


def _detect_kind(path: Path) -> str:
    root = ET.parse(path).getroot()
    t = root.get("Type", "")
    if "Schematic" in t:
        return "schematic"
    if "PCB" in t:
        return "pcb"
    return "unknown"


def _graft_schematic(tpl: ET.Element, mine: ET.Element) -> None:
    tlib = tpl.find("./Library")
    if tlib is None:
        return
    mlib = mine.find("./Library")
    plib_t = tlib.find("./Library")
    plib_m = mlib.find("./Library") if mlib is not None else None
    if plib_t is not None:
        for tag in ("PadStyles", "Patterns"):
            holder = plib_t.find(tag)
            if holder is not None:
                for c in list(holder):
                    holder.remove(c)
                if plib_m is not None:
                    src_el = plib_m.find(tag)
                    if src_el is not None:
                        for c in src_el:
                            holder.append(copy.deepcopy(c))
    comps_t = tlib.find("Components")
    if comps_t is not None:
        for c in list(comps_t):
            comps_t.remove(c)
        if mlib is not None:
            for c in mlib.findall("./Components/Component"):
                comps_t.append(copy.deepcopy(c))

    sch_t = tpl.find("./Schematic")
    sch_m = mine.find("./Schematic")
    if sch_t is None or sch_m is None:
        return
    comps_ct = sch_t.find("./Components")
    sch_m_comps = sch_m.find("./Components")
    if comps_ct is not None and sch_m_comps is not None:
        for c in list(comps_ct):
            comps_ct.remove(c)
        for p in sch_m_comps:
            comps_ct.append(copy.deepcopy(p))

    nets_t = sch_t.find("./Nets")
    mnets = sch_m.find("./Nets")
    if nets_t is not None:
        for n in list(nets_t):
            nets_t.remove(n)
        if mnets is not None:
            for n in mnets:
                nets_t.append(copy.deepcopy(n))


def _graft_pcb(tpl: ET.Element, mine: ET.Element) -> None:
    tboard = tpl.find("./Board")
    mboard = mine.find("./Board")
    if tboard is None or mboard is None:
        return

    # outline
    tout = tboard.find("./BoardOutline/Points")
    minel = mboard.find("./BoardOutline/Points")
    if tout is not None and minel is not None:
        for c in list(tout):
            tout.remove(c)
        for p_ in minel:
            tout.append(copy.deepcopy(p_))

    # library patterns/pad styles
    def get_lib(el: ET.Element) -> tuple[ET.Element | None, ET.Element | None]:
        sub = el.find("./Library/Library")
        if sub is None:
            return None, None
        return sub.find("PadStyles"), sub.find("Patterns")

    tp, tpat = get_lib(tpl)
    mp, mpat = get_lib(mine)
    for h in (tp, tpat):
        if h is not None:
            for c in list(h):
                h.remove(c)
    for h_src, h_dst in ((mp, tp), (mpat, tpat)):
        if h_src is not None and h_dst is not None:
            for c in h_src:
                h_dst.append(copy.deepcopy(c))

    # components / ratlines
    for tag in ("Components", "Ratlines"):
        th = tboard.find(tag)
        mh = mboard.find(tag)
        if th is not None:
            for c in list(th):
                th.remove(c)
            if mh is not None:
                for c in mh:
                    th.append(copy.deepcopy(c))

    tnets = tboard.find("Nets")
    mnets = mboard.find("Nets")
    if tnets is not None:
        for n in list(tnets):
            tnets.remove(n)
        if mnets is not None:
            for n in mnets:
                tnets.append(copy.deepcopy(n))

    for tag in ("CopperPours", "Shapes"):
        th = tboard.find(tag)
        mh = mboard.find(tag)
        if th is not None:
            for c in list(th):
                th.remove(c)
            if mh is not None:
                for c in mh:
                    th.append(copy.deepcopy(c))


# ---------------------------------------------------------------------------
# 3. SVG board preview
# ---------------------------------------------------------------------------

def render_board_svg(pcb_path: str, output_dir: str) -> dict[str, Any]:
    """Render Top + Bottom SVG previews of the PCB."""
    root = ET.parse(pcb_path).getroot()
    board = root.find("./Board")
    if board is None:
        return {"ok": False, "error": "No Board element found", "files": []}

    scale = 12.0
    margin_mm = 3.0

    outline_pts = board.find("./BoardOutline/Points")
    if outline_pts is None:
        return {"ok": False, "error": "No BoardOutline/Points found", "files": []}

    outline = [
        (float(p_.get("X", "0")), float(p_.get("Y", "0")))
        for p_ in outline_pts
    ]
    if not outline:
        return {"ok": False, "error": "Empty outline", "files": []}

    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    min_x = min(xs) - margin_mm
    min_y = min(ys) - margin_mm
    board_w = max(xs) - min_x + margin_mm
    board_h = max(ys) - min_y + margin_mm

    traces: list[tuple[str, int, float, list[tuple[float, float]]]] = []
    vias: list[tuple[float, float]] = []
    for net in board.findall("./Nets/Net"):
        name = net.findtext("./Name") or ""
        traces_el = net.find("./Traces")
        if traces_el is None:
            continue
        for tr in traces_el:
            run_lay: int | None = None
            run_pts: list[tuple[float, float]] = []
            pts_node = tr.find("./Points")
            if pts_node is None:
                continue
            for p_ in pts_node:
                lay = int(p_.get("Lay", "0"))
                w = float(p_.get("Width", "0.25"))
                xy = (float(p_.get("X", "0")), float(p_.get("Y", "0")))
                if p_.get("ViaStyle", "-1") not in ("-1", None):
                    vias.append(xy)
                if run_lay is None:
                    run_lay = lay
                elif lay != run_lay:
                    traces.append((name, run_lay, w, run_pts))
                    run_lay = lay
                    run_pts = [run_pts[-1]] if run_pts else []
                run_pts.append(xy)
            if run_lay is not None and len(run_pts) >= 2:
                traces.append((name, run_lay, w, run_pts))

    pours: list[tuple[int, list[tuple[float, float]]]] = []
    for p_ in board.findall("./CopperPours/CopperPour"):
        pour_lay = int(p_.get("Lay", "0"))
        pour_pts_el = p_.find("./Points")
        if pour_pts_el is not None:
            pts_list = [
                (float(q.get("X", "0")), float(q.get("Y", "0")))
                for q in pour_pts_el
            ]
            pours.append((pour_lay, pts_list))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(pcb_path).stem
    files: list[str] = []

    for side, lay_idx, mirror in (("Top", 0, False), ("Bottom", 1, True)):
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{board_w*scale:.0f}" '
            f'height="{board_h*scale:.0f}" viewBox="0 0 {board_w*scale:.0f} {board_h*scale:.0f}">',
            '<rect width="100%" height="100%" fill="#111"/>',
            f'<g transform="translate({margin_mm*scale:.0f},{margin_mm*scale:.0f})">',
        ]

        def transform(
            x: float, y: float, is_mirror: bool = mirror
        ) -> tuple[float, float]:
            px = (x - min_x) * scale
            py = (y - min_y) * scale
            if is_mirror:
                px = board_w * scale - px
            return px - margin_mm * scale, py - margin_mm * scale

        outline_str = " ".join(
            f"{px:.1f},{py:.1f}" for px, py in (transform(*p) for p in outline)
        )
        lines.append(
            f'<polygon points="{outline_str}" fill="#1a1a1a" stroke="#e0e0e0" stroke-width="2"/>'
        )
        pour_fill = "#2255cc18" if mirror else "#cc222218"
        copper = "#2255cc" if mirror else "#cc2222"
        for ply, pts in pours:
            if ply != lay_idx:
                continue
            p_str = " ".join(
                f"{px:.1f},{py:.1f}" for px, py in (transform(*q) for q in pts)
            )
            lines.append(f'<polygon points="{p_str}" fill="{pour_fill}"/>')
        for _net, lay, w, pts in traces:
            if lay != lay_idx:
                continue
            d_str = " ".join(
                f"{px:.1f},{py:.1f}" for px, py in (transform(*q) for q in pts)
            )
            lines.append(
                f'<polyline points="{d_str}" fill="none" stroke="{copper}" '
                f'stroke-width="{w*scale:.1f}" stroke-linecap="round"/>'
            )
        for vx, vy in vias:
            px, py = transform(vx, vy)
            lines.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="none" '
                f'stroke="#ddd" stroke-width="2"/>'
            )
        lines.append(
            f'<text x="10" y="20" font-size="16" fill="#fff">{stem} {side}</text>'
        )
        lines.append("</g></svg>")
        svg_path = out_dir / f"{stem}-{side.lower()}.svg"
        svg_path.write_text("\n".join(lines), encoding="utf-8")
        files.append(str(svg_path))

    return {"ok": True, "files": files}
