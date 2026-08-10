from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import json
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .cinematic import CinematicEvent


@dataclass(frozen=True, slots=True)
class DesktopCommand:
    window_title_contains: str = "DipTrace"
    move_to: tuple[float, float] | None = None
    path: tuple[tuple[float, float], ...] = ()
    click: str | None = None
    click_count: int = 1
    hotkey: tuple[str, ...] = ()
    text: str | None = None
    pause_ms: int = 0

    def __post_init__(self) -> None:
        if not self.window_title_contains.strip():
            raise ValueError("window_title_contains must not be empty")
        if self.move_to is not None:
            x, y = self.move_to
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("move_to coordinates must be normalized to 0..1")
        for x, y in self.path:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("path coordinates must be normalized to 0..1")
        if self.move_to is not None and self.path:
            raise ValueError("desktop command cannot use move_to and path together")
        if self.click not in {None, "left", "right", "middle"}:
            raise ValueError("click must be left, right, middle or omitted")
        if not 1 <= self.click_count <= 3:
            raise ValueError("click_count must be between 1 and 3")
        if not 0 <= self.pause_ms <= 10_000:
            raise ValueError("pause_ms must be between 0 and 10000")


def _normalized_point(value: object, *, field_name: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError(f"{field_name} must contain [x, y]")
    return float(value[0]), float(value[1])


def _desktop_command_from_raw(
    raw: Mapping[str, Any],
    *,
    default_window: str,
) -> DesktopCommand:
    move_raw = raw.get("move_to")
    move_to = (
        _normalized_point(move_raw, field_name="desktop.move_to")
        if move_raw is not None
        else None
    )

    path_raw = raw.get("path")
    path: tuple[tuple[float, float], ...] = ()
    if path_raw is not None:
        if not isinstance(path_raw, Sequence) or isinstance(path_raw, (str, bytes)):
            raise ValueError("desktop.path must be an array of [x, y] points")
        path = tuple(
            _normalized_point(point, field_name=f"desktop.path[{index}]")
            for index, point in enumerate(path_raw)
        )

    hotkey_raw = raw.get("hotkey")
    hotkey: tuple[str, ...] = ()
    if hotkey_raw is not None:
        if (
            not isinstance(hotkey_raw, Sequence)
            or isinstance(hotkey_raw, (str, bytes))
            or not all(isinstance(value, str) and value.strip() for value in hotkey_raw)
        ):
            raise ValueError("desktop.hotkey must be an array of key names")
        hotkey = tuple(str(value).lower() for value in hotkey_raw)

    text = raw.get("text")
    if text is not None and not isinstance(text, str):
        raise ValueError("desktop.text must be a string")

    return DesktopCommand(
        window_title_contains=str(raw.get("window_title_contains") or default_window),
        move_to=move_to,
        path=path,
        click=str(raw["click"]).lower() if raw.get("click") is not None else None,
        click_count=int(raw.get("click_count", 1)),
        hotkey=hotkey,
        text=text,
        pause_ms=int(raw.get("pause_ms", 0)),
    )


def desktop_commands_from_payload(
    payload: Mapping[str, Any],
    *,
    default_window: str = "DipTrace",
) -> tuple[DesktopCommand, ...]:
    raw = payload.get("desktop")
    if raw is None:
        return ()
    if not isinstance(raw, Mapping):
        raise ValueError("desktop payload must be an object")

    window_title = str(raw.get("window_title_contains") or default_window)
    steps_raw = raw.get("steps")
    if steps_raw is None:
        return (_desktop_command_from_raw(raw, default_window=window_title),)
    if not isinstance(steps_raw, Sequence) or isinstance(steps_raw, (str, bytes)):
        raise ValueError("desktop.steps must be an array of command objects")
    if not steps_raw:
        raise ValueError("desktop.steps must not be empty")

    commands: list[DesktopCommand] = []
    for index, step in enumerate(steps_raw):
        if not isinstance(step, Mapping):
            raise ValueError(f"desktop.steps[{index}] must be an object")
        commands.append(_desktop_command_from_raw(step, default_window=window_title))
    return tuple(commands)


def desktop_command_from_payload(
    payload: Mapping[str, Any],
    *,
    default_window: str = "DipTrace",
) -> DesktopCommand | None:
    """Compatibility parser for payloads that contain at most one desktop command."""

    commands = desktop_commands_from_payload(payload, default_window=default_window)
    if not commands:
        return None
    if len(commands) != 1:
        raise ValueError("desktop payload contains multiple commands")
    return commands[0]


class DryRunDesktopDriver:
    def __init__(self, *, default_window: str = "DipTrace") -> None:
        self.default_window = default_window
        self.commands: list[DesktopCommand] = []

    def handle(self, event: CinematicEvent) -> None:
        self.commands.extend(
            desktop_commands_from_payload(event.payload, default_window=self.default_window)
        )


class WindowsDesktopDriver:
    """Small dependency-free Windows host driver for deterministic cinematic playback."""

    _MOUSE_FLAGS = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }
    _VK = {
        "ctrl": 0x11,
        "control": 0x11,
        "shift": 0x10,
        "alt": 0x12,
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

    def __init__(
        self,
        *,
        default_window: str = "DipTrace",
        cursor_motion_seconds: float = 0.18,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("WindowsDesktopDriver is available only on Windows")
        if cursor_motion_seconds < 0:
            raise ValueError("cursor_motion_seconds must be >= 0")
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            raise RuntimeError("Windows user32 bindings are unavailable")
        self.default_window = default_window
        self.cursor_motion_seconds = cursor_motion_seconds
        self.user32: Any = windll.user32

    def handle(self, event: CinematicEvent) -> None:
        commands = desktop_commands_from_payload(
            event.payload,
            default_window=self.default_window,
        )
        if not commands:
            if event.kind == "focus":
                self._focus_window(self.default_window)
            return
        for command in commands:
            self._execute(command)

    def _execute(self, command: DesktopCommand) -> None:
        hwnd = self._focus_window(command.window_title_contains)
        if command.hotkey:
            self._hotkey(command.hotkey)
        if command.text:
            self._type_text(command.text)
        if command.path:
            button = command.click or "left"
            for x, y in command.path:
                self._move_to(hwnd, x, y)
                self._click(button, command.click_count)
        else:
            if command.move_to is not None:
                self._move_to(hwnd, *command.move_to)
            if command.click is not None:
                self._click(command.click, command.click_count)
        if command.pause_ms:
            time.sleep(command.pause_ms / 1000.0)

    def _focus_window(self, title_contains: str) -> int:
        needle = title_contains.casefold()
        matches: list[int] = []
        winfunctype: Any = getattr(ctypes, "WINFUNCTYPE")
        enum_proc_type = winfunctype(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not self.user32.IsWindowVisible(hwnd):
                return True
            length = self.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buffer, len(buffer))
            if needle in buffer.value.casefold():
                matches.append(int(hwnd))
                return False
            return True

        self.user32.EnumWindows(enum_proc_type(callback), 0)
        if not matches:
            raise RuntimeError(f"window was not found: {title_contains}")
        hwnd = matches[0]
        self.user32.ShowWindow(hwnd, 9)
        if not self.user32.SetForegroundWindow(hwnd):
            raise RuntimeError(f"cannot focus window: {title_contains}")
        time.sleep(0.08)
        return hwnd

    def _move_to(self, hwnd: int, normalized_x: float, normalized_y: float) -> None:
        rect = ctypes.wintypes.RECT()
        if not self.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            raise RuntimeError("cannot read DipTrace client rectangle")
        point = ctypes.wintypes.POINT(
            int((rect.right - rect.left) * normalized_x),
            int((rect.bottom - rect.top) * normalized_y),
        )
        if not self.user32.ClientToScreen(hwnd, ctypes.byref(point)):
            raise RuntimeError("cannot map DipTrace client coordinates")

        current = ctypes.wintypes.POINT()
        self.user32.GetCursorPos(ctypes.byref(current))
        steps = max(1, int(self.cursor_motion_seconds * 60))
        for index in range(1, steps + 1):
            t = index / steps
            eased = 3 * t * t - 2 * t * t * t
            x = round(current.x + (point.x - current.x) * eased)
            y = round(current.y + (point.y - current.y) * eased)
            self.user32.SetCursorPos(x, y)
            if self.cursor_motion_seconds:
                time.sleep(self.cursor_motion_seconds / steps)

    def _click(self, button: str, count: int) -> None:
        down, up = self._MOUSE_FLAGS[button]
        for _ in range(count):
            self.user32.mouse_event(down, 0, 0, 0, 0)
            self.user32.mouse_event(up, 0, 0, 0, 0)
            if count > 1:
                time.sleep(0.08)

    def _hotkey(self, keys: Sequence[str]) -> None:
        virtual_keys = [self._virtual_key(key) for key in keys]
        for virtual_key in virtual_keys:
            self.user32.keybd_event(virtual_key, 0, 0, 0)
        for virtual_key in reversed(virtual_keys):
            self.user32.keybd_event(virtual_key, 0, 0x0002, 0)

    def _type_text(self, text: str) -> None:
        for character in text:
            packed = int(self.user32.VkKeyScanW(ord(character)))
            if packed == -1:
                raise ValueError(
                    "character cannot be typed with current keyboard layout: "
                    f"{character!r}"
                )
            virtual_key = packed & 0xFF
            modifiers = (packed >> 8) & 0xFF
            held: list[int] = []
            if modifiers & 1:
                held.append(self._VK["shift"])
            if modifiers & 2:
                held.append(self._VK["ctrl"])
            if modifiers & 4:
                held.append(self._VK["alt"])
            for modifier in held:
                self.user32.keybd_event(modifier, 0, 0, 0)
            self.user32.keybd_event(virtual_key, 0, 0, 0)
            self.user32.keybd_event(virtual_key, 0, 0x0002, 0)
            for modifier in reversed(held):
                self.user32.keybd_event(modifier, 0, 0x0002, 0)

    def _virtual_key(self, key: str) -> int:
        normalized = key.lower()
        if normalized in self._VK:
            return self._VK[normalized]
        if len(normalized) == 1 and normalized.isascii() and normalized.isalnum():
            return ord(normalized.upper())
        if normalized.startswith("f") and normalized[1:].isdigit():
            number = int(normalized[1:])
            if 1 <= number <= 24:
                return 0x70 + number - 1
        raise ValueError(f"unsupported hotkey name: {key}")


def play_manifest(
    manifest: Mapping[str, Any],
    driver: DryRunDesktopDriver | WindowsDesktopDriver,
    *,
    sleep: Any = time.sleep,
) -> None:
    cues = manifest.get("cues")
    if not isinstance(cues, list):
        raise ValueError("cinematic manifest has no cues array")
    for index, raw_cue in enumerate(cues):
        if not isinstance(raw_cue, Mapping):
            raise ValueError(f"invalid cue at index {index}")
        raw_event = raw_cue.get("event")
        if not isinstance(raw_event, Mapping):
            raise ValueError(f"cue {index} has no event object")
        event = CinematicEvent(
            kind=str(raw_event.get("kind") or "operation"),  # type: ignore[arg-type]
            label=str(raw_event.get("label") or f"Cue {index + 1}"),
            domain=str(raw_event.get("domain") or "general"),  # type: ignore[arg-type]
            phase=str(raw_event.get("phase") or "single"),  # type: ignore[arg-type]
            tool=str(raw_event["tool"]) if raw_event.get("tool") is not None else None,
            target=str(raw_event["target"]) if raw_event.get("target") is not None else None,
            payload=dict(raw_event.get("payload") or {}),
        )
        driver.handle(event)
        start_ms = int(raw_cue.get("start_ms", 0))
        settle_until_ms = int(raw_cue.get("settle_until_ms", start_ms))
        delay_ms = max(0, settle_until_ms - start_ms)
        if delay_ms:
            sleep(delay_ms / 1000.0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="diptrace-mcp-cinematic-host",
        description="Play a cinematic manifest against a Windows desktop host.",
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--window", default="DipTrace")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise SystemExit("cinematic manifest root must be an object")
    if args.dry_run:
        dry_driver = DryRunDesktopDriver(default_window=args.window)
        play_manifest(manifest, dry_driver, sleep=lambda _seconds: None)
        for command in dry_driver.commands:
            print(json.dumps(asdict(command), ensure_ascii=False, sort_keys=True))
        return 0
    windows_driver = WindowsDesktopDriver(default_window=args.window)
    play_manifest(manifest, windows_driver)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
