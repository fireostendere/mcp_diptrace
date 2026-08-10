from __future__ import annotations

from types import SimpleNamespace

import pytest

from diptrace_mcp import cinematic_recording as recording
from diptrace_mcp.cinematic_recording import build_windows_capture_command, main


def test_window_capture_command_targets_arbitrary_window() -> None:
    command = build_windows_capture_command(
        "demo.mp4",
        window_title="DipTrace Schematic",
        fps=60,
        duration_seconds=12.5,
    )

    assert command[:3] == ["ffmpeg", "-y", "-f"]
    assert "title=DipTrace Schematic" in command
    assert command[command.index("-framerate") + 1] == "60"
    assert command[command.index("-t") + 1] == "12.5"
    assert command[-1] == "demo.mp4"


def test_window_capture_command_accepts_resolved_hwnd() -> None:
    command = build_windows_capture_command(
        "demo.mp4",
        window_title="DipTrace",
        window_handle=0x1234ABCD,
    )

    assert "hwnd=0x1234abcd" in command
    assert "title=DipTrace" not in command


def test_desktop_capture_command_can_hide_cursor() -> None:
    command = build_windows_capture_command(
        "desktop.mp4",
        window_title=None,
        desktop=True,
        draw_mouse=False,
    )

    assert "desktop" in command
    assert command[command.index("-draw_mouse") + 1] == "0"


def test_capture_command_rejects_invalid_inputs() -> None:
    for kwargs, message in [
        ({"fps": 0}, "fps"),
        ({"fps": 241}, "fps"),
        ({"duration_seconds": 0}, "duration"),
        ({"window_handle": 0}, "window_handle"),
        ({"desktop": True, "window_title": "Other"}, "desktop"),
        ({"window_title": " "}, "required"),
    ]:
        with pytest.raises(ValueError, match=message):
            build_windows_capture_command("demo.mp4", **kwargs)


def test_recording_cli_print_command_is_platform_independent(capsys) -> None:
    assert (
        main(
            [
                "demo.mp4",
                "--window-title",
                "DipTrace PCB Layout",
                "--fps",
                "30",
                "--print-command",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "gdigrab" in output
    assert "DipTrace PCB Layout" in output


def test_record_windows_fail_closed_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recording.os, "name", "posix")
    with pytest.raises(RuntimeError, match="only on Windows"):
        recording.record_windows("demo.mp4")


def test_record_windows_requires_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(recording.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        recording.record_windows("demo.mp4")


def test_record_windows_resolves_hwnd_and_runs_shell_free_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(recording.shutil, "which", lambda _name: "ffmpeg")
    monkeypatch.setattr(recording, "find_window_handle", lambda title: 0xCAFE)

    def fake_run(command: list[str], *, check: bool):
        assert check is False
        seen.append(command)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(recording.subprocess, "run", fake_run)

    result = recording.record_windows(
        "demo.mp4",
        window_title="DipTrace PCB",
        fps=30,
        duration_seconds=2.5,
        draw_mouse=False,
    )

    assert result == 7
    assert "hwnd=0xcafe" in seen[0]
    assert seen[0][seen[0].index("-draw_mouse") + 1] == "0"


def test_record_windows_desktop_skips_window_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(recording.shutil, "which", lambda _name: "ffmpeg")
    monkeypatch.setattr(
        recording,
        "find_window_handle",
        lambda _title: pytest.fail("desktop capture must not resolve a window"),
    )
    monkeypatch.setattr(
        recording.subprocess,
        "run",
        lambda _command, check: SimpleNamespace(returncode=0),
    )

    assert recording.record_windows("desktop.mp4", desktop=True) == 0


def test_record_windows_requires_title_for_window_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(recording.shutil, "which", lambda _name: "ffmpeg")
    with pytest.raises(ValueError, match="window_title"):
        recording.record_windows("demo.mp4", window_title=" ")


def test_recording_cli_live_branch_delegates_to_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_record(output, **kwargs):
        captured["output"] = output
        captured.update(kwargs)
        return 4

    monkeypatch.setattr(recording, "record_windows", fake_record)

    assert main(["demo.mp4", "--desktop", "--fps", "24", "--hide-mouse"]) == 4
    assert str(captured["output"]).endswith("demo.mp4")
    assert captured["desktop"] is True
    assert captured["window_title"] is None
    assert captured["fps"] == 24
    assert captured["draw_mouse"] is False
