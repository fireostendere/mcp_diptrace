from __future__ import annotations

from types import SimpleNamespace

import pytest

from diptrace_mcp import diptrace_window as window


class FakeUser32:
    def __init__(self) -> None:
        self.titles = {1: "", 2: "Other", 3: "Design - DipTrace Schematic"}
        self.visible = {1: False, 2: True, 3: True}
        self.rect_ok = True
        self.cursor_ok = True
        self.screen_to_client_ok = True
        self.width = 1000
        self.height = 500

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

    def GetClientRect(self, _hwnd: int, pointer) -> bool:
        if not self.rect_ok:
            return False
        rect = pointer._obj
        rect.left = 0
        rect.top = 0
        rect.right = self.width
        rect.bottom = self.height
        return True

    def GetCursorPos(self, pointer) -> bool:
        if not self.cursor_ok:
            return False
        point = pointer._obj
        point.x = 350
        point.y = 250
        return True

    def ScreenToClient(self, _hwnd: int, pointer) -> bool:
        if not self.screen_to_client_ok:
            return False
        point = pointer._obj
        point.x -= 100
        point.y -= 50
        return True


def _install_windows(monkeypatch: pytest.MonkeyPatch, user32: FakeUser32) -> None:
    monkeypatch.setattr(window.os, "name", "nt")
    monkeypatch.setattr(
        window.ctypes,
        "windll",
        SimpleNamespace(user32=user32),
        raising=False,
    )
    monkeypatch.setattr(
        window.ctypes,
        "WINFUNCTYPE",
        lambda *_types: lambda callback: callback,
        raising=False,
    )


def test_window_helpers_fail_closed_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window.os, "name", "posix")
    with pytest.raises(RuntimeError, match="only on Windows"):
        window.find_window_handle("DipTrace")
    with pytest.raises(RuntimeError, match="only on Windows"):
        window.normalized_cursor_position("DipTrace")


def test_user32_requires_windows_bindings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window.os, "name", "nt")
    monkeypatch.setattr(window.ctypes, "windll", None, raising=False)
    with pytest.raises(RuntimeError, match="bindings"):
        window._user32()


def test_find_window_handle_matches_visible_title(monkeypatch: pytest.MonkeyPatch) -> None:
    user32 = FakeUser32()
    _install_windows(monkeypatch, user32)

    assert window.find_window_handle("diptrace schematic") == 3
    with pytest.raises(ValueError, match="must not be empty"):
        window.find_window_handle(" ")

    user32.titles = {2: "Other"}
    user32.visible = {2: True}
    with pytest.raises(RuntimeError, match="not found"):
        window.find_window_handle("DipTrace")


def test_normalized_cursor_position_maps_client_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()
    _install_windows(monkeypatch, user32)

    point = window.normalized_cursor_position("DipTrace")

    assert point.x == pytest.approx(0.25)
    assert point.y == pytest.approx(0.4)


def test_normalized_cursor_position_reports_win32_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user32 = FakeUser32()
    _install_windows(monkeypatch, user32)

    user32.rect_ok = False
    with pytest.raises(RuntimeError, match="client rectangle"):
        window.normalized_cursor_position("DipTrace")

    user32.rect_ok = True
    user32.width = 0
    with pytest.raises(RuntimeError, match="empty"):
        window.normalized_cursor_position("DipTrace")

    user32.width = 1000
    user32.cursor_ok = False
    with pytest.raises(RuntimeError, match="cursor position"):
        window.normalized_cursor_position("DipTrace")

    user32.cursor_ok = True
    user32.screen_to_client_ok = False
    with pytest.raises(RuntimeError, match="map cursor"):
        window.normalized_cursor_position("DipTrace")
