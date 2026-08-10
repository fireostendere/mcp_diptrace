from __future__ import annotations

import json
import math

import pytest

from diptrace_mcp import diptrace_ui as ui
from diptrace_mcp.diptrace_ui import (
    CalibrationAnchor,
    ClientPoint,
    DesignPoint,
    DesignToClientTransform,
    DipTraceCinematicAdapter,
    DipTraceUIProfile,
    UIActionStep,
    make_diptrace_profile,
)


def _transform() -> DesignToClientTransform:
    return DesignToClientTransform.calibrate(
        [
            CalibrationAnchor(DesignPoint(0, 0), ClientPoint(0.1, 0.9)),
            CalibrationAnchor(DesignPoint(10, 0), ClientPoint(0.9, 0.9)),
            CalibrationAnchor(DesignPoint(0, 10), ClientPoint(0.1, 0.1)),
            CalibrationAnchor(DesignPoint(10, 10), ClientPoint(0.9, 0.1)),
        ]
    )


def test_profile_roundtrip_preserves_unrendered_action_template(tmp_path) -> None:
    profile = make_diptrace_profile("schematic").with_action(
        "place_component",
        [UIActionStep(text="{component}:{refdes}")],
    )
    path = tmp_path / "profile.json"

    profile.save(path)
    restored = DipTraceUIProfile.load(path)

    assert restored.actions["place_component"][0].text == "{component}:{refdes}"
    assert restored.render_action(
        "place_component",
        context={"component": "STM32", "refdes": "U1"},
    ) == [{"text": "STM32:U1"}]


def test_points_transform_and_calibration_validate_inputs() -> None:
    with pytest.raises(ValueError, match="finite"):
        DesignPoint(math.inf, 0)
    with pytest.raises(ValueError, match="finite"):
        ClientPoint(math.nan, 0)
    with pytest.raises(ValueError, match="normalized"):
        ClientPoint(1.1, 0)
    with pytest.raises(ValueError, match="finite"):
        DesignToClientTransform(math.nan, 0, 0, 0, 1, 0)
    with pytest.raises(ValueError, match="invertible"):
        DesignToClientTransform(1, 2, 0, 2, 4, 0)
    with pytest.raises(ValueError, match="at least one"):
        _transform().error([])
    with pytest.raises(ValueError, match="at least three"):
        DesignToClientTransform.calibrate(
            [CalibrationAnchor(DesignPoint(0, 0), ClientPoint(0.1, 0.1))]
        )
    with pytest.raises(ValueError, match="thresholds"):
        DesignToClientTransform.calibrate(
            [
                CalibrationAnchor(DesignPoint(0, 0), ClientPoint(0.1, 0.1)),
                CalibrationAnchor(DesignPoint(1, 0), ClientPoint(0.2, 0.1)),
                CalibrationAnchor(DesignPoint(0, 1), ClientPoint(0.1, 0.2)),
            ],
            max_rms_error=0,
        )


def test_linear_solver_and_residual_fail_closed() -> None:
    with pytest.raises(ValueError, match="3x3"):
        ui._solve_three([[1.0]], [1.0])
    with pytest.raises(ValueError, match="matching"):
        ui._least_squares_plane([DesignPoint(0, 0)], [1.0, 2.0])

    anchors = [
        CalibrationAnchor(DesignPoint(0, 0), ClientPoint(0.1, 0.1)),
        CalibrationAnchor(DesignPoint(1, 0), ClientPoint(0.9, 0.1)),
        CalibrationAnchor(DesignPoint(0, 1), ClientPoint(0.1, 0.9)),
        CalibrationAnchor(DesignPoint(1, 1), ClientPoint(0.95, 0.95)),
    ]
    with pytest.raises(ValueError, match="residual"):
        DesignToClientTransform.calibrate(
            anchors,
            max_rms_error=0.001,
            max_point_error=0.001,
        )


def test_ui_action_step_serializes_every_supported_field() -> None:
    step = UIActionStep(
        path=(ClientPoint(0.1, 0.2), ClientPoint(0.3, 0.4)),
        click="right",
        click_count=2,
        hotkey=("ctrl", "r"),
        text="{net}",
        pause_ms=50,
    )

    assert step.to_dict() == {
        "path": [[0.1, 0.2], [0.3, 0.4]],
        "click": "right",
        "click_count": 2,
        "hotkey": ["ctrl", "r"],
        "text": "{net}",
        "pause_ms": 50,
    }
    assert step.render({"net": "GND"})["text"] == "GND"
    with pytest.raises(ValueError, match="missing UI action"):
        step.render({})


def test_ui_action_step_validation_fail_closed() -> None:
    for kwargs, message in [
        ({"click": "wheel"}, "mouse button"),
        ({"click_count": 4}, "click_count"),
        ({"pause_ms": -1}, "pause_ms"),
        (
            {
                "move_to": ClientPoint(0.1, 0.1),
                "path": (ClientPoint(0.2, 0.2), ClientPoint(0.3, 0.3)),
            },
            "move_to and path",
        ),
        ({"path": (ClientPoint(0.2, 0.2),)}, "at least two"),
        ({"hotkey": ("",)}, "hotkey"),
    ]:
        with pytest.raises(ValueError, match=message):
            UIActionStep(**kwargs)


def test_profile_validation_and_readiness_fail_closed() -> None:
    for kwargs, message in [
        ({"profile_id": "", "editor": "pcb", "diptrace_version": "5.3"}, "profile_id"),
        ({"profile_id": "x", "editor": "bad", "diptrace_version": "5.3"}, "editor"),
        ({"profile_id": "x", "editor": "pcb", "diptrace_version": ""}, "version"),
        (
            {
                "profile_id": "x",
                "editor": "pcb",
                "diptrace_version": "5.3",
                "window_title_contains": " ",
            },
            "window",
        ),
        (
            {
                "profile_id": "x",
                "editor": "pcb",
                "diptrace_version": "5.3",
                "actions": {"": (UIActionStep(),)},
            },
            "action names",
        ),
    ]:
        with pytest.raises(ValueError, match=message):
            DipTraceUIProfile(**kwargs)

    profile = make_diptrace_profile("pcb")
    with pytest.raises(ValueError, match="not calibrated"):
        profile.require_ready()
    with pytest.raises(ValueError, match="not calibrated"):
        profile.map_design(0, 0)
    with pytest.raises(ValueError, match="name"):
        profile.with_action(" ", [UIActionStep()])
    with pytest.raises(ValueError, match="at least one"):
        profile.with_action("route_trace", [])

    profile = profile.with_transform(_transform())
    with pytest.raises(ValueError, match="missing required actions"):
        profile.require_ready()
    assert profile.render_action("missing", optional=True) == []
    with pytest.raises(ValueError, match="not configured"):
        profile.render_action("missing")


def test_profile_from_dict_rejects_malformed_json_shapes(tmp_path) -> None:
    base = {
        "schema": "diptrace-ui-profile/v1",
        "profile_id": "x",
        "editor": "pcb",
        "diptrace_version": "5.3",
        "actions": {},
        "transform": None,
    }
    malformed = [
        ({**base, "schema": "bad"}, "schema"),
        ({**base, "editor": "bad"}, "editor"),
        ({**base, "actions": []}, "actions"),
        ({**base, "actions": {"": [{}]}}, "action name"),
        ({**base, "actions": {"route": []}}, "contain steps"),
        ({**base, "actions": {"route": ["bad"]}}, "object"),
        ({**base, "actions": {"route": [{"move_to": [0.2]}]}}, "move_to"),
        ({**base, "actions": {"route": [{"path": "bad"}]}}, "path"),
        ({**base, "actions": {"route": [{"hotkey": "ctrl"}]}}, "hotkey"),
        ({**base, "actions": {"route": [{"click": "wheel"}]}}, "click"),
        ({**base, "actions": {"route": [{"text": 7}]}}, "text"),
        ({**base, "transform": []}, "transform"),
    ]
    for raw, message in malformed:
        with pytest.raises(ValueError, match=message):
            DipTraceUIProfile.from_dict(raw)

    path = tmp_path / "invalid.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        DipTraceUIProfile.load(path)


def test_profile_roundtrip_with_transform_and_complex_steps(tmp_path) -> None:
    profile = (
        make_diptrace_profile("pcb", window_title_contains="DipTrace PCB")
        .with_transform(_transform())
        .with_action(
            "place_component",
            [UIActionStep(move_to=ClientPoint(0.2, 0.3), click="left")],
        )
        .with_action(
            "route_trace",
            [
                UIActionStep(
                    path=(ClientPoint(0.1, 0.1), ClientPoint(0.9, 0.9)),
                    click="left",
                )
            ],
        )
    )
    path = profile.save(tmp_path / "pcb.json")
    restored = DipTraceUIProfile.load(path)

    assert restored.transform == profile.transform
    assert restored.actions == profile.actions
    restored.require_ready()


def test_adapter_rejects_wrong_editor_empty_geometry_and_missing_cancel() -> None:
    pcb = make_diptrace_profile("pcb").with_transform(_transform())
    schematic = make_diptrace_profile("schematic").with_transform(_transform())
    pcb_adapter = DipTraceCinematicAdapter(pcb)
    schematic_adapter = DipTraceCinematicAdapter(schematic)

    with pytest.raises(ValueError, match="identifier"):
        pcb_adapter.place_component(" ", 1, 1)
    with pytest.raises(ValueError, match="PCB"):
        schematic_adapter.route_trace([DesignPoint(0, 0), DesignPoint(1, 1)])
    with pytest.raises(ValueError, match="schematic"):
        pcb_adapter.wire([DesignPoint(0, 0), DesignPoint(1, 1)])
    with pytest.raises(ValueError, match="at least two"):
        DipTraceCinematicAdapter._path_step([ClientPoint(0.1, 0.1)])
    with pytest.raises(ValueError, match="at least one step"):
        pcb_adapter._payload([])
    with pytest.raises(ValueError, match="not configured"):
        pcb_adapter.cancel()


def test_make_profile_rejects_unknown_editor() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        make_diptrace_profile("bad")  # type: ignore[arg-type]
