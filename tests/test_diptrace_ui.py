from __future__ import annotations

import pytest

from diptrace_mcp.diptrace_ui import (
    CalibrationAnchor,
    ClientPoint,
    DesignPoint,
    DesignToClientTransform,
    DipTraceCinematicAdapter,
    UIActionStep,
    make_diptrace_profile,
)


def _transform() -> DesignToClientTransform:
    return DesignToClientTransform.calibrate(
        [
            CalibrationAnchor(DesignPoint(0.0, 0.0), ClientPoint(0.2, 0.8)),
            CalibrationAnchor(DesignPoint(10.0, 0.0), ClientPoint(0.6, 0.8)),
            CalibrationAnchor(DesignPoint(0.0, 10.0), ClientPoint(0.2, 0.3)),
            CalibrationAnchor(DesignPoint(10.0, 10.0), ClientPoint(0.6, 0.3)),
        ]
    )


def test_affine_calibration_maps_design_to_normalized_client_space() -> None:
    transform = _transform()

    mapped = transform.map(DesignPoint(5.0, 5.0))

    assert mapped.x == pytest.approx(0.4)
    assert mapped.y == pytest.approx(0.55)
    restored = transform.inverse(mapped)
    assert restored.x == pytest.approx(5.0)
    assert restored.y == pytest.approx(5.0)
    assert transform.error(
        [CalibrationAnchor(DesignPoint(5.0, 5.0), ClientPoint(0.4, 0.55))]
    ) == pytest.approx((0.0, 0.0))


def test_affine_calibration_rejects_degenerate_anchors() -> None:
    anchors = [
        CalibrationAnchor(DesignPoint(0.0, 0.0), ClientPoint(0.1, 0.1)),
        CalibrationAnchor(DesignPoint(1.0, 1.0), ClientPoint(0.2, 0.2)),
        CalibrationAnchor(DesignPoint(2.0, 2.0), ClientPoint(0.3, 0.3)),
    ]

    with pytest.raises(ValueError, match="degenerate"):
        DesignToClientTransform.calibrate(anchors)


def test_profile_tracks_calibration_and_required_editor_actions() -> None:
    profile = make_diptrace_profile("schematic").with_transform(_transform())
    assert profile.is_calibrated is True
    assert profile.is_ready is False
    assert profile.missing_actions == ("place_component", "wire")

    profile = profile.with_action("place_component", [UIActionStep(hotkey=("ctrl", "p"))])
    profile = profile.with_action("wire", [UIActionStep(hotkey=("w",))])

    assert profile.is_ready is True
    assert profile.missing_actions == ()


def test_component_placement_renders_template_and_design_target() -> None:
    profile = make_diptrace_profile("schematic").with_transform(_transform())
    profile = profile.with_action(
        "place_component",
        [
            UIActionStep(hotkey=("ctrl", "p"), pause_ms=100),
            UIActionStep(text="{component}"),
            UIActionStep(hotkey=("enter",)),
        ],
    )
    adapter = DipTraceCinematicAdapter(profile)

    payload = adapter.place_component("U1", 5.0, 5.0)
    steps = payload["desktop"]["steps"]

    assert steps[0] == {"hotkey": ["ctrl", "p"], "pause_ms": 100}
    assert steps[1] == {"text": "U1"}
    assert steps[2] == {"hotkey": ["enter"]}
    assert steps[3]["move_to"] == pytest.approx([0.4, 0.55])
    assert steps[3]["click"] == "left"


def test_schematic_wire_maps_planner_vertices_to_click_path() -> None:
    profile = make_diptrace_profile("schematic").with_transform(_transform())
    profile = profile.with_action("wire", [UIActionStep(hotkey=("w",))])
    profile = profile.with_action("finish_wire", [UIActionStep(hotkey=("esc",))])
    adapter = DipTraceCinematicAdapter(profile)

    payload = adapter.wire(
        [DesignPoint(0.0, 0.0), DesignPoint(5.0, 0.0), DesignPoint(5.0, 5.0)],
        net="VCC",
    )
    steps = payload["desktop"]["steps"]
    path = steps[1]["path"]

    assert steps[0] == {"hotkey": ["w"]}
    assert path[0] == pytest.approx([0.2, 0.8])
    assert path[1] == pytest.approx([0.4, 0.8])
    assert path[2] == pytest.approx([0.4, 0.55])
    assert steps[2] == {"hotkey": ["esc"]}


def test_pcb_trace_uses_same_coordinate_transform() -> None:
    profile = make_diptrace_profile("pcb").with_transform(_transform())
    profile = profile.with_action("route_trace", [UIActionStep(hotkey=("r",))])
    adapter = DipTraceCinematicAdapter(profile)

    payload = adapter.route_trace(
        [DesignPoint(2.5, 2.0), DesignPoint(7.5, 2.0)],
        net="CLK",
    )
    steps = payload["desktop"]["steps"]
    path = steps[1]["path"]

    assert steps[0] == {"hotkey": ["r"]}
    assert path[0] == pytest.approx([0.3, 0.7])
    assert path[1] == pytest.approx([0.5, 0.7])


def test_mapping_outside_calibrated_viewport_fails_closed() -> None:
    profile = make_diptrace_profile("pcb").with_transform(_transform())

    with pytest.raises(ValueError, match="normalized"):
        profile.map_design(100.0, 100.0)
