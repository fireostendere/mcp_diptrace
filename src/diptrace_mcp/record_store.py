from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .record_ids import (
    InvalidRecordPath,
    is_link_like,
    prepare_safe_store_root,
    require_safe_store_root,
)
from .retention import Clock, RetentionPolicy, RetentionReport
from .xml_document import atomic_write_bytes


class RecordStore:
    """Shared safe persistence seam for state-backed record stores.

    Record identity, decoding errors, terminal states, retention candidates,
    artifacts, and public exceptions remain owned by each concrete store.
    """

    __slots__ = ("_record_store_root",)

    state_dir: Path
    retention: RetentionPolicy
    clock: Clock
    last_retention_report: RetentionReport

    def _initialize_record_store(
        self,
        *,
        state_dir: Path,
        store_root: Path,
    ) -> None:
        self._record_store_root = prepare_safe_store_root(state_dir, store_root)

    def _initial_retention_report(self) -> RetentionReport:
        return self._prune_retention()

    def _prune_retention(self) -> RetentionReport:
        raise NotImplementedError

    def _require_safe_root(self) -> None:
        require_safe_store_root(self.state_dir, self._record_store_root)

    def _write_store_json(
        self,
        path: Path,
        value: dict[str, Any],
        *,
        ensure_ascii: bool = False,
        indent: int | None = 2,
        sort_keys: bool = False,
        trailing_newline: bool = False,
    ) -> None:
        destination = self._require_safe_output_path(path)
        self._atomic_write_store_json(
            destination,
            value,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            trailing_newline=trailing_newline,
        )

    def _atomic_write_store_json(
        self,
        path: Path,
        value: dict[str, Any],
        *,
        ensure_ascii: bool,
        indent: int | None,
        sort_keys: bool,
        trailing_newline: bool,
    ) -> None:
        payload = json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
        ).encode("utf-8")
        if trailing_newline:
            payload += b"\n"
        atomic_write_bytes(path, payload)

    def _require_safe_output_path(self, path: Path) -> Path:
        self._require_safe_root()
        root = self._record_store_root
        try:
            relative = path.relative_to(root)
            if not relative.parts:
                raise InvalidRecordPath("Record output path names the store root")
            current = path.parent
            while current != root:
                if is_link_like(current) or not current.is_dir():
                    raise InvalidRecordPath(
                        f"Record output directory is redirected or unavailable: {current}"
                    )
                parent = current.parent
                if parent == current:
                    raise InvalidRecordPath(f"Record output path is outside its store: {path}")
                current = parent
            if is_link_like(path):
                raise InvalidRecordPath(f"Record output path is redirected: {path}")
            if path.exists() and not path.is_file():
                raise InvalidRecordPath(f"Record output path is not a regular file: {path}")
            path.parent.resolve(strict=True).relative_to(root.resolve(strict=True))
        except InvalidRecordPath:
            raise
        except (OSError, ValueError) as exc:
            raise InvalidRecordPath(
                f"Record output path is redirected or outside its store: {path}"
            ) from exc
        return path
