#!/usr/bin/env python3
"""Build the DUT Controller Rev.A PCB (dut-controller-reva-pcb.dipxml).

Stage 1: scaffold + sync + placement (+ rotations). Routing follows once the
placement passes headless QC without hard placement errors.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from diptrace_mcp.adapters import build_snapshot  # noqa: E402
from diptrace_mcp.domain import QuerySelector  # noqa: E402
from diptrace_mcp.operations import (  # noqa: E402
    AddTraceOperation,
    RotateComponentsOperation,
    TracePathPoint,
)
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document, default_layers  # noqa: E402
from diptrace_mcp.semantic_compiler import apply_semantic_operations  # noqa: E402
from diptrace_mcp.synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan  # noqa: E402
from diptrace_mcp.xml_document import DipTraceDocument  # noqa: E402

SCHEMATIC_PATH = ROOT / "dut-controller-reva.dchxml"
BOARD_PATH = ROOT / "dut-controller-reva-pcb.dipxml"

BOARD_W = 132.0
BOARD_H = 96.0

# refdes -> (x, y, rotation_deg). Coordinates are board centres in mm.
POS: dict[str, tuple[float, float, float]] = {
    # --- Sheet ESP32_CONTROL -------------------------------------------------
    "U1": (30.0, 74.0, 0),
    "C1": (24.0, 87.0, 180),
    "C2": (28.0, 87.0, 180),
    "C3": (32.0, 87.0, 180),
    "C4": (36.0, 87.0, 180),
    "R1": (42.0, 84.0, 180),
    "C5": (47.0, 87.0, 180),
    "SW1": (46.0, 78.0, 0),
    "SW2": (54.0, 78.0, 0),
    "LED1": (43.0, 68.0, 270),
    "R2": (39.5, 68.0, 270),
    "J15": (98.0, 91.0, 270),
    # --- POWER ---------------------------------------------------------------
    "F1": (14.5, 63.0, 270),
    "D1": (17.0, 57.5, 0),
    "C6": (21.0, 63.0, 270),
    "U2": (28.0, 60.0, 0),
    "C7": (35.0, 63.5, 270),
    "C8": (38.5, 61.0, 270),
    "J11": (7.0, 30.0, 90),
    "D2": (16.0, 33.0, 90),
    "F2": (20.5, 33.0, 90),
    "Q1": (27.5, 34.5, 180),
    "Q3": (33.5, 37.5, 180),
    "R3": (29.5, 28.5, 0),
    "R4": (37.5, 41.0, 270),
    "D4": (31.5, 28.5, 90),
    "RSH_PWR1": (38.0, 34.0, 90),
    "J12": (7.0, 18.0, 90),
    "J13": (7.0, 52.0, 90),
    "D3": (16.0, 55.0, 90),
    "F3": (20.5, 55.0, 90),
    "Q2": (27.5, 56.5, 180),
    "Q4": (33.5, 59.5, 180),
    "R6": (29.5, 50.5, 0),
    "R7": (37.5, 63.0, 270),
    "D5": (31.5, 50.5, 90),
    "RSH_PWR2": (38.0, 56.0, 90),
    "J14": (7.0, 40.0, 90),
    "U21": (43.5, 39.0, 0),
    "C18": (48.5, 42.0, 270),
    "U22": (43.5, 61.0, 0),
    "C19": (48.5, 64.0, 270),
    # --- USB_DUT -------------------------------------------------------------
    "J1": (6.5, 76.0, 90),
    "J2": (6.5, 88.0, 90),
    "U3": (58.0, 82.0, 0),
    "U4": (58.0, 68.0, 0),
    "U5": (92.0, 84.0, 0),
    "U6": (92.0, 62.0, 0),
    "J3": (126.0, 84.0, 270),
    "J4": (126.0, 60.0, 270),
    "D8": (18.0, 88.0, 0),
    "D7": (18.0, 76.0, 0),
    "D9": (112.0, 88.0, 0),
    "D10": (112.0, 56.0, 0),
    "D11": (117.0, 92.5, 90),
    "D12": (117.0, 51.5, 90),
    "F4": (101.0, 90.0, 270),
    "F5": (101.0, 56.0, 270),
    "R11": (16.0, 71.0, 270),
    "R12": (19.0, 71.0, 270),
    "R13": (16.0, 93.5, 270),
    "R14": (19.0, 93.5, 270),
    "R15": (97.5, 79.0, 0),
    "R16": (97.5, 57.0, 0),
    "R17": (52.0, 87.0, 0),
    "R18": (52.0, 63.0, 0),
    "R19": (49.0, 79.0, 0),
    "R20": (49.0, 71.0, 0),
    "R70": (86.5, 79.0, 0),
    "R21": (86.5, 67.0, 0),
    "C20": (63.0, 86.0, 270),
    "C21": (63.0, 64.0, 270),
    "C22": (88.0, 81.0, 270),
    "C23": (88.0, 59.0, 270),
    # --- UART ----------------------------------------------------------------
    "U9": (56.0, 44.0, 0),
    "U10": (56.0, 38.0, 0),
    "U11": (63.0, 44.0, 0),
    "U12": (70.5, 44.0, 0),
    "U13": (56.0, 26.0, 0),
    "U14": (56.0, 20.0, 0),
    "U15": (63.0, 26.0, 0),
    "U16": (70.5, 26.0, 0),
    "J5": (126.0, 38.0, 270),
    "J6": (126.0, 26.0, 270),
    "R22": (63.0, 49.0, 0),
    "R23": (67.5, 49.0, 0),
    "D13": (71.5, 49.0, 0),
    "R24": (63.0, 31.0, 0),
    "R25": (67.5, 31.0, 0),
    "D14": (71.5, 31.0, 0),
    "R26": (77.0, 46.0, 0),
    "R27": (77.0, 42.0, 0),
    "R28": (77.0, 28.0, 0),
    "R29": (77.0, 24.0, 0),
    "R30": (49.0, 47.5, 0),
    "R31": (49.0, 45.5, 0),
    "R32": (49.0, 43.5, 0),
    "R33": (49.0, 29.5, 0),
    "R34": (49.0, 27.5, 0),
    "R35": (49.0, 25.5, 0),
    "C24": (52.0, 41.0, 0),
    "C25": (52.0, 23.0, 0),
    "C26": (66.5, 49.0, 0),
    "C27": (66.5, 31.0, 0),
    # --- SWITCHES ------------------------------------------------------------
    "U17": (66.0, 60.0, 0),
    "K1": (80.0, 74.0, 0),
    "K2": (88.0, 74.0, 0),
    "K3": (96.0, 74.0, 0),
    "K4": (104.0, 74.0, 0),
    "K5": (80.0, 66.0, 0),
    "K6": (88.0, 66.0, 0),
    "K7": (96.0, 66.0, 0),
    "K8": (104.0, 66.0, 0),
    "R36": (83.0, 77.5, 0),
    "R37": (91.0, 77.5, 0),
    "R38": (99.0, 77.5, 0),
    "R39": (107.0, 77.5, 0),
    "R40": (83.0, 69.5, 0),
    "R41": (91.0, 69.5, 0),
    "R42": (99.0, 69.5, 0),
    "R43": (107.0, 69.5, 0),
    "R44": (60.5, 55.5, 0),
    "R45": (64.5, 55.5, 0),
    "R46": (58.0, 64.5, 270),
    "R47": (61.5, 64.5, 270),
    "R48": (73.0, 64.5, 270),
    "LED2": (76.5, 64.5, 270),
    "C28": (71.5, 55.5, 0),
    "J7": (118.0, 74.0, 270),
    # --- AUX_ADC ---------------------------------------------------------------
    "U18": (108.0, 34.0, 0),
    "C9": (103.0, 39.0, 0),
    "C29": (114.0, 39.0, 0),
    "R49": (94.0, 46.0, 0),
    "R50": (97.5, 46.0, 0),
    "C10": (100.5, 46.0, 0),
    "D14": (103.5, 46.0, 0),
    "R51": (94.0, 42.5, 0),
    "R52": (97.5, 42.5, 0),
    "C11": (100.5, 42.5, 0),
    "D15": (103.5, 42.5, 0),
    "R53": (94.0, 22.0, 0),
    "R54": (97.5, 22.0, 0),
    "C12": (100.5, 22.0, 0),
    "D16": (103.5, 22.0, 0),
    "R55": (94.0, 18.5, 0),
    "R56": (97.5, 18.5, 0),
    "C13": (100.5, 18.5, 0),
    "D17": (103.5, 18.5, 0),
    "D15": (103.5, 46.0, 0),
    "D16": (103.5, 42.5, 0),
    "D17": (103.5, 22.0, 0),
    "D18": (103.5, 18.5, 0),
    "RSER1": (116.0, 46.0, 0),
    "RSER2": (116.0, 43.0, 0),
    "RSER3": (116.0, 40.0, 0),
    "RSER4": (116.0, 37.0, 0),
    "RSER5": (116.0, 22.0, 0),
    "RSER6": (116.0, 19.0, 0),
    "RSER7": (116.0, 16.0, 0),
    "RSER8": (116.0, 13.0, 0),
    "D19": (119.5, 46.0, 0),
    "D20": (119.5, 43.0, 0),
    "D21": (119.5, 40.0, 0),
    "D22": (119.5, 37.0, 0),
    "D23": (119.5, 22.0, 0),
    "D24": (119.5, 19.0, 0),
    "D25": (119.5, 16.0, 0),
    "D26": (119.5, 13.0, 0),
    "J9": (126.0, 44.0, 270),
    "J10": (126.0, 16.0, 270),
    # --- CURRENT_SENSE ---------------------------------------------------------
    "U19": (104.0, 84.0, 0),
    "U20": (104.0, 62.0, 0),
    "RSH_USB1": (109.5, 90.0, 270),
    "RSH_USB2": (109.5, 58.0, 270),
    "C16": (99.5, 84.0, 270),
    "C17": (99.5, 62.0, 270),
}

# MON dividers live on sheet 6 but were placed there too
MON = {
    "R57": (94.0, 34.0, 0),
    "R58": (97.5, 34.0, 0),
    "C14": (100.5, 34.0, 0),
    "R59": (94.0, 30.5, 0),
    "R60": (97.5, 30.5, 0),
    "C15": (100.5, 30.5, 0),
}
POS.update(MON)


def main() -> None:
    schematic = DipTraceDocument.load(SCHEMATIC_PATH, 256 * 1024 * 1024)

    # RefDes -> embedded component style (needed for sync mappings)
    style_of: dict[str, str] = {}
    pattern_of: dict[str, str] = {}
    library_patterns = {
        p.get("PatternStyle"): p for p in schematic.root.findall(".//Pattern")
    }
    for part in schematic.root.findall("./Schematic/Components/Part"):
        refdes = part.findtext("./RefDes") or ""
        comp_style = part.get("ComponentStyle", "")
        style_of[refdes] = comp_style
        pattern_of[refdes] = f"{comp_style}_PatType0"
        assert f"{comp_style}_PatType0" in library_patterns, f"missing pattern for {refdes}"

    missing = [r for r in POS if r not in style_of]
    extra = [r for r in style_of if r not in POS]
    if missing:
        raise SystemExit(f"POS refs not in schematic: {missing}")
    if extra:
        raise SystemExit(f"schematic refs missing from POS: {extra}")

    board = DipTraceDocument.from_bytes(
        BOARD_PATH,
        build_pcb_document(
            PcbScaffold(width_mm=BOARD_W, height_mm=BOARD_H, trace_width_mm=0.25,
                        layers=default_layers(2)),
            units=schematic.units,
            version=schematic.version,
        ),
    )

    mappings = [
        ComponentSyncMapping(
            refdes=refdes,
            pattern_style=pattern_of[refdes],
            x=x,
            y=y,
            side="Top",
        )
        for refdes, (x, y, _rot) in sorted(POS.items())
    ]
    sync = build_sync_plan(
        schematic,
        board,
        mappings=mappings,
        placement=SyncPlacement(origin_x=0, origin_y=0, pitch_x=0.5, pitch_y=0.5),
        pattern_documents=[schematic],
    )
    placed = apply_semantic_operations(board, [sync.operation]).document

    # Sync-created PCB pads carry only positional Ids; stamp the real pad
    # numbers back so every later stage (nets, QC, router) resolves them.
    raw_tree = __import__("diptrace_mcp.xml_document", fromlist=["RawTreeSnapshot"]).RawTreeSnapshot.capture(placed)
    pattern_numbers: dict[str, list[str]] = {}
    for pat in placed.root.findall(".//Patterns/Pattern"):
        style = pat.get("PatternStyle", "")
        pattern_numbers[style.casefold()] = [
            (pd.findtext("./Number") or "").strip() for pd in pat.findall("./Pads/Pad")
        ]
    stamped = 0
    for comp in placed.root.findall(".//Components/Component"):
        pref = comp.find("./Pattern")
        style = (pref.get("Style") if pref is not None else comp.get("PatternStyle", "") or "")
        numbers = pattern_numbers.get(style.casefold())
        if not numbers:
            continue
        for pad in comp.findall("./Pads/Pad"):
            if pad.find("Number") is not None:
                continue
            try:
                idx = int(pad.get("Id", "0")) - 1
            except ValueError:
                continue
            if 0 <= idx < len(numbers) and numbers[idx]:
                num_el = ET.SubElement(pad, "Number")
                num_el.text = numbers[idx]
                stamped += 1
    placed = DipTraceDocument.from_bytes(
        BOARD_PATH,
        raw_tree.compile(placed.root, BOARD_PATH),
    )
    print("stamped pad numbers:", stamped)

    rot_ops = [
        RotateComponentsOperation(
            selector=QuerySelector(refdes=[refdes]), angle_deg=rot, mode="absolute"
        )
        for refdes, (_x, _y, rot) in sorted(POS.items())
        if rot
    ]
    if rot_ops:
        placed = apply_semantic_operations(placed, rot_ops).document

    BOARD_PATH.write_bytes(placed.raw_bytes)
    print("placed parts:", len(POS))
    print("sha256:", placed.sha256)




# ---------------------------------------------------------------------------
# Routing stage (run with --route BATCH). Loads the placed board, routes one
# batch, saves. Batches are ordered so earlier (critical) traces become
# obstacles for later ones.
# ---------------------------------------------------------------------------

BATCHES: dict[str, dict] = {
    "usb": {
        "nets": ["CTRL_DP", "CTRL_DN", "UP_DP", "UP_DN", "USB1_DP", "USB1_DN", "USB2_DP", "USB2_DN"],
        "width": 0.25, "clearance": 0.18, "layers": ["Top", "Bottom"], "max_vias": 2,
    },
    "power": {
        "nets": ["+5V", "+3V3", "+5V_FUSED", "VBUS_CTRL_RAW", "VBUS1_SW", "VBUS1_OUT",
                 "VBUS2_SW", "VBUS2_OUT", "PWR1_VIN", "PWR1_MID", "PWR1_OUT",
                 "PWR2_VIN", "PWR2_MID", "PWR2_OUT"],
        "width": 0.6, "clearance": 0.2, "layers": ["Top"], "max_vias": 2,
    },
    "analog": {
        "nets": ["I2C_SDA", "I2C_SCL",
                 "ADC1_DIV", "ADC2_DIV", "ADC3_DIV", "ADC4_DIV", "MON5V_DIV", "MON3V3_DIV",
                 "ADC1_RAW", "ADC2_RAW", "ADC3_RAW", "ADC4_RAW"],
        "width": 0.25, "clearance": 0.2, "layers": ["Top"], "max_vias": 1,
    },
    "sense": {
        "nets": [f"AUX{i}_{k}" for i in (1, 2) for k in ("MCU1", "MCU2", "MCU3", "MCU4", "IO1", "IO2", "IO3", "IO4")],
        "width": 0.25, "clearance": 0.18, "layers": ["Top", "Bottom"], "max_vias": 2,
    },
}


def _intent_for(batch: str) -> "PCBIntentOverrides":
    from diptrace_mcp.pcb_design_intent import (
        PCBComponentOverride, PCBElectricalConstraints, PCBIntentOverrides, PCBNetOverride,
    )
    cfg = BATCHES[batch]
    nets = [
        PCBNetOverride(
            selector=n,
            roles=["differential"] if batch == "usb" else (
                ["power"] if batch == "power" else (["analog"] if batch in ("analog",) else ["digital"])
            ),
            constraints=PCBElectricalConstraints(
                trace_width_mm=cfg["width"],
                max_vias=cfg["max_vias"],
                preferred_layers=cfg["layers"],
                minimum_spacing_mm=cfg["clearance"],
            ),
        )
        for n in cfg["nets"]
    ]
    anchors = [
        PCBComponentOverride(selector=r, mechanical_anchor=True)
        for r in ("J1", "J2", "J3", "J4", "J5", "J6", "J7", "J9", "J10", "J11", "J12", "J13", "J14", "J15")
    ]
    return PCBIntentOverrides(components=anchors, nets=nets)


def route_batch(batch: str) -> None:
    from diptrace_mcp.pcb_autorouter import PCBRouterConfig, plan_pcb_routes
    cfg = BATCHES[batch]
    doc = DipTraceDocument.load(BOARD_PATH, 256 * 1024 * 1024)
    plan = plan_pcb_routes(
        doc,
        overrides=_intent_for(batch),
        config=PCBRouterConfig(
            nets=cfg["nets"],
            routing_layers=cfg["layers"],
            default_trace_width_mm=cfg["width"],
            clearance_mm=cfg["clearance"],
            grid_mm=0.25,
            max_vias_per_connection=cfg["max_vias"],
            via_cost=8.0,
            max_detour=6.0,
            max_nodes=1_800_000,
            route_time_budget_ms=480_000,
            ripup_retry=True,
            max_ripup_attempts=4,
            allow_component_moves=False,
        ),
    )
    routed = apply_semantic_operations(doc, plan.operations).document
    BOARD_PATH.write_bytes(routed.raw_bytes)
    failed = plan.routing.failed
    print(f"batch={batch} ops={len(plan.operations)} failed={len(failed)}")
    if failed:
        print("failed:", failed)




# ---------------------------------------------------------------------------
# Manual critical routing: explicit chains of (refdes, pad_number) endpoints
# plus optional explicit waypoints. Generates L-shaped segments (H-first).
# ---------------------------------------------------------------------------

MANUAL_CHAINS = {
    "CTRL_DP": {"w": 0.25, "layer": "Top", "chains": [[
        ("J1", "6"), ("WP", 11.5, 75.75), ("WP", 11.5, 66.0),
        ("WP", 30.85, 66.0), ("U1", "24")]]},
    "CTRL_DN": {"w": 0.25, "layer": "Top", "chains": [[
        ("J1", "7"), ("WP", 10.9, 76.25), ("WP", 10.9, 65.35),
        ("WP", 29.95, 65.35), ("U1", "23")]]},
    "UP_DP": {"w": 0.25, "layer": "Top", "chains": [
        [("J2", "6"), ("WP", 11.5, 87.75), ("WP", 11.5, 86.85), ("D8", "1")],
        [("D8", "6"), ("WP", 52.5, 89.15), ("WP", 52.5, 81.32), ("U3", "1")],
        [("D8", "6"), ("WP", 49.0, 89.15), ("WP", 49.0, 67.32), ("U4", "1")],
    ]},
    "UP_DN": {"w": 0.25, "layer": "Top", "chains": [
        [("J2", "5"), ("WP", 10.9, 87.25), ("WP", 10.9, 86.85), ("D8", "3")],
        [("D8", "5"), ("WP", 54.5, 88.65), ("WP", 54.5, 81.32), ("U3", "2")],
        [("D8", "5"), ("WP", 47.5, 88.65), ("WP", 47.5, 67.32), ("U4", "2")],
    ]},
    "USB1_DP": {"w": 0.25, "layer": "Top", "chains": [
        [("U3", "8"), ("WP", 121.0, 82.68), ("WP", 121.0, 80.5), ("J3", "7")],
        [("U3", "8"), ("WP", 110.4, 82.68), ("WP", 110.4, 86.85), ("D9", "1")],
    ]},
    "USB1_DN": {"w": 0.25, "layer": "Bottom", "chains": [
        [("U3", "7"), ("WP", 119.0, 82.68), ("WP", 119.0, 90.55), ("J3", "2")],
        [("U3", "7"), ("WP", 113.9, 82.68), ("WP", 113.9, 86.85), ("D9", "3")],
    ]},
    "USB2_DP": {"w": 0.25, "layer": "Top", "chains": [
        [("U4", "8"), ("WP", 125.2, 68.68), ("WP", 125.2, 56.5), ("J4", "7")],
        [("U4", "8"), ("WP", 110.4, 68.68), ("WP", 110.4, 54.85), ("D10", "1")],
    ]},
    "USB2_DN": {"w": 0.25, "layer": "Bottom", "chains": [
        [("U4", "7"), ("WP", 119.0, 68.68), ("WP", 119.0, 66.55), ("J4", "2")],
        [("U4", "7"), ("WP", 113.9, 68.68), ("WP", 113.9, 54.85), ("D10", "3")],
    ]},
}


def _pad_index(snapshot):
    idx = {}
    comp_ref = {}
    for c in snapshot.board.components:
        comp_ref[c.id if hasattr(c, "id") else None] = c.refdes
    for p in snapshot.board.pads:
        ref = getattr(p, "refdes", None)
        num = str(p.attributes.get("number") or p.attributes.get("pad") or "")
        net = p.net_name or ""
        pos = (round(p.position["x"], 3), round(p.position["y"], 3))
        idx.setdefault((ref, num), []).append((pos, net))
    return idx


def manual_route() -> None:
    doc = DipTraceDocument.load(BOARD_PATH, 256 * 1024 * 1024)
    snap = build_snapshot(doc)

    # Build (refdes, number) -> (position, net_name, stable pad id, component id)
    comp_ref_by_id = {}
    for c in snap.objects.values():
        if getattr(c, "kind", "") == "component":
            comp_ref_by_id[c.stable_id] = getattr(c, "refdes", None)
    pad_lookup: dict[tuple[str, str], list[dict]] = {}
    for p in snap.board.pads:
        ref = comp_ref_by_id.get(p.parent_id) or getattr(p, "refdes", None)
        if ref is None:
            continue
        num = str(p.attributes.get("number") or p.attributes.get("pad") or "")
        pad_lookup.setdefault((ref, num), []).append({
            "xy": (p.position["x"], p.position["y"]),
            "net": p.net_name,
            "stable_id": getattr(p, "stable_id", None),
            "comp": getattr(p, "parent_id", None),
        })

    ops = []
    report = []
    for net, spec in MANUAL_CHAINS.items():
        for chain in spec["chains"]:
            pts = []
            for entry_ in chain:
                if entry_[0] == "WP":
                    pts.append({"xy": (entry_[1], entry_[2]), "net": net,
                                "stable_id": None, "comp": None})
                    continue
                ref, num = entry_
                cand = pad_lookup.get((ref, num))
                if not cand:
                    raise SystemExit(f"manual_route: pad {ref}.{num} not found")
                entry = cand[0]
                if entry["net"] and entry["net"] != net:
                    raise SystemExit(f"manual_route: {ref}.{num} on net {entry['net']}, want {net}")
                pts.append(entry)
            # Build L-segments H-first
            path = [pts[0]["xy"]]
            for prev, cur in zip(pts, pts[1:]):
                (x0, y0), (x1, y1) = path[-1], cur["xy"]
                if abs(y1 - y0) > 0.01 and abs(x1 - x0) > 0.01:
                    path.append((x1, y0))
                path.append((x1, y1))
            pad_pts = [p_ for p_ in pts if p_["stable_id"]]
            if len(pad_pts) < 2:
                raise SystemExit(f"manual_route: chain needs >=2 pads {chain}")
            sid0, sid1 = pad_pts[0]["stable_id"], pad_pts[-1]["stable_id"]
            ops.append(AddTraceOperation(
                net=net, start_object_id=sid0, end_object_id=sid1,
                points=[TracePathPoint(x=x, y=y) for x, y in path],
                layer=spec["layer"], width=spec["w"],
            ))
            report.append(f"{net}: {len(chain)} nodes")
    working = doc
    applied = 0
    for op in ops:
        try:
            working = apply_semantic_operations(working, [op]).document
            applied += 1
        except Exception as exc:
            det = getattr(exc, "details", None) or {}
            print(f"SKIP {op.net}: seg={det.get('segment_index')} req={det.get('required')}")
            for oid in (det.get("object_ids") or [])[:1]:
                obj = snap.objects.get(oid)
                if obj is not None:
                    cref = next((c.refdes for c in snap.objects.values()
                                 if getattr(c, 'kind', '') == 'component' and c.stable_id == obj.parent_id), '?')
                    print(f"   obstacle: {cref}.{obj.attributes.get('number')} @ ({obj.position['x']:.2f},{obj.position['y']:.2f}) net={obj.net_name}")
    BOARD_PATH.write_bytes(working.raw_bytes)
    print(f"applied {applied}/{len(ops)} traces")
    print("\n".join(report))
    print("traces:", len(ops))


def _pad_component_number(doc, entry):
    """Resolve the numeric pad Id inside the owning component for endpoint ids."""
    return "1"


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--manual":
        main()
        manual_route()
    elif len(sys.argv) >= 3 and sys.argv[1] == "--route":
        route_batch(sys.argv[2])
    else:
        main()
