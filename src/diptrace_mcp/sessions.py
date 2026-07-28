from __future__ import annotations

import json
import os
import stat
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
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
BridgeImportMode = Literal["All", "None", "Unknown"]

_JSON_READ_ATTEMPTS = 8
_JSON_READ_RETRY_SECONDS = 0.025
_FILE_READ_CHUNK_BYTES = 1024 * 1024
_SESSION_THREAD_LOCKS: dict[str, threading.RLock] = {}
_SESSION_THREAD_LOCKS_GUARD = threading.Lock()
_BRIDGE_IMPORT_MODE_BY_SOURCE_TYPE: dict[str, BridgeImportMode] = {
    "DipTrace-PCB": "All",
    "DipTrace-Schematic": "All",
    "DipTrace-ComponentLibrary": "None",
    "DipTrace-PatternLibrary": "None",
}


def _thread_lock_for(path: Path) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(path))
    with _SESSION_THREAD_LOCKS_GUARD:
        return _SESSION_THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_file_descriptor(file_descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        if os.fstat(file_descriptor).st_size == 0:
            os.write(file_descriptor, b"\0")
        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(  # type: ignore[attr-defined]
            file_descriptor,
            msvcrt.LK_LOCK,  # type: ignore[attr-defined]
            1,
        )
        return

    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_EX)


def _unlock_file_descriptor(file_descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(file_descriptor, 0, os.SEEK_SET)
        msvcrt.locking(  # type: ignore[attr-defined]
            file_descriptor,
            msvcrt.LK_UNLCK,  # type: ignore[attr-defined]
            1,
        )
        return

    import fcntl

    fcntl.flock(file_descriptor, fcntl.LOCK_UN)


@contextmanager
def _exclusive_session_lock(path: Path) -> Iterator[None]:
    """Serialize session lifecycle mutations across threads and processes."""

    thread_lock = _thread_lock_for(path)
    with thread_lock:
        if is_link_like(path):
            raise SessionError("Session lock path is redirected")
        flags = os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            file_descriptor = os.open(path, flags, 0o600)
        except OSError as exc:
            raise SessionError("Cannot open the session state lock") from exc
        try:
            try:
                descriptor_stat = os.fstat(file_descriptor)
                path_stat = path.stat(follow_symlinks=False)
            except OSError as exc:
                raise SessionError("Cannot validate the session state lock") from exc
            if (
                not stat.S_ISREG(descriptor_stat.st_mode)
                or stat.S_ISLNK(path_stat.st_mode)
                or descriptor_stat.st_nlink != 1
                or path_stat.st_nlink != 1
                or (descriptor_stat.st_dev, descriptor_stat.st_ino)
                != (path_stat.st_dev, path_stat.st_ino)
            ):
                raise SessionError("Session lock path is redirected")
            try:
                _lock_file_descriptor(file_descriptor)
            except OSError as exc:
                raise SessionError("Cannot acquire the session state lock") from exc
            try:
                yield
            finally:
                _unlock_file_descriptor(file_descriptor)
        finally:
            os.close(file_descriptor)


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


def _stable_regular_file_bytes(
    path: Path,
    max_bytes: int,
    *,
    purpose: str,
) -> bytes:
    """Read one bounded, non-linked regular file without accepting a path swap."""

    if is_link_like(path):
        raise SessionError(
            f"{purpose} is redirected",
            code="path_access_denied",
        )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(path, flags)
    except OSError as exc:
        raise SessionError(
            f"Cannot open {purpose} safely",
            code="path_access_denied",
        ) from exc
    try:
        try:
            before = os.fstat(file_descriptor)
            path_before = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise SessionError(
                f"Cannot validate {purpose}",
                code="path_access_denied",
            ) from exc
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(path_before.st_mode)
            or before.st_nlink != 1
            or path_before.st_nlink != 1
            or (before.st_dev, before.st_ino) != (path_before.st_dev, path_before.st_ino)
        ):
            raise SessionError(
                f"{purpose} must be one non-linked regular file",
                code="path_access_denied",
            )
        if before.st_size > max_bytes:
            raise SessionError(
                f"{purpose} exceeds the configured document-size limit",
                code="document_too_large",
            )

        chunks: list[bytes] = []
        size = 0
        while True:
            try:
                chunk = os.read(file_descriptor, _FILE_READ_CHUNK_BYTES)
            except OSError as exc:
                raise SessionError(
                    f"Cannot read {purpose}",
                    code="session_io_error",
                ) from exc
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise SessionError(
                    f"{purpose} exceeds the configured document-size limit",
                    code="document_too_large",
                )
            chunks.append(chunk)

        try:
            after = os.fstat(file_descriptor)
            path_after = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise SessionError(
                f"Cannot revalidate {purpose}",
                code="path_access_denied",
            ) from exc
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if (
            identity_before != identity_after
            or after.st_nlink != 1
            or path_after.st_nlink != 1
            or (after.st_dev, after.st_ino)
            != (path_after.st_dev, path_after.st_ino)
            or is_link_like(path)
        ):
            raise SessionError(
                f"{purpose} changed while it was being read",
                code="sha256_mismatch",
            )
        return b"".join(chunks)
    finally:
        os.close(file_descriptor)


def _require_apply_supported(metadata: dict[str, Any]) -> None:
    source_type = str(metadata.get("source_type", ""))
    import_mode = _BRIDGE_IMPORT_MODE_BY_SOURCE_TYPE.get(source_type, "Unknown")
    if import_mode == "None":
        raise SessionError(
            "Apply is unavailable for this library bridge profile because "
            "its shipped ImpMode is None; cancel the read-only session",
            code="capability_unavailable",
        )
    if import_mode != "All":
        raise SessionError(
            "Apply is unavailable because this source type has no shipped "
            "bridge import policy; cancel the read-only session",
            code="capability_unavailable",
        )


class SessionStore:
    def __init__(
        self,
        state_dir: Path,
        max_document_bytes: int = 128 * 1024 * 1024,
        *,
        allowed_roots: tuple[Path, ...] | None = None,
        retention: RetentionPolicy | None = None,
        clock: Clock = system_clock,
    ):
        self.state_dir = state_dir
        self.sessions_dir = state_dir / "sessions"
        self.active_file = state_dir / "active.json"
        self.lock_file = state_dir / "session.lock"
        self.max_document_bytes = max_document_bytes
        self.allowed_roots = (
            tuple(root.resolve(strict=False) for root in allowed_roots)
            if allowed_roots is not None
            else None
        )
        self.retention = retention or RetentionPolicy()
        self.clock = clock
        prepare_safe_store_root(self.state_dir, self.sessions_dir)
        self.last_retention_report = self._prune_retention()

    def _require_safe_root(self) -> None:
        require_safe_store_root(self.state_dir, self.sessions_dir)

    def _read_exchange_path(self, path: Path) -> tuple[Path, bytes]:
        if not path.is_absolute():
            raise SessionError(
                "Session exchange path must be absolute",
                code="path_access_denied",
            )
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise SessionError(
                "Session exchange path is unavailable",
                code="path_access_denied",
            ) from exc
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(
            os.path.abspath(resolved)
        ):
            raise SessionError(
                "Session exchange path is redirected",
                code="path_access_denied",
            )
        if self.allowed_roots is not None:
            inside_allowed_root = False
            for root in self.allowed_roots:
                try:
                    resolved.relative_to(root)
                except ValueError:
                    continue
                inside_allowed_root = True
                break
            if not inside_allowed_root:
                raise SessionError(
                    "Session exchange path is outside allowed roots",
                    code="path_access_denied",
                )
        return resolved, _stable_regular_file_bytes(
            resolved,
            self.max_document_bytes,
            purpose="session exchange file",
        )

    def _read_bound_exchange(
        self,
        metadata: dict[str, Any],
    ) -> tuple[Path, bytes]:
        if self.allowed_roots is None:
            raise SessionError(
                "Session apply requires configured allowed roots",
                code="path_access_denied",
            )
        raw_path = metadata.get("exchange_path")
        original_sha256 = metadata.get("original_sha256")
        session_id = metadata.get("session_id")
        if (
            not isinstance(raw_path, str)
            or not isinstance(original_sha256, str)
            or not isinstance(session_id, str)
        ):
            raise SessionError(
                "Session metadata has no valid exchange-file binding",
                code="session_state_invalid",
            )
        original_path = self.original_path(session_id)
        try:
            require_confined_file(self.session_dir(session_id), original_path)
        except (FileNotFoundError, InvalidRecordId, InvalidRecordPath) as exc:
            raise SessionError(
                "Session original XML is unavailable or redirected",
                code="session_state_invalid",
            ) from exc
        original = _stable_regular_file_bytes(
            original_path,
            self.max_document_bytes,
            purpose="session original XML",
        )
        recorded_original_sha256 = sha256_bytes(original)
        if original_sha256 != recorded_original_sha256:
            raise SessionError(
                "Session metadata does not match the captured original XML",
                code="session_state_invalid",
            )
        exchange_path, exchange = self._read_exchange_path(Path(raw_path))
        current_sha256 = sha256_bytes(exchange)
        if current_sha256 != recorded_original_sha256:
            raise SessionError(
                "External exchange file changed after the live session started",
                code="sha256_mismatch",
                details={
                    "expected_sha256": recorded_original_sha256,
                    "current_sha256": current_sha256,
                },
            )
        return exchange_path, exchange

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

    def _read_working_bytes(self, session_id: str) -> bytes:
        working_path = self.working_path(session_id)
        try:
            require_confined_file(self.session_dir(session_id), working_path)
        except (FileNotFoundError, InvalidRecordPath) as exc:
            raise SessionError(
                "Session working XML is unavailable or redirected",
                code="path_access_denied",
            ) from exc
        return _stable_regular_file_bytes(
            working_path,
            self.max_document_bytes,
            purpose="session working XML",
        )

    def working_sha256(self, session_id: str) -> str:
        """Return the SHA-256 of one bounded, stable live working-file read."""

        return sha256_bytes(self._read_working_bytes(session_id))

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
        with _exclusive_session_lock(self.lock_file):
            return self._create_unlocked(exchange_path)

    def _create_unlocked(self, exchange_path: Path) -> dict[str, Any]:
        current = self.active_metadata()
        if current is not None:
            raise SessionError(
                f"Another DipTrace MCP session is active: {current.get('session_id')}"
            )
        exchange_path, exchange = self._read_exchange_path(exchange_path)
        document = DipTraceDocument.from_bytes(exchange_path, exchange)
        session_id = str(uuid.uuid4())
        directory = self.session_dir(session_id)
        self._require_safe_root()
        directory.mkdir(parents=True, exist_ok=False)
        original = self.original_path(session_id)
        working = self.working_path(session_id)
        atomic_write_bytes(original, exchange)
        atomic_write_bytes(working, exchange)
        bridge_import_mode: BridgeImportMode = _BRIDGE_IMPORT_MODE_BY_SOURCE_TYPE.get(
            document.source_type,
            "Unknown",
        )
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
            "bridge_import_mode": bridge_import_mode,
            "apply_supported": bridge_import_mode != "None",
            "apply_unavailable_reason": (
                None
                if bridge_import_mode == "All"
                else (
                    "shipped_library_profile_uses_ImpMode_None"
                    if bridge_import_mode == "None"
                    else "source_type_has_no_shipped_import_policy"
                )
            ),
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

    def request_finish(
        self,
        action: SessionAction,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        with _exclusive_session_lock(self.lock_file):
            return self._request_finish_unlocked(action, expected_sha256)

    def _request_finish_unlocked(
        self,
        action: SessionAction,
        expected_sha256: str | None,
    ) -> dict[str, Any]:
        metadata = self.active_metadata()
        if metadata is None:
            raise SessionError("There is no active DipTrace session")
        if action == "apply":
            _require_apply_supported(metadata)
        session_id = str(metadata["session_id"])
        working = self._read_working_bytes(session_id)
        current_sha256 = sha256_bytes(working)
        if action == "apply":
            if expected_sha256 is None:
                raise SessionError(
                    "expected_sha256 of the latest inspected working XML is required "
                    "when action=apply",
                    code="confirmation_required",
                )
            if current_sha256 != expected_sha256:
                raise SessionError(
                    "Working XML changed after it was inspected",
                    code="sha256_mismatch",
                    details={
                        "expected_sha256": expected_sha256,
                        "current_sha256": current_sha256,
                    },
                )
            document = DipTraceDocument.from_bytes(
                self.working_path(session_id),
                working,
            )
            if document.source_type != metadata.get("source_type"):
                raise SessionError("Working XML type differs from the original session")
            self._read_bound_exchange(metadata)
        request = {
            "action": action,
            "requested_at": utc_now(),
            "expected_sha256": current_sha256,
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
        with _exclusive_session_lock(self.lock_file):
            return self._finalize_unlocked(session_id, action, expected_sha256)

    def _finalize_unlocked(
        self,
        session_id: str,
        action: SessionAction,
        expected_sha256: str | None,
    ) -> dict[str, Any]:
        metadata = self.read_metadata(session_id)
        if metadata.get("status") != "active":
            raise SessionError(f"Session is not active: {session_id}")
        if action == "apply":
            _require_apply_supported(metadata)

        working_path = self.working_path(session_id)
        working = self._read_working_bytes(session_id)
        current_sha256 = sha256_bytes(working)

        if action == "apply":
            if expected_sha256 is None:
                raise SessionError(
                    "expected_sha256 of the finish request is required when action=apply",
                    code="confirmation_required",
                )
            if current_sha256 != expected_sha256:
                raise SessionError(
                    "Working XML changed after the finish request",
                    code="sha256_mismatch",
                    details={
                        "expected_sha256": expected_sha256,
                        "current_sha256": current_sha256,
                    },
                )
            document = DipTraceDocument.from_bytes(working_path, working)
            if document.source_type != metadata.get("source_type"):
                raise SessionError("Working XML type differs from the original session")
            exchange_path, _exchange = self._read_bound_exchange(metadata)
            atomic_write_bytes(exchange_path, working)
            _post_write_path, applied = self._read_exchange_path(exchange_path)
            applied_sha256 = sha256_bytes(applied)
            if applied_sha256 != current_sha256:
                # A different post-write value could be an external writer.  Never
                # overwrite it blindly while attempting compensation.
                raise SessionError(
                    "Exchange-file SHA-256 does not match the applied working XML",
                    code="sha256_mismatch",
                    details={
                        "expected_sha256": current_sha256,
                        "current_sha256": applied_sha256,
                    },
                )

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
