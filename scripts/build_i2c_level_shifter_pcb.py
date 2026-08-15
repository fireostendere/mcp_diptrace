#!/usr/bin/env python3
"""Build and autoroute the repository I2C level-shifter module."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.operations import (
    ConnectPinsOperation,
    PinEndpoint,
    PlacePartOperation,
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
from diptrace_mcp.services.builtin_library import (
    _catalog_location,
    _component_definitions,
    _component_row,
)
from diptrace_mcp.synchronization import ComponentSyncMapping, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument

ROOT = Path(__file__).resolve().parents[1]
PHYSICAL_REFDES = {"Q1", "Q2", "R1", "R2", "R3", "R4"}
HEADER = "builtin-component:498648114:2"
PATTERNS = {
    "J1": "PatType100",
    "J2": "PatType100",
    "Q1": "PatType99",
    "Q2": "PatType99",
    "R1": "PatType2",
    "R2": "PatType2",
    "R3": "PatType2",
    "R4": "PatType2",
}


def _physical_schematic(source: Path, header_export: Path) -> DipTraceDocument:
    original = DipTraceDocument.load(source, 16 * 1024 * 1024)
    root = ET.fromstring(original.raw_bytes)
    components = root.find("./Schematic/Components")
    assert components is not None
    kept_ids: set[str] = set()
    for part in list(components.findall("./Part")):
        if (part.findtext("./RefDes") or "") in PHYSICAL_REFDES:
            kept_ids.add(part.get("Id", ""))
        else:
            components.remove(part)
    for net_element in root.findall("./Schematic/Nets/Net"):
        pins = net_element.find("./Pins")
        wires = net_element.find("./Wires")
        if pins is not None:
            for item in list(pins):
                if item.get("Part", "") not in kept_ids:
                    pins.remove(item)
        if wires is not None:
            wires.clear()

    target = DipTraceDocument.from_bytes(
        Path("i2c-level-shifter-module.dchxml"),
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    exported = DipTraceDocument.load(header_export, 512 * 1024 * 1024)
    location = _catalog_location("/mnt/c/Program Files/DipTrace")
    definitions = _component_definitions(exported, target, _component_row(location, HEADER))
    place = lambda refdes, x: PlacePartOperation(  # noqa: E731
        component_style=definitions["component_style"],
        refdes=refdes,
        name=definitions["name"],
        value="I2C LV" if refdes == "J1" else "I2C HV",
        x=x,
        y=0,
        pin_count=definitions["pin_count"],
        library_component_xml=(definitions["component_xml"] if refdes == "J1" else None),
        library_pattern_xml=(definitions["pattern_xml"] if refdes == "J1" else []),
        library_pad_style_xml=(definitions["pad_style_xml"] if refdes == "J1" else []),
    )
    operations = [place("J1", -45), place("J2", 45)]
    pin_nets = {
        "J1": ("GND", "3V3", "SCL_3V3", "SDA_3V3"),
        "J2": ("GND", "5V", "SCL_5V", "SDA_5V"),
    }
    for refdes, nets in pin_nets.items():
        for pin, net_name in enumerate(nets):
            operations.append(
                ConnectPinsOperation(net=net_name, pins=[PinEndpoint(refdes=refdes, pin=pin)])
            )
    return apply_semantic_operations(target, operations).document


def _intent() -> PCBIntentOverrides:
    components = [
        PCBComponentOverride(selector="J1", role="connector", mechanical_anchor=True),
        PCBComponentOverride(selector="J2", role="connector", mechanical_anchor=True),
    ]
    for refdes in ("Q1", "R1", "R3"):
        components.append(PCBComponentOverride(selector=refdes, block_id="sda"))
    for refdes in ("Q2", "R2", "R4"):
        components.append(PCBComponentOverride(selector=refdes, block_id="scl"))
    nets = [
        PCBNetOverride(
            selector=name,
            roles=[role],
            constraints=PCBElectricalConstraints(
                trace_width_mm=width,
                max_vias=0 if name == "GND" else 2,
                preferred_layers=["Bottom"] if name == "GND" else [],
            ),
        )
        for name, role, width in (
            ("3V3", "high_current_power", 0.4),
            ("5V", "high_current_power", 0.4),
            ("SDA_3V3", "digital", 0.25),
            ("SDA_5V", "digital", 0.25),
            ("SCL_3V3", "clock", 0.25),
            ("SCL_5V", "clock", 0.25),
            ("GND", "ground", 0.5),
        )
    ]
    return PCBIntentOverrides(components=components, nets=nets)


def build(header_export: Path) -> dict[str, object]:
    schematic = _physical_schematic(ROOT / "i2c-level-shifter.dchxml", header_export)
    schematic_path = ROOT / "i2c-level-shifter-module.dchxml"
    schematic_path.write_bytes(schematic.raw_bytes)

    board = DipTraceDocument.from_bytes(
        ROOT / "i2c-level-shifter-pcb.dipxml",
        build_pcb_document(
            PcbScaffold(width_mm=40, height_mm=20, trace_width_mm=0.25),
            units=schematic.units,
            version=schematic.version,
        ),
    )
    positions = {
        "J1": (7.0, 10.0),
        "J2": (33.0, 10.0),
        "Q1": (20.0, 14.0),
        "Q2": (20.0, 8.5),
        "R1": (15.5, 13.5),
        "R2": (15.5, 11.5),
        "R3": (24.5, 13.5),
        "R4": (24.5, 11.5),
    }
    sync = build_sync_plan(
        schematic,
        board,
        mappings=[
            ComponentSyncMapping(
                refdes=refdes,
                pattern_style=PATTERNS[refdes],
                x=x,
                y=y,
            )
            for refdes, (x, y) in positions.items()
        ],
        pattern_documents=[schematic],
    )
    placed = apply_semantic_operations(board, [sync.operation]).document
    placed = apply_semantic_operations(
        placed,
        [
            RotateComponentsOperation(
                selector=QuerySelector(refdes=["J1"]), angle_deg=90, mode="absolute"
            ),
            RotateComponentsOperation(
                selector=QuerySelector(refdes=["J2"]), angle_deg=90, mode="absolute"
            ),
        ],
    ).document
    (ROOT / ".local/i2c-level-shifter-pcb-unrouted.dipxml").write_bytes(placed.raw_bytes)

    route_plan = plan_pcb_routes(
        placed,
        overrides=_intent(),
        config=PCBRouterConfig(
            clearance_mm=0.2,
            grid_mm=0.25,
            max_vias_per_connection=2,
            max_detour=8,
            max_nodes=50_000,
            route_time_budget_ms=3_000,
            max_ripup_attempts=4,
            component_move_penalty_mm=2,
            placement=PCBPlacementV2Config(grid_mm=0.5, search_radius_steps=6),
        ),
    )
    if route_plan.routing.failed:
        raise RuntimeError(f"autorouter left {len(route_plan.routing.failed)} connections")
    routed = apply_semantic_operations(placed, route_plan.operations).document
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
            [
                SetTextVisibilityOperation(
                    selector=QuerySelector(ids=extra_silk),
                    visibility="Hide",
                )
            ],
        ).document
    (ROOT / "i2c-level-shifter-pcb.dipxml").write_bytes(routed.raw_bytes)
    snapshot = build_snapshot(routed)
    assert snapshot.board is not None
    assert all(
        record.attributes.get("Show") == "Hide"
        for record in snapshot.objects.values()
        if record.stable_id in extra_silk
    )
    return {
        "components": len(snapshot.board.components),
        "nets": len(snapshot.board.nets),
        "traces": len(snapshot.board.traces),
        "vias": len(snapshot.board.vias),
        "failed_routes": len(route_plan.routing.failed),
        "selected_candidate": route_plan.selected_candidate,
        "route_length_mm": route_plan.metrics["total_length_mm"],
        "ripups": route_plan.metrics["ripup_count"],
        "candidates": route_plan.metrics["candidates"],
        "widths_mm": {
            item.net_name: item.effective_width_mm for item in route_plan.width_resolutions
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--header-export",
        type=Path,
        default=ROOT / ".local/i2c-header-library.elixml",
    )
    args = parser.parse_args()
    print(json.dumps(build(args.header_export), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
