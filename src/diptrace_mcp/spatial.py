from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .domain import ObjectRecord
from .geometry import BBox, Point


def _record_bbox(record: ObjectRecord) -> BBox | None:
    if record.bbox is None:
        return None
    return BBox(**record.bbox)


def bbox_distance_to_point(box: BBox, point: Point) -> float:
    dx = max(box.min_x - point.x, 0.0, point.x - box.max_x)
    dy = max(box.min_y - point.y, 0.0, point.y - box.max_y)
    return math.hypot(dx, dy)


@dataclass(slots=True)
class SpatialIndex:
    """Deterministic uniform-grid index over normalized, backend-neutral bboxes."""

    cell_size_mm: float = 5.0
    _records: dict[str, ObjectRecord] = field(default_factory=dict, init=False)
    _cells: dict[tuple[str, int, int], set[str]] = field(
        default_factory=lambda: defaultdict(set),
        init=False,
    )

    def __post_init__(self) -> None:
        if not math.isfinite(self.cell_size_mm) or self.cell_size_mm <= 0:
            raise ValueError("cell_size_mm must be finite and greater than zero")

    @classmethod
    def build(
        cls,
        records: Iterable[ObjectRecord],
        *,
        cell_size_mm: float = 5.0,
    ) -> SpatialIndex:
        index = cls(cell_size_mm=cell_size_mm)
        for record in records:
            index.insert(record)
        return index

    def insert(self, record: ObjectRecord) -> None:
        self.remove(record.stable_id)
        box = _record_bbox(record)
        if box is None:
            return
        self._records[record.stable_id] = record
        layer = record.layer or "*"
        for cell_x, cell_y in self._bbox_cells(box):
            self._cells[(layer, cell_x, cell_y)].add(record.stable_id)

    def remove(self, stable_id: str) -> None:
        record = self._records.pop(stable_id, None)
        if record is None:
            return
        box = _record_bbox(record)
        if box is None:
            return
        layer = record.layer or "*"
        for cell_x, cell_y in self._bbox_cells(box):
            key = (layer, cell_x, cell_y)
            ids = self._cells.get(key)
            if ids is None:
                continue
            ids.discard(stable_id)
            if not ids:
                self._cells.pop(key, None)

    def query(
        self,
        region: BBox,
        *,
        layers: set[str] | None = None,
        kinds: set[str] | None = None,
    ) -> list[ObjectRecord]:
        candidate_ids: set[str] = set()
        requested_layers = layers or {key[0] for key in self._cells}
        for layer in requested_layers:
            for cell_x, cell_y in self._bbox_cells(region):
                candidate_ids.update(self._cells.get((layer, cell_x, cell_y), ()))
        records = [
            self._records[stable_id]
            for stable_id in candidate_ids
            if (kinds is None or self._records[stable_id].kind in kinds)
            and _record_bbox(self._records[stable_id]).intersects(region)  # type: ignore[union-attr]
        ]
        return sorted(records, key=lambda item: item.stable_id)

    def nearest(
        self,
        point: Point,
        *,
        layers: set[str] | None = None,
        kinds: set[str] | None = None,
        limit: int = 1,
        max_distance_mm: float | None = None,
    ) -> list[tuple[ObjectRecord, float]]:
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        candidates = (
            record
            for record in self._records.values()
            if (layers is None or (record.layer or "*") in layers)
            and (kinds is None or record.kind in kinds)
        )
        measured = [
            (record, bbox_distance_to_point(_record_bbox(record), point))  # type: ignore[arg-type]
            for record in candidates
        ]
        if max_distance_mm is not None:
            measured = [item for item in measured if item[1] <= max_distance_mm]
        measured.sort(key=lambda item: (item[1], item[0].stable_id))
        return measured[:limit]

    def _bbox_cells(self, box: BBox) -> Iterable[tuple[int, int]]:
        min_x = math.floor(box.min_x / self.cell_size_mm)
        max_x = math.floor(box.max_x / self.cell_size_mm)
        min_y = math.floor(box.min_y / self.cell_size_mm)
        max_y = math.floor(box.max_y / self.cell_size_mm)
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                yield cell_x, cell_y
