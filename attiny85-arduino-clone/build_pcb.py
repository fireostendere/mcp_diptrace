#!/usr/bin/env python3
"""Headless, datasheet-gated PCB build for the ATtiny85 Arduino clone."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.copper_pours import add_copper_pours
from diptrace_mcp.domain import QuerySelector
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
from diptrace_mcp.xml_document import DipTraceDocument

ROOT = Path(__file__).absolute().parent
SCHEMATIC = ROOT / "attiny85-arduino-clone.dchxml"
BOARD = ROOT / "attiny85-arduino-clone-pcb.dipxml"

BOARD_W = 42.2
BOARD_H = 13.7
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
    "J1": (4.0, 12.5),
    "C1": (10.2, 14.43),
    "U3": (12.6, 12.85),
    "L1": (12.6, 16.35),
    "C2": (15.3, 14.545),
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
    "C5": (38.2, 17.9),
    "C6": (27.25, 17.65),
    "R6": (29.5, 17.65),
    # J3 carries IO and the complete ISP pin set; the duplicate J2 is omitted.
    "J3": (41.0, 12.5),
}

ROTATIONS = {
    "J1": 270,  # USB opening over the left edge, tails into the board
    "U3": 90,
    "C1": 90,
    "C2": 90,
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
    """Route three secondary links through a sibling via of the same net.

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
                point(j15.position["x"], j15.position["y"]),
                point(4.125, 5.625, "Top"),
                point(5.0, 5.625, "Top"),
                point(6.75, 7.375, "Top", via=True),
                point(8.0, 8.625, "Bottom"),
                point(8.125, 10.375, "Bottom", via=True),
                point(c12.position["x"], c12.position["y"], "Top"),
            ],
        )
    )

    snapshot = build_snapshot(document)
    operations = []
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
        operations.append(
            ReplaceTraceOperation(
                trace_id=trace.stable_id,
                points=points,
                layer="Top",
                width=0.25,
            )
        )
    document = apply_semantic_operations(document, operations).document

    # Replacing the trace path leaves the old standalone via objects in
    # place; drop one of each now-coincident same-net pair.
    snapshot = build_snapshot(document)
    stale: list[str] = []
    vias = list(snapshot.board.vias)
    for i, left in enumerate(vias):
        for right in vias[i + 1 :]:
            if left.net_id != right.net_id:
                continue
            if (
                abs(left.position["x"] - right.position["x"]) < 1e-6
                and abs(left.position["y"] - right.position["y"]) < 1e-6
            ):
                if right.stable_id not in stale:
                    stale.append(right.stable_id)
    if stale:
        document = apply_semantic_operations(
            document,
            [DeleteViaOperation(selector=QuerySelector(ids=stale))],
        ).document
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
    # Widths stay <=0.25 mm: at 0.5 mm QFN/VSON pitch the router's pad
    # obstacle expansion (width/2 + clearance) must stay under the pad gap,
    # otherwise pad escapes have no clearance-safe grid access.
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
            ("VBUS", "power", 0.25),
            ("+3V3", "power", 0.25),
            ("TPS_L1", "power", 0.25),
            ("TPS_L2", "power", 0.25),
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
            # Config caps are 1M nodes / 30 s; long cross-board USB traces
            # genuinely need most of that budget before finding a corridor.
            max_nodes=1_000_000,
            route_time_budget_ms=30_000,
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
        *(([net], ["Top"]) for net in ("TPS_L1", "TPS_L2")),
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
                [(j1.position["x"], c1.position["y"], 0.25)],
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
                [(vin.position["x"] - 0.35, vin.position["y"], 0.5)],
            )
        ],
    ).document
    c1 = _pad(routed, "C1", "1")
    enable = _pad(routed, "U3", "1")
    assert c1.position is not None and enable.position is not None
    branch_x = c1.position["x"] + 0.4
    routed = apply_semantic_operations(
        routed,
        [
            _top_trace(
                routed,
                "VBUS",
                ("C1", "1"),
                ("U3", "1"),
                [
                    (branch_x, c1.position["y"], 0.25),
                    (branch_x, enable.position["y"], 0.25),
                    (enable.position["x"] - 0.25, enable.position["y"], 0.25),
                ],
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
            raise RuntimeError(f"autorouter failures after passes: {sorted(remaining)}")

    routed = _dedupe_overlapping_vias(routed)

    pour_result = add_copper_pours(
        routed,
        net="GND",
        layers=("Top", "Bottom"),
        clearance_mm=0.13,
        board_clearance_mm=0.2,
        spoke_width_mm=0.3,
        stitch_pitch_mm=2.0,
        stitch_edge_mm=0.8,
    )
    routed = pour_result.document

    snapshot = build_snapshot(routed)
    extra_silk = [
        record.stable_id
        for record in snapshot.objects.values()
        if record.kind == "component_text"
        and record.attributes.get("surface") == "Silk"
        and record.name in {"Name", "Value"}
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
