#!/usr/bin/env python3
"""Headless PCB build for the ATtiny85 Arduino-clone schematic.

Pipeline mirrors scripts/build_i2c_level_shifter_pcb.py: scaffold, schematic
sync with explicit placements, rotation, routing on Top, silkscreen, and GND
pours with stitching. The grounding strategy follows
.agents/skills/diptrace-pcb-grounding and attiny85-arduino-clone/rules/.
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.copper_pours import add_copper_pours
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.geometry import BBox
from diptrace_mcp.operations import (
    MoveBoardTextsOperation,
    RotateComponentsOperation,
    SetTextVisibilityOperation,
)
from diptrace_mcp.pcb_autorouter import PCBRouterConfig, plan_pcb_routes
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
)
from diptrace_mcp.pcb_placement import PCBPlacementV2Config
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.silkscreen import (
    SilkscreenPlanConfig,
    hide_assembly_markings,
    plan_silkscreen,
)
from diptrace_mcp.synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument

ROOT = Path(__file__).resolve().parent
SCHEMATIC = ROOT / "attiny85-arduino-clone.dchxml"
BOARD = ROOT / "attiny85-arduino-clone-pcb.dipxml"

BOARD_W = 44.5
BOARD_H = 22.0

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
    "J2": "PatType17",
    "J3": "PatType18",
}

DEBUG_OUT = ROOT / ".local" / "attiny85-debug.dipxml"

# The micro-USB shell tabs share one net in DipTrace ("6@" pads); sync needs
# unique pad numbers, so the seven shield pads are renumbered 7..13 and tied
# to GND explicitly afterwards (USB shell is a GND connection for ESD/EMC).
J1_PAD_NUMBERS = [str(n) for n in range(1, 14)]
J1_SHIELD_PADS = [str(n) for n in range(7, 14)]

# Functional blocks drive the placement; see docs in README.md.
POSITIONS = {
    # USB power stage (TPS63802 buck-boost): caps and inductor tight to U3,
    # FB divider under it, hot loop kept local.
    "J1": (4.0, 11.0),
    "C1": (8.6, 13.5),
    "U3": (11.8, 13.5),
    "L1": (15.6, 13.5),
    "C2": (18.8, 13.5),
    "R1": (10.6, 9.3),
    "R2": (12.6, 9.3),
    "R3": (15.0, 9.3),
    # USB-UART bridge (CP2102) with local decoupling and VBUS divider.
    "U2": (25.5, 13.5),
    "C3": (21.6, 16.8),
    "C4": (21.6, 10.2),
    "R4": (21.2, 13.5),
    "R5": (19.5, 13.5),
    # MCU with decoupling across VCC/GND, reset network near pin 1.
    "U1": (33.0, 14.0),
    "C5": (38.2, 14.0),
    "R6": (29.5, 8.8),
    "C6": (27.0, 8.8),
    # Headers: ISP bottom center, IO at the right edge.
    "J2": (25.0, 4.5),
    "J3": (41.0, 11.5),
}

ROTATIONS = {
    "J1": 270,  # USB opening over the left edge, tails into the board
    "C1": 90,
    "C2": 90,
    "C3": 90,
    "C4": 90,
    "C5": 90,
    "C6": 0,
    "R1": 90,
    "R2": 90,
    "R3": 0,
    "R4": 90,
    "R5": 90,
    "R6": 0,
    "L1": 90,
    "U1": 90,  # pin rows vertical: UART left, power right, GND bottom-left
    "J3": 90,  # 2x4 becomes two vertical columns at the right edge
}

# Order matters: the sequential router keeps earlier traces as obstacles.
# Long cross-board signals claim their corridors first; the short local power
# links of the buck-boost stage still fit afterwards because their endpoints
# are adjacent. +3V3 is not routed: it is poured on Top after routing.
ROUTED_NETS = [
    "USB_D+",
    "USB_D-",
    "CP2102_TXD",
    "CP2102_RXD",
    "CP2102_DTR",
    "CP2102_VBUS",
    "RESET",
    "PB0_MOSI",
    "PB1_MISO",
    "PB2_SCK",
    "TPS_L1",
    "TPS_L2",
    "TPS_FB",
    "TPS_PG",
    "VBUS",
]

# Power stays on Top with zero vias; signals may escape to Bottom when the
# Top corridor is congested (house rules allow breaking the Bottom plane only
# where a necessary via requires it).
# VBUS may take a Bottom segment when the Top corridor is gone; the local
# buck-boost switching nets stay strictly on Top with zero vias.
TOP_ONLY_NETS = {"TPS_L1", "TPS_L2", "TPS_FB", "TPS_PG"}


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


def _intent() -> PCBIntentOverrides:
    components = [
        PCBComponentOverride(selector="J1", role="connector", mechanical_anchor=True),
        PCBComponentOverride(selector="J2", role="connector", mechanical_anchor=True),
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


def build() -> dict[str, object]:
    schematic = DipTraceDocument.load(SCHEMATIC, 16 * 1024 * 1024)
    physical = _physical_schematic(schematic)
    board = DipTraceDocument.from_bytes(
        BOARD,
        build_pcb_document(
            PcbScaffold(
                width_mm=BOARD_W,
                height_mm=BOARD_H,
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
                x=x,
                y=y,
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
    DEBUG_OUT.parent.mkdir(exist_ok=True)
    DEBUG_OUT.write_bytes(placed.raw_bytes)

    def router_config(nets: list[str]) -> PCBRouterConfig:
        return PCBRouterConfig(
            nets=nets,
            routing_layers=["Top", "Bottom"],
            clearance_mm=0.13,
            grid_mm=0.125,
            max_vias_per_connection=2,
            max_detour=12,
            max_nodes=200_000,
            route_time_budget_ms=15_000,
            max_ripup_attempts=6,
            allow_component_moves=False,
            component_move_penalty_mm=2,
            placement=PCBPlacementV2Config(grid_mm=0.5, search_radius_steps=6),
        )

    # The router walks connections in snapshot order, so ordering is enforced
    # externally: long signals route on the clean board first, then the local
    # power links, then retries see the accumulated copper.
    tps_block = ["TPS_L1", "TPS_L2", "TPS_FB", "TPS_PG"]
    signal_nets = [n for n in ROUTED_NETS if n not in TOP_ONLY_NETS and n != "VBUS"]
    groups = [tps_block, signal_nets, ["VBUS"]]

    routed = placed
    remaining: list[str] = []
    metrics: dict[str, object] = {}
    for group in [*groups, None, None]:
        nets = group if group is not None else remaining
        if not nets:
            remaining = []
            break
        route_plan = plan_pcb_routes(routed, overrides=_intent(), config=router_config(nets))
        if route_plan.operations:
            routed = apply_semantic_operations(routed, route_plan.operations).document
        metrics = route_plan.metrics
        failed_ids = {item["net"] for item in route_plan.routing.failed}
        if not failed_ids:
            remaining = []
            continue
        name_by_id = {
            record.stable_id: record.name
            for record in build_snapshot(routed).board.nets
        }
        remaining = [name_by_id[item] for item in failed_ids if item in name_by_id]
        if group is None and (not route_plan.operations or not remaining):
            break
    if remaining:
        raise RuntimeError(f"autorouter failures after passes: {sorted(remaining)}")

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

    pour_result = add_copper_pours(
        routed,
        net="GND",
        layers=("Top", "Bottom"),
        stitch_pitch_mm=2.0,
        stitch_edge_mm=0.8,
    )
    routed = pour_result.document
    vcc_pour = add_copper_pours(routed, net="+3V3", layers=("Top",))
    routed = vcc_pour.document
    BOARD.write_bytes(routed.raw_bytes)

    snapshot = build_snapshot(routed)
    assert snapshot.board is not None
    assert len(snapshot.board.copper_pours) == 3
    return {
        "components": len(snapshot.board.components),
        "nets": len(snapshot.board.nets),
        "traces": len(snapshot.board.traces),
        "vias": len(snapshot.board.vias),
        "copper_pours": len(snapshot.board.copper_pours),
        "stitch_vias": pour_result.stitch_via_count,
        "failed_routes": len(remaining),
        "route_length_mm": metrics.get("total_length_mm"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(build(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
