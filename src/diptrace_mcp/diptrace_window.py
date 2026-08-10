from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from typing import Any

from .diptrace_ui import ClientPoint


def _user32() -> Any:
    if os.name != "nt":
        raise RuntimeError("DipTrace window probing is available only on Windows")
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise RuntimeError("Windows user32 bindings are unavailable")
    return windll.user32


def find_window_handle(title_contains: str) -> int:
    """Return the first visible top-level window whose title contains the requested text."""

    if not title_contains.strip():
        raise ValueError("window title substring must not be empty")
    user32 = _user32()
    needle = title_contains.casefold()
    matches: list[int] = []
    winfunctype: Any = getattr(ctypes, "WINFUNCTYPE")
    enum_proc_type = winfunctype(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        if needle in buffer.value.casefold():
            matches.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(enum_proc_type(callback), 0)
    if not matches:
        raise RuntimeError(f"window was not found: {title_contains}")
    return matches[0]


def normalized_cursor_position(title_contains: str = "DipTrace") -> ClientPoint:
    """Return the current cursor position normalized to the matching window client area."""

    user32 = _user32()
    hwnd = find_window_handle(title_contains)
    rect = ctypes.wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("cannot read DipTrace client rectangle")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError("DipTrace client rectangle is empty")

    point = ctypes.wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise RuntimeError("cannot read Windows cursor position")
    if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
        raise RuntimeError("cannot map cursor into DipTrace client coordinates")
    return ClientPoint(point.x / width, point.y / height)
