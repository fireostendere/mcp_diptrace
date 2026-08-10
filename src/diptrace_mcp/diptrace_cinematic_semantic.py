from __future__ import annotations

from .diptrace_ui import DesignPoint, DipTraceCinematicAdapter
from .operations import AddTraceOperation, AddWireOperation, PlacePartOperation
from .pcb_placement import PCBPlacementV2Plan


def schematic_place_part_payload(
    adapter: DipTraceCinematicAdapter,
    operation: PlacePartOperation,
) -> dict[str, object]:
    """Translate a schematic placement operation into calibrated DipTrace UI playback."""

    if adapter.profile.editor != "schematic":
        raise ValueError("schematic part placement requires a schematic UI profile")
    return adapter.place_component(
        operation.component_style,
        operation.x,
        operation.y,
        context={
            "component": operation.component_style,
            "component_style": operation.component_style,
            "refdes": operation.refdes,
            "name": operation.name or "",
            "value": operation.value,
        },
    )


def schematic_wire_payload(
    adapter: DipTraceCinematicAdapter,
    operation: AddWireOperation,
) -> dict[str, object]:
    """Translate the selected schematic wire planner path into visible click playback."""

    if adapter.profile.editor != "schematic":
        raise ValueError("schematic wire playback requires a schematic UI profile")
    return adapter.wire(
        [DesignPoint(point.x, point.y) for point in operation.points],
        net=operation.net,
    )


def pcb_placement_plan_payloads(
    adapter: DipTraceCinematicAdapter,
    plan: PCBPlacementV2Plan,
) -> list[dict[str, object]]:
    """Translate PCB Generation A placement proposals into visible component moves."""

    if adapter.profile.editor != "pcb":
        raise ValueError("PCB placement playback requires a PCB UI profile")
    payloads: list[dict[str, object]] = []
    for proposal in plan.proposals:
        payloads.append(
            adapter.place_component(
                proposal.object_id,
                proposal.x,
                proposal.y,
                context={
                    "component": proposal.object_id,
                    "object_id": proposal.object_id,
                },
            )
        )
    return payloads


def pcb_trace_payload(
    adapter: DipTraceCinematicAdapter,
    operation: AddTraceOperation,
) -> dict[str, object]:
    """Translate a simple PCB trace operation into visible DipTrace routing playback."""

    if adapter.profile.editor != "pcb":
        raise ValueError("PCB trace playback requires a PCB UI profile")
    for point in operation.points:
        if point.via_style is not None:
            raise ValueError(
                "trace contains a via transition; configure staged via playback before replay"
            )
        if point.layer is not None and point.layer != operation.layer:
            raise ValueError(
                "trace changes layers; configure staged layer playback before replay"
            )
    return adapter.route_trace(
        [DesignPoint(point.x, point.y) for point in operation.points],
        net=operation.net,
    )
