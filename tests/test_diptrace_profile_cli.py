from __future__ import annotations

import json

import pytest

import diptrace_mcp.diptrace_profile_cli as profile_cli
from diptrace_mcp.diptrace_profile_cli import main
from diptrace_mcp.diptrace_ui import ClientPoint, DipTraceUIProfile


def test_profile_cli_builds_calibrates_and_configures_schematic_profile(tmp_path, capsys) -> None:
    profile_path = tmp_path / "schematic-profile.json"
    anchors_path = tmp_path / "anchors.json"
    place_steps_path = tmp_path / "place.json"
    wire_steps_path = tmp_path / "wire.json"

    assert (
        main(
            [
                "template",
                "--editor",
                "schematic",
                "--version",
                "5.3",
                "--output",
                str(profile_path),
            ]
        )
        == 0
    )
    capsys.readouterr()

    anchors_path.write_text(
        json.dumps(
            [
                {"design": [0.0, 0.0], "client": [0.2, 0.8]},
                {"design": [10.0, 0.0], "client": [0.6, 0.8]},
                {"design": [0.0, 10.0], "client": [0.2, 0.3]},
            ]
        ),
        encoding="utf-8",
    )
    assert main(["calibrate", str(profile_path), str(anchors_path)]) == 0
    calibration_output = json.loads(capsys.readouterr().out)
    assert calibration_output["anchors"] == 3
    assert calibration_output["rms_error"] < 1e-9

    place_steps_path.write_text(
        json.dumps([{"text": "{component}"}, {"hotkey": ["enter"]}]),
        encoding="utf-8",
    )
    wire_steps_path.write_text(json.dumps([{"hotkey": ["w"]}]), encoding="utf-8")
    assert main(["action", str(profile_path), "place_component", str(place_steps_path)]) == 0
    capsys.readouterr()
    assert main(["action", str(profile_path), "wire", str(wire_steps_path)]) == 0
    capsys.readouterr()

    assert main(["validate", str(profile_path)]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["ready"] is True
    assert validation["missing_actions"] == []

    profile = DipTraceUIProfile.load(profile_path)
    assert profile.is_ready is True
    assert profile.map_design(5.0, 5.0).x == pytest.approx(0.4)
    assert profile.map_design(5.0, 5.0).y == pytest.approx(0.55)


def test_profile_cli_probe_prints_normalized_client_point(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        profile_cli,
        "normalized_cursor_position",
        lambda _window: ClientPoint(0.375, 0.625),
    )

    assert main(["probe", "--window", "DipTrace Schematic"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output == {"client": [0.375, 0.625]}
