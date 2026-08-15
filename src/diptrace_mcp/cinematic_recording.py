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
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack, suppress
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from . import headless_gui as hg
from .cinematic import CinematicEvent
from .cinematic_host import (
    _PATH_POINT_PAUSE_SECONDS,
    DesktopCommand,
    desktop_commands_from_payload,
    play_manifest,
)
from .cinematic_preflight import CinematicPreflightResult, preflight_cinematic_manifest
from .diptrace_window import find_window_handle
from .windows_configurator import ConfiguratorError, validate_diptrace_directory

_WM_CLOSE = 0x0010
_WM_KEYDOWN = 0x0100
_WM_KEYUP = 0x0101
_WM_CHAR = 0x0102
_WM_HSCROLL = 0x0114
_WM_VSCROLL = 0x0115
_BM_CLICK = 0x00F5
_EM_SETSEL = 0x00B1
_WM_MOUSEMOVE = 0x0200
_WM_PRINT = 0x0317
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
_PW_RENDERFULLCONTENT = 0x00000002
_PRF_RENDER_ALL = 0x0002 | 0x0004 | 0x0008 | 0x0010
_CAPTURE_LEAD_SECONDS = 0.35
_FRAME_PADDING = 0.14
_OUTPUT_PADDING = 0.1
_MIN_GIF_TIMEOUT_SECONDS = 300.0


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BitmapInfoHeader),
        ("bmiColors", ctypes.c_uint32 * 1),
    ]


@dataclass(frozen=True, slots=True)
class HeadlessCinematicRequest:
    diptrace_root: Path
    project: Path
    manifest: Path
    video_output: Path
    editor: str
    window_title: str | None = None
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
        if self.window_title is not None and not self.window_title.strip():
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

    @property
    def effective_window_title(self) -> str:
        return self.window_title.strip() if self.window_title else self.project.stem

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
            window_title=hg._optional_string(value.get("window_title")),
            fps=hg._coerce_int(value.get("fps"), 60),
            startup_timeout_seconds=hg._coerce_float(value.get("startup_timeout_seconds"), 30.0),
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

    def fit_content(
        self,
        capture: Callable[[], bytes],
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        """Center the drawing and return its UI-free recording crop."""

        window = self._window(self.default_window)
        viewport = self._drawing_viewport(window, width, height)
        usable_width = (viewport[2] - viewport[0]) * (1.0 - 2.0 * _FRAME_PADDING)
        usable_height = (viewport[3] - viewport[1]) * (1.0 - 2.0 * _FRAME_PADDING)
        is_pcb = "pcb" in self.default_window.casefold()
        bounds_detector = _purple_outline_bbox if is_pcb else _visible_content_bbox
        if is_pcb:
            drawing, _ = self._target(window, 0.65, 0.65)
            self._hotkey(drawing, ("home",))
            time.sleep(0.1)
        current_bounds = bounds_detector(capture(), width=width, viewport=viewport)
        if current_bounds is not None and is_pcb:
            scale = min(
                usable_width / (current_bounds[2] - current_bounds[0]),
                usable_height / (current_bounds[3] - current_bounds[1]),
            )
            if scale > 1.1:
                zoom_edit = self._zoom_edit(window)
                source_zoom = self._zoom_percent(zoom_edit)
                self._set_zoom(
                    zoom_edit,
                    min(3200, max(25, round(source_zoom * scale))),
                )
                time.sleep(0.1)
                scrollbars = self._scrollbars(window)
                self._center_with_scrollbars(capture, width, viewport, scrollbars, bounds_detector)
                self._center_with_scrollbars(capture, width, viewport, scrollbars, bounds_detector)
                enlarged = bounds_detector(capture(), width=width, viewport=viewport)
                if enlarged is not None and (
                    enlarged[0] > viewport[0] + 16
                    and enlarged[1] > viewport[1] + 16
                    and enlarged[2] < viewport[2] - 16
                    and enlarged[3] < viewport[3] - 16
                ):
                    return _padded_content_box(enlarged, viewport)
                self._hotkey(drawing, ("home",))
                time.sleep(0.1)
                current_bounds = bounds_detector(capture(), width=width, viewport=viewport)
                if current_bounds is None:
                    raise RuntimeError("DipTrace PCB overview was not restored")
            return _padded_content_box(current_bounds, viewport)
        if current_bounds is not None and _content_is_framed(current_bounds, viewport):
            return _padded_content_box(current_bounds, viewport)
        scrollbars = self._scrollbars(window)
        zoom_edit = self._zoom_edit(window)
        bounds: tuple[int, int, int, int] | None = None
        source_zoom = 25
        for source_zoom in (100, 50, 25):
            self._set_zoom(zoom_edit, source_zoom)
            time.sleep(0.1)
            bounds = _visible_content_bbox(capture(), width=width, viewport=viewport)
            if bounds is None:
                bounds = self._find_visible_bounds(capture, width, viewport, scrollbars)
            if bounds is None:
                continue
            if (
                bounds[0] > viewport[0] + 4
                and bounds[1] > viewport[1] + 4
                and bounds[2] < viewport[2] - 4
                and bounds[3] < viewport[3] - 4
            ):
                break
        if bounds is None:
            raise RuntimeError("DipTrace drawing bounds were not found")
        scale = min(
            usable_width / (bounds[2] - bounds[0]),
            usable_height / (bounds[3] - bounds[1]),
        )
        self._center_with_scrollbars(capture, width, viewport, scrollbars, _visible_content_bbox)
        self._set_zoom(zoom_edit, min(3200, max(25, round(source_zoom * scale))))
        time.sleep(0.1)
        self._find_visible_bounds(capture, width, viewport, scrollbars)
        self._center_with_scrollbars(capture, width, viewport, scrollbars, _visible_content_bbox)
        final_bounds = _visible_content_bbox(capture(), width=width, viewport=viewport)
        if final_bounds is None:
            raise RuntimeError("DipTrace drawing disappeared during framing")
        return _padded_content_box(final_bounds, viewport)

    def _drawing_viewport(
        self,
        window: int,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int, int, int, int]:
        callback_type: Any = ctypes.__dict__.get("WINFUNCTYPE", ctypes.CFUNCTYPE)(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        window_rect = wintypes.RECT()
        if not self.user32.GetWindowRect(window, ctypes.byref(window_rect)):
            return (0, 0, frame_width, frame_height)
        scale = (
            max(1.0, float(self.user32.GetDpiForWindow(window)) / 96.0)
            if hasattr(self.user32, "GetDpiForWindow")
            else 1.0
        )
        panels: list[tuple[int, int, int, int]] = []

        def callback(hwnd: int, _lparam: int) -> bool:
            value = ctypes.create_unicode_buffer(64)
            self.user32.GetClassNameW(hwnd, value, len(value))
            if value.value != "TPanel":
                return True
            rect = wintypes.RECT()
            if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                panels.append(
                    (
                        max(0, round((rect.left - window_rect.left) * scale)),
                        max(0, round((rect.top - window_rect.top) * scale)),
                        min(
                            frame_width,
                            round((rect.right - window_rect.left) * scale),
                        ),
                        min(
                            frame_height,
                            round((rect.bottom - window_rect.top) * scale),
                        ),
                    )
                )
            return True

        self.user32.EnumChildWindows(window, callback_type(callback), 0)
        candidates = [
            box
            for box in panels
            if box[2] - box[0] >= frame_width * 0.45 and box[3] - box[1] >= frame_height * 0.45
        ]
        if not candidates:
            return (0, 0, frame_width, frame_height)
        viewport = max(
            candidates,
            key=lambda box: (box[2] - box[0]) * (box[3] - box[1]),
        )
        left, top, right, bottom = viewport
        for box in panels:
            if box == viewport:
                continue
            overlap = min(bottom, box[3]) - max(top, box[1])
            if overlap < (bottom - top) * 0.7:
                continue
            if box[0] <= left + 4 < box[2]:
                left = max(left, box[2])
            elif box[0] < right - 4 <= box[2]:
                right = min(right, box[0])
        return (left + 4, top + 4, right - 4, bottom - 4)

    def _zoom_edit(self, window: int) -> int:
        controls = self._child_controls(window)
        edits = [
            (box[0], hwnd)
            for hwnd, class_name, parent_class, box in controls
            if class_name == "Edit" and parent_class == "TComboBox"
        ]
        if not edits:
            raise RuntimeError("DipTrace zoom field was not found")
        return min(edits)[1]

    def _set_zoom(self, edit: int, percent: int) -> None:
        self._send(edit, _EM_SETSEL, 0, -1)
        self._text(edit, f"{percent}%")
        self._hotkey(edit, ("enter",))

    def _zoom_percent(self, edit: int) -> int:
        self.user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.SendMessageW.restype = wintypes.LPARAM
        seen: list[str] = []
        for control in (edit, int(self.user32.GetParent(edit))):
            length = int(self.user32.SendMessageW(control, 0x000E, 0, 0))
            value = ctypes.create_unicode_buffer(length + 1)
            self.user32.SendMessageW(control, 0x000D, len(value), ctypes.addressof(value))
            seen.append(value.value)
            try:
                return round(float(value.value.strip().removesuffix("%").replace(",", ".")))
            except ValueError:
                continue
        raise RuntimeError(f"DipTrace zoom value is invalid: {seen!r}")

    def _center_with_scrollbars(
        self,
        capture: Callable[[], bytes],
        width: int,
        viewport: tuple[int, int, int, int],
        scrollbars: Mapping[int, int],
        bounds_detector: Callable[..., tuple[int, int, int, int] | None],
    ) -> None:
        for axis, message, viewport_center in (
            (0, _WM_HSCROLL, (viewport[0] + viewport[2]) / 2),
            (1, _WM_VSCROLL, (viewport[1] + viewport[3]) / 2),
        ):
            scrollbar = scrollbars.get(axis)
            bounds = bounds_detector(capture(), width=width, viewport=viewport)
            if scrollbar is None or bounds is None:
                continue
            current = int(self.user32.GetScrollPos(scrollbar, 2))
            best_error = abs((bounds[axis] + bounds[axis + 2]) / 2 - viewport_center)
            best_position = current
            direction = 0
            for candidate_direction in (1, -1):
                candidate = current + candidate_direction
                self._set_scroll_position(scrollbar, message, candidate)
                time.sleep(0.05)
                candidate_bounds = bounds_detector(capture(), width=width, viewport=viewport)
                if candidate_bounds is None:
                    continue
                error = abs(
                    (candidate_bounds[axis] + candidate_bounds[axis + 2]) / 2 - viewport_center
                )
                if error < best_error:
                    best_error, best_position, direction = error, candidate, candidate_direction
                    break
            if not direction:
                self._set_scroll_position(scrollbar, message, current)
                time.sleep(0.2)
                continue
            for _ in range(99):
                candidate = best_position + direction
                if not -100 <= candidate <= 100:
                    break
                self._set_scroll_position(scrollbar, message, candidate)
                time.sleep(0.05)
                candidate_bounds = bounds_detector(capture(), width=width, viewport=viewport)
                if candidate_bounds is None:
                    break
                error = abs(
                    (candidate_bounds[axis] + candidate_bounds[axis + 2]) / 2 - viewport_center
                )
                if error >= best_error:
                    break
                best_error, best_position = error, candidate
            self._set_scroll_position(scrollbar, message, best_position)
            time.sleep(0.2)

    def _find_visible_bounds(
        self,
        capture: Callable[[], bytes],
        width: int,
        viewport: tuple[int, int, int, int],
        scrollbars: Mapping[int, int],
    ) -> tuple[int, int, int, int] | None:
        bounds = _visible_content_bbox(capture(), width=width, viewport=viewport)
        if bounds is not None or set(scrollbars) != {0, 1}:
            return bounds
        original = {
            axis: int(self.user32.GetScrollPos(scrollbar, 2))
            for axis, scrollbar in scrollbars.items()
        }
        deltas = [0, *(value for step in range(1, 11) for value in (step, -step))]
        local = sorted(
            ((dx, dy) for dx in deltas for dy in deltas),
            key=lambda pair: abs(pair[0]) + abs(pair[1]),
        )
        coarse = sorted(
            (
                (horizontal - original[0], vertical - original[1])
                for horizontal in range(-100, 101, 20)
                for vertical in range(-100, 101, 20)
            ),
            key=lambda pair: abs(pair[0]) + abs(pair[1]),
        )
        seen: set[tuple[int, int]] = set()
        for dx, dy in [*local, *coarse]:
            horizontal = min(100, max(-100, original[0] + dx))
            vertical = min(100, max(-100, original[1] + dy))
            if (horizontal, vertical) in seen:
                continue
            seen.add((horizontal, vertical))
            self._set_scroll_position(scrollbars[0], _WM_HSCROLL, horizontal)
            self._set_scroll_position(scrollbars[1], _WM_VSCROLL, vertical)
            time.sleep(0.01)
            bounds = _visible_content_bbox(capture(), width=width, viewport=viewport)
            if bounds is not None:
                return bounds
        self._set_scroll_position(scrollbars[0], _WM_HSCROLL, original[0])
        self._set_scroll_position(scrollbars[1], _WM_VSCROLL, original[1])
        return None

    def _scrollbars(self, window: int) -> dict[int, int]:
        candidates: dict[int, list[tuple[int, int]]] = {0: [], 1: []}
        for hwnd, class_name, _parent_class, box in self._child_controls(window):
            if class_name != "TScrollBar":
                continue
            control_width, control_height = box[2] - box[0], box[3] - box[1]
            axis = 0 if control_width > control_height else 1
            candidates[axis].append((max(control_width, control_height), hwnd))
        return {axis: max(controls)[1] for axis, controls in candidates.items() if controls}

    def _set_scroll_position(
        self,
        scrollbar: int,
        message: int,
        position: int,
    ) -> None:
        self.user32.SetScrollPos(scrollbar, 2, position, True)
        parent = int(self.user32.GetParent(scrollbar))
        if not parent:
            raise RuntimeError("DipTrace scrollbar has no parent window")
        self._send(parent, message, 4 | ((position & 0xFFFF) << 16), scrollbar)

    def _child_controls(self, window: int) -> list[tuple[int, str, str, tuple[int, int, int, int]]]:
        callback_type: Any = ctypes.__dict__.get("WINFUNCTYPE", ctypes.CFUNCTYPE)(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        controls: list[tuple[int, str, str, tuple[int, int, int, int]]] = []

        def class_name(hwnd: int) -> str:
            value = ctypes.create_unicode_buffer(64)
            self.user32.GetClassNameW(hwnd, value, len(value))
            return value.value

        def callback(hwnd: int, _lparam: int) -> bool:
            rect = wintypes.RECT()
            if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                controls.append(
                    (
                        int(hwnd),
                        class_name(hwnd),
                        class_name(int(self.user32.GetParent(hwnd))),
                        (rect.left, rect.top, rect.right, rect.bottom),
                    )
                )
            return True

        self.user32.EnumChildWindows(window, callback_type(callback), 0)
        return controls

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
                time.sleep(_PATH_POINT_PAUSE_SECONDS)
        else:
            target = hwnd
            click_point: tuple[int, int] | None = None
            if command.move_to is not None:
                target, click_point = self._target(hwnd, *command.move_to)
                self._send(target, _WM_MOUSEMOVE, 0, _pack_point(*click_point))
            if command.click is not None:
                self._click(
                    target,
                    click_point if click_point is not None else self._center(target),
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
    matches: list[tuple[int, int]] = []
    ctypes_any: Any = ctypes
    callback_type: Any = ctypes_any.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )

    def callback(hwnd: int, _lparam: int) -> bool:
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
            score = int(bool(user32.IsWindowVisible(hwnd)))
            if hasattr(user32, "GetClassNameW"):
                class_name = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_name, len(class_name))
                if class_name.value.casefold() == "tform1":
                    score += 8
            if hasattr(user32, "GetMenu") and user32.GetMenu(hwnd):
                score += 4
            if hasattr(user32, "GetWindowRect"):
                rect = wintypes.RECT()
                if (
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    and rect.right > rect.left
                    and rect.bottom > rect.top
                ):
                    score += 2
            matches.append((score, int(hwnd)))
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return max(matches)[1] if matches else None


def _wait_for_window(user32: Any, pid: int, title: str, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd = _find_window_handle_for_pid(user32, pid, title)
        if hwnd is not None:
            return hwnd
        time.sleep(0.1)
    raise RuntimeError(f"DipTrace window did not appear within {timeout:g}s")


def _dismiss_project_ok_dialog(user32: Any, pid: int, title: str) -> bool:
    """Dismiss DipTrace's informational XML-open dialog without physical input."""

    needle = title.casefold()
    callback_type: Any = ctypes.__dict__.get("WINFUNCTYPE", ctypes.CFUNCTYPE)(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    dialogs: list[int] = []

    def text(hwnd: int) -> str:
        length = int(user32.GetWindowTextLengthW(hwnd))
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def class_name(hwnd: int) -> str:
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer.value

    def find_dialog(hwnd: int, _lparam: int) -> bool:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if (
            int(process_id.value) == pid
            and user32.IsWindowVisible(hwnd)
            and class_name(hwnd).casefold() == "tfmymessage"
            and needle in text(hwnd).casefold()
        ):
            dialogs.append(int(hwnd))
        return True

    appearance_deadline = time.monotonic() + 2.0
    while True:
        dialogs.clear()
        user32.EnumWindows(callback_type(find_dialog), 0)
        if dialogs:
            break
        if time.monotonic() >= appearance_deadline:
            return False
        time.sleep(0.05)

    buttons: list[int] = []

    def find_button(hwnd: int, _lparam: int) -> bool:
        if (
            user32.IsWindowVisible(hwnd)
            and user32.IsWindowEnabled(hwnd)
            and class_name(hwnd).casefold() == "tbutton"
            and text(hwnd).strip().casefold() in {"ok", "ок"}
        ):
            buttons.append(int(hwnd))
            return False
        return True

    dialog = dialogs[0]
    user32.EnumChildWindows(dialog, callback_type(find_button), 0)
    if not buttons:
        raise RuntimeError("DipTrace startup dialog has no enabled OK button")
    if not user32.PostMessageW(buttons[0], _BM_CLICK, 0, 0):
        raise RuntimeError("cannot dismiss DipTrace startup dialog")
    deadline = time.monotonic() + 5.0
    while user32.IsWindow(dialog) and user32.IsWindowVisible(dialog):
        if time.monotonic() >= deadline:
            raise RuntimeError("DipTrace startup dialog did not close")
        time.sleep(0.05)
    return True


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
    path_points = 0
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
                commands = desktop_commands_from_payload(payload)
                pause_ms += sum(command.pause_ms for command in commands)
                path_points += sum(len(command.path) for command in commands)
    return max(
        1.0,
        _CAPTURE_LEAD_SECONDS
        + preflight.duration_ms / 1000.0
        + pause_ms / 1000.0
        + path_points * _PATH_POINT_PAUSE_SECONDS
        + tail,
    )


def _h264_output_arguments(
    output: str | Path,
    *,
    video_filter: str = "pad=ceil(iw/2)*2:ceil(ih/2)*2",
) -> list[str]:
    return [
        "-vf",
        video_filter,
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


def _build_printwindow_encode_command(
    ffmpeg: str,
    output: str | Path,
    *,
    width: int,
    height: int,
    fps: int,
    crop_box: tuple[int, int, int, int] | None = None,
) -> list[str]:
    if width <= 0 or height <= 0:
        raise ValueError("raw-video dimensions must be positive")
    if not 1 <= fps <= 240:
        raise ValueError("fps must be between 1 and 240")
    video_filter = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    if crop_box is not None:
        left, top, right, bottom = crop_box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("raw-video crop must be inside the frame")
        video_filter = f"crop={right - left}:{bottom - top}:{left}:{top}," + video_filter
    return [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgra",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        *_h264_output_arguments(output, video_filter=video_filter),
    ]


def _content_is_framed(
    bounds: tuple[int, int, int, int],
    viewport: tuple[int, int, int, int],
) -> bool:
    viewport_width = viewport[2] - viewport[0]
    viewport_height = viewport[3] - viewport[1]
    content_width = bounds[2] - bounds[0]
    content_height = bounds[3] - bounds[1]
    fill = max(
        content_width / (viewport_width * (1.0 - 2.0 * _FRAME_PADDING)),
        content_height / (viewport_height * (1.0 - 2.0 * _FRAME_PADDING)),
    )
    return (
        bounds[0] >= viewport[0]
        and bounds[1] >= viewport[1]
        and bounds[2] <= viewport[2]
        and bounds[3] <= viewport[3]
        and min(content_width / viewport_width, content_height / viewport_height) >= 0.2
        and 0.85 <= fill <= 1.15
        and abs(bounds[0] + bounds[2] - viewport[0] - viewport[2]) <= viewport_width * 0.12
        and abs(bounds[1] + bounds[3] - viewport[1] - viewport[3]) <= viewport_height * 0.12
    )


def _padded_content_box(
    bounds: tuple[int, int, int, int],
    viewport: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    padding_x = round((bounds[2] - bounds[0]) * _OUTPUT_PADDING)
    padding_y = round((bounds[3] - bounds[1]) * _OUTPUT_PADDING)
    return (
        max(viewport[0], bounds[0] - padding_x),
        max(viewport[1], bounds[1] - padding_y),
        min(viewport[2], bounds[2] + padding_x),
        min(viewport[3], bounds[3] + padding_y),
    )


def _visible_content_bbox(
    frame: bytes,
    *,
    width: int,
    viewport: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    """Find non-background drawing content while ignoring faint grid pixels."""

    left, top, right, bottom = viewport
    if width <= 0 or right - left < 8 or bottom - top < 8:
        return None
    sample_step = max(4, min(right - left, bottom - top) // 80)
    samples: dict[tuple[int, int, int], int] = {}
    for y in range(top + 2, bottom - 2, sample_step):
        for x in range(left + 2, right - 2, sample_step):
            offset = (y * width + x) * 4
            color = (
                frame[offset] >> 4,
                frame[offset + 1] >> 4,
                frame[offset + 2] >> 4,
            )
            samples[color] = samples.get(color, 0) + 1
    if not samples:
        return None
    background_bin = max(samples, key=lambda color: samples[color])
    background = tuple(channel * 16 + 8 for channel in background_bin)
    min_x, min_y, max_x, max_y = right, bottom, left, top
    count = 0
    for y in range(top + 2, bottom - 2, 2):
        row = y * width * 4
        for x in range(left + 2, right - 2, 2):
            offset = row + x * 4
            if (
                max(frame[offset : offset + 3]) < 220
                or max(abs(frame[offset + index] - background[index]) for index in range(3)) < 48
            ):
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            count += 1
    if count < 16:
        return None
    return (min_x, min_y, max_x + 2, max_y + 2)


def _purple_outline_bbox(
    frame: bytes,
    *,
    width: int,
    viewport: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    """Find DipTrace's purple board outline, including clipped edges."""

    left, top, right, bottom = viewport
    min_x, min_y, max_x, max_y = right, bottom, left, top
    count = 0
    for y in range(top, bottom, 2):
        row = y * width * 4
        for x in range(left, right, 2):
            offset = row + x * 4
            blue, green, red = frame[offset : offset + 3]
            if red < 80 or blue < 80 or green > 50 or green + 40 >= min(red, blue):
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            count += 1
    if count < 16:
        return None
    return (min_x, min_y, max_x + 2, max_y + 2)


def _frame_has_visible_client_content(
    frame: bytes,
    *,
    width: int,
    client_box: tuple[int, int, int, int],
) -> bool:
    left, top, right, bottom = client_box
    inset_x = max(1, (right - left) // 20)
    inset_y = max(1, (bottom - top) // 10)
    left, top = left + inset_x, top + inset_y
    right, bottom = right - inset_x, bottom - inset_y
    xs = range(left, right, max(1, (right - left) // 64))
    ys = range(top, bottom, max(1, (bottom - top) // 32))
    # ponytail: sparse central-client sampling; use a histogram for dark PCB themes.
    samples = [(y * width + x) * 4 for y in ys for x in xs]
    visible = sum(max(frame[offset : offset + 3]) > 16 for offset in samples)
    return visible >= max(1, len(samples) // 20)


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
    if not desktop and window_handle is None and (window_title is None or not window_title.strip()):
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
    command.extend(_h264_output_arguments(output))
    return command


def _record_printwindow_video(
    *,
    user32: Any,
    hwnd: int,
    ffmpeg: str,
    output: Path,
    fps: int,
    duration_seconds: float,
    playback: Callable[[], None],
    prepare: Callable[[Callable[[], bytes], int, int], tuple[int, int, int, int] | None]
    | None = None,
) -> int:
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise RuntimeError("Windows GDI bindings are unavailable")
    gdi32: Any = windll.gdi32
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PrintWindow.restype = wintypes.BOOL
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(_BitmapInfo),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.GdiFlush.argtypes = []
    gdi32.GdiFlush.restype = wintypes.BOOL

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("cannot read DipTrace window rectangle")
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        raise RuntimeError("DipTrace window rectangle is empty")
    client_rect = wintypes.RECT()
    client_origin = wintypes.POINT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)) or not user32.ClientToScreen(
        hwnd, ctypes.byref(client_origin)
    ):
        raise RuntimeError("cannot read DipTrace client rectangle")
    client_left = max(0, int(client_origin.x - rect.left))
    client_top = max(0, int(client_origin.y - rect.top))
    client_box = (
        client_left,
        client_top,
        min(width, client_left + int(client_rect.right - client_rect.left)),
        min(height, client_top + int(client_rect.bottom - client_rect.top)),
    )
    if client_box[2] <= client_box[0] or client_box[3] <= client_box[1]:
        raise RuntimeError("DipTrace client rectangle is empty")
    frame_size = width * height * 4
    bitmap_info = _BitmapInfo()
    bitmap_info.bmiHeader = _BitmapInfoHeader(
        ctypes.sizeof(_BitmapInfoHeader),
        width,
        -height,
        1,
        32,
        0,
        frame_size,
        0,
        0,
        0,
        0,
    )
    memory_dc = gdi32.CreateCompatibleDC(None)
    if not memory_dc:
        raise RuntimeError("cannot create PrintWindow device context")
    bits = ctypes.c_void_p()
    bitmap: int | None = None
    previous: int | None = None
    process: subprocess.Popen[bytes] | None = None
    resources = ExitStack()
    stderr_log: Any = None
    playback_thread: threading.Thread | None = None
    playback_errors: list[Exception] = []
    try:
        bitmap = int(
            gdi32.CreateDIBSection(
                memory_dc,
                ctypes.byref(bitmap_info),
                0,
                ctypes.byref(bits),
                None,
                0,
            )
        )
        bits_address = bits.value
        if not bitmap or not bits_address:
            raise RuntimeError("cannot allocate PrintWindow frame buffer")
        previous = int(gdi32.SelectObject(memory_dc, bitmap))
        if previous in {0, ctypes.c_void_p(-1).value}:
            raise RuntimeError("cannot select PrintWindow frame buffer")

        def capture_frame() -> tuple[bytes, bool]:
            frame: bytes | None = None
            has_client_content = False
            for flags in (0, None, _PW_RENDERFULLCONTENT):
                ctypes.memset(bits_address, 0, frame_size)
                if flags is None:
                    message_result = ctypes.c_size_t()
                    rendered = user32.SendMessageTimeoutW(
                        hwnd,
                        _WM_PRINT,
                        memory_dc,
                        _PRF_RENDER_ALL,
                        _SEND_TIMEOUT_FLAGS,
                        2_000,
                        ctypes.byref(message_result),
                    )
                else:
                    rendered = user32.PrintWindow(hwnd, memory_dc, flags)
                if not rendered:
                    continue
                gdi32.GdiFlush()
                candidate = ctypes.string_at(bits_address, frame_size)
                candidate_has_content = _frame_has_visible_client_content(
                    candidate,
                    width=width,
                    client_box=client_box,
                )
                if frame is None or candidate_has_content:
                    frame = candidate
                    has_client_content = candidate_has_content
                if candidate_has_content:
                    break
            if frame is None:
                raise RuntimeError("PrintWindow failed to render DipTrace")
            return frame, has_client_content

        crop_box = None
        if prepare is not None:
            crop_box = prepare(lambda: capture_frame()[0], width, height)
            time.sleep(0.1)

        command = _build_printwindow_encode_command(
            ffmpeg,
            output,
            width=width,
            height=height,
            fps=fps,
            crop_box=crop_box,
        )
        stderr_log = resources.enter_context(
            tempfile.TemporaryFile()  # noqa: SIM115 - ExitStack owns this file.
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=stderr_log,
        )
        if process.stdin is None:
            raise RuntimeError("cannot open ffmpeg raw-video pipe")

        def run_playback() -> None:
            try:
                playback()
            except Exception as exc:
                playback_errors.append(exc)

        total_frames = max(1, round(duration_seconds * fps))
        lead_frames = min(total_frames - 1, max(0, round(_CAPTURE_LEAD_SECONDS * fps)))
        started = time.monotonic()
        saw_visible_client_content = False
        for index in range(total_frames):
            delay = started + index / fps - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            if playback_thread is None and index >= lead_frames:
                playback_thread = threading.Thread(target=run_playback, daemon=True)
                playback_thread.start()
            frame, has_client_content = capture_frame()
            saw_visible_client_content = saw_visible_client_content or has_client_content
            try:
                written = process.stdin.write(frame)
            except BrokenPipeError as exc:
                code = process.poll()
                raise RuntimeError(
                    f"ffmpeg raw-video pipe closed unexpectedly (code {code})"
                ) from exc
            if written != frame_size:
                raise RuntimeError("ffmpeg raw-video pipe accepted a partial frame")

        if playback_thread is not None:
            playback_thread.join(5.0)
            if playback_thread.is_alive():
                raise RuntimeError("hidden cinematic playback did not finish")
        with suppress(BrokenPipeError):
            process.stdin.close()
        exit_code = process.wait(timeout=15.0)
        if exit_code != 0:
            stderr_log.seek(0)
            detail = stderr_log.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"ffmpeg raw-video encode failed with code {exit_code}"
                + (f": {detail}" if detail else "")
            )
        if playback_errors:
            raise RuntimeError(f"hidden cinematic playback failed: {playback_errors[0]}")
        if not saw_visible_client_content:
            raise RuntimeError("PrintWindow capture has no rendered client-area content")
        return process.pid
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        if playback_thread is not None and playback_thread.is_alive():
            playback_thread.join(5.0)
        if process is not None:
            if process.stdin is not None and not process.stdin.closed:
                with suppress(OSError):
                    process.stdin.close()
            if process.poll() is None:
                with suppress(OSError):
                    process.terminate()
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    with suppress(OSError):
                        process.kill()
                    with suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=2.0)
        with suppress(Exception):
            resources.close()
        if previous:
            gdi32.SelectObject(memory_dc, previous)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)


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


def _convert_video_to_gif(
    video: Path,
    gif: Path,
    *,
    fps: int,
    width: int,
    timeout_seconds: float = _MIN_GIF_TIMEOUT_SECONDS,
) -> None:
    if not 0 < timeout_seconds < float("inf"):
        raise ValueError("timeout_seconds must be finite and positive")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required for GIF conversion")
    gif.parent.mkdir(parents=True, exist_ok=True)
    gif.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="diptrace-cinematic-gif-") as raw_temp:
        palette = Path(raw_temp) / "palette.png"
        scale = f"fps={fps},scale={width}:-1:flags=lanczos"
        commands = [
            [
                ffmpeg,
                "-y",
                "-i",
                str(video),
                "-vf",
                f"{scale},palettegen",
                "-frames:v",
                "1",
                "-update",
                "1",
                str(palette),
            ],
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
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                gif.unlink(missing_ok=True)
                raise RuntimeError(f"GIF conversion timed out after {timeout_seconds:g}s") from exc
            if completed.returncode != 0:
                gif.unlink(missing_ok=True)
                raise RuntimeError(f"GIF conversion failed with code {completed.returncode}")
    if not gif.is_file() or gif.stat().st_size <= 0:
        gif.unlink(missing_ok=True)
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
    ffmpeg_pid: int | None = None
    hwnd: int | None = None
    forced = False
    error: str | None = None
    try:
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise hg.HeadlessGuiError("Windows user32 bindings are unavailable")
        user32: Any = windll.user32
        window_title = request.effective_window_title
        hwnd = _wait_for_window(
            user32,
            diptrace.pid,
            window_title,
            request.startup_timeout_seconds,
        )
        time.sleep(0.2)
        _dismiss_project_ok_dialog(user32, diptrace.pid, window_title)
        user32.ShowWindow(hwnd, 3)
        user32.UpdateWindow(hwnd)
        time.sleep(1.0)
        capture_seconds = _capture_seconds(manifest, preflight, request.tail_seconds)
        message_driver: Any = HiddenMessageDesktopDriver(
            expected_pid=diptrace.pid,
            default_window=window_title,
        )
        ffmpeg_pid = _record_printwindow_video(
            user32=user32,
            hwnd=hwnd,
            ffmpeg=ffmpeg_path,
            output=request.video_output,
            fps=request.fps,
            duration_seconds=capture_seconds,
            playback=lambda: play_manifest(manifest, message_driver),
            prepare=message_driver.fit_content,
        )
        if not request.video_output.is_file() or request.video_output.stat().st_size <= 0:
            raise hg.HeadlessGuiError("headless cinematic capture produced no video")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if hwnd is not None:
            with suppress(Exception):
                windll = getattr(ctypes, "windll", None)
                if windll is not None:
                    windll.user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
        try:
            exit_code = diptrace.wait(2.0)
        except Exception as exc:
            exit_code = None
            error = hg._append_error(error, f"DipTrace cleanup wait failed: {exc}")
        if exit_code is None:
            forced = True
            try:
                diptrace.terminate(126)
                with suppress(Exception):
                    diptrace.wait(2.0)
            except Exception as exc:
                error = hg._append_error(error, f"DipTrace cleanup failed: {exc}")
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
    request.video_output.unlink(missing_ok=True)
    if request.gif_output is not None:
        request.gif_output.unlink(missing_ok=True)

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
                    with suppress(Exception):
                        worker.wait(2.0)
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
                timeout_seconds=max(
                    _MIN_GIF_TIMEOUT_SECONDS,
                    _capture_seconds(manifest, preflight, request.tail_seconds) * 4,
                ),
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
        str(args.window_title) if args.window_title else None,
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
    capture.add_argument(
        "--window-title",
        help="Window-title substring (defaults to the project filename).",
    )
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
