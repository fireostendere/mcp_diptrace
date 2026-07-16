from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from .errors import SessionError
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
    def __init__(self, state_dir: Path, max_document_bytes: int = 128 * 1024 * 1024):
        self.state_dir = state_dir
        self.sessions_dir = state_dir / "sessions"
        self.active_file = state_dir / "active.json"
        self.max_document_bytes = max_document_bytes
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        if not session_id or any(character not in "0123456789abcdef-" for character in session_id):
            raise SessionError("Invalid session id")
        return self.sessions_dir / session_id

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
        return _read_json(self.metadata_path(session_id))

    def update_metadata(self, session_id: str, **updates: Any) -> dict[str, Any]:
        metadata = self.read_metadata(session_id)
        metadata.update(updates)
        _atomic_write_json(self.metadata_path(session_id), metadata)
        return metadata

    def active_metadata(self) -> dict[str, Any] | None:
        if not self.active_file.exists():
            return None
        active = _read_json(self.active_file)
        session_id = active.get("session_id")
        if not isinstance(session_id, str):
            raise SessionError("active.json does not contain a valid session_id")
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
            active = _read_json(self.active_file)
            if active.get("session_id") == session_id:
                self.active_file.unlink(missing_ok=True)
        return metadata
