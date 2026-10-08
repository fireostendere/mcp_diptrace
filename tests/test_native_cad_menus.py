from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from diptrace_mcp import native_cad

SEPARATOR = native_cad._MF_SEPARATOR


class Item:
    def __init__(self, name: str, kind: int = 0, submenu: Any = None) -> None:
        self.name, self.kind, self.submenu = name, kind, submenu

    def item_type(self) -> int:
        return self.kind

    def sub_menu(self) -> Any:
        return self.submenu

    def text(self) -> str:
        return self.name


class Menu:
    def __init__(self, items: list[Item]) -> None:
        self._items = items

    def items(self) -> list[Item]:
        return self._items

    def item(self, index: int) -> Item:
        return self._items[index]


def _window(objects: list[Item]) -> Any:
    top = [Item("&File"), Item("&Edit"), Item("&View"), Item("&Objects", submenu=Menu(objects))]

    class Window:
        def menu(self) -> Menu:
            return Menu(top)

    return Window()


def _objects(first_group: list[str]) -> list[Item]:
    sep = Item("", SEPARATOR)
    return [
        *(Item(name) for name in first_group),
        sep,
        Item("Place Ratline"),
        Item("Via Tools", submenu=Menu([])),
        sep,
        Item("Place Copper Pour"),
        Item("Update All Copper Pours"),
        Item("Clear All Copper Pours"),
        sep,
        Item("Place Board Outline"),
    ]


@pytest.mark.parametrize(
    "first_group",
    [
        # 5.3.0.3 static menu, and 5.3.5.1 opened menu
        ["Place Component", "Find Component", "SnapMagic", "New Part Request..."],
        # 5.3.5.1 static menu: "New Part Request..." appears only when opened
        ["Place Component", "Find Component", "SnapMagic"],
    ],
)
def test_update_pours_is_found_by_group_not_position(first_group: list[str]) -> None:
    item = native_cad._update_pours_item(_window(_objects(first_group)))

    assert item.text() == "Update All Copper Pours"


def test_update_pours_fails_closed_on_unexpected_group() -> None:
    objects = _objects(["Place Component"])
    del objects[6]  # leaves a two-item pour group
    with pytest.raises(native_cad.HeadlessGuiError, match="copper-pour group"):
        native_cad._update_pours_item(_window(objects))


def test_ready_main_window_acknowledges_until_menu_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pcb.exe on a private desktop: the Direct3D warning disables the form at first.
    states = iter((False, False, True))
    acknowledged: list[str] = []
    monkeypatch.setattr(native_cad, "_main_window", lambda *_args: "form")
    monkeypatch.setattr(native_cad, "_is_ready", lambda _window: next(states))
    monkeypatch.setattr(native_cad.time, "sleep", lambda _seconds: None)

    window = native_cad._ready_main_window("app", Path("b.dip"), 5, acknowledged.append)

    assert window == "form" and acknowledged == ["app"] * 3


def test_ready_main_window_fails_closed_at_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native_cad, "_main_window", lambda *_args: "modal")
    monkeypatch.setattr(native_cad, "_is_ready", lambda _window: False)
    monkeypatch.setattr(native_cad.time, "sleep", lambda _seconds: None)

    with pytest.raises(native_cad.HeadlessGuiError, match="never became ready"):
        native_cad._ready_main_window("app", Path("b.dip"), 0, lambda _app: None)
