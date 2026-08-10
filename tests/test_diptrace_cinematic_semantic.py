from __future__ import annotations

from typing import Any, cast

import pytest

from diptrace_mcp.diptrace_cinematic_semantic import (
    pcb_placement_plan_payloads,
    pcb_trace_payload,
    schematic_place_part_payload,
    schematic_wire_payload,
)
from diptrace_mcp.diptrace_ui import (
    CalibrationAnchor,
    ClientPoint,
    DesignPoint,
    DesignToClientTransform,
    DipTraceCinematicAdapter,
    UIActionStep,
    make_diptrace_profile,
)
from diptrace_mcp.operations import AddTraceOperation, AddWireOperation, PlacePartOperation
from diptrace_mcp.pcb_placement import PCBPlacementV2Plan
from diptrace_mcp.placement import PlacementProposal


def _transform() -> DesignToClientTransform:
    return DesignToClientTransform.calibrate(
        [
            CalibrationAnchor(DesignPoint(0.0, 0.0), ClientPoint(0.1, 0.9)),
            CalibrationAnchor(DesignPoint(20.0, 0.0), ClientPoint(0.9, 0.9)),
            CalibrationAnchor(DesignPoint(0.0, 20.0), ClientPoint(0.1, 0.1)),
        ]
    )


def test_place_part_operation_uses_existing_schematic_semantic_coordinates() -> None:
    profile = make_diptrace_profile("schematic").with_transform(_transform())
    profile = profile.with_action(
        "place_component",
        [UIActionStep(text="{component}"), UIActionStep(hotkey=("enter",))],
    )
    operation = PlacePartOperation(
        component_style="STM32 MCU",
        refdes="U1",
        x=10.0,
        y=5.0,
        pin_count=32,
    )

    payload = schematic_place_part_payload(DipTraceCinematicAdapter(profile), operation)
    steps = payload["desktop"]["steps"]

    assert steps[0] == {"text": "STM32 MCU"}
    assert steps[-1]["move_to"] == pytest.approx([0.5, 0.7])


def test_add_wire_operation_uses_existing_wire_planner_vertices() -> None:
    profile = make_diptrace_profile("schematic").with_transform(_transform())
    profile = profile.with_action("wire", [UIActionStep(hotkey=("w",))])
    operation = AddWireOperation(
        net="VCC",
        points=[
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
        ],
        start={"type": "Free"},
        end={"type": "Free"},
    )

    payload = schematic_wire_payload(DipTraceCinematicAdapter(profile), operation)
    path = payload["desktop"]["steps"][1]["path"]

    assert path[0] == pytest.approx([0.1, 0.9])
    assert path[1] == pytest.approx([0.5, 0.9])
    assert path[2] == pytest.approx([0.5, 0.5])


def test_pcb_generation_a_placement_plan_uses_same_design_transform() -> None:
    profile = make_diptrace_profile("pcb").with_transform(_transform())
    profile = profile.with_action("place_component", [UIActionStep(text="{object_id}")])
    plan = PCBPlacementV2Plan(
        operations=[],
        proposals=[
            PlacementProposal(object_id="component:U1", x=5.0, y=5.0),
            PlacementProposal(object_id="component:U2", x=15.0, y=10.0),
        ],
        before=cast(Any, None),
        after=cast(Any, None),
        changed_component_ids=["component:U1", "component:U2"],
        assumptions=[],
        warnings=[],
        limitations=[],
    )

    payloads = pcb_placement_plan_payloads(DipTraceCinematicAdapter(profile), plan)

    assert len(payloads) == 2
    assert payloads[0]["desktop"]["steps"][0] == {"text": "component:U1"}
    assert payloads[0]["desktop"]["steps"][-1]["move_to"] == pytest.approx([0.3, 0.7])
    assert payloads[1]["desktop"]["steps"][-1]["move_to"] == pytest.approx([0.7, 0.5])


def test_add_trace_operation_uses_existing_pcb_trace_vertices() -> None:
    profile = make_diptrace_profile("pcb").with_transform(_transform())
    profile = profile.with_action("route_trace", [UIActionStep(hotkey=("r",))])
    operation = AddTraceOperation(
        net="CLK",
        start_object_id="pad:U1:1",
        end_object_id="pad:U2:1",
        points=[{"x": 5.0, "y": 5.0}, {"x": 15.0, "y": 5.0}],
        layer="Top",
        width=0.2,
    )

    payload = pcb_trace_payload(DipTraceCinematicAdapter(profile), operation)
    path = payload["desktop"]["steps"][1]["path"]

    assert path[0] == pytest.approx([0.3, 0.7])
    assert path[1] == pytest.approx([0.7, 0.7])


def test_trace_with_layer_transition_fails_closed_until_profile_supports_it() -> None:
    profile = make_diptrace_profile("pcb").with_transform(_transform())
    profile = profile.with_action("route_trace", [UIActionStep(hotkey=("r",))])
    operation = AddTraceOperation(
        net="CLK",
        start_object_id="pad:U1:1",
        end_object_id="pad:U2:1",
        points=[
            {"x": 5.0, "y": 5.0, "layer": "Top"},
            {"x": 15.0, "y": 5.0, "layer": "Bottom", "via_style": "Default"},
        ],
        layer="Top",
        width=0.2,
    )

    with pytest.raises(ValueError, match="via transition"):
        pcb_trace_payload(DipTraceCinematicAdapter(profile), operation)
