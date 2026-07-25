from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .errors import SessionError
from .record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    is_link_like,
    iter_valid_record_files,
    prepare_safe_store_root,
    require_confined_file,
    require_confined_record_file,
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
from .xml_document import (
    DipTraceDocument,
    atomic_write_bytes,
    sha256_bytes,
    utc_now,
)

SessionAction = Literal["apply", "cancel"]

_JSON_READ_ATTEMPTS = 8
_JSON_READ_RETRY_SECONDS = 0.025


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    atomic_write_bytes(path, data)


def _read_json(path: Path) -> dict[str, Any]:
    last_error: OSError | json.JSONDecodeError | None = None
    for attempt in range(_JSON_READ_ATTEMPTS):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            break
        except (OSError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 < _JSON_READ_ATTEMPTS:
                time.sleep(_JSON_READ_RETRY_SECONDS)
    else:
        raise SessionError(f"Cannot read session state: {path}") from last_error
    if not isinstance(value, dict):
        raise SessionError(f"Session state must be a JSON object: {path}")
    return value


class SessionStore:
    def __init__(
        self,
        state_dir: Path,
        max_document_bytes: int = 128 * 1024 * 1024,
        *,
        retention: RetentionPolicy | None = None,
        clock: Clock = system_clock,
    ):
        self.state_dir = state_dir
        self.sessions_dir = state_dir / "sessions"
        self.active_file = state_dir / "active.json"
        self.max_document_bytes = max_document_bytes
        self.retention = retention or RetentionPolicy()
        self.clock = clock
        prepare_safe_store_root(self.state_dir, self.sessions_dir)
        self.last_retention_report = self._prune_retention()

    def _require_safe_root(self) -> None:
        require_safe_store_root(self.state_dir, self.sessions_dir)

    def _prune_retention(self) -> RetentionReport:
        active_reference_valid, active_session_id = self._retention_active_session_id()
        if not active_reference_valid:
            # A corrupt or redirected active.json means we cannot prove which
            # session is safe to remove, so retain every session.
            return RetentionReport()
        candidates: list[RetentionCandidate] = []
        paths = sorted(self.sessions_dir.glob("*/metadata.json"))
        for path_session_id, path in iter_valid_record_files(
            self.sessions_dir,
            paths,
            kind="session",
            record_filename="metadata.json",
        ):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(metadata, dict):
                continue
            timestamp = self._validated_terminal_timestamp(
                path_session_id,
                path,
                metadata,
            )
            if timestamp is None or path_session_id == active_session_id:
                continue
            candidates.append(
                RetentionCandidate(
                    identifier=path_session_id,
                    path=path.parent,
                    timestamp=timestamp,
                )
            )
        return prune_terminal_records(
            state_root=self.state_dir,
            store_root=self.sessions_dir,
            candidates=candidates,
            policy=self.retention,
            clock=self.clock,
        )

    def _validated_terminal_timestamp(
        self,
        session_id: str,
        metadata_path: Path,
        metadata: dict[str, Any],
    ) -> datetime | None:
        if (
            metadata.get("session_id") != session_id
            or metadata.get("status") not in {"applied", "cancelled"}
            or not isinstance(metadata.get("exchange_path"), str)
            or not isinstance(metadata.get("source_type"), str)
            or not isinstance(metadata.get("version"), str)
            or not isinstance(metadata.get("units"), str)
            or not isinstance(metadata.get("bridge_pid"), int)
            or not isinstance(metadata.get("edit_count"), int)
            or parse_retention_timestamp(metadata.get("created_at")) is None
            or parse_retention_timestamp(metadata.get("updated_at")) is None
        ):
            return None
        finished_at = parse_retention_timestamp(metadata.get("finished_at"))
        if finished_at is None:
            return None
        directory = metadata_path.parent
        original = directory / "original.xml"
        working = directory / "working.xml"
        try:
            require_confined_file(directory, original)
            require_confined_file(directory, working)
            if (
                original.stat().st_size > self.max_document_bytes
                or working.stat().st_size > self.max_document_bytes
                or metadata.get("original_sha256") != sha256_bytes(original.read_bytes())
                or metadata.get("working_sha256") != sha256_bytes(working.read_bytes())
            ):
                return None
        except (InvalidRecordPath, OSError, ValueError):
            return None
        return finished_at

    def _retention_active_session_id(self) -> tuple[bool, str | None]:
        if not self.active_file.exists() and not is_link_like(self.active_file):
            return True, None
        try:
            if is_link_like(self.active_file):
                return False, None
            require_confined_file(self.state_dir, self.active_file)
            payload = json.loads(self.active_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return False, None
            session_id = payload.get("session_id")
            if not isinstance(session_id, str):
                return False, None
            validated = require_record_id(session_id, "session")
            metadata_path = require_confined_record_file(
                self.sessions_dir,
                validated,
                kind="session",
                record_filename="metadata.json",
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict) or metadata.get("session_id") != validated:
                return False, None
            return True, validated
        except (
            InvalidRecordId,
            InvalidRecordPath,
            OSError,
            ValueError,
        ):
            return False, None

    def session_dir(self, session_id: str) -> Path:
        try:
            validated = require_record_id(session_id, "session")
        except InvalidRecordId:
            raise SessionError("Invalid session id") from None
        return self.sessions_dir / validated

    def metadata_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "metadata.json"

    def working_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "working.xml"

    def original_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "original.xml"

    def control_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "control.json"

    def backups_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "backups"

    def read_metadata(self, session_id: str) -> dict[str, Any]:
        try:
            path = require_confined_record_file(
                self.sessions_dir,
                session_id,
                kind="session",
                record_filename="metadata.json",
            )
        except InvalidRecordId:
            raise SessionError("Invalid session id") from None
        except FileNotFoundError as exc:
            raise SessionError(f"Session was not found: {session_id}") from exc
        except InvalidRecordPath as exc:
            raise SessionError(
                "Session state path is redirected or outside its store"
            ) from exc
        metadata = _read_json(path)
        if metadata.get("session_id") != session_id:
            raise SessionError(
                "Session state id does not match the requested session"
            )
        return metadata

    def _read_active(self) -> dict[str, Any]:
        try:
            path = require_confined_file(self.state_dir, self.active_file)
            active = _read_json(path)
            session_id = active.get("session_id")
            if not isinstance(session_id, str):
                raise SessionError("active.json does not contain a valid session_id")
            require_record_id(session_id, "session")
        except FileNotFoundError as exc:
            raise SessionError("active.json disappeared while it was being read") from exc
        except (InvalidRecordId, InvalidRecordPath) as exc:
            raise SessionError("active.json contains unsafe session state") from exc
        return active

    def update_metadata(self, session_id: str, **updates: Any) -> dict[str, Any]:
        metadata = self.read_metadata(session_id)
        metadata.update(updates)
        self._require_safe_root()
        _atomic_write_json(self.metadata_path(session_id), metadata)
        return metadata

    def active_metadata(self) -> dict[str, Any] | None:
        if not self.active_file.exists() and not is_link_like(self.active_file):
            return None
        active = self._read_active()
        session_id = str(active["session_id"])
        metadata = self.read_metadata(session_id)
        if metadata.get("status") != "active":
            return None
        working = self.working_path(session_id)
        if not working.is_file():
            raise SessionError(f"Active session has no working XML: {session_id}")
        return metadata

    def create(self, exchange_path: Path) -> dict[str, Any]:
        current = self.active_metadata()
        if current is not None:
            raise SessionError(
                f"Another DipTrace MCP session is active: {current.get('session_id')}"
            )
        document = DipTraceDocument.load(exchange_path, self.max_document_bytes)
        session_id = str(uuid.uuid4())
        directory = self.session_dir(session_id)
        self._require_safe_root()
        directory.mkdir(parents=True, exist_ok=False)
        original = self.original_path(session_id)
        working = self.working_path(session_id)
        shutil.copyfile(exchange_path, original)
        shutil.copyfile(exchange_path, working)
        metadata: dict[str, Any] = {
            "session_id": session_id,
            "status": "active",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "bridge_pid": os.getpid(),
            "exchange_path": str(exchange_path),
            "working_path": str(working),
            "source_type": document.source_type,
            "version": document.version,
            "units": document.units,
            "original_sha256": document.sha256,
            "working_sha256": document.sha256,
            "edit_count": 0,
        }
        self._require_safe_root()
        _atomic_write_json(self.metadata_path(session_id), metadata)
        _atomic_write_json(self.active_file, {"session_id": session_id})
        return metadata

    def record_edit(self, session_id: str, working_sha256: str, backup: Path) -> None:
        metadata = self.read_metadata(session_id)
        self.update_metadata(
            session_id,
            working_sha256=working_sha256,
            updated_at=utc_now(),
            edit_count=int(metadata.get("edit_count", 0)) + 1,
            last_backup=str(backup),
        )

    def request_finish(self, action: SessionAction) -> dict[str, Any]:
        metadata = self.active_metadata()
        if metadata is None:
            raise SessionError("There is no active DipTrace session")
        session_id = str(metadata["session_id"])
        working = self.working_path(session_id).read_bytes()
        if action == "apply":
            document = DipTraceDocument.from_bytes(self.working_path(session_id), working)
            if document.source_type != metadata.get("source_type"):
                raise SessionError("Working XML type differs from the original session")
        request = {
            "action": action,
            "requested_at": utc_now(),
            "expected_sha256": sha256_bytes(working),
        }
        # Publish control.json last: the Windows bridge treats it as a commit marker.
        # Publishing it first races the metadata replace on shared WSL/Windows paths.
        self.update_metadata(
            session_id,
            finish_requested=action,
            finish_requested_at=request["requested_at"],
        )
        self._require_safe_root()
        _atomic_write_json(self.control_path(session_id), request)
        return {"session_id": session_id, **request}

    def read_finish_request(self, session_id: str) -> dict[str, Any] | None:
        path = self.control_path(session_id)
        if not path.exists():
            return None
        return _read_json(path)

    def clear_finish_request(self, session_id: str) -> None:
        self.control_path(session_id).unlink(missing_ok=True)

    def finalize(
        self,
        session_id: str,
        action: SessionAction,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        metadata = self.read_metadata(session_id)
        if metadata.get("status") != "active":
            raise SessionError(f"Session is not active: {session_id}")

        working_path = self.working_path(session_id)
        working = working_path.read_bytes()
        current_sha256 = sha256_bytes(working)
        if expected_sha256 and current_sha256 != expected_sha256:
            raise SessionError("Working XML changed after the finish request")

        if action == "apply":
            document = DipTraceDocument.from_bytes(working_path, working)
            if document.source_type != metadata.get("source_type"):
                raise SessionError("Working XML type differs from the original session")
            exchange_path = Path(str(metadata["exchange_path"]))
            atomic_write_bytes(exchange_path, working)

        status = "applied" if action == "apply" else "cancelled"
        metadata = self.update_metadata(
            session_id,
            status=status,
            updated_at=utc_now(),
            finished_at=utc_now(),
            working_sha256=current_sha256,
        )
        self.clear_finish_request(session_id)
        if self.active_file.exists():
            active = self._read_active()
            if active.get("session_id") == session_id:
                self.active_file.unlink(missing_ok=True)
        return metadata
