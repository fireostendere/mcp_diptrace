from __future__ import annotations

import re
from fnmatch import fnmatchcase

from .domain import (
    ObjectRecord,
    QuerySelector,
)
from .geometry import BBox, Point, distance


def _matches_selector(item: ObjectRecord, selector: QuerySelector) -> bool:
    if selector.ids and item.stable_id not in selector.ids:
        return False
    if selector.kinds and item.kind not in selector.kinds:
        return False
    if selector.refdes:
        refdes = item.refdes or ""
        if not any(refdes.casefold() == candidate.casefold() for candidate in selector.refdes):
            return False
    if selector.refdes_glob and not fnmatchcase(
        (item.refdes or "").casefold(), selector.refdes_glob.casefold()
    ):
        return False
    if selector.refdes_regex and not re.search(selector.refdes_regex, item.refdes or ""):
        return False
    if selector.names:
        name = item.name or ""
        if not any(name.casefold() == candidate.casefold() for candidate in selector.names):
            return False
    if selector.name_regex and not re.search(selector.name_regex, item.name or ""):
        return False
    if selector.values:
        value = item.value or ""
        if not any(value.casefold() == candidate.casefold() for candidate in selector.values):
            return False
    if selector.fields:
        item_fields = item.attributes.get("additional_fields", {})
        if not isinstance(item_fields, dict):
            return False
        if any(
            str(item_fields.get(key, "")) != expected for key, expected in selector.fields.items()
        ):
            return False
    if selector.nets:
        names = {item.net_name or "", item.net_id or ""}
        if not any(candidate in names for candidate in selector.nets) and not any(
            candidate.casefold() == net.casefold()
            for candidate in selector.nets
            for net in names
            if net
        ):
            return False
    if selector.layers and (item.layer or "") not in selector.layers:
        return False
    if selector.sides and (item.side or "") not in selector.sides:
        return False
    if selector.selected is not None and item.selected != selector.selected:
        return False
    if selector.locked is not None and item.locked != selector.locked:
        return False
    if selector.text:
        needle = selector.text.casefold()
        haystack = " ".join(
            [
                item.label or "",
                item.name or "",
                item.value or "",
                item.refdes or "",
                item.net_name or "",
                " ".join(f"{key}={value}" for key, value in item.attributes.items()),
            ]
        ).casefold()
        if needle not in haystack:
            return False
    if selector.bbox:
        if item.bbox is None:
            return False
        bbox = BBox(
            selector.bbox["min_x"],
            selector.bbox["min_y"],
            selector.bbox["max_x"],
            selector.bbox["max_y"],
        )
        item_bbox = BBox(
            item.bbox["min_x"],
            item.bbox["min_y"],
            item.bbox["max_x"],
            item.bbox["max_y"],
        )
        if not bbox.intersects(item_bbox):
            return False
    if selector.near is not None:
        if item.position is None:
            return False
        target = Point(selector.near["x"], selector.near["y"])
        item_point = Point(item.position["x"], item.position["y"])
        if (
            selector.max_distance is not None
            and distance(item_point, target) > selector.max_distance
        ):
            return False
    return True
