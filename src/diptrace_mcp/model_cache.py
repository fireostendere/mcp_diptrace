from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from pydantic import BaseModel

from .adapters import DocumentSnapshot, build_snapshot
from .config import DEFAULT_MODEL_CACHE_MAX_BYTES
from .xml_document import DipTraceDocument


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    snapshot: DocumentSnapshot
    accounted_bytes: int


def _snapshot_accounted_bytes(snapshot: DocumentSnapshot) -> int:
    """Estimate the retained Python object graph without serializing it.

    ``sys.getsizeof`` is not a process RSS measurement, but recursively walking the
    supported snapshot containers accounts for the retained source bytes, XML tree,
    normalized models and indexes. Shared objects are counted once by identity.
    """

    seen: set[int] = set()
    pending: list[Any] = [snapshot]
    total = 0
    while pending:
        value = pending.pop()
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        total += sys.getsizeof(value)
        if isinstance(value, ET.Element):
            pending.extend((value.tag, value.attrib, value.text, value.tail))
            pending.extend(value)
        elif isinstance(value, BaseModel):
            pending.extend(
                getattr(value, attribute, None)
                for attribute in (
                    "__dict__",
                    "__pydantic_fields_set__",
                    "__pydantic_extra__",
                    "__pydantic_private__",
                )
            )
        elif is_dataclass(value) and not isinstance(value, type):
            pending.extend(
                getattr(value, item.name) for item in fields(value)
            )
        elif isinstance(value, Mapping):
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            pending.extend(value)
    return total


@dataclass(slots=True)
class ModelCache:
    max_entries: int = 8
    max_bytes: int = DEFAULT_MODEL_CACHE_MAX_BYTES
    _items: OrderedDict[tuple[str, str, bool], _CacheEntry] = field(
        default_factory=OrderedDict,
        init=False,
    )
    _current_bytes: int = field(default=0, init=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_entries < 1:
            raise ValueError("max_entries must be greater than zero")
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be greater than zero")

    @property
    def current_bytes(self) -> int:
        with self._lock:
            return self._current_bytes

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._items)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entry_count": len(self._items),
                "max_entries": self.max_entries,
                "accounted_bytes": self._current_bytes,
                "max_bytes": self.max_bytes,
            }

    def get(self, document: DipTraceDocument, *, live_session: bool) -> DocumentSnapshot:
        with self._lock:
            key = (str(document.path.resolve()), document.sha256, live_session)
            cached = self._items.pop(key, None)
            if cached is not None:
                self._items[key] = cached
                return cached.snapshot
            snapshot = build_snapshot(document, live_session=live_session)
            self.invalidate(document.path)
            accounted_bytes = _snapshot_accounted_bytes(snapshot)
            if accounted_bytes > self.max_bytes:
                return snapshot
            self._items[key] = _CacheEntry(
                snapshot=snapshot,
                accounted_bytes=accounted_bytes,
            )
            self._current_bytes += accounted_bytes
            while (
                len(self._items) > self.max_entries
                or self._current_bytes > self.max_bytes
            ):
                _evicted_key, evicted = self._items.popitem(last=False)
                self._current_bytes -= evicted.accounted_bytes
            return snapshot

    def invalidate(self, path: Path) -> None:
        with self._lock:
            normalized = str(path.resolve())
            stale = [key for key in self._items if key[0] == normalized]
            for key in stale:
                entry = self._items.pop(key, None)
                if entry is not None:
                    self._current_bytes -= entry.accounted_bytes
