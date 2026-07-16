from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import DocumentSnapshot, build_snapshot
from .xml_document import DipTraceDocument


@dataclass(slots=True)
class ModelCache:
    max_entries: int = 8
    _items: OrderedDict[tuple[str, str, bool], DocumentSnapshot] = field(
        default_factory=OrderedDict,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.max_entries < 1:
            raise ValueError("max_entries must be greater than zero")

    def get(self, document: DipTraceDocument, *, live_session: bool) -> DocumentSnapshot:
        key = (str(document.path.resolve()), document.sha256, live_session)
        cached = self._items.pop(key, None)
        if cached is not None:
            self._items[key] = cached
            return cached
        snapshot = build_snapshot(document, live_session=live_session)
        self.invalidate(document.path)
        self._items[key] = snapshot
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
        return snapshot

    def invalidate(self, path: Path) -> None:
        normalized = str(path.resolve())
        stale = [key for key in self._items if key[0] == normalized]
        for key in stale:
            self._items.pop(key, None)
