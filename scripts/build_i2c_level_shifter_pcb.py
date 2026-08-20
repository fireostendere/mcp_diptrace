#!/usr/bin/env python3
"""Build and autoroute the repository I2C level-shifter module."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.copper_pours import add_copper_pours
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.geometry import BBox, from_mm
from diptrace_mcp.operations import (
    AddTraceOperation,
    ConnectPinsOperation,
    MoveBoardTextsOperation,
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
from diptrace_mcp.silkscreen import (
    SilkscreenPlanConfig,
    hide_assembly_markings,
    plan_silkscreen,
)
from diptrace_mcp.synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument, RawTreeSnapshot

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


def _compact_standard_header(document: DipTraceDocument) -> DipTraceDocument:
    working = DipTraceDocument.from_bytes(document.path, document.raw_bytes)
    raw_tree = RawTreeSnapshot.capture(working)
    pattern = working.root.find("./Library/Library/Patterns/Pattern[@PatternStyle='PatType100']")
    if pattern is None:
        raise RuntimeError("imported 2.54 mm header pattern was not found")

    unit = lambda value: f"{from_mm(value, working.units):.9g}"  # noqa: E731
    pattern.attrib.update(
        {
            "Mounting": "Through",
            "Width": unit(10.668),
            "Height": unit(3.048),
            "Orientation": "0",
            "Type": "Free",
        }
    )
    for tag, text in (
        ("Name", "HDR_1X04_P2.54_STRAIGHT_COMPACT"),
        ("Name_Description", "Compact straight 1x4 through-hole header, 2.54 mm pitch"),
        ("Name_Unique", "GENERIC_HDR_1X04_P2.54_COMPACT"),
    ):
        element = pattern.find(f"./{tag}")
        if element is None:
            element = ET.SubElement(pattern, tag)
        element.text = text
    origin = pattern.find("./Origin")
    if origin is not None:
        origin.attrib.update({"X": "0", "Y": "0"})
    for tag in ("RecoveryCode", "Model3D"):
        element = pattern.find(f"./{tag}")
        if element is not None:
            pattern.remove(element)

    pads = pattern.find("./Pads")
    shapes = pattern.find("./Shapes")
    if pads is None or shapes is None:
        raise RuntimeError("imported header pattern has no pads or shapes")
    pads.clear()
    for index, x_mm in enumerate((-3.81, -1.27, 1.27, 3.81), start=1):
        pad = ET.SubElement(
            pads,
            "Pad",
            {
                "Id": str(index),
                "Style": "PadT4" if index == 1 else "PadT3",
                "X": unit(x_mm),
                "Y": "0",
                "Angle": "0",
                "Locked": "N",
                "Side": "Top",
            },
        )
        ET.SubElement(pad, "Number").text = str(index)

    shapes.clear()
    for shape_id, layer, bounds in (
        ("1", "Top Outline", (-5.08, -1.27, 5.08, 1.27)),
        ("2", "Top Courtyard", (-5.334, -1.524, 5.334, 1.524)),
        ("3", "Top Silk", (-5.08, -1.27, 5.08, 1.27)),
    ):
        shape = ET.SubElement(
            shapes,
            "Shape",
            {
                "Id": shape_id,
                "Type": "Rectangle",
                "Locked": "N",
                "Layer": layer,
                "LineWidth": unit(0.15 if layer == "Top Silk" else 0.05),
                "AllLayers": "N",
            },
        )
        points = ET.SubElement(shape, "Points")
        min_x, min_y, max_x, max_y = bounds
        ET.SubElement(points, "Point", {"X": unit(min_x), "Y": unit(min_y)})
        ET.SubElement(points, "Point", {"X": unit(max_x), "Y": unit(max_y)})

    for part in working.root.findall("./Schematic/Components/Part"):
        if part.findtext("./RefDes") in {"J1", "J2"}:
            name = part.find("./Name")
            if name is not None:
                name.text = "HDR_1X04_P2.54"

    return DipTraceDocument.from_bytes(
        working.path,
        raw_tree.compile(working.root, working.path),
    )


def _placement_stage(document: DipTraceDocument, refdes: set[str]) -> DipTraceDocument:
    working = DipTraceDocument.from_bytes(document.path, document.raw_bytes)
    raw_tree = RawTreeSnapshot.capture(working)
    components = working.container.find("./Components")
    if components is None:
        raise RuntimeError("PCB components container is missing")
    visible_ids: set[str] = set()
    for component in list(components):
        if component.findtext("./RefDes") in refdes:
            visible_ids.add(component.get("Id", ""))
        else:
            components.remove(component)
    for net in working.container.findall("./Nets/Net"):
        pads = net.find("./Pads")
        traces = net.find("./Traces")
        if pads is not None:
            for item in list(pads):
                if item.get("Comp", "") not in visible_ids:
                    pads.remove(item)
        if traces is not None:
            traces.clear()
    ratlines = working.container.find("./Ratlines")
    if ratlines is not None:
        ratlines.clear()
    for tag in ("CopperPours", "CopperPourFills"):
        container = working.container.find(f"./{tag}")
        if container is not None:
            container.clear()
    return DipTraceDocument.from_bytes(
        working.path,
        raw_tree.compile(working.root, working.path),
    )


def _write_progress_stages(
    placed: DipTraceDocument,
    route_operations: list[object],
) -> int:
    directory = ROOT / ".local"
    directory.mkdir(exist_ok=True)
    order = ("J1", "J2", "Q1", "Q2", "R1", "R2", "R3", "R4")
    for index in range(len(order) + 1):
        stage = _placement_stage(placed, set(order[:index]))
        (directory / f"i2c-level-shifter-pcb-stage-{index:03d}.dipxml").write_bytes(stage.raw_bytes)

    progress = _placement_stage(placed, set(order))
    stage_index = len(order) + 1
    for operation in route_operations:
        progress = apply_semantic_operations(progress, [operation]).document
        if not isinstance(operation, AddTraceOperation):
            continue
        (directory / f"i2c-level-shifter-pcb-stage-{stage_index:03d}.dipxml").write_bytes(
            progress.raw_bytes
        )
        stage_index += 1
    for stale in directory.glob("i2c-level-shifter-pcb-stage-*.dipxml"):
        if int(stale.stem.rsplit("-", 1)[1]) > stage_index:
            stale.unlink()
    return stage_index


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
    return _compact_standard_header(apply_semantic_operations(target, operations).document)


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
            ("3V3", "power", 0.3),
            ("5V", "power", 0.3),
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
            PcbScaffold(width_mm=25, height_mm=12, trace_width_mm=0.25),
            units=schematic.units,
            version=schematic.version,
        ),
    )
    positions = {
        "J1": (1.75, 6.0),
        "J2": (23.25, 6.0),
        "Q1": (12.5, 8.75),
        "Q2": (12.5, 4.75),
        "R1": (8.25, 8.75),
        "R2": (8.25, 4.75),
        "R3": (16.75, 8.75),
        "R4": (16.75, 4.75),
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
        placement=SyncPlacement(
            origin_x=0,
            origin_y=0,
            pitch_x=0.5,
            pitch_y=0.5,
        ),
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
            RotateComponentsOperation(
                selector=QuerySelector(refdes=["Q1", "Q2"]),
                angle_deg=180,
                mode="absolute",
            ),
            RotateComponentsOperation(
                selector=QuerySelector(refdes=["R1", "R2"]),
                angle_deg=270,
                mode="absolute",
            ),
        ],
    ).document
    placed = hide_assembly_markings(placed)
    (ROOT / ".local/i2c-level-shifter-pcb-unrouted.dipxml").write_bytes(placed.raw_bytes)

    route_plan = plan_pcb_routes(
        placed,
        overrides=_intent(),
        config=PCBRouterConfig(
            nets=["3V3", "5V", "SDA_3V3", "SDA_5V", "SCL_3V3", "SCL_5V"],
            routing_layers=["Top"],
            clearance_mm=0.15,
            grid_mm=0.125,
            max_vias_per_connection=0,
            max_detour=8,
            max_nodes=100_000,
            route_time_budget_ms=5_000,
            max_ripup_attempts=4,
            allow_component_moves=False,
            component_move_penalty_mm=2,
            placement=PCBPlacementV2Config(grid_mm=0.5, search_radius_steps=6),
        ),
    )
    if route_plan.routing.failed:
        raise RuntimeError(f"autorouter failures: {route_plan.routing.failed}")
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
    routed = apply_semantic_operations(
        routed,
        [
            MoveBoardTextsOperation(
                selector=QuerySelector(refdes=["J1"], names=["RefDes"], layers=["Top Silk"]),
                absolute_x=4.25,
                absolute_y=1.0,
            ),
            MoveBoardTextsOperation(
                selector=QuerySelector(refdes=["J2"], names=["RefDes"], layers=["Top Silk"]),
                absolute_x=20.75,
                absolute_y=1.0,
            ),
            MoveBoardTextsOperation(
                selector=QuerySelector(refdes=["Q1"], names=["RefDes"], layers=["Top Silk"]),
                absolute_x=12.5,
                absolute_y=11.0,
            ),
            MoveBoardTextsOperation(
                selector=QuerySelector(refdes=["Q2"], names=["RefDes"], layers=["Top Silk"]),
                absolute_x=12.5,
                absolute_y=1.0,
            ),
            *[
                MoveBoardTextsOperation(
                    selector=QuerySelector(refdes=[refdes], names=["RefDes"], layers=["Top Silk"]),
                    absolute_x=x,
                    absolute_y=y,
                )
                for refdes, x, y in (
                    ("R1", 6.9, 8.75),
                    ("R2", 6.9, 4.75),
                    ("R3", 18.6, 8.75),
                    ("R4", 18.6, 4.75),
                )
            ],
        ],
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
    stage_count = _write_progress_stages(routed, route_plan.operations)
    (ROOT / "i2c-level-shifter-pcb.dipxml").write_bytes(routed.raw_bytes)
    (ROOT / f".local/i2c-level-shifter-pcb-stage-{stage_count:03d}.dipxml").write_bytes(
        routed.raw_bytes
    )
    snapshot = build_snapshot(routed)
    assert snapshot.board is not None
    assert all(
        record.attributes.get("Show") == "Hide"
        for record in snapshot.objects.values()
        if record.stable_id in extra_silk
    )
    assert all(
        set(record.attributes.get("segment_layers", [])) <= {"0"}
        for record in snapshot.board.traces
    )
    component_positions = {item.refdes: item.position for item in snapshot.board.components}
    assert component_positions["Q1"]["x"] == component_positions["Q2"]["x"]
    assert len(snapshot.board.copper_pours) == 2
    assert pour_result.stitch_via_count >= 8
    assert min(item.position["y"] for item in snapshot.board.vias) < 6
    assert max(item.position["y"] for item in snapshot.board.vias) > 6
    visible_silk = [
        item
        for item in snapshot.board.texts
        if "Silk" in (item.layer or "")
        and item.attributes.get("Show", "Show") != "Hide"
        and item.bbox is not None
    ]
    silk_obstacles = [
        *snapshot.board.components,
        *snapshot.board.pads,
        *snapshot.board.holes,
        *snapshot.board.vias,
    ]
    assert not any(
        BBox(**text.bbox).overlap_area(BBox(**obstacle.bbox)) > 0
        for text in visible_silk
        for obstacle in silk_obstacles
        if obstacle.bbox is not None
        and (text.side is None or obstacle.side is None or text.side == obstacle.side)
    )
    return {
        "components": len(snapshot.board.components),
        "nets": len(snapshot.board.nets),
        "traces": len(snapshot.board.traces),
        "vias": len(snapshot.board.vias),
        "copper_pours": len(snapshot.board.copper_pours),
        "stages": stage_count + 1,
        "silkscreen_moves": len(silk_plan.changed_ids),
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
