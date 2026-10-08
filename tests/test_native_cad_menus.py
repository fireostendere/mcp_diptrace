from __future__ import annotations

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
