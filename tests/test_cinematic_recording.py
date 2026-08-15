from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import cinematic_recording as recording
from diptrace_mcp.cinematic import CinematicTimeline
from diptrace_mcp.cinematic_recording import (
    HeadlessCinematicRequest,
    HeadlessCinematicResult,
    HiddenMessageDesktopDriver,
    build_windows_capture_command,
    main,
)


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


def _manifest(tmp_path: Path) -> Path:
    timeline = CinematicTimeline(title="Hidden", preset="gif")
    timeline.operation(
        "route_trace",
        payload={"desktop": {"move_to": [0.4, 0.5], "click": "left"}},
    )
    path = tmp_path / "demo.cinematic.json"
    path.write_text(json.dumps(timeline.manifest()), encoding="utf-8")
    return path


def test_headless_request_and_result_json_contract(tmp_path: Path) -> None:
    request = HeadlessCinematicRequest(
        tmp_path / "DipTrace",
        tmp_path / "board.dip",
        tmp_path / "manifest.json",
        tmp_path / "demo.mp4",
        "PCB",
        gif_output=tmp_path / "demo.gif",
    )
    assert request.editor == "pcb"
    assert HeadlessCinematicRequest.from_json(request.as_json()) == request

    result = HeadlessCinematicResult(
        True,
        "hidden",
        1,
        2,
        3,
        "board.dip",
        "manifest.json",
        "m",
        "demo.mp4",
        "v",
        gif_output="demo.gif",
        gif_sha256="g",
    )
    assert HeadlessCinematicResult.from_json(result.as_json()) == result

    for kwargs, message in [
        ({"editor": "bad"}, "editor"),
        ({"fps": 0}, "fps"),
        ({"gif_fps": 0}, "gif_fps"),
        ({"gif_width": 100}, "gif_width"),
        ({"startup_timeout_seconds": 0}, "startup_timeout"),
        ({"tail_seconds": -1}, "tail_seconds"),
        ({"video_output": tmp_path / "demo.avi"}, "mp4"),
        ({"gif_output": tmp_path / "demo.png"}, "gif"),
        ({"window_title": " "}, "window_title"),
    ]:
        values = dict(
            diptrace_root=tmp_path,
            project=tmp_path / "board.dip",
            manifest=tmp_path / "manifest.json",
            video_output=tmp_path / "demo.mp4",
            editor="pcb",
        )
        values.update(kwargs)
        with pytest.raises(ValueError, match=message):
            HeadlessCinematicRequest(**values)


def test_capture_seconds_includes_manifest_timing_and_command_pause(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    manifest, preflight = recording._read_manifest(manifest_path)
    cues = manifest["cues"]
    assert isinstance(cues, list)
    event = cues[0]["event"]
    event["payload"]["desktop"]["pause_ms"] = 250
    preflight = recording.preflight_cinematic_manifest(manifest)
    seconds = recording._capture_seconds(manifest, preflight, 0.5)
    assert seconds >= 1.0
    assert seconds >= preflight.duration_ms / 1000 + 0.75


def test_headless_validation_rejects_overwrite_and_missing_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DipTrace"
    root.mkdir()
    (root / "Pcb.exe").write_bytes(b"exe")
    project = tmp_path / "project.mp4"
    project.write_bytes(b"project")
    manifest = _manifest(tmp_path)
    monkeypatch.setattr(
        recording,
        "validate_diptrace_directory",
        lambda _root: SimpleNamespace(root=root),
    )
    request = HeadlessCinematicRequest(root, project, manifest, project, "pcb")
    with pytest.raises(recording.HeadlessGuiError, match="overwrite"):
        recording._validate_headless_request(request)

    missing = HeadlessCinematicRequest(
        root, tmp_path / "missing.dip", manifest, tmp_path / "demo.mp4", "pcb"
    )
    with pytest.raises(recording.HeadlessGuiError, match="project file"):
        recording._validate_headless_request(missing)


def test_hidden_driver_rejects_global_input_and_modifier_hotkeys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class User32:
        def SendMessageTimeoutW(self, *_args):
            result = _args[-1]._obj
            result.value = 1
            return 1

    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(
        recording.ctypes,
        "windll",
        SimpleNamespace(user32=User32()),
        raising=False,
    )
    driver = HiddenMessageDesktopDriver(expected_pid=10)
    with pytest.raises(RuntimeError, match="modifier/multi-key"):
        driver._hotkey(22, ("ctrl", "s"))
    driver._hotkey(22, ("esc",))
    driver._text(22, "A")


def test_hidden_driver_window_and_click_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    class User32:
        def __init__(self) -> None:
            self.messages: list[int] = []

        def EnumWindows(self, callback, _lparam):
            callback(22, 0)
            return 1

        def IsWindowVisible(self, _hwnd):
            return True

        def GetWindowThreadProcessId(self, _hwnd, pointer):
            pointer._obj.value = 10
            return 1

        def GetWindowTextLengthW(self, _hwnd):
            return len("DipTrace")

        def GetWindowTextW(self, _hwnd, buffer, _length):
            buffer.value = "DipTrace"
            return len(buffer.value)

        def GetClientRect(self, _hwnd, pointer):
            rect = pointer._obj
            rect.left = 0
            rect.top = 0
            rect.right = 1000
            rect.bottom = 800
            return 1

        def ChildWindowFromPointEx(self, hwnd, _point, _flags):
            return hwnd

        def SendMessageTimeoutW(self, _hwnd, message, _w, _l, _flags, _timeout, result):
            self.messages.append(message)
            result._obj.value = 1
            return 1

    user32 = User32()
    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(
        recording.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
        raising=False,
    )
    monkeypatch.setattr(
        recording.ctypes,
        "WINFUNCTYPE",
        lambda *_types: lambda callback: callback,
        raising=False,
    )
    driver = HiddenMessageDesktopDriver(expected_pid=10)
    event = SimpleNamespace(
        payload={"desktop": {"move_to": [0.5, 0.5], "click": "left"}},
        kind="operation",
    )
    driver.handle(event)
    assert recording._WM_MOUSEMOVE in user32.messages
    assert recording._BUTTON_MESSAGES["left"][0] in user32.messages
    assert recording._BUTTON_MESSAGES["left"][1] in user32.messages


def test_window_lookup_filters_pid_and_title(monkeypatch: pytest.MonkeyPatch) -> None:
    class User32:
        def EnumWindows(self, callback, _lparam):
            for hwnd in (11, 22):
                if not callback(hwnd, 0):
                    break
            return 1

        def IsWindowVisible(self, _hwnd):
            return True

        def GetWindowThreadProcessId(self, hwnd, pointer):
            pointer._obj.value = 10 if hwnd == 22 else 99
            return 1

        def GetWindowTextLengthW(self, _hwnd):
            return len("Board - DipTrace")

        def GetWindowTextW(self, _hwnd, buffer, _length):
            buffer.value = "Board - DipTrace"
            return len(buffer.value)

    monkeypatch.setattr(
        recording.ctypes,
        "WINFUNCTYPE",
        lambda *_types: lambda callback: callback,
        raising=False,
    )
    assert recording._find_window_handle_for_pid(User32(), 10, "DipTrace") == 22
    assert recording._find_window_handle_for_pid(User32(), 12, "DipTrace") is None


def test_message_helpers_are_bounded() -> None:
    assert recording._virtual_key("escape") == 0x1B
    assert recording._virtual_key("f24") == 0x87
    assert recording._virtual_key("a") == ord("A")
    with pytest.raises(ValueError, match="unsupported"):
        recording._virtual_key("ctrl")
    assert recording._pack_point(1, 2) == 0x00020001


def test_gif_conversion_uses_shell_free_two_pass_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"video")
    gif = tmp_path / "demo.gif"
    monkeypatch.setattr(recording.shutil, "which", lambda _name: "ffmpeg")

    def fake_run(command: list[str], *, check: bool):
        assert check is False
        calls.append(command)
        Path(command[-1]).write_bytes(b"artifact")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(recording.subprocess, "run", fake_run)
    recording._convert_video_to_gif(video, gif, fps=20, width=800)
    assert len(calls) == 2
    assert "palettegen" in " ".join(calls[0])
    assert "paletteuse" in " ".join(calls[1])
    assert gif.is_file()


def test_headless_worker_argv_supports_source_and_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(recording.sys.__dict__, "frozen", False)
    source = recording._cinematic_worker_argv("_worker", "--x")
    assert "diptrace_mcp.cinematic_recording" in source
    monkeypatch.setitem(recording.sys.__dict__, "frozen", True)
    frozen = recording._cinematic_worker_argv("_worker", "--x")
    assert frozen[1] == "cinematic"


def test_run_headless_cinematic_guards_platform_and_elevation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = HeadlessCinematicRequest(
        tmp_path,
        tmp_path / "board.dip",
        tmp_path / "manifest.json",
        tmp_path / "demo.mp4",
        "pcb",
    )
    monkeypatch.setattr(recording.os, "name", "posix")
    with pytest.raises(recording.HeadlessGuiError, match="only on Windows"):
        recording.run_headless_cinematic(request)

    monkeypatch.setattr(recording.os, "name", "nt")
    monkeypatch.setattr(recording, "process_is_elevated", lambda: True)
    with pytest.raises(recording.HeadlessGuiError, match="must not be elevated"):
        recording.run_headless_cinematic(request)


def test_headless_cli_delegates_and_prints_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = HeadlessCinematicResult(
        True,
        "hidden",
        1,
        2,
        3,
        "board.dip",
        "manifest.json",
        "m",
        str(tmp_path / "demo.mp4"),
        "v",
    )
    monkeypatch.setattr(recording, "run_headless_cinematic", lambda _request: result)
    code = recording.headless_main(
        [
            "capture",
            "--diptrace-root",
            str(tmp_path),
            "--project",
            str(tmp_path / "board.dip"),
            "--editor",
            "pcb",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--video",
            str(tmp_path / "demo.mp4"),
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cmd_headless_worker_records_failure(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text("{}", encoding="utf-8")
    code = recording._cmd_headless_worker(
        argparse.Namespace(request=str(request), result=str(result), desktop_name="hidden")
    )
    assert code == 1
    assert json.loads(result.read_text(encoding="utf-8"))["ok"] is False
