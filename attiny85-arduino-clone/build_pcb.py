#!/usr/bin/env python3
"""Headless, datasheet-gated PCB build for the ATtiny85 Arduino clone."""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.copper_pours import add_copper_pours
from diptrace_mcp.geometry import Point
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.errors import GeometryError
from diptrace_mcp.operations import (
    AddTraceOperation,
    DeleteViaOperation,
    ReplaceTraceOperation,
    RotateComponentsOperation,
    SetTextVisibilityOperation,
    TracePathPoint,
)
from diptrace_mcp.pcb_autorouter import PCBRouterConfig, plan_pcb_routes
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
)
from diptrace_mcp.pcb_placement import PCBPlacementV2Config
from diptrace_mcp.pcb_quality import PCBQualityConfig, review_pcb_quality
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document, default_layers
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.silkscreen import (
    SilkscreenPlanConfig,
    hide_assembly_markings,
    plan_silkscreen,
)
from diptrace_mcp.synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument, RawTreeSnapshot

ROOT = Path(__file__).absolute().parent
SCHEMATIC = ROOT / "attiny85-arduino-clone.dchxml"
BOARD = ROOT / "attiny85-arduino-clone-pcb.dipxml"

BOARD_W = 42.2
# 13.9 = 13.7 routed geometry + 0.2 outline clearance: the router's USB_D+
# hop runs at y=13.62 (copper to 13.72), and native DRC flagged it 25 um
# past the old 13.7 edge. The router does not model outline clearance.
BOARD_H = 13.9
X_SHIFT = 2.1247434  # J1's footprint BOARD EDGE line lands at board X=0.
Y_SHIFT = 5.65

# Pattern styles embedded in the schematic (PatTypeN names come from the
# provenance table; the schematic Library carries their geometry).
PATTERNS = {
    "U1": "PatType0",
    "U2": "PatType1",
    "J1": "PatType2",
    "U3": "PatType3",
    "C1": "PatType4",
    "C2": "PatType5",
    "R1": "PatType6",
    "R2": "PatType7",
    "R3": "PatType8",
    "L1": "PatType9",
    "C3": "PatType10",
    "C4": "PatType11",
    "C5": "PatType11",
    "C6": "PatType11",
    "R4": "PatType12",
    "R5": "PatType13",
    "R6": "PatType16",
    "J3": "PatType18",
}

# The micro-USB shell tabs share one net in DipTrace ("6@" pads); sync needs
# unique pad numbers, so the seven shield pads are renumbered 7..13 and tied
# to GND explicitly afterwards (USB shell is a GND connection for ESD/EMC).
J1_PAD_NUMBERS = [str(n) for n in range(1, 14)]
J1_SHIELD_PADS = [str(n) for n in range(7, 14)]

# Functional blocks drive the placement; see docs in README.md.
POSITIONS = {
    # USB power stage (TPS63802 buck-boost): caps and inductor tight to U3,
    # FB divider under it, hot loop kept local.
    # TI TPS63802 layout example (datasheet Fig. 12-1): C1 flanks VIN and C2
    # flanks VOUT at pin-row height (y 8.025), pads facing the IC; L1 stays
    # directly above (its 4.9x4.3 mm body is already body-limited).
    # C1 rot 180 puts its VBUS pad toward VIN; C2 rot 0 keeps +3V3 pad
    # toward VOUT. Board coords = POSITIONS minus X_SHIFT/Y_SHIFT.
    "J1": (4.0, 12.5),
    "C1": (9.81, 13.675),
    "U3": (12.6, 12.85),
    "L1": (12.6, 16.35),
    # C2 cleared of U3/L1 Top Outline overlaps: pad-1 left edge >= 12.125
    # (U3 outline ends 11.975) and top edge <= 8.42 (L1 outline starts 8.554).
    "C2": (15.635, 13.365),
    "R1": (14.115, 10.2),
    "R2": (12.085, 10.2),
    "R3": (16.145, 10.2),
    # USB-UART bridge (CP2102) with local decoupling and VBUS divider.
    "U2": (25.5, 13.5),
    "C3": (21.6, 16.8),
    "C4": (21.6, 10.2),
    "R4": (19.5, 17.1),
    "R5": (20.5, 13.5),
    # MCU with decoupling across VCC/GND, reset network near pin 1.
    "U1": (33.0, 14.0),
    # C5 nudged 0.2 mm left: J3's Top Silk rectangle line terminated inside
    # C5 pad-1 copper (native "Silk to Pad", Gap=-0.0934, Rule=0).
    "C5": (38.0, 17.9),
    "C6": (27.25, 17.65),
    "R6": (29.5, 17.65),
    # J3 carries IO and the complete ISP pin set; the duplicate J2 is omitted.
    "J3": (41.0, 12.5),
}

ROTATIONS = {
    "J1": 270,  # USB opening over the left edge, tails into the board
    "U3": 90,
    "C1": 180,  # VBUS pad toward U3.VIN (TI Fig. 12-1 flank)
    "C2": 0,  # +3V3 pad toward U3.VOUT
    "C3": 90,
    "C4": 90,
    "C5": 90,
    "C6": 0,
    "R1": 180,
    "R2": 180,
    "R3": 180,
    "R4": 90,
    "R5": 90,
    "R6": 0,
    "L1": 180,
    "U2": 180,  # UART faces U1; VBUS faces its divider R4/R5.
    "U1": 270,  # UART faces U2 on the left; ISP faces J3 on the right.
    "J3": 90,  # 2x4 becomes two vertical columns at the right edge
}

# Order matters: the sequential router keeps earlier traces as obstacles.
# Long cross-board signals claim their corridors first; the short local power
# links of the buck-boost stage still fit afterwards because their endpoints
# are adjacent.
ROUTED_NETS = [
    "GND",
    "+3V3",
    "USB_D+",
    "USB_D-",
    "PB1_MISO",
    "PB0_MOSI",
    "PB2_SCK",
    "RESET",
    "CP2102_RXD",
    "CP2102_TXD",
    "CP2102_DTR",
    "CP2102_VBUS",
    "TPS_L1",
    "TPS_L2",
    "TPS_FB",
    "TPS_PG",
    "VBUS",
]

# The complete regulator control loop stays on Top.
TOP_ONLY_NETS = {"TPS_L1", "TPS_L2", "TPS_FB", "TPS_PG", "VBUS"}


def _physical_schematic(document: DipTraceDocument) -> DipTraceDocument:
    """Strip net-port symbols so sync only creates physical PCB components."""
    root = ET.fromstring(document.raw_bytes)
    components = root.find("./Schematic/Components")
    assert components is not None
    kept_ids: set[str] = set()
    for part in list(components.findall("./Part")):
        if (part.findtext("./RefDes") or "") in PATTERNS:
            kept_ids.add(part.get("Id", ""))
        else:
            components.remove(part)
    for net in root.findall("./Schematic/Nets/Net"):
        pins = net.find("./Pins")
        if pins is not None:
            for item in list(pins):
                if item.get("Part", "") not in kept_ids:
                    pins.remove(item)
    _renumber_j1_shield_pads(root)
    return DipTraceDocument.from_bytes(
        document.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )


def _renumber_j1_shield_pads(root: ET.Element) -> None:
    """Give the micro-USB shield tabs unique pad numbers (7..13).

    DipTrace writes multi-pad nets as "6@"; the sync compiler requires unique
    numbers, and the renumbered pads are tied to GND after placement.
    """
    for pattern in root.iter("Pattern"):
        if pattern.get("PatternStyle") != PATTERNS["J1"]:
            continue
        pads = pattern.find("Pads")
        assert pads is not None
        next_number = 7
        for pad in pads.findall("Pad"):
            number = pad.find("Number")
            if number is not None and number.text and number.text.endswith("@"):
                number.text = str(next_number)
                next_number += 1


def _tie_j1_shield_to_gnd(document: DipTraceDocument) -> DipTraceDocument:
    root = ET.fromstring(document.raw_bytes)
    component = next(
        c for c in root.findall(".//Components/Component") if c.findtext("RefDes") == "J1"
    )
    net = next(n for n in root.findall(".//Nets/Net") if n.findtext("Name") == "GND")
    pads = net.find("Pads")
    assert pads is not None
    for pad_number in J1_SHIELD_PADS:
        ET.SubElement(pads, "Item", {"Comp": component.get("Id", ""), "Pad": pad_number})
    return DipTraceDocument.from_bytes(
        document.path, ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )


def _validate_tps_footprint(document: DipTraceDocument) -> None:
    root = ET.fromstring(document.raw_bytes)
    expected = {
        "PadT9": (0.25, 0.599999),
        "PadT10": (0.25, 0.899998),
        "PadT11": (0.25, 1.299997),
    }
    for style_name, (width, height) in expected.items():
        style = root.find(f"./Library/Library/PadStyles/PadStyle[@Name='{style_name}']")
        assert style is not None, f"TPS63802 pad style {style_name} is missing"
        stack = style.find("./MainStack")
        mask = style.find("./MaskPaste")
        assert stack is not None and mask is not None
        assert abs(float(stack.get("Width", "nan")) - width) < 1e-6
        assert abs(float(stack.get("Height", "nan")) - height) < 1e-6
        assert mask.get("TopMask") == "Open"
        assert abs(float(mask.get("CustomSwell", "nan")) - 0.07) < 1e-6
    pad8 = root.find("./Library/Library/PadStyles/PadStyle[@Name='PadT11']/MaskPaste")
    assert pad8 is not None and pad8.get("TopPaste") == "Segments"
    assert pad8.get("Segment_Percent") == "83"
    assert len(pad8.findall("./TopSegments/Item")) == 2


def _pad(document: DipTraceDocument, refdes: str, number: str):
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    component = next(item for item in snapshot.board.components if item.refdes == refdes)
    return next(
        item
        for item in snapshot.board.pads
        if item.parent_id == component.stable_id and item.label == number
    )


def _trace_between(snapshot, net_name: str, pad_a, pad_b):
    """Find the routed trace whose endpoints sit exactly on the two pads."""
    assert snapshot.board is not None

    def at(point, pad) -> bool:
        return abs(point["x"] - pad.position["x"]) < 1e-6 and abs(
            point["y"] - pad.position["y"]
        ) < 1e-6

    for trace in snapshot.board.traces:
        if trace.net_name != net_name:
            continue
        points = trace.attributes.get("points") or []
        if len(points) < 2:
            continue
        if (at(points[0], pad_a) and at(points[-1], pad_b)) or (
            at(points[0], pad_b) and at(points[-1], pad_a)
        ):
            return trace
    raise AssertionError(f"no {net_name} trace between the given pads")


def _dedupe_overlapping_vias(document: DipTraceDocument) -> DipTraceDocument:
    """Canonicalize three secondary GND links through sibling same-net vias.

    The sequential router drops each connection's vias independently, so two
    same-net transitions can land within one grid step and print as an ugly
    double ring. Sharing an adjacent via removes the duplicate copper without
    changing any electrical decision.
    """
    via_style = build_snapshot(document).board.via_styles[0].id

    def point(x: float, y: float, layer: str | None = None, *, via: bool = False):
        return TracePathPoint(
            x=x,
            y=y,
            layer=layer,
            width=0.25,
            via_style=via_style if via else None,
        )

    replacements: list[tuple[str, str, str, list[TracePathPoint]]] = []
    u27 = _pad(document, "U2", "7")
    r62 = _pad(document, "R6", "2")
    replacements.append(
        (
            "+3V3",
            u27.stable_id,
            r62.stable_id,
            [
                point(u27.position["x"], u27.position["y"]),
                point(21.25, 9.965, "Top"),
                point(21.25, 9.875, "Top", via=True),
                point(26.125, 10.0, "Bottom"),
                point(27.375, 11.25, "Bottom", via=True),
                point(27.875, 11.75, "Top"),
                point(r62.position["x"], r62.position["y"], "Top"),
            ],
        )
    )
    pad29 = _pad(document, "U2", "29")
    u14 = _pad(document, "U1", "4")
    replacements.append(
        (
            "GND",
            pad29.stable_id,
            u14.stable_id,
            [
                point(pad29.position["x"], pad29.position["y"]),
                point(23.375, 8.875, "Top"),
                point(23.875, 9.375, "Top"),
                point(23.875, 10.5, "Top"),
                point(24.0, 10.75, "Top", via=True),
                point(25.25, 11.875, "Bottom"),
                point(27.875, 11.875, "Bottom"),
                point(28.625, 11.125, "Bottom"),
                point(28.625, 6.875, "Bottom", via=True),
                point(28.25, 6.5, "Top"),
                point(27.295, 6.5, "Top"),
                point(u14.position["x"], u14.position["y"], "Top"),
            ],
        )
    )
    j15 = _pad(document, "J1", "5")
    c12 = _pad(document, "C1", "2")
    replacements.append(
        (
            "GND",
            j15.stable_id,
            c12.stable_id,
            [
                # The old Top lane crossed y 6.8 inside the VBUS feed corridor
                # (x 5.06..9.2). Drop to Bottom south of it and resurface at
                # the (8.125,10.375) stitch via as before.
                point(j15.position["x"], j15.position["y"]),
                point(4.125, 5.625, "Top"),
                point(5.75, 5.625, "Top"),
                point(5.75, 6.2, "Top", via=True),
                point(7.6, 7.75, "Bottom"),
                point(7.6, 10.375, "Bottom", via=True),
                point(c12.position["x"], c12.position["y"], "Top"),
            ],
        )
    )
    # NOTE: the VBUS sense-tap replacement (U3.10 -> R4.2) is gone. With the
    # manual J1->C1->VIN tree and the 0.25 router intent the autorouter closes
    # the tap itself within clearance, so the hand-authored southern lane no
    # longer matches the surrounding copper and failed validation.

    snapshot = build_snapshot(document)
    for net_name, pad_a_id, pad_b_id, points in replacements:
        pad_a = next(p for p in snapshot.board.pads if p.stable_id == pad_a_id)
        pad_b = next(p for p in snapshot.board.pads if p.stable_id == pad_b_id)
        trace = _trace_between(snapshot, net_name, pad_a, pad_b)
        previous = trace.attributes.get("points") or []
        # The compiler compares endpoints bit-for-bit against the stored
        # trace, in stored order: reuse its exact coordinates and orientation.
        forward = abs(points[0].x - previous[0]["x"]) < 1e-6 and abs(
            points[0].y - previous[0]["y"]
        ) < 1e-6
        if not forward:
            points = list(reversed(points))
        points[0] = TracePathPoint(x=previous[0]["x"], y=previous[0]["y"])
        points[-1] = TracePathPoint(
            x=previous[-1]["x"],
            y=previous[-1]["y"],
            layer="Top",
            width=0.25,
        )
        operation = ReplaceTraceOperation(
            trace_id=trace.stable_id,
            points=points,
            layer="Top",
            width=0.25,
        )
        try:
            document = apply_semantic_operations(document, [operation]).document
        except GeometryError as exc:
            culprit_ids = set(getattr(exc, "object_ids", None) or [])
            nets_by_id = {
                record.stable_id: record.name for record in snapshot.board.nets
            }
            culprits = [
                f"{nets_by_id.get(t.net_id, '?')}-trace "
                f"{[(round(p['x'], 2), round(p['y'], 2)) for p in (t.attributes.get('points') or [])]}"
                for t in snapshot.board.traces
                if t.stable_id in culprit_ids
            ]
            print(
                f"dedupe replacement failed: {net_name} "
                f"{pad_a.label}-pad -> {pad_b.label}-pad\n"
                f"  segment_index={getattr(exc, 'details', {}).get('segment_index')} "
                f"measured={getattr(exc, 'details', {}).get('measured')} "
                f"required={getattr(exc, 'details', {}).get('required')}\n"
                f"  against: {culprits}",
                file=sys.stderr,
                flush=True,
            )
            raise

    # NOTE: no stale-via cleanup here. Coincident same-net vias after a
    # replacement are intentional sibling-via sharing (the replacement paths
    # deliberately route through an existing same-net transition). The old
    # cleanup deleted one via of each coincident pair via DeleteViaOperation,
    # whose compiler rewrites the FOLLOWING trace point to the incoming
    # layer - silently killing the new trace's Top->Bottom transition. The
    # native DipTrace editor then re-inserts the missing via wherever it
    # loads, which landed vias next to pads (C6.2, U2 pin row) and produced
    # 31 native DRC violations.

    return document


def _top_trace(
    document: DipTraceDocument,
    net: str,
    start: tuple[str, str],
    end: tuple[str, str],
    intermediate: list[tuple[float, float, float]],
    *,
    width: float = 0.25,
) -> AddTraceOperation:
    first = _pad(document, *start)
    last = _pad(document, *end)
    assert first.position is not None and last.position is not None
    return AddTraceOperation(
        net=net,
        start_object_id=first.stable_id,
        end_object_id=last.stable_id,
        points=[
            TracePathPoint(**first.position),
            *(
                TracePathPoint(x=x, y=y, layer="Top", width=point_width)
                for x, y, point_width in intermediate
            ),
            TracePathPoint(**last.position, layer="Top", width=width),
        ],
        layer="Top",
        width=width,
        clearance=0.13,
    )


def _intent() -> PCBIntentOverrides:
    components = [
        PCBComponentOverride(selector="J1", role="connector", mechanical_anchor=True),
        PCBComponentOverride(selector="J3", role="connector", mechanical_anchor=True),
        PCBComponentOverride(selector="U3", block_id="power"),
        PCBComponentOverride(selector="L1", block_id="power"),
        PCBComponentOverride(selector="C1", block_id="power"),
        PCBComponentOverride(selector="C2", block_id="power"),
        PCBComponentOverride(selector="U2", block_id="usb"),
        PCBComponentOverride(selector="U1", block_id="mcu"),
    ]
    # TI TPS63802 layout rules (LAY-001): hot-loop nets route short/wide/
    # direct. TPS_L1/TPS_L2 are pre-covered by deterministic _top_trace calls
    # at 0.45 mm; the intent matches so any QC/router fallback agrees.
    # Fine-pitch escapes elsewhere stay <=0.25 mm: at 0.5 mm QFN/VSON pitch
    # the pad obstacle expansion (width/2 + clearance) must stay under the
    # pad gap.
    nets = [
        PCBNetOverride(
            selector=name,
            roles=[role],
            constraints=PCBElectricalConstraints(
                trace_width_mm=width,
                max_vias=0 if name in TOP_ONLY_NETS else 2,
            ),
        )
        for name, role, width in (
            ("GND", "ground", 0.25),
            # Router-side VBUS work is the high-impedance R4 sense tap only;
            # 0.25 keeps its fine-pad escape feasible. The input trunk
            # J1→C1→VIN is pre-routed manually at 0.5 mm.
            ("VBUS", "power", 0.25),
            ("+3V3", "power", 0.25),
            ("TPS_L1", "power", 0.45),
            ("TPS_L2", "power", 0.45),
            ("TPS_FB", "digital", 0.2),
            ("TPS_PG", "digital", 0.2),
            ("USB_D+", "digital", 0.2),
            ("USB_D-", "digital", 0.2),
            ("CP2102_VBUS", "digital", 0.2),
            ("CP2102_TXD", "digital", 0.2),
            ("CP2102_RXD", "digital", 0.2),
            ("CP2102_DTR", "digital", 0.2),
            ("RESET", "digital", 0.2),
            ("PB0_MOSI", "digital", 0.2),
            ("PB1_MISO", "digital", 0.2),
            ("PB2_SCK", "clock", 0.2),
        )
    ]
    return PCBIntentOverrides(components=components, nets=nets)


def build(layer_count: int = 2, *, output: Path = BOARD) -> dict[str, object]:
    if layer_count not in {2, 4}:
        raise ValueError("layer_count must be 2 or 4")
    layers = default_layers(layer_count)
    routing_layers = [layer.name for layer in layers]
    bottom_first_layers = [routing_layers[-1], routing_layers[0]]
    inner_first_layers = (
        [routing_layers[1], routing_layers[0]] if layer_count == 4 else bottom_first_layers
    )
    power_first_layers = (
        [routing_layers[2], routing_layers[0]] if layer_count == 4 else routing_layers
    )
    schematic = DipTraceDocument.load(SCHEMATIC, 16 * 1024 * 1024)
    _validate_tps_footprint(schematic)
    physical = _physical_schematic(schematic)
    board = DipTraceDocument.from_bytes(
        BOARD,
        build_pcb_document(
            PcbScaffold(
                width_mm=BOARD_W,
                height_mm=BOARD_H,
                layers=layers,
                trace_width_mm=0.25,
                clearance_mm=0.13,
            ),
            units=schematic.units,
            version=schematic.version,
        ),
    )
    # Native Pcb.exe defaults RefDes placement to RefDesGlobal
    # SilkAlign="Auto" with a 3 mm font: the auto text lands on the pads
    # (native "C2:1 - Silk to Pad"). Declare an explicit Markings block:
    # with it present the editor honors the silkscreen planner's
    # per-component offsets (verified by round-trip) and the 1.2 mm vector
    # font fits small footprints. CompRotate=N is what Pcb.exe itself
    # writes; ATTINY_SILK_ALIGN / ATTINY_MARKING_FONT_MM override.
    silk_align = os.environ.get("ATTINY_SILK_ALIGN", "Top")
    font_mm = os.environ.get("ATTINY_MARKING_FONT_MM", "1.2")
    if silk_align or font_mm:
        raw_tree = RawTreeSnapshot.capture(board)
        settings_el = board.root.find("./Board/Settings")
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
            ET.SubElement(
                markings,
                "RefDesGlobal",
                {
                    "SilkShow": "Show",
                    "SilkAlign": silk_align,
                    "AssyShow": "Common",
                    "AssyAlign": "Auto",
                },
            )
        settings_el.insert(0, markings)
        board = DipTraceDocument.from_bytes(
            board.path, raw_tree.compile(board.root, board.path)
        )
    sync = build_sync_plan(
        physical,
        board,
        mappings=[
            ComponentSyncMapping(
                refdes=refdes,
                pattern_style=PATTERNS[refdes],
                pad_numbers=J1_PAD_NUMBERS if refdes == "J1" else [],
                x=x - X_SHIFT,
                y=y - Y_SHIFT,
            )
            for refdes, (x, y) in POSITIONS.items()
        ],
        placement=SyncPlacement(origin_x=0, origin_y=0, pitch_x=0.5, pitch_y=0.5),
        pattern_documents=[physical],
    )
    placed = apply_semantic_operations(board, [sync.operation]).document
    placed = apply_semantic_operations(
        placed,
        [
            RotateComponentsOperation(
                selector=QuerySelector(refdes=[refdes]),
                angle_deg=angle,
                mode="absolute",
            )
            for refdes, angle in ROTATIONS.items()
        ],
    ).document
    placed = hide_assembly_markings(placed)
    placed = _tie_j1_shield_to_gnd(placed)
    output.parent.mkdir(parents=True, exist_ok=True)
    debug_out = output.with_name(f".{output.stem}-placed{output.suffix}")
    failed_out = output.with_name(f".{output.stem}-routing-failed{output.suffix}")
    debug_out.write_bytes(placed.raw_bytes)

    def router_config(nets: list[str], layers: list[str] = routing_layers) -> PCBRouterConfig:
        return PCBRouterConfig(
            nets=nets,
            routing_layers=layers,
            clearance_mm=0.13,
            grid_mm=0.125,
            max_vias_per_connection=2,
            via_cost=2.0,
            max_detour=12,
            # Node cap is the real limiter: wall-clock must never bind first,
            # else machine load flips builds run-to-run (USB_D- flap).
            # 1M nodes ~ 300 s measured on this box, so 900 s is a pure
            # runaway guard and results stay deterministic.
            max_nodes=1_000_000,
            route_time_budget_ms=900_000,
            avoid_component_bodies=False,
            allow_via_in_pad=False,
            max_ripup_attempts=3,
            allow_component_moves=False,
            component_move_penalty_mm=2,
            placement=PCBPlacementV2Config(grid_mm=0.5, search_radius_steps=6),
        )

    # The router walks connections in snapshot order, so ordering is enforced
    # externally: long signals route on the clean board first, then the local
    # power links, then retries see the accumulated copper.
    tps_block = ["TPS_L1", "TPS_L2", "TPS_FB", "TPS_PG"]
    signal_nets = [
        net
        for net in ROUTED_NETS
        if net
        not in {
            "GND",
            "+3V3",
            "VBUS",
            "USB_D+",
            "USB_D-",
            "CP2102_VBUS",
            *tps_block,
        }
    ]
    groups = [
        # TPS_L1/TPS_L2 are manual reference traces (datasheet hot loop).
        (["TPS_FB"], ["Top"]),
        (["TPS_PG"], ["Top"]),
        (["CP2102_VBUS"], ["Top"]),
        (["VBUS"], ["Top"]),
        (["USB_D-"], routing_layers),
        (["USB_D+"], routing_layers),
        (["+3V3"], power_first_layers),
        *(
            (
                [net],
                inner_first_layers
                if net == "CP2102_TXD" and layer_count == 4
                else ["Top"]
                if net
                in {
                    "PB2_SCK",
                    "RESET",
                    "CP2102_DTR",
                    "CP2102_VBUS",
                    "PB0_MOSI",
                }
                else routing_layers,
            )
            for net in signal_nets
        ),
        (["GND"], bottom_first_layers),
    ]

    routed = placed
    # Route keepout between the TPS_L1/L2 legs: the hot-loop channel is not
    # a GND corridor (user rule - ground ties under the chip via the pour).
    # x-limits clear the 0.35 mm legs (edges 10.1504/10.8004) even after the
    # validator's half-width expansion (0.175).
    raw_tree = RawTreeSnapshot.capture(routed)
    board_el = routed.root.find("./Board")
    shapes_el = board_el.find("./Shapes")
    if shapes_el is None:
        shapes_el = ET.SubElement(board_el, "Shapes")
    keepout_id = max(
        (int(s.get("Id", "-1")) for s in shapes_el.findall("./Shape") if s.get("Id", "").isdigit()),
        default=-1,
    ) + 1
    keepout = ET.SubElement(
        shapes_el,
        "Shape",
        {"Id": str(keepout_id), "Type": "Rectangle", "AllLayers": "N", "Layer": "Route Keepout"},
    )
    keepout_pts = ET.SubElement(keepout, "Points")
    for kx, ky in ((10.33, 8.50), (10.62, 8.50), (10.62, 10.70), (10.33, 10.70)):
        ET.SubElement(keepout_pts, "Point", {"X": f"{kx:.9g}", "Y": f"{ky:.9g}"})
    routed = DipTraceDocument.from_bytes(
        routed.path, raw_tree.compile(routed.root, routed.path)
    )
    j1 = _pad(routed, "J1", "1")
    c1 = _pad(routed, "C1", "1")
    assert j1.position is not None and c1.position is not None
    routed = apply_semantic_operations(
        routed,
        [
            _top_trace(
                routed,
                "VBUS",
                ("J1", "1"),
                ("C1", "1"),
                # C1 rot 180 puts the VBUS pad on the RIGHT (IC side) and the
                # GND pad on the left, so a straight feed along the pin row
                # would drive over the GND land, and the north side is walled
                # by L1.1's 1.2x3.8 mm land (x from 8.686, y from 8.8). Feed
                # from below: exit J1 right (x 5.06 keeps 0.135 to the lands),
                # down to y 6.8 (0.15 under the (6.75,7.375) stitch via),
                # under the cap, up into the pad. All 0.25 - the 0.45 trunk
                # starts at the C1->VIN hop.
                [
                    (5.06, j1.position["y"], 0.25),
                    (5.06, 6.8, 0.25),
                    (c1.position["x"] + 0.755, 6.8, 0.25),
                ],
                width=0.25,
            )
        ],
    ).document
    c1 = _pad(routed, "C1", "1")
    vin = _pad(routed, "U3", "10")
    assert c1.position is not None and vin.position is not None
    routed = apply_semantic_operations(
        routed,
        [
            _top_trace(
                routed,
                "VBUS",
                ("C1", "1"),
                ("U3", "10"),
                # Straight 0.45 mm hop at pin-row height: 0.5 mm copper would
                # sit 0.125 mm from the TPS_L1 land next door (needs 0.13).
                [(vin.position["x"] - 0.35, vin.position["y"], 0.45)],
            )
        ],
    ).document
    c1 = _pad(routed, "C1", "1")
    enable = _pad(routed, "U3", "1")
    assert c1.position is not None and enable.position is not None
    # EN taps VBUS at C1's right pad and drops below the cap body, then cuts
    # across to the EN land clear of U3's body outline (x 8.9).
    branch_x = c1.position["x"] + 0.755
    routed = apply_semantic_operations(
        routed,
        [
            _top_trace(
                routed,
                "VBUS",
                ("C1", "1"),
                ("U3", "1"),
                [
                    (branch_x, c1.position["y"] - 0.8, 0.25),
                    (enable.position["x"] - 0.25, enable.position["y"], 0.25),
                ],
            )
        ],
    ).document
    # GND under the chip (user rule): tie U3.8 to AGND U3.3 with a short
    # bridge inside the body outline - the Top pour + stitching vias below
    # the chip carry it away. No GND trace between the inductor legs (the
    # keepout above seals that channel).
    routed = apply_semantic_operations(
        routed,
        [
            _top_trace(
                routed,
                "GND",
                ("U3", "8"),
                ("U3", "3"),
                [],
                width=0.35,
            )
        ],
    ).document
    # TI TPS63802 layout example (datasheet Fig. 12-1, rules LAY-001/LAY-004):
    # switch nodes leave the IC straight toward the inductor with one bend and
    # wide copper; FB/PG stay away from them. Verticals sit exactly on the SW
    # pad axes. Widths taper: 0.35 mm through the pin-row zone keeps >=0.175 mm
    # to the neighbouring VIN/GND/VOUT lands AND leaves the U3.8 GND pad a
    # routable corridor between the legs (a flat 0.45 mm wall seals it);
    # the main hot-loop stretch north of the row runs 0.45 mm.
    sw_legs = (
        (("U3", "9"), ("L1", "1"), "TPS_L1"),
        (("U3", "7"), ("L1", "2"), "TPS_L2"),
    )
    for sw_pad, l_pad, net_name in sw_legs:
        sw = _pad(routed, *sw_pad)
        lp = _pad(routed, *l_pad)
        assert sw.position is not None and lp.position is not None
        routed = apply_semantic_operations(
            routed,
            [
                _top_trace(
                    routed,
                    net_name,
                    sw_pad,
                    l_pad,
                    [
                        (sw.position["x"], sw.position["y"] + 0.675, 0.35),
                        (sw.position["x"], lp.position["y"], 0.45),
                    ],
                    width=0.45,
                )
            ],
        ).document
    vout = _pad(routed, "U3", "6")
    c2 = _pad(routed, "C2", "1")
    assert vout.position is not None and c2.position is not None
    routed = apply_semantic_operations(
        routed,
        [
            _top_trace(
                routed,
                "+3V3",
                ("U3", "6"),
                ("C2", "1"),
                [
                    (vout.position["x"] + 0.35, vout.position["y"], 0.25),
                    (c2.position["x"] - 0.35, c2.position["y"], 0.5),
                ],
                width=0.5,
            )
        ],
    ).document
    metrics: dict[str, object] = {}
    for requested, layers in groups:
        print(f"routing {','.join(requested)} on {','.join(layers)}", file=sys.stderr, flush=True)
        remaining = requested
        for _attempt in range(3):
            attempt_layers = ["Top"] if _attempt == 2 and layers != ["Top"] else layers
            route_plan = plan_pcb_routes(
                routed,
                overrides=_intent(),
                config=router_config(remaining, attempt_layers),
            )
            if route_plan.operations:
                routed = apply_semantic_operations(routed, route_plan.operations).document
            metrics = route_plan.metrics
            failed_ids = {item["net"] for item in route_plan.routing.failed}
            if not failed_ids:
                remaining = []
                break
            name_by_id = {
                record.stable_id: record.name for record in build_snapshot(routed).board.nets
            }
            next_remaining = [name_by_id[item] for item in failed_ids if item in name_by_id]
            if not route_plan.operations and next_remaining == remaining:
                break
            remaining = next_remaining
        if remaining:
            failed_out.write_bytes(routed.raw_bytes)
            snapshot_now = build_snapshot(routed)
            ref_by_id = {
                record.stable_id: record.refdes for record in snapshot_now.board.components
            }
            pad_names = {
                record.stable_id: f"{ref_by_id.get(record.parent_id, '?')}.{record.label}"
                for record in snapshot_now.board.pads
            }
            for item in route_plan.routing.failed:
                start = pad_names.get(item.get("start"), item.get("start"))
                end = pad_names.get(item.get("end"), item.get("end"))
                print(
                    f"failed link: net={item['net']} {start} -> {end}: {item['error']}",
                    file=sys.stderr,
                    flush=True,
                )
            raise RuntimeError(f"autorouter failures after passes: {sorted(remaining)}")

    routed = _dedupe_overlapping_vias(routed)

    def _trace2_probe(tag: str) -> None:
        for tr_el in routed.root.iter("Trace"):
            pts = tr_el.findall(".//Point")
            if len(pts) == 7 and abs(float(pts[2].get("X")) - 21.25) < 0.01:
                with Path(f".trace2_{tag}.json").open("w", encoding="utf-8") as h:
                    json.dump(
                        [{k: p.get(k) for k in ("X", "Y", "Lay", "ViaStyle")} for p in pts],
                        h,
                    )
                return

    _trace2_probe("after_dedupe")

    # Native DipTrace DRC measured its own pour fill up to ~62 um inside the
    # requested clearance near polygon corners. 0.22 additionally spawned a
    # 0.119 mm finding at U2.22 that 0.18 never produced, so 0.18 stays.
    # SMD GND lands direct-tie to the pour (reflow assembly; THT connector
    # pads keep their 4-spoke relief). extra_vias = CP2102-GM rule: via
    # cluster under the exposed pad 29 - the only GND return of the QFN.
    u2 = _pad(routed, "U2", "29")
    assert u2.position is not None
    ex, ey = u2.position["x"], u2.position["y"]
    pour_result = add_copper_pours(
        routed,
        net="GND",
        layers=("Top", "Bottom"),
        clearance_mm=0.18,
        board_clearance_mm=0.2,
        spoke_width_mm=0.3,
        stitch_pitch_mm=2.0,
        stitch_edge_mm=0.8,
        extra_vias=[
            Point(x=ex + dx, y=ey + dy)
            for dx in (-0.775, 0.0, 0.775)
            for dy in (-0.825, 0.0, 0.825)
        ]
        # Stitch the ground under U3 (user rule): three vias in the open
        # strip between the bottom pin row and the FB divider resistors,
        # clear of the FB escape diagonal (x ~11.25 at y 5.5).
        + [Point(x=x, y=5.5) for x in (9.3, 10.15, 12.0)],
        smd_spoke="Direct",
    )
    routed = pour_result.document
    _trace2_probe("after_pours")

    snapshot = build_snapshot(routed)
    extra_silk = [
        record.stable_id
        for record in snapshot.objects.values()
        if record.kind == "component_text"
        and record.attributes.get("surface") == "Silk"
        and record.name in {"Name", "Value", "Pattern", "Manufacturer", "Datasheet"}
    ]
    if extra_silk:
        routed = apply_semantic_operations(
            routed,
            [SetTextVisibilityOperation(selector=QuerySelector(ids=extra_silk), visibility="Hide")],
        ).document
    silk_plan = plan_silkscreen(
        build_snapshot(routed),
        SilkscreenPlanConfig(clearance=0.15, search_steps=20),
    )
    if silk_plan.unresolved:
        raise RuntimeError(f"silkscreen has unresolved labels: {silk_plan.unresolved}")
    if silk_plan.operations:
        routed = apply_semantic_operations(routed, silk_plan.operations).document
    _trace2_probe("after_silk")

    snapshot = build_snapshot(routed)
    assert snapshot.board is not None
    assert len(snapshot.board.components) == len(PATTERNS)
    assert len(snapshot.board.copper_pours) == 2
    assert not snapshot.board.ratlines
    assert all(component.refdes != "J2" for component in snapshot.board.components)
    quality = review_pcb_quality(
        snapshot,
        config=PCBQualityConfig(
            via_pad_clearance_mm=0.13,
            centerline_groups={"y": ["J1", "J3"]},
            centerline_tolerance_mm=0.1,
        ),
    )
    if quality.hard_error_count:
        output.with_name(f".{output.stem}-preqc{output.suffix}").write_bytes(routed.raw_bytes)
        raise RuntimeError(
            "PCB quality gate failed: "
            + json.dumps(
                [
                    item.model_dump()
                    for item in quality.findings
                    if item.severity == "error"
                ],
                indent=1,
            )
        )
    # C5.1 silk-to-pad (native): Pcb.exe saves RefDes as RefDesGlobal
    # SilkAlign="Auto" and drops every per-component RefDesMarking offset,
    # so offset-based fixes cannot reach the native layout. Real lever is
    # the document-level <Markings> block (spec 4.4.1.7); pending a probe.
    output.write_bytes(routed.raw_bytes)
    return {
        "components": len(snapshot.board.components),
        "nets": len(snapshot.board.nets),
        "traces": len(snapshot.board.traces),
        "vias": len(snapshot.board.vias),
        "copper_pours": pour_result.pour_count,
        "stitch_vias": pour_result.stitch_via_count,
        "layers": routing_layers,
        "failed_routes": len(remaining),
        "route_length_mm": metrics.get("total_length_mm"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layers", type=int, choices=(2, 4), default=2)
    parser.add_argument("--output", type=Path, default=BOARD)
    args = parser.parse_args()
    print(json.dumps(build(args.layers, output=args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
