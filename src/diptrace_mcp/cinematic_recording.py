from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from . import headless_gui as hg
from .cinematic import CinematicEvent
from .cinematic_host import DesktopCommand, desktop_commands_from_payload, play_manifest
from .cinematic_preflight import CinematicPreflightResult, preflight_cinematic_manifest
from .diptrace_window import find_window_handle
from .windows_configurator import ConfiguratorError, validate_diptrace_directory

_WM_CLOSE = 0x0010
_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_CHAR = 0x0102
_WM_MOUSEMOVE = 0x0200
_BUTTON_MESSAGES = {
    "left": (0x0201, 0x0202, 0x0203, 0x0001),
    "right": (0x0204, 0x0205, 0x0206, 0x0002),
    "middle": (0x0207, 0x0208, 0x0209, 0x0010),
}
_SINGLE_KEYS = {
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
}
_SEND_TIMEOUT_FLAGS = 0x0001 | 0x0002
_CHILD_FLAGS = 0x0001 | 0x0002
_CAPTURE_LEAD_SECONDS = 0.35


@dataclass(frozen=True, slots=True)
class HeadlessCinematicRequest:
    diptrace_root: Path
    project: Path
    manifest: Path
    video_output: Path
    editor: str
    window_title: str = "DipTrace"
    fps: int = 60
    startup_timeout_seconds: float = 30.0
    tail_seconds: float = 0.75
    gif_output: Path | None = None
    gif_fps: int = 20
    gif_width: int = 1280

    def __post_init__(self) -> None:
        editor = self.editor.strip().lower()
        if editor not in hg._EDITOR_EXECUTABLES:
            choices = ", ".join(sorted(hg._EDITOR_EXECUTABLES))
            raise ValueError(f"editor must be one of: {choices}")
        if not self.window_title.strip():
            raise ValueError("window_title must not be empty")
        if not 1 <= self.fps <= 240:
            raise ValueError("fps must be between 1 and 240")
        if not 1 <= self.gif_fps <= 60:
            raise ValueError("gif_fps must be between 1 and 60")
        if not 320 <= self.gif_width <= 3840:
            raise ValueError("gif_width must be between 320 and 3840")
        if not 0 < self.startup_timeout_seconds <= 300:
            raise ValueError("startup_timeout_seconds must be > 0 and <= 300")
        if not 0 <= self.tail_seconds <= 10:
            raise ValueError("tail_seconds must be between 0 and 10")
        video = Path(self.video_output)
        gif = Path(self.gif_output) if self.gif_output is not None else None
        if video.suffix.lower() != ".mp4":
            raise ValueError("video_output must use the .mp4 suffix")
        if gif is not None and gif.suffix.lower() != ".gif":
            raise ValueError("gif_output must use the .gif suffix")
        object.__setattr__(self, "editor", editor)
        object.__setattr__(self, "diptrace_root", Path(self.diptrace_root))
        object.__setattr__(self, "project", Path(self.project))
        object.__setattr__(self, "manifest", Path(self.manifest))
        object.__setattr__(self, "video_output", video)
        object.__setattr__(self, "gif_output", gif)

    @property
    def executable(self) -> Path:
        return self.diptrace_root / hg._EDITOR_EXECUTABLES[self.editor]

    def as_json(self) -> dict[str, object]:
        return {
            "diptrace_root": str(self.diptrace_root),
            "project": str(self.project),
            "manifest": str(self.manifest),
            "video_output": str(self.video_output),
            "editor": self.editor,
            "window_title": self.window_title,
            "fps": self.fps,
            "startup_timeout_seconds": self.startup_timeout_seconds,
            "tail_seconds": self.tail_seconds,
            "gif_output": str(self.gif_output) if self.gif_output else None,
            "gif_fps": self.gif_fps,
            "gif_width": self.gif_width,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> HeadlessCinematicRequest:
        gif = hg._optional_string(value.get("gif_output"))
        return cls(
            diptrace_root=Path(hg._required_string(value, "diptrace_root")),
            project=Path(hg._required_string(value, "project")),
            manifest=Path(hg._required_string(value, "manifest")),
            video_output=Path(hg._required_string(value, "video_output")),
            editor=hg._required_string(value, "editor"),
            window_title=hg._string_or_default(value.get("window_title"), "DipTrace"),
            fps=hg._coerce_int(value.get("fps"), 60),
            startup_timeout_seconds=hg._coerce_float(
                value.get("startup_timeout_seconds"), 30.0
            ),
            tail_seconds=hg._coerce_float(value.get("tail_seconds"), 0.75),
            gif_output=Path(gif) if gif else None,
            gif_fps=hg._coerce_int(value.get("gif_fps"), 20),
            gif_width=hg._coerce_int(value.get("gif_width"), 1280),
        )


@dataclass(frozen=True, slots=True)
class HeadlessCinematicResult:
    ok: bool
    desktop_name: str
    worker_pid: int
    diptrace_pid: int | None
    ffmpeg_pid: int | None
    project: str
    manifest: str
    manifest_sha256: str | None
    video_output: str
    video_sha256: str | None
    gif_output: str | None = None
    gif_sha256: str | None = None
    input_desktop_before: str | None = None
    input_desktop_after: str | None = None
    window_station_name: str | None = None
    session_id: int | None = None
    forced_termination: bool = False
    error: str | None = None

    def as_json(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))

    @classmethod
    def from_json(cls, value: Mapping[str, object]) -> HeadlessCinematicResult:
        return cls(
            ok=bool(value.get("ok", False)),
            desktop_name=hg._string_or_default(value.get("desktop_name"), "unknown"),
            worker_pid=hg._coerce_int(value.get("worker_pid"), 0),
            diptrace_pid=hg._optional_int(value.get("diptrace_pid")),
            ffmpeg_pid=hg._optional_int(value.get("ffmpeg_pid")),
            project=hg._string_or_default(value.get("project"), ""),
            manifest=hg._string_or_default(value.get("manifest"), ""),
            manifest_sha256=hg._optional_string(value.get("manifest_sha256")),
            video_output=hg._string_or_default(value.get("video_output"), ""),
            video_sha256=hg._optional_string(value.get("video_sha256")),
            gif_output=hg._optional_string(value.get("gif_output")),
            gif_sha256=hg._optional_string(value.get("gif_sha256")),
            input_desktop_before=hg._optional_string(value.get("input_desktop_before")),
            input_desktop_after=hg._optional_string(value.get("input_desktop_after")),
            window_station_name=hg._optional_string(value.get("window_station_name")),
            session_id=hg._optional_int(value.get("session_id")),
            forced_termination=bool(value.get("forced_termination", False)),
            error=hg._optional_string(value.get("error")),
        )


class HiddenMessageDesktopDriver:
    """Replay through window messages without touching global physical input."""

    def __init__(self, *, expected_pid: int, default_window: str = "DipTrace") -> None:
        if os.name != "nt":
            raise RuntimeError("hidden cinematic playback is available only on Windows")
        if expected_pid <= 0:
            raise ValueError("expected_pid must be positive")
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise RuntimeError("Windows user32 bindings are unavailable")
        self.user32: Any = windll.user32
        self.expected_pid = expected_pid
        self.default_window = default_window
        self._last_target: int | None = None

    def handle(self, event: CinematicEvent) -> None:
        commands = desktop_commands_from_payload(
            event.payload,
            default_window=self.default_window,
        )
        if not commands:
            if event.kind == "focus":
                self._window(self.default_window)
            return
        for command in commands:
            self._execute(command)

    def _execute(self, command: DesktopCommand) -> None:
        hwnd = self._window(command.window_title_contains)
        if command.hotkey:
            self._hotkey(hwnd, command.hotkey)
        if command.text:
            self._text(self._last_target or hwnd, command.text)
        if command.path:
            for x, y in command.path:
                target, point = self._target(hwnd, x, y)
                self._send(target, _WM_MOUSEMOVE, 0, _pack_point(*point))
                self._click(target, point, command.click or "left", command.click_count)
        else:
            target = hwnd
            point: tuple[int, int] | None = None
            if command.move_to is not None:
                target, point = self._target(hwnd, *command.move_to)
                self._send(target, _WM_MOUSEMOVE, 0, _pack_point(*point))
            if command.click is not None:
                self._click(
                    target,
                    point if point is not None else self._center(target),
                    command.click,
                    command.click_count,
                )
        if command.pause_ms:
            time.sleep(command.pause_ms / 1000.0)

    def _window(self, title: str) -> int:
        hwnd = _find_window_handle_for_pid(self.user32, self.expected_pid, title)
        if hwnd is None:
            raise RuntimeError(f"DipTrace window was not found for pid {self.expected_pid}")
        return hwnd

    def _target(
        self,
        hwnd: int,
        normalized_x: float,
        normalized_y: float,
    ) -> tuple[int, tuple[int, int]]:
        rect = wintypes.RECT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("cannot read DipTrace client rectangle")
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise RuntimeError("DipTrace client rectangle is empty")
        point = wintypes.POINT(
            min(max(round(width * normalized_x), 0), width - 1),
            min(max(round(height * normalized_y), 0), height - 1),
        )
        current = hwnd
        for _ in range(8):
            child = int(self.user32.ChildWindowFromPointEx(current, point, _CHILD_FLAGS))
            if not child or child == current:
                break
            mapped = wintypes.POINT(point.x, point.y)
            self.user32.MapWindowPoints(current, child, ctypes.byref(mapped), 1)
            current = child
            point = mapped
        self._last_target = current
        return current, (int(point.x), int(point.y))

    def _center(self, hwnd: int) -> tuple[int, int]:
        rect = wintypes.RECT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("cannot read target client rectangle")
        return (
            max((rect.right - rect.left) // 2, 0),
            max((rect.bottom - rect.top) // 2, 0),
        )

    def _send(self, hwnd: int, message: int, wparam: int, lparam: int) -> None:
        result = ctypes.c_size_t()
        if not self.user32.SendMessageTimeoutW(
            hwnd,
            message,
            wparam,
            lparam,
            _SEND_TIMEOUT_FLAGS,
            2_000,
            ctypes.byref(result),
        ):
            raise RuntimeError(f"bounded Win32 message failed: 0x{message:04x}")

    def _click(
        self,
        hwnd: int,
        point: tuple[int, int],
        button: str,
        count: int,
    ) -> None:
        down, up, double, mask = _BUTTON_MESSAGES[button]
        packed = _pack_point(*point)
        self._send(hwnd, down, mask, packed)
        self._send(hwnd, up, 0, packed)
        if count >= 2:
            self._send(hwnd, double, mask, packed)
            self._send(hwnd, up, 0, packed)
        if count == 3:
            self._send(hwnd, down, mask, packed)
            self._send(hwnd, up, 0, packed)

    def _hotkey(self, hwnd: int, keys: Sequence[str]) -> None:
        if len(keys) != 1:
            raise RuntimeError(
                "hidden cinematic mode refuses modifier/multi-key hotkeys; "
                "configure a message-safe click macro"
            )
        virtual_key = _virtual_key(keys[0])
        self._send(hwnd, _WM_KEYDOWN, virtual_key, 0)
        self._send(hwnd, _WM_KEYUP, virtual_key, 0)

    def _text(self, hwnd: int, text: str) -> None:
        encoded = text.encode("utf-16-le")
        for offset in range(0, len(encoded), 2):
            code_unit = int.from_bytes(encoded[offset : offset + 2], "little")
            self._send(hwnd, _WM_CHAR, code_unit, 0)


def _virtual_key(key: str) -> int:
    normalized = key.strip().lower()
    if normalized in _SINGLE_KEYS:
        return _SINGLE_KEYS[normalized]
    if len(normalized) == 1 and normalized.isascii() and normalized.isalnum():
        return ord(normalized.upper())
    if normalized.startswith("f") and normalized[1:].isdigit():
        number = int(normalized[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    raise ValueError(f"unsupported message-safe key name: {key}")


def _pack_point(x: int, y: int) -> int:
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


def _find_window_handle_for_pid(user32: Any, pid: int, title: str) -> int | None:
    needle = title.casefold()
    matches: list[int] = []
    callback_type: Any = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if int(process_id.value) != pid:
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        if needle in buffer.value.casefold():
            matches.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return matches[0] if matches else None


def _wait_for_window(user32: Any, pid: int, title: str, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = _find_window_handle_for_pid(user32, pid, title)
        if hwnd is not None:
            return hwnd
        time.sleep(0.1)
    raise RuntimeError(f"DipTrace window did not appear within {timeout:g}s")


def _read_manifest(path: Path) -> tuple[dict[str, Any], CinematicPreflightResult]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read cinematic manifest: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("cinematic manifest root must be an object")
    manifest = cast(dict[str, Any], raw)
    return manifest, preflight_cinematic_manifest(manifest)


def _validate_headless_request(
    request: HeadlessCinematicRequest,
) -> tuple[HeadlessCinematicRequest, dict[str, Any], CinematicPreflightResult]:
    try:
        root = validate_diptrace_directory(request.diptrace_root).root
    except ConfiguratorError as exc:
        raise hg.HeadlessGuiError(str(exc)) from exc
    request = replace(
        request,
        diptrace_root=root,
        project=request.project.expanduser().resolve(strict=False),
        manifest=request.manifest.expanduser().resolve(strict=False),
        video_output=request.video_output.expanduser().resolve(strict=False),
        gif_output=(
            request.gif_output.expanduser().resolve(strict=False)
            if request.gif_output is not None
            else None
        ),
    )
    if not request.executable.is_file():
        raise hg.HeadlessGuiError(f"selected DipTrace editor is missing: {request.executable}")
    if not request.project.is_file():
        raise hg.HeadlessGuiError(f"project file does not exist: {request.project}")
    if not request.manifest.is_file():
        raise hg.HeadlessGuiError(f"cinematic manifest does not exist: {request.manifest}")
    if request.video_output in {request.project, request.manifest}:
        raise hg.HeadlessGuiError("capture output must not overwrite project or manifest")
    if request.gif_output is not None:
        if request.gif_output in {request.project, request.manifest}:
            raise hg.HeadlessGuiError("capture output must not overwrite project or manifest")
        if request.gif_output == request.video_output:
            raise hg.HeadlessGuiError("video and GIF outputs must be different files")
    manifest, preflight = _read_manifest(request.manifest)
    return request, manifest, preflight


def _capture_seconds(
    manifest: Mapping[str, Any],
    preflight: CinematicPreflightResult,
    tail: float,
) -> float:
    pause_ms = 0
    cues = manifest.get("cues")
    if isinstance(cues, list):
        for cue in cues:
            if not isinstance(cue, Mapping):
                continue
            event = cue.get("event")
            if not isinstance(event, Mapping):
                continue
            payload = event.get("payload")
            if isinstance(payload, Mapping):
                pause_ms += sum(
                    command.pause_ms
                    for command in desktop_commands_from_payload(payload)
                )
    return max(
        1.0,
        _CAPTURE_LEAD_SECONDS
        + preflight.duration_ms / 1000.0
        + pause_ms / 1000.0
        + tail,
    )


def build_windows_capture_command(
    output: str | Path,
    *,
    window_title: str | None = "DipTrace",
    window_handle: int | None = None,
    desktop: bool = False,
    fps: int = 60,
    duration_seconds: float | None = None,
    draw_mouse: bool = True,
) -> list[str]:
    """Build a shell-free ffmpeg gdigrab command for one window or the desktop."""

    if fps < 1 or fps > 240:
        raise ValueError("fps must be between 1 and 240")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if window_handle is not None and window_handle <= 0:
        raise ValueError("window_handle must be a positive integer")
    if desktop and (window_handle is not None or window_title not in {None, "DipTrace"}):
        raise ValueError("desktop capture cannot also select a window")
    if not desktop and window_handle is None and (
        window_title is None or not window_title.strip()
    ):
        raise ValueError("window_title or window_handle is required for window capture")

    if desktop:
        target = "desktop"
    elif window_handle is not None:
        target = f"hwnd=0x{window_handle:x}"
    else:
        target = f"title={window_title}"
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        str(fps),
        "-draw_mouse",
        "1" if draw_mouse else "0",
        "-i",
        target,
    ]
    if duration_seconds is not None:
        command.extend(["-t", f"{duration_seconds:g}"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return command


def record_windows(
    output: str | Path,
    *,
    window_title: str | None = "DipTrace",
    desktop: bool = False,
    fps: int = 60,
    duration_seconds: float | None = None,
    draw_mouse: bool = True,
) -> int:
    """Record synchronously with ffmpeg. Without duration, Ctrl+C stops capture."""

    if os.name != "nt":
        raise RuntimeError("cinematic window recording is currently available only on Windows")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for cinematic window recording")
    window_handle = None
    if not desktop:
        if window_title is None or not window_title.strip():
            raise ValueError("window_title is required unless desktop capture is selected")
        window_handle = find_window_handle(window_title)
    command = build_windows_capture_command(
        output,
        window_title=window_title,
        window_handle=window_handle,
        desktop=desktop,
        fps=fps,
        duration_seconds=duration_seconds,
        draw_mouse=draw_mouse,
    )
    return subprocess.run(command, check=False).returncode


def _convert_video_to_gif(video: Path, gif: Path, *, fps: int, width: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for GIF conversion")
    gif.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="diptrace-cinematic-gif-") as raw_temp:
        palette = Path(raw_temp) / "palette.png"
        scale = f"fps={fps},scale={width}:-1:flags=lanczos"
        commands = [
            [ffmpeg, "-y", "-i", str(video), "-vf", f"{scale},palettegen", str(palette)],
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-i",
                str(palette),
                "-lavfi",
                f"{scale}[x];[x][1:v]paletteuse",
                str(gif),
            ],
        ]
        for command in commands:
            completed = subprocess.run(command, check=False)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"GIF conversion failed with code {completed.returncode}"
                )
    if not gif.is_file() or gif.stat().st_size <= 0:
        raise RuntimeError("GIF conversion produced no output")


def _cinematic_worker_argv(*args: str) -> list[str]:
    if bool(sys.__dict__.get("frozen", False)):
        return [sys.executable, "cinematic", *args]
    return [
        sys.executable,
        "-m",
        "diptrace_mcp.cinematic_recording",
        "headless-capture",
        *args,
    ]


def _perform_hidden_capture(
    request: HeadlessCinematicRequest,
    *,
    desktop_name: str,
    expected_session: int,
) -> HeadlessCinematicResult:
    request, manifest, preflight = _validate_headless_request(request)
    if hg.process_is_elevated():
        raise hg.HeadlessGuiError("headless cinematic worker must not be elevated")
    if hg.thread_desktop_name().casefold() != desktop_name.casefold():
        raise hg.HeadlessGuiError("cinematic worker landed on the wrong desktop")
    station = hg.process_window_station_name()
    session = hg.process_session_id()
    if station.casefold() != hg._INTERACTIVE_WINDOW_STATION.casefold():
        raise hg.HeadlessGuiError("cinematic worker is not attached to WinSta0")
    if session != expected_session:
        raise hg.HeadlessGuiError("cinematic worker landed in the wrong Windows session")
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        raise hg.HeadlessGuiError("ffmpeg is required for headless cinematic capture")

    qualified = f"{station}\\{desktop_name}"
    request.video_output.parent.mkdir(parents=True, exist_ok=True)
    request.video_output.unlink(missing_ok=True)
    diptrace = hg._launch_process_on_desktop(
        [str(request.executable), str(request.project)],
        qualified,
    )
    ffmpeg_process: hg.CreatedProcess | None = None
    ffmpeg_pid: int | None = None
    hwnd: int | None = None
    forced = False
    error: str | None = None
    try:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise hg.HeadlessGuiError("Windows user32 bindings are unavailable")
        user32: Any = windll.user32
        hwnd = _wait_for_window(
            user32,
            diptrace.pid,
            request.window_title,
            request.startup_timeout_seconds,
        )
        user32.ShowWindow(hwnd, 3)
        capture_seconds = _capture_seconds(manifest, preflight, request.tail_seconds)
        command = build_windows_capture_command(
            request.video_output,
            window_title=None,
            desktop=True,
            fps=request.fps,
            duration_seconds=capture_seconds,
            draw_mouse=False,
        )
        command[0] = ffmpeg_path
        ffmpeg_process = hg._launch_process_on_desktop(command, qualified)
        ffmpeg_pid = ffmpeg_process.pid
        time.sleep(_CAPTURE_LEAD_SECONDS)
        play_manifest(
            manifest,
            HiddenMessageDesktopDriver(
                expected_pid=diptrace.pid,
                default_window=request.window_title,
            ),
        )
        exit_code = ffmpeg_process.wait(capture_seconds + 15.0)
        if exit_code is None:
            ffmpeg_process.terminate(124)
            ffmpeg_process.wait(2.0)
            raise hg.HeadlessGuiError("headless cinematic ffmpeg capture timed out")
        if exit_code != 0:
            raise hg.HeadlessGuiError(
                f"headless cinematic ffmpeg exited with code {exit_code}"
            )
        if not request.video_output.is_file() or request.video_output.stat().st_size <= 0:
            raise hg.HeadlessGuiError("headless cinematic capture produced no video")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if ffmpeg_process is not None:
            with suppress(Exception):
                if ffmpeg_process.wait(0) is None:
                    ffmpeg_process.terminate(125)
            ffmpeg_process.close()
        if hwnd is not None:
            with suppress(Exception):
                windll = getattr(ctypes, "windll", None)
                if windll is not None:
                    windll.user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
        with suppress(Exception):
            if diptrace.wait(2.0) is None:
                forced = True
                diptrace.terminate(126)
        diptrace.close()

    return HeadlessCinematicResult(
        ok=error is None,
        desktop_name=desktop_name,
        worker_pid=os.getpid(),
        diptrace_pid=diptrace.pid,
        ffmpeg_pid=ffmpeg_pid,
        project=str(request.project),
        manifest=str(request.manifest),
        manifest_sha256=preflight.content_sha256,
        video_output=str(request.video_output),
        video_sha256=hg._sha256(request.video_output),
        window_station_name=station,
        session_id=session,
        forced_termination=forced,
        error=error,
    )


def run_headless_cinematic(
    request: HeadlessCinematicRequest,
) -> HeadlessCinematicResult:
    if os.name != "nt":
        raise hg.HeadlessGuiError("headless cinematic capture is available only on Windows")
    if hg.process_is_elevated():
        raise hg.HeadlessGuiError("headless cinematic capture must not be elevated")
    request, manifest, preflight = _validate_headless_request(request)
    if shutil.which("ffmpeg") is None:
        raise hg.HeadlessGuiError("ffmpeg is required for headless cinematic capture")

    before = hg.input_desktop_name()
    station_before = hg.process_window_station_name()
    session_before = hg.process_session_id()
    desktop_name = f"DipTraceMCP-Cinematic-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    timeout = (
        request.startup_timeout_seconds
        + _capture_seconds(manifest, preflight, request.tail_seconds)
        + 45.0
    )
    with tempfile.TemporaryDirectory(prefix="diptrace-headless-cinematic-") as raw_temp:
        request_path = Path(raw_temp) / "request.json"
        result_path = Path(raw_temp) / "result.json"
        payload = request.as_json()
        payload["_expected_session_id"] = session_before
        hg._write_json(request_path, payload)
        with hg.HiddenDesktop(desktop_name) as desktop:
            argv = _cinematic_worker_argv(
                "_worker",
                "--request",
                str(request_path),
                "--result",
                str(result_path),
                "--desktop-name",
                desktop_name,
            )
            with desktop.launch(argv) as worker:
                exit_code = worker.wait(timeout)
                if exit_code is None:
                    worker.terminate(124)
                    raise hg.HeadlessGuiError("headless cinematic worker timed out")
        if not result_path.is_file():
            raise hg.HeadlessGuiError(
                f"cinematic worker exited with code {exit_code} without a result"
            )
        result = HeadlessCinematicResult.from_json(hg._load_json(result_path))

    after = hg.input_desktop_name()
    station_after = hg.process_window_station_name()
    session_after = hg.process_session_id()
    errors: list[str] = []
    if before is not None and after is not None and before != after:
        errors.append(f"input desktop changed unexpectedly: {before!r} -> {after!r}")
    if station_after.casefold() != station_before.casefold():
        errors.append("window station changed unexpectedly")
    if session_after != session_before:
        errors.append("Windows session changed unexpectedly")
    result = replace(
        result,
        input_desktop_before=before,
        input_desktop_after=after,
        window_station_name=station_after,
        session_id=session_after,
    )
    if errors:
        combined = [value for value in [result.error, *errors] if value]
        result = replace(result, ok=False, error="; ".join(combined))
    if result.ok and request.gif_output is not None:
        try:
            _convert_video_to_gif(
                request.video_output,
                request.gif_output,
                fps=request.gif_fps,
                width=request.gif_width,
            )
            result = replace(
                result,
                gif_output=str(request.gif_output),
                gif_sha256=hg._sha256(request.gif_output),
            )
        except Exception as exc:
            result = replace(
                result,
                ok=False,
                gif_output=str(request.gif_output),
                gif_sha256=hg._sha256(request.gif_output),
                error=f"{type(exc).__name__}: {exc}",
            )
    return result


def _cmd_headless_worker(args: argparse.Namespace) -> int:
    result_path = Path(str(args.result))
    payload: dict[str, object] = {}
    try:
        payload = hg._load_json(Path(str(args.request)))
        result = _perform_hidden_capture(
            HeadlessCinematicRequest.from_json(payload),
            desktop_name=str(args.desktop_name),
            expected_session=hg._coerce_int(payload.get("_expected_session_id"), -1),
        )
    except Exception as exc:
        result = HeadlessCinematicResult(
            False,
            str(args.desktop_name),
            os.getpid(),
            None,
            None,
            hg._string_or_default(payload.get("project"), ""),
            hg._string_or_default(payload.get("manifest"), ""),
            None,
            hg._string_or_default(payload.get("video_output"), ""),
            None,
            gif_output=hg._optional_string(payload.get("gif_output")),
            error=f"{type(exc).__name__}: {exc}",
        )
    hg._write_json(result_path, result.as_json())
    return 0 if result.ok else 1


def _cmd_headless_capture(args: argparse.Namespace) -> int:
    request = HeadlessCinematicRequest(
        Path(str(args.diptrace_root)),
        Path(str(args.project)),
        Path(str(args.manifest)),
        Path(str(args.video)),
        str(args.editor),
        str(args.window_title),
        int(args.fps),
        float(args.startup_timeout),
        float(args.tail),
        Path(str(args.gif)) if args.gif else None,
        int(args.gif_fps),
        int(args.gif_width),
    )
    try:
        result = run_headless_cinematic(request)
    except (hg.HeadlessGuiError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result.as_json(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _build_headless_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-headless-gui cinematic",
        description="Capture DipTrace cinematic playback on a hidden Win32 desktop.",
    )
    subs = parser.add_subparsers(dest="command", required=True)
    capture = subs.add_parser("capture")
    capture.add_argument("--diptrace-root", required=True)
    capture.add_argument("--project", required=True)
    capture.add_argument("--editor", choices=sorted(hg._EDITOR_EXECUTABLES), required=True)
    capture.add_argument("--manifest", required=True)
    capture.add_argument("--video", required=True)
    capture.add_argument("--gif")
    capture.add_argument("--window-title", default="DipTrace")
    capture.add_argument("--fps", type=int, default=60)
    capture.add_argument("--gif-fps", type=int, default=20)
    capture.add_argument("--gif-width", type=int, default=1280)
    capture.add_argument("--startup-timeout", type=float, default=30.0)
    capture.add_argument("--tail", type=float, default=0.75)
    capture.set_defaults(handler=_cmd_headless_capture)

    worker = subs.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--request", required=True)
    worker.add_argument("--result", required=True)
    worker.add_argument("--desktop-name", required=True)
    worker.set_defaults(handler=_cmd_headless_worker)
    return parser


def headless_main(argv: Sequence[str] | None = None) -> int:
    args = _build_headless_parser().parse_args(argv)
    return int(args.handler(args))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-cinematic-record",
        description="Record a DipTrace or arbitrary Windows window for cinematic playback.",
    )
    parser.add_argument("output", type=Path)
    parser.add_argument("--window-title", default="DipTrace")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--hide-mouse", action="store_true")
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print a title-based shell-free ffmpeg argument vector without recording.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    effective = list(argv) if argv is not None else list(sys.argv[1:])
    if effective and effective[0] == "headless-capture":
        return headless_main(effective[1:])
    args = _build_parser().parse_args(effective)
    window_title = None if args.desktop else args.window_title
    if args.print_command:
        command = build_windows_capture_command(
            args.output,
            window_title=window_title,
            desktop=args.desktop,
            fps=args.fps,
            duration_seconds=args.duration,
            draw_mouse=not args.hide_mouse,
        )
        print(subprocess.list2cmdline(command))
        return 0
    return record_windows(
        args.output,
        window_title=window_title,
        desktop=args.desktop,
        fps=args.fps,
        duration_seconds=args.duration,
        draw_mouse=not args.hide_mouse,
    )


if __name__ == "__main__":
    raise SystemExit(main())
