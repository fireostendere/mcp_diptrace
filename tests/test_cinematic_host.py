from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from diptrace_mcp import cinematic_host as host
from diptrace_mcp.cinematic import CinematicEvent, CinematicTimeline
from diptrace_mcp.cinematic_host import (
    DesktopCommand,
    DryRunDesktopDriver,
    WindowsDesktopDriver,
    desktop_command_from_payload,
    desktop_commands_from_payload,
    main,
    play_manifest,
)


class FakeUser32:
    def __init__(self) -> None:
        self.titles = {10: "", 11: "Other Window", 22: "Board - DipTrace PCB Layout"}
        self.visible = {10: False, 11: True, 22: True}
        self.foreground_ok = True
        self.client_rect_ok = True
        self.client_to_screen_ok = True
        self.cursor_ok = True
        self.mouse_events: list[int] = []
        self.key_events: list[tuple[int, int]] = []
        self.cursor_positions: list[tuple[int, int]] = []
        self.shown: list[int] = []

    def EnumWindows(self, callback, _lparam: int) -> int:
        for hwnd in self.titles:
            if not callback(hwnd, 0):
                break
        return 1

    def IsWindowVisible(self, hwnd: int) -> bool:
        return self.visible.get(hwnd, False)

    def GetWindowTextLengthW(self, hwnd: int) -> int:
        return len(self.titles.get(hwnd, ""))

    def GetWindowTextW(self, hwnd: int, buffer, _length: int) -> int:
        value = self.titles.get(hwnd, "")
        buffer.value = value
        return len(value)

    def ShowWindow(self, hwnd: int, _command: int) -> int:
        self.shown.append(hwnd)
        return 1

    def SetForegroundWindow(self, _hwnd: int) -> bool:
        return self.foreground_ok

    def GetClientRect(self, _hwnd: int, pointer) -> bool:
        if not self.client_rect_ok:
            return False
        rect = pointer._obj
        rect.left = 0
        rect.top = 0
        rect.right = 1000
        rect.bottom = 800
        return True

    def ClientToScreen(self, _hwnd: int, pointer) -> bool:
        if not self.client_to_screen_ok:
            return False
        point = pointer._obj
        point.x += 100
        point.y += 200
        return True

    def GetCursorPos(self, pointer) -> bool:
        if not self.cursor_ok:
            return False
        point = pointer._obj
        point.x = 10
        point.y = 20
        return True

    def SetCursorPos(self, x: int, y: int) -> int:
        self.cursor_positions.append((x, y))
        return 1

    def mouse_event(self, flag: int, *_args: int) -> None:
        self.mouse_events.append(flag)

    def keybd_event(self, virtual_key: int, _scan: int, flags: int, _extra: int) -> None:
        self.key_events.append((virtual_key, flags))

    def VkKeyScanW(self, codepoint: int) -> int:
        character = chr(codepoint)
        if character == "~":
            return -1
        if character == "*":
            return (7 << 8) | 0x38
        return ord(character.upper())


def _install_fake_windows(monkeypatch: pytest.MonkeyPatch, user32: FakeUser32) -> None:
    monkeypatch.setattr(host.os, "name", "nt")
    monkeypatch.setattr(
        host.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
        raising=False,
    )
    monkeypatch.setattr(
        host.ctypes,
        "WINFUNCTYPE",
        lambda *_types: lambda callback: callback,
        raising=False,
    )
    monkeypatch.setattr(host.time, "sleep", lambda _seconds: None)


def test_desktop_command_uses_normalized_coordinates() -> None:
    command = desktop_command_from_payload(
        {
            "desktop": {
                "move_to": [0.25, 0.75],
                "click": "left",
                "hotkey": ["ctrl", "s"],
                "text": "R1",
            }
        }
    )

    assert command is not None
    assert command.move_to == (0.25, 0.75)
    assert command.hotkey == ("ctrl", "s")
    assert command.text == "R1"


def test_desktop_command_rejects_screen_coordinates_outside_client_space() -> None:
    with pytest.raises(ValueError, match="normalized"):
        desktop_command_from_payload({"desktop": {"move_to": [640, 480]}})


def test_desktop_command_accepts_click_path_for_wire_or_trace_playback() -> None:
    command = desktop_command_from_payload(
        {
            "desktop": {
                "path": [[0.2, 0.4], [0.5, 0.4], [0.5, 0.7]],
                "click": "left",
            }
        }
    )

    assert command is not None
    assert command.path == ((0.2, 0.4), (0.5, 0.4), (0.5, 0.7))


def test_desktop_command_rejects_invalid_click_path_point() -> None:
    with pytest.raises(ValueError, match="normalized"):
        desktop_command_from_payload(
            {"desktop": {"path": [[0.2, 0.4], [1.5, 0.7]], "click": "left"}}
        )


def test_desktop_payload_supports_multiple_profile_steps() -> None:
    commands = desktop_commands_from_payload(
        {
            "desktop": {
                "window_title_contains": "DipTrace Schematic",
                "steps": [
                    {"hotkey": ["ctrl", "p"], "pause_ms": 100},
                    {"text": "U1"},
                    {"move_to": [0.4, 0.5], "click": "left"},
                ],
            }
        }
    )

    assert len(commands) == 3
    assert commands[0].window_title_contains == "DipTrace Schematic"
    assert commands[0].hotkey == ("ctrl", "p")
    assert commands[0].pause_ms == 100
    assert commands[1].text == "U1"
    assert commands[2].move_to == (0.4, 0.5)


def test_single_command_compatibility_parser_rejects_multi_step_payload() -> None:
    with pytest.raises(ValueError, match="multiple commands"):
        desktop_command_from_payload(
            {"desktop": {"steps": [{"hotkey": ["w"]}, {"hotkey": ["esc"]}]}}
        )


def test_desktop_payload_parser_fail_closed_cases() -> None:
    assert desktop_commands_from_payload({}) == ()
    assert desktop_command_from_payload({}) is None
    for payload, message in [
        ({"desktop": "bad"}, "object"),
        ({"desktop": {"move_to": [0.2]}}, "move_to"),
        ({"desktop": {"path": "bad"}}, "path"),
        ({"desktop": {"path": [[0.1]]}}, "path"),
        ({"desktop": {"hotkey": "ctrl"}}, "hotkey"),
        ({"desktop": {"hotkey": [""]}}, "hotkey"),
        ({"desktop": {"text": 42}}, "text"),
        ({"desktop": {"steps": "bad"}}, "steps"),
        ({"desktop": {"steps": []}}, "steps"),
        ({"desktop": {"steps": ["bad"]}}, "steps"),
    ]:
        with pytest.raises(ValueError, match=message):
            desktop_commands_from_payload(payload)


def test_desktop_command_validation_fail_closed_cases() -> None:
    for kwargs, message in [
        ({"window_title_contains": " "}, "empty"),
        ({"move_to": (0.1, 0.1), "path": ((0.2, 0.2),)}, "move_to and path"),
        ({"click": "wheel"}, "click"),
        ({"click_count": 0}, "click_count"),
        ({"pause_ms": 10_001}, "pause_ms"),
    ]:
        with pytest.raises(ValueError, match=message):
            DesktopCommand(**kwargs)


def test_dry_run_player_consumes_manifest_without_touching_desktop() -> None:
    timeline = CinematicTimeline(title="Desktop demo", preset="gif")
    timeline.operation(
        "route_trace",
        payload={"desktop": {"move_to": [0.4, 0.5], "click": "left"}},
    )
    timeline.operation(
        "route_trace",
        payload={"desktop": {"move_to": [0.8, 0.5], "click": "left"}},
    )
    driver = DryRunDesktopDriver()
    sleeps: list[float] = []

    play_manifest(timeline.manifest(), driver, sleep=sleeps.append)

    assert len(driver.commands) == 2
    assert driver.commands[0].move_to == (0.4, 0.5)
    assert driver.commands[1].move_to == (0.8, 0.5)
    assert sleeps == [0.3, 0.3]


def test_dry_run_expands_multi_step_semantic_operation() -> None:
    timeline = CinematicTimeline(title="Schematic placement", preset="gif")
    timeline.operation(
        "schematic_place_component",
        payload={
            "desktop": {
                "steps": [
                    {"hotkey": ["ctrl", "p"]},
                    {"text": "U1"},
                    {"move_to": [0.4, 0.5], "click": "left"},
                ]
            }
        },
    )
    driver = DryRunDesktopDriver()

    play_manifest(timeline.manifest(), driver, sleep=lambda _seconds: None)

    assert len(driver.commands) == 3
    assert driver.commands[0].hotkey == ("ctrl", "p")
    assert driver.commands[1].text == "U1"
    assert driver.commands[2].click == "left"


def test_focus_event_without_desktop_payload_is_noop_in_dry_run() -> None:
    driver = DryRunDesktopDriver()
    driver.handle(CinematicEvent(kind="focus", label="DipTrace"))
    assert driver.commands == []


def test_play_manifest_rejects_malformed_cues() -> None:
    driver = DryRunDesktopDriver()
    with pytest.raises(ValueError, match="cues"):
        play_manifest({}, driver)
    with pytest.raises(ValueError, match="index 0"):
        play_manifest({"cues": ["bad"]}, driver)
    with pytest.raises(ValueError, match="event object"):
        play_manifest({"cues": [{}]}, driver)


def test_host_cli_dry_run_prints_commands(tmp_path, capsys) -> None:
    timeline = CinematicTimeline(title="Host CLI", preset="gif")
    timeline.operation(
        "route_trace",
        payload={"desktop": {"move_to": [0.1, 0.2], "click": "left"}},
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(timeline.manifest()), encoding="utf-8")

    assert main([str(path), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert '"move_to": [0.1, 0.2]' in output


def test_host_cli_rejects_non_object_manifest(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="root"):
        main([str(path), "--dry-run"])


def test_windows_driver_constructor_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host.os, "name", "posix")
    with pytest.raises(RuntimeError, match="only on Windows"):
        WindowsDesktopDriver()

    monkeypatch.setattr(host.os, "name", "nt")
    with pytest.raises(ValueError, match=">= 0"):
        WindowsDesktopDriver(cursor_motion_seconds=-0.1)
    monkeypatch.setattr(host.ctypes, "windll", None, raising=False)
    with pytest.raises(RuntimeError, match="bindings"):
        WindowsDesktopDriver()


def test_windows_driver_executes_focus_hotkey_text_path_and_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()
    _install_fake_windows(monkeypatch, user32)
    driver = WindowsDesktopDriver(default_window="DipTrace", cursor_motion_seconds=0)
    event = CinematicEvent(
        kind="operation",
        label="Route",
        payload={
            "desktop": {
                "steps": [
                    {"hotkey": ["ctrl", "a", "f12"]},
                    {"text": "*A"},
                    {
                        "path": [[0.2, 0.3], [0.6, 0.7]],
                        "click": "left",
                        "click_count": 2,
                        "pause_ms": 5,
                    },
                    {"move_to": [0.5, 0.5], "click": "right"},
                ]
            }
        },
    )

    driver.handle(event)

    assert user32.shown
    assert user32.cursor_positions[-1] == (600, 600)
    assert len(user32.mouse_events) == 10
    assert any(key == 0x7B for key, _flags in user32.key_events)
    assert any(key == host.WindowsDesktopDriver._VK["alt"] for key, _ in user32.key_events)


def test_windows_driver_focus_event_and_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user32 = FakeUser32()
    _install_fake_windows(monkeypatch, user32)
    driver = WindowsDesktopDriver(cursor_motion_seconds=0)

    driver.handle(CinematicEvent(kind="focus", label="Focus"))
    assert user32.shown[-1] == 22

    user32.titles = {1: "Other"}
    with pytest.raises(RuntimeError, match="not found"):
        driver._focus_window("DipTrace")

    user32.titles = {22: "DipTrace"}
    user32.visible = {22: True}
    user32.foreground_ok = False
    with pytest.raises(RuntimeError, match="cannot focus"):
        driver._focus_window("DipTrace")


def test_windows_driver_coordinate_keyboard_and_mouse_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()
    _install_fake_windows(monkeypatch, user32)
    driver = WindowsDesktopDriver(cursor_motion_seconds=0.05)

    driver._move_to(22, 0.5, 0.5)
    assert len(user32.cursor_positions) == 3

    user32.client_rect_ok = False
    with pytest.raises(RuntimeError, match="client rectangle"):
        driver._move_to(22, 0.5, 0.5)
    user32.client_rect_ok = True
    user32.client_to_screen_ok = False
    with pytest.raises(RuntimeError, match="map"):
        driver._move_to(22, 0.5, 0.5)

    assert driver._virtual_key("escape") == 0x1B
    assert driver._virtual_key("z") == ord("Z")
    assert driver._virtual_key("f24") == 0x87
    with pytest.raises(ValueError, match="unsupported"):
        driver._virtual_key("f25")
    with pytest.raises(ValueError, match="keyboard layout"):
        driver._type_text("~")

    driver._click("middle", 1)
    assert user32.mouse_events[-2:] == [0x0020, 0x0040]


def test_host_cli_live_branch_can_be_driven_by_injected_driver(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timeline = CinematicTimeline(title="Live host", preset="gif")
    timeline.operation("route_trace", payload={"desktop": {"hotkey": ["esc"]}})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(timeline.manifest()), encoding="utf-8")
    driver = DryRunDesktopDriver(default_window="Injected")
    monkeypatch.setattr(host, "WindowsDesktopDriver", lambda **_kwargs: driver)
    monkeypatch.setattr(host.time, "sleep", lambda _seconds: None)

    assert main([str(path), "--window", "Injected"]) == 0
    assert driver.commands[0].hotkey == ("esc",)
