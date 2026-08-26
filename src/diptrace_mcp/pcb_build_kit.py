"""Reusable PCB build helpers extracted from proven builds.

Sources:
  attiny85-arduino-clone/build_pcb.py (1087 LOC)
  attiny85-arduino-clone/build_connectivity.py (122 LOC)
  scripts/build_i2c_level_shifter_pcb.py (532 LOC)
  dut-controller-reva scripts/nativeize_reva.py + pcb build
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
)
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document, default_layers
from diptrace_mcp.xml_document import DipTraceDocument, RawTreeSnapshot


# ---------------------------------------------------------------------------
# Schematic → PCB helpers
# ---------------------------------------------------------------------------

def strip_schematic_to_physical(schematic: DipTraceDocument,
                                keep_refdes: set[str] | None = None,
                                strip_suffixes: tuple[str, ...] = ("PSG", "PWR", "NPI", "NPO")
                                ) -> DipTraceDocument:
    """Remove net-port/power symbols so only physical parts remain for sync.

    keep_refdes: if given, only these RefDes survive (e.g. set(POS.keys())).
    strip_suffixes: generated-port prefixes to drop even when keep_refdes given.
    """
    root = ET.fromstring(schematic.raw_bytes)
    comps = root.find("./Schematic/Components")
    kept_ids: set[str] = set()
    for part in list(comps.findall("./Part")):
        ref = part.findtext("./RefDes") or ""
        if keep_refdes is not None:
            if ref not in keep_refdes:
                comps.remove(part)
                continue
        elif any(ref.startswith(p) for p in strip_suffixes):
            comps.remove(part)
            continue
        kept_ids.add(part.get("Id", ""))
    for net_el in root.findall("./Schematic/Nets/Net"):
        pins = net_el.find("./Pins")
        wires = net_el.find("./Wires")
        if pins is not None:
            for item in list(pins):
                if item.get("Part", "") not in kept_ids:
                    pins.remove(item)
        if wires is not None:
            wires.clear()
    # Caller should assert: no long generated nets remain referenced
    return DipTraceDocument.from_bytes(
        schematic.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def renumber_merged_pads(root: ET.Element, pattern_style: str) -> None:
    """Give pads sharing a merged number (e.g. '6@') unique IDs like J1 shield fix.

    Call on the schematic Library/Patterns/Pattern before sync, then explicitly
    tie the new pad numbers to GND on the PCB post-sync.
    """
    for pat in root.iter("Pattern"):
        if pat.get("PatternStyle") != pattern_style:
            continue
        pads = pat.find("Pads")
        if pads is None:
            return
        next_num = max(
            (int(p.findtext("./Number") or 0) for p in pads if (p.findtext("./Number") or "").isdigit()),
            default=6,
        ) + 1
        for pad in pads.findall("Pad"):
            txt = pad.find("./Number")
            if txt is not None and txt.text and txt.text.endswith("@"):
                txt.text = str(next_num)
                next_num += 1


def tie_renumbered_pads_to_gnd(
    document: DipTraceDocument, refdes: str, pad_numbers: list[str]
) -> DipTraceDocument:
    """Post-sync: add (Comp,Pad) items to the GND net's pad list."""
    root = ET.fromstring(document.raw_bytes)
    comp = next(c for c in root.findall(".//Components/Component")
                if c.findtext("./RefDes") == refdes)
    comp_id = comp.get("Id", "")
    gnd_net = next(n for n in root.findall(".//Nets/Net") if n.findtext("Name") == "GND")
    pads = gnd_net.find("Pads")
    if pads is None:
        pads = ET.SubElement(gnd_net, "Pads")
    for pn in pad_numbers:
        ET.SubElement(pads, "Item", {"Comp": comp_id, "Pad": pn})
    return DipTraceDocument.from_bytes(
        document.path, ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


# ---------------------------------------------------------------------------
# Intent helpers
# ---------------------------------------------------------------------------

def make_intent(
    *,
    connectors: list[str] | None = None,
    power_nets: list[tuple[str, float]] | None = None,
    ground_nets: list[str] | None = None,
    switching_nodes: list[str] | None = None,
    analog_nets: list[str] | None = None,
    differential_pairs: list[tuple[str, str]] | None = None,
) -> PCBIntentOverrides:
    """One-liner intent from role lists. Caller can also build PCBIntentOverrides
    directly for finer control."""
    nets: list[PCBNetOverride] = []
    for net in (ground_nets or []):
        nets.append(PCBNetOverride(
            selector=net, roles=["ground"],
            constraints=PCBElectricalConstraints(trace_width_mm=0.5, max_vias=0)))
    for net, w in (power_nets or []):
        nets.append(PCBNetOverride(
            selector=net, roles=["power"],
            constraints=PCBElectricalConstraints(trace_width_mm=w, max_vias=2)))
    for net in (switching_nodes or []):
        nets.append(PCBNetOverride(
            selector=net, roles=["switching_node"],
            constraints=PCBElectricalConstraints(trace_width_mm=0.45, max_vias=1)))
    for net in (analog_nets or []):
        nets.append(PCBNetOverride(
            selector=net, roles=["analog"],
            constraints=PCBElectricalConstraints(trace_width_mm=0.25, max_vias=1)))
    comps = [PCBComponentOverride(selector=r, mechanical_anchor=True)
             for r in (connectors or [])]
    return PCBIntentOverrides(components=comps, nets=nets)


# ---------------------------------------------------------------------------
# Board outline / keepout helpers
# ---------------------------------------------------------------------------

def inject_route_keepout(
    document: DipTraceDocument,
    x0: float, y0: float, x1: float, y1: float,
    layer: str = "Route Keepout",
) -> DipTraceDocument:
    """Insert a rectangular Route Keepout (e.g. between inductor legs).

    Coordinates in mm. Pass the body clearance (+0.35mm beyond leg edges if
    using a DRC-expanded bbox).
    """
    raw = RawTreeSnapshot.capture(document)
    board = document.root.find("./Board")
    shapes = board.find("./Shapes")
    if shapes is None:
        shapes = ET.SubElement(board, "Shapes")
    next_id = max((int(s.get("Id", "-1")) for s in shapes.findall("./Shape")
                   if s.get("Id", "-1").isdigit()), default=-1) + 1
    sh = ET.SubElement(shapes, "Shape",
                       {"Id": str(next_id), "Type": "Rectangle",
                        "AllLayers": "N", "Layer": layer})
    pts = ET.SubElement(sh, "Points")
    ET.SubElement(pts, "Point", {"X": f"{x0:.9g}", "Y": f"{y0:.9g}"})
    ET.SubElement(pts, "Point", {"X": f"{x1:.9g}", "Y": f"{y1:.9g}"})
    return DipTraceDocument.from_bytes(document.path, raw.compile(document.root, document.path))


# ---------------------------------------------------------------------------
# Cinematic / stage dumping
# ---------------------------------------------------------------------------

def dump_stage(document: DipTraceDocument, stage_dir: str | Path, name: str) -> Path:
    """Write board snapshot to stage_dir/<name>.dipxml for media pipeline."""
    env = os.environ.get("ATTINY_STAGE_DIR") or str(stage_dir)
    p = Path(env) / f"{name}.dipxml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(document.raw_bytes)
    return p


# ---------------------------------------------------------------------------
# Markings / silkscreen preset (house rule)
# ---------------------------------------------------------------------------

def inject_markings_preset(
    document: DipTraceDocument,
    *,
    silk_align: str = "Top",
    font_mm: str = "1.2",
) -> DipTraceDocument:
    """Declare an explicit Markings block so native Pcb.exe honors planner
    offsets (instead of 3mm auto text that lands on pads)."""
    raw = RawTreeSnapshot.capture(document)
    settings = document.root.find("./Board/Settings")
    markings = ET.Element("Markings")
    ET.SubElement(markings, "CompRotate").text = "N"
    if font_mm:
        ET.SubElement(markings, "FontVector").text = "Y"
        ET.SubElement(markings, "FontName").text = "Tahoma"
        ET.SubElement(markings, "FontSize").text = font_mm
        ET.SubElement(markings, "FontSizeFloat").text = font_mm
        ET.SubElement(markings, "FontWidth").text = "-2"
        ET.SubElement(markings, "FontScale").text = "1"
    if silk_align:
        ET.SubElement(markings, "RefDesGlobal",
                      {"SilkShow": "Show", "SilkAlign": silk_align,
                       "AssyShow": "Common", "AssyAlign": "Auto"})
    settings.insert(0, markings)
    return DipTraceDocument.from_bytes(document.path, raw.compile(document.root, document.path))


# ---------------------------------------------------------------------------
# Placement helpers
# ---------------------------------------------------------------------------

def placement_from_dict(
    positions: dict[str, tuple[float, float]],
    rotations: dict[str, float] | None = None,
) -> dict[str, dict[str, float]]:
    """Normalise a flat {refdes:(x,y)} + rotations dict into a renderable list."""
    rotations = rotations or {}
    return {r: {"x": x, "y": y, "rot": rotations.get(r, 0.0)}
            for r, (x, y) in positions.items()}
