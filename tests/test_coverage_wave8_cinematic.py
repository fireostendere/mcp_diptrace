from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import cinematic_recording as recording
from diptrace_mcp.cinematic import CinematicEvent, CinematicTimeline
from diptrace_mcp.cinematic_host import DesktopCommand
from diptrace_mcp.headless_gui import HeadlessGuiError


class _Api:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def _request(tmp_path: Path, *, gif: Path | None = None) -> recording.HeadlessCinematicRequest:
    root = tmp_path / "DipTrace"
    editor = root / "Pcb.exe"
    editor.parent.mkdir()
    editor.touch()
    project = tmp_path / "board.dip"
    project.touch()
    manifest = tmp_path / "demo.json"
    manifest.write_text(json.dumps(CinematicTimeline(title="x").manifest()), encoding="utf-8")
    return recording.HeadlessCinematicRequest(
        root, project, manifest, tmp_path / "demo.mp4", "pcb", gif_output=gif
    )


def test_validation_and_driver_message_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    monkeypatch.setattr(
        recording, "validate_diptrace_directory", lambda root: SimpleNamespace(root=root)
    )
    checked, manifest, _ = recording._validate_headless_request(request)
    assert checked.project == request.project.resolve() and manifest["title"] == "x"
    for field, value, message in (
        ("diptrace_root", tmp_path / "missing-root", "editor is missing"),
        ("project", tmp_path / "missing.dip", "project file"),
        ("manifest", tmp_path / "missing.json", "manifest"),
    ):
        with pytest.raises(HeadlessGuiError, match=message):
            recording._validate_headless_request(recording.replace(request, **{field: value}))
    project_mp4 = tmp_path / "project.mp4"
    project_mp4.touch()
    invalid_video = recording.HeadlessCinematicRequest(
        request.diptrace_root,
        project_mp4,
        request.manifest,
        project_mp4,
        "pcb",
    )
    with pytest.raises(HeadlessGuiError, match="must not overwrite"):
        recording._validate_headless_request(invalid_video)
    project_gif = tmp_path / "project.gif"
    project_gif.touch()
    invalid_gif = recording.HeadlessCinematicRequest(
        request.diptrace_root,
        project_gif,
        request.manifest,
        request.video_output,
        "pcb",
        gif_output=project_gif,
    )
    with pytest.raises(HeadlessGuiError, match="must not overwrite"):
        recording._validate_headless_request(invalid_gif)

    sent: list[tuple[int, int, int, int]] = []
    driver = object.__new__(recording.HiddenMessageDesktopDriver)
    driver.default_window, driver.expected_pid, driver._last_target = "DipTrace", 7, None
    driver.user32 = SimpleNamespace(
        GetClientRect=_Api(
            lambda _h, rect: setattr(rect._obj, "right", 10) or setattr(rect._obj, "bottom", 6) or 1
        ),
        ChildWindowFromPointEx=lambda hwnd, _point, _flags: 9 if hwnd == 1 else 9,
        MapWindowPoints=lambda _a, _b, point, _n: setattr(point._obj, "x", 2) or 1,
        SendMessageTimeoutW=lambda h, m, w, lp, *_: sent.append((h, m, w, lp)) or 1,
    )
    target, point = driver._target(1, 0.9, 0.5)
    assert (target, point, driver._center(1)) == (9, (2, 3), (5, 3))
    driver._click(target, point, "left", 3)
    driver._hotkey(target, ["f2"])
    driver._text(target, "A✓")
    assert len(sent) == 10
    with pytest.raises(RuntimeError, match="multi-key"):
        driver._hotkey(target, ["ctrl", "x"])
    driver._window = lambda _title: 1
    driver.handle(CinematicEvent(kind="focus", label="focus"))


def test_windows_helpers_and_headless_result_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    callbacks = []
    monkeypatch.setattr(
        recording.ctypes,
        "WINFUNCTYPE",
        lambda *_args: lambda callback: callbacks.append(callback) or callback,
        raising=False,
    )

    class Buffer:
        value = "DipTrace PCB"

        def __init__(self, size):
            self.size = size

        def __len__(self):
            return self.size

    monkeypatch.setattr(recording.ctypes, "create_unicode_buffer", Buffer)
    user32 = SimpleNamespace(
        GetWindowThreadProcessId=lambda _h, pid: setattr(pid._obj, "value", 8),
        GetWindowTextLengthW=lambda _h: 12,
        GetWindowTextW=lambda _h, buf, _n: None,
        IsWindowVisible=lambda _h: 1,
        GetClassNameW=lambda _h, buf, _n: setattr(buf, "value", "TForm1"),
        GetMenu=lambda _h: 1,
        GetWindowRect=lambda _h, rect: (
            setattr(rect._obj, "right", 100) or setattr(rect._obj, "bottom", 80)
        ),
        EnumWindows=lambda callback, _: callback(2, 0),
    )
    assert recording._find_window_handle_for_pid(user32, 8, "pcb") == 2
    monkeypatch.setattr(recording, "_find_window_handle_for_pid", lambda *_args: 2)
    assert recording._wait_for_window(user32, 8, "pcb", 1.0) == 2
    monkeypatch.setattr(recording.shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        recording._convert_video_to_gif(
            tmp_path / "a.mp4", tmp_path / "a.gif", fps=2, width=20, timeout_seconds=1
        )

    request = _request(tmp_path, gif=tmp_path / "demo.gif")
    monkeypatch.setattr(recording, "os", SimpleNamespace(name="nt", getpid=os.getpid))
    monkeypatch.setattr(
        recording,
        "_validate_headless_request",
        lambda value: (value, {"cues": []}, SimpleNamespace(duration_ms=1)),
    )
    monkeypatch.setattr(recording.hg, "input_desktop_name", lambda: "default")
    monkeypatch.setattr(recording.hg, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(recording.hg, "process_session_id", lambda: 1)
    monkeypatch.setattr(recording.hg, "process_is_elevated", lambda: False)
    monkeypatch.setattr(recording.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(recording, "_cinematic_worker_argv", lambda *args: list(args))
    monkeypatch.setattr(
        recording.KillOnCloseJob,
        "create",
        lambda: SimpleNamespace(terminate_and_close=lambda: None),
    )
    monkeypatch.setattr(
        recording,
        "_convert_video_to_gif",
        lambda *_args, **_kwargs: request.gif_output.write_bytes(b"gif"),
    )

    class Worker:
        def wait(self, _timeout):
            result = recording.HeadlessCinematicResult(
                True, "hidden", 1, 2, 3, "p", "m", "s", str(request.video_output), "v"
            )
            result_path = Path(self.argv[self.argv.index("--result") + 1])
            result_path.write_text(json.dumps(result.as_json()), encoding="utf-8")
            return 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Desktop:
        def __init__(self, _name):
            pass

        def launch(self, argv, *, job):
            worker = Worker()
            worker.argv = argv
            return worker

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(recording.hg, "HiddenDesktop", Desktop)
    result = recording.run_headless_cinematic(request)
    assert result.ok and result.gif_sha256


def test_driver_constructor_execute_and_message_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recording, "os", SimpleNamespace(name="posix"))
    with pytest.raises(RuntimeError, match="only on Windows"):
        recording.HiddenMessageDesktopDriver(expected_pid=1)
    monkeypatch.setattr(recording, "os", SimpleNamespace(name="nt"))
    with pytest.raises(ValueError, match="positive"):
        recording.HiddenMessageDesktopDriver(expected_pid=0)
    monkeypatch.delattr(recording.ctypes, "windll", raising=False)
    with pytest.raises(RuntimeError, match="bindings"):
        recording.HiddenMessageDesktopDriver(expected_pid=1)

    calls: list[tuple[object, ...]] = []
    driver = object.__new__(recording.HiddenMessageDesktopDriver)
    driver.expected_pid = 7
    driver.default_window = "DipTrace"
    driver._last_target = None
    driver._window = lambda title: calls.append(("window", title)) or 1
    driver._hotkey = lambda *args: calls.append(("hotkey", *args))
    driver._text = lambda *args: calls.append(("text", *args))
    driver._target = lambda *_args: (2, (3, 4))
    driver._send = lambda *args: calls.append(("send", *args))
    driver._click = lambda *args: calls.append(("click", *args))
    driver._center = lambda _target: (5, 6)
    monkeypatch.setattr(recording.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    driver._execute(
        DesktopCommand(
            path=((0.1, 0.2), (0.3, 0.4)),
            click="left",
            hotkey=("f2",),
            text="x",
            pause_ms=10,
        )
    )
    driver._execute(DesktopCommand(move_to=(0.5, 0.5), click="right"))
    driver._execute(DesktopCommand(click="left"))
    assert any(call[0] == "hotkey" for call in calls)
    assert any(call[0] == "sleep" for call in calls)

    for method in ("_window", "_target", "_center", "_send"):
        delattr(driver, method)
    monkeypatch.setattr(recording, "_find_window_handle_for_pid", lambda *_args: None)
    driver.user32 = SimpleNamespace()
    with pytest.raises(RuntimeError, match="was not found"):
        driver._window("Missing")
    driver.user32 = SimpleNamespace(GetClientRect=lambda *_args: 0)
    with pytest.raises(RuntimeError, match="client rectangle"):
        driver._target(1, 0.5, 0.5)
    with pytest.raises(RuntimeError, match="target client"):
        driver._center(1)
    driver.user32 = SimpleNamespace(SendMessageTimeoutW=lambda *_args: 0)
    with pytest.raises(RuntimeError, match="bounded Win32"):
        driver._send(1, 2, 3, 4)


def test_menu_diagnostics_tolerate_broken_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = SimpleNamespace(
        item_type=lambda: (_ for _ in ()).throw(RuntimeError("bad type")),
        item_id=lambda: (_ for _ in ()).throw(RuntimeError("bad id")),
        is_checked=lambda: False,
        is_enabled=lambda: True,
        text=lambda: (_ for _ in ()).throw(RuntimeError("bad text")),
        sub_menu=lambda: (_ for _ in ()).throw(RuntimeError("bad submenu")),
    )
    record = recording._menu_item_snapshot(broken, 0)
    assert record["submenu_error"] == "bad submenu"
    assert recording._menu_value(broken, "item_id") is None
    assert recording._menu_type_has_flag(broken, 1) is False
    assert recording._menu_text(broken) is None

    monkeypatch.setattr(recording, "_MENU_DIAGNOSTIC_MAX_ITEMS", 1)
    menu = SimpleNamespace(items=lambda: [broken, broken])
    snapshot = recording._menu_snapshot(menu, "File")
    assert snapshot["truncated"] is True


def test_printwindow_encoder_success_and_failure_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = recording.ctypes.create_string_buffer(4 * 4 * 4)

    def create_bitmap(_dc, _info, _usage, bits, _section, _offset):
        bits._obj.value = recording.ctypes.addressof(frame)
        return 2

    def window_rect(_hwnd, rect):
        rect._obj.right = 4
        rect._obj.bottom = 4
        return 1

    def client_rect(_hwnd, rect):
        rect._obj.right = 4
        rect._obj.bottom = 4
        return 1

    user32 = SimpleNamespace(
        GetWindowRect=_Api(window_rect),
        GetClientRect=_Api(client_rect),
        ClientToScreen=_Api(lambda _hwnd, _point: 1),
        PrintWindow=_Api(lambda *_args: 1),
        SendMessageTimeoutW=_Api(lambda *_args: 1),
    )
    gdi32 = SimpleNamespace(
        CreateCompatibleDC=_Api(lambda _dc: 1),
        CreateDIBSection=_Api(create_bitmap),
        SelectObject=_Api(lambda *_args: 3),
        DeleteObject=_Api(lambda *_args: 1),
        DeleteDC=_Api(lambda *_args: 1),
        GdiFlush=_Api(lambda: 1),
    )
    monkeypatch.setattr(
        recording.ctypes,
        "windll",
        SimpleNamespace(gdi32=gdi32),
        raising=False,
    )
    monkeypatch.setattr(recording, "_frame_has_visible_client_content", lambda *_a, **_k: True)
    monkeypatch.setattr(recording.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(recording.time, "sleep", lambda _seconds: None)

    class Input:
        def __init__(self, mode: str = "ok") -> None:
            self.mode = mode
            self.closed = False

        def write(self, value: bytes) -> int:
            if self.mode == "broken":
                raise BrokenPipeError
            return len(value) if self.mode == "ok" else len(value) - 1

        def close(self) -> None:
            self.closed = True

    class Encoder:
        pid = 44

        def __init__(self, mode: str = "ok", code: int = 0) -> None:
            self.stdin = Input(mode)
            self.code = code

        def poll(self):
            return self.code

        def wait(self, timeout=None):
            return self.code

        def terminate(self):
            return None

        def kill(self):
            return None

    current = [Encoder()]
    monkeypatch.setattr(recording.subprocess, "Popen", lambda *_a, **_k: current[0])
    output = tmp_path / "video.mp4"
    pid = recording._record_printwindow_video_in_physical_pixels(
        user32=user32,
        hwnd=1,
        ffmpeg="ffmpeg",
        output=output,
        fps=1,
        duration_seconds=1,
        playback=lambda: None,
        prepare=lambda capture, width, height: (0, 0, width, height) if capture() else None,
    )
    assert pid == 44

    for encoder, message in (
        (Encoder("broken"), "closed unexpectedly"),
        (Encoder("partial"), "partial frame"),
        (Encoder(code=2), "encode failed"),
    ):
        current[0] = encoder
        with pytest.raises(RuntimeError, match=message):
            recording._record_printwindow_video_in_physical_pixels(
                user32=user32,
                hwnd=1,
                ffmpeg="ffmpeg",
                output=output,
                fps=1,
                duration_seconds=1,
                playback=lambda: None,
            )
