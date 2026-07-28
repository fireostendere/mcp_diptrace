from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from .errors import DocumentError
from .record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    iter_valid_record_files,
    prepare_safe_store_root,
    require_confined_record_artifact,
    require_record_id,
    require_safe_store_root,
)
from .retention import (
    Clock,
    RetentionCandidate,
    RetentionPolicy,
    RetentionReport,
    parse_retention_timestamp,
    prune_terminal_records,
    system_clock,
)
from .xml_document import atomic_write_bytes, utc_now


@dataclass(slots=True)
class RawPreviewStore:
    """Persist bounded raw-edit preview artifacts outside the tool response."""

    state_dir: Path
    retention: RetentionPolicy = dataclass_field(default_factory=RetentionPolicy)
    clock: Clock = dataclass_field(default=system_clock, repr=False)
    previews_dir: Path = dataclass_field(init=False)
    last_retention_report: RetentionReport = dataclass_field(init=False)
    _lock: threading.RLock = dataclass_field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.previews_dir = self.state_dir / "raw_previews"
        prepare_safe_store_root(self.state_dir, self.previews_dir)
        self._lock = threading.RLock()
        self.last_retention_report = self._prune_retention()

    def _require_safe_root(self) -> None:
        require_safe_store_root(self.state_dir, self.previews_dir)

    def _prune_retention(self) -> RetentionReport:
        candidates: list[RetentionCandidate] = []
        paths = sorted(self.previews_dir.glob("preview_*/metadata.json"))
        for preview_id, path in iter_valid_record_files(
            self.previews_dir,
            paths,
            kind="preview",
            record_filename="metadata.json",
        ):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("preview_id") != preview_id:
                continue
            timestamp = parse_retention_timestamp(payload.get("created_at"))
            if timestamp is None:
                continue
            candidates.append(
                RetentionCandidate(
                    identifier=preview_id,
                    path=path.parent,
                    timestamp=timestamp,
                )
            )
        return prune_terminal_records(
            state_root=self.state_dir,
            store_root=self.previews_dir,
            candidates=candidates,
            policy=self.retention,
            clock=self.clock,
        )

    def preview_dir(self, preview_id: str) -> Path:
        try:
            validated = require_record_id(preview_id, "preview")
        except InvalidRecordId:
            raise DocumentError(
                "Invalid raw preview id",
                code="object_not_found",
            ) from None
        return self.previews_dir / validated

    def store(self, diff: str, metadata: dict[str, Any]) -> tuple[str, str]:
        preview_id = f"preview_{uuid.uuid4().hex}"
        resource_uri = f"diptrace://raw-preview/{preview_id}/diff"
        with self._lock:
            self._require_safe_root()
            directory = self.preview_dir(preview_id)
            directory.mkdir(parents=False, exist_ok=False)
            atomic_write_bytes(directory / "diff.txt", diff.encode("utf-8"))
            payload = {
                "preview_id": preview_id,
                "created_at": utc_now(),
                "resource_uri": resource_uri,
                "diff_metadata": metadata,
            }
            atomic_write_bytes(
                directory / "metadata.json",
                (
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode("utf-8"),
            )
        return preview_id, resource_uri

    def read_diff(self, preview_id: str) -> str:
        self._require_safe_root()
        try:
            path = require_confined_record_artifact(
                self.previews_dir,
                preview_id,
                "diff.txt",
                kind="preview",
            )
        except (InvalidRecordId, InvalidRecordPath, FileNotFoundError) as exc:
            raise DocumentError(
                "Raw preview diff does not exist or is unsafe",
                code="object_not_found",
            ) from exc
        return path.read_text(encoding="utf-8")
