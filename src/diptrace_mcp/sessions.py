from __future__ import annotations

import json
import os
import stat
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from .config import DEFAULT_LIVE_SESSION_TTL_SECONDS
from .errors import DocumentError, SessionError, Sha256MismatchError
from .record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    is_link_like,
    iter_valid_record_files,
    require_confined_file,
    require_confined_record_file,
    require_record_id,
)
from .record_store import RecordStore
from .retention import (
    Clock,
    RetentionCandidate,
    RetentionPolicy,
    RetentionReport,
    parse_retention_timestamp,
    prune_terminal_records,
    system_clock,
)
from .write_limits import WriteImpact, require_write_impact, write_impact
from .xml_document import (
    DipTraceDocument,
    atomic_write_bytes,
    sha256_bytes,
    utc_now,
)

SessionAction = Literal["apply", "cancel"]
BridgeImportMode = Literal["All", "None", "Unknown"]
BridgeProcessLiveness = Literal["alive", "dead", "unknown"]
FinishOutcome = Literal["applied", "cancelled", "not_acknowledged"]

_JSON_READ_ATTEMPTS = 8
_JSON_READ_RETRY_SECONDS = 0.025
_FILE_READ_CHUNK_BYTES = 1024 * 1024
_FINISH_POLL_SECONDS = 0.05
DEFAULT_FINISH_ACK_WAIT_SECONDS = 2.0
LIVE_PREVIEW_CHANGED_ID_LIMIT = 20
_SESSION_LEASE_WAIT_SECONDS = 30.0
_SESSION_LEASE_POLL_SECONDS = 0.025
_SESSION_LEASE_RELEASE_ATTEMPTS = 8
_BRIDGE_IMPORT_MODE_BY_SOURCE_TYPE: dict[str, BridgeImportMode] = {
    "DipTrace-PCB": "All",
    "DipTrace-Schematic": "All",
    "DipTrace-ComponentLibrary": "None",
    "DipTrace-PatternLibrary": "None",
}


@dataclass(frozen=True, slots=True)
class LiveWorkingMutation:
    session_id: str
    before_sha256: str
    after_sha256: str
    backup: Path


@dataclass(slots=True)
class LiveWorkingGuard:
    """One live working-file mutation while the lifecycle lease is held."""

    store: SessionStore
    session_id: str
    metadata_before: dict[str, Any]
    working_before: bytes
    recorded_sha256: str | None = None
    committed: bool = False

    def record_edit(
        self,
        *,
        working_sha256: str,
        backup: Path | None = None,
    ) -> Path:
        current = self.store._read_working_bytes(self.session_id)
        if sha256_bytes(current) != working_sha256:
            raise Sha256MismatchError(
                "Live working XML does not match the guarded edit metadata"
            )
        if backup is None:
            backup = self.store._store_working_backup_unlocked(
                self.session_id,
                self.working_before,
            )
        self.recorded_sha256 = working_sha256
        self.store._record_edit_unlocked(
            self.metadata_before,
            working_sha256=working_sha256,
            backup=backup,
        )
        return backup

    def commit(self) -> None:
        """Mark caller state durable so later response errors cannot undo the file."""

        self.committed = True


def _pid_namespace() -> str:
    """Return a stable namespace token without pretending Windows and WSL share PIDs."""

    if os.name == "nt":
        return "windows-global"
    if sys.platform.startswith("linux"):
        try:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
                encoding="ascii"
            ).strip()
            namespace = os.readlink("/proc/self/ns/pid")
        except OSError:
            return "linux:unavailable"
        return f"linux:{boot_id}:{namespace}"
    return f"{sys.platform}:system"  # type: ignore[unreachable]


def _linux_process_start_token(pid: int) -> str | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        # Field 22 is process start time.  The command in field 2 may contain
        # spaces or parentheses, so split only after its final closing parenthesis.
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").rsplit(
            ")", 1
        )[1].split()
        return fields[19]
    except (IndexError, OSError):
        return None


def _current_bridge_process_identity() -> dict[str, object]:
    pid = os.getpid()
    return {
        "pid": pid,
        "platform": sys.platform,
        "pid_namespace": _pid_namespace(),
        "start_token": (
            _windows_process_snapshot(pid)[1]
            if os.name == "nt"
            else _linux_process_start_token(pid)
        ),
    }


def _classify_windows_process(
    *,
    opened: bool,
    last_error: int,
    exit_code: int | None,
) -> BridgeProcessLiveness:
    if not opened:
        return "dead" if last_error == 87 else "unknown"
    if exit_code is None:
        return "unknown"
    return "alive" if exit_code == 259 else "dead"


def _classify_process_identity(
    liveness: BridgeProcessLiveness,
    *,
    expected_start_token: object,
    current_start_token: str | None,
) -> BridgeProcessLiveness:
    if liveness == "dead":
        return "dead"
    if (
        liveness != "alive"
        or not isinstance(expected_start_token, str)
        or current_start_token is None
    ):
        return "unknown"
    return "alive" if current_start_token == expected_start_token else "dead"


def _windows_process_snapshot(
    pid: int,
) -> tuple[BridgeProcessLiveness, str | None]:
    """Query Windows liveness and creation time without POSIX/WSL PID guesses."""

    try:
        import ctypes
        from ctypes import wintypes

        win_dll: Any = getattr(ctypes, "WinDLL", None)
        set_last_error: Any = getattr(ctypes, "set_last_error", None)
        get_last_error: Any = getattr(ctypes, "get_last_error", None)
        if win_dll is None or set_last_error is None or get_last_error is None:
            return "unknown", None
        kernel32: Any = win_dll("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        set_last_error(0)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            error = int(get_last_error())
            # ERROR_INVALID_PARAMETER is what OpenProcess reports for a PID that
            # does not exist. Access-denied is not evidence that the process died.
            return (
                _classify_windows_process(
                    opened=False,
                    last_error=error,
                    exit_code=None,
                ),
                None,
            )
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return "unknown", None
            liveness = _classify_windows_process(
                opened=True,
                last_error=0,
                exit_code=int(exit_code.value),
            )
            if liveness != "alive":
                return liveness, None
            creation = wintypes.FILETIME()
            exit_time = wintypes.FILETIME()
            kernel_time = wintypes.FILETIME()
            user_time = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time),
            ):
                return "unknown", None
            token = f"{int(creation.dwHighDateTime):08x}{int(creation.dwLowDateTime):08x}"
            return "alive", token
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return "unknown", None


def _windows_process_liveness(
    pid: int,
    expected_start_token: object,
) -> BridgeProcessLiveness:
    liveness, current_start_token = _windows_process_snapshot(pid)
    return _classify_process_identity(
        liveness,
        expected_start_token=expected_start_token,
        current_start_token=current_start_token,
    )


def _bridge_process_liveness(metadata: dict[str, Any]) -> BridgeProcessLiveness:
    """Check a recorded PID only inside the exact recorded platform/namespace."""

    identity = metadata.get("bridge_process")
    if not isinstance(identity, dict):
        # Legacy metadata contains only bridge_pid. Guessing its namespace could
        # classify an unrelated WSL or Windows PID as the bridge.
        return "unknown"
    pid = identity.get("pid")
    platform = identity.get("platform")
    namespace = identity.get("pid_namespace")
    if (
        not isinstance(pid, int)
        or pid <= 0
        or platform != sys.platform
        or namespace != _pid_namespace()
        or (
            isinstance(namespace, str)
            and namespace.endswith(":unavailable")
        )
    ):
        return "unknown"
    if os.name == "nt":
        return _windows_process_liveness(pid, identity.get("start_token"))
    expected_start = identity.get("start_token")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        pass
    except OSError:
        return "unknown"
    return _classify_process_identity(
        "alive",
        expected_start_token=expected_start,
        current_start_token=_linux_process_start_token(pid),
    )


@contextmanager
def _exclusive_session_lock(path: Path) -> Iterator[None]:
    """Serialize lifecycle changes with an atomic lease shared by WSL and Windows.

    POSIX ``flock`` and Windows byte-range locks do not interoperate on NTFS.  A
    directory create is atomic through both views of the filesystem, so the lease
    directory is the cross-platform commit marker.  A nonce prevents one owner
    from releasing a lease reclaimed after its exact process identity is dead.
    Unknown cross-namespace owners are never expired by time alone.
    """

    lease = path.with_name(f"{path.name}.lease")
    owner_path = lease / "owner.json"
    reaper = path.with_name(f"{path.name}.reaper")
    nonce = uuid.uuid4().hex
    deadline = time.perf_counter() + _SESSION_LEASE_WAIT_SECONDS
    if path.exists() or is_link_like(path):
        try:
            legacy_stat = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise SessionError("Session lock path is redirected") from exc
        if (
            stat.S_ISLNK(legacy_stat.st_mode)
            or not stat.S_ISREG(legacy_stat.st_mode)
            or legacy_stat.st_nlink != 1
        ):
            raise SessionError("Session lock path is redirected")
    owner = {
        "nonce": nonce,
        "process": _current_bridge_process_identity(),
        "acquired_at": time.time(),
    }
    candidate = path.with_name(f"{path.name}.candidate.{nonce}")
    try:
        candidate.mkdir(mode=0o700)
        _atomic_write_json(candidate / "owner.json", owner)
    except OSError as exc:
        raise SessionError("Cannot prepare the session state lease") from exc
    acquired = False
    try:
        while True:
            if reaper.exists() or is_link_like(reaper):
                if time.perf_counter() >= deadline:
                    raise SessionError(
                        "Timed out waiting for session lease recovery",
                        code="session_lock_timeout",
                    )
                time.sleep(_SESSION_LEASE_POLL_SECONDS)
                continue
            if is_link_like(lease):
                raise SessionError("Session lease path is redirected")
            if not lease.exists():
                try:
                    candidate.rename(lease)
                except OSError:
                    if not lease.exists():
                        raise SessionError(
                            "Cannot publish the session state lease",
                            code="session_lock_unavailable",
                        ) from None
                else:
                    acquired = True
                    if reaper.exists() or is_link_like(reaper):
                        # A reaper won the race after our first gate check. It
                        # never touches a live owner; release and retry after it.
                        _release_owned_session_lease(lease, nonce)
                        acquired = False
                        candidate.mkdir(mode=0o700)
                        _atomic_write_json(candidate / "owner.json", owner)
                        continue
                    break
            try:
                existing_owner = _read_json(owner_path)
                owner_process = existing_owner.get("process")
                owner_liveness = (
                    _bridge_process_liveness({"bridge_process": owner_process})
                    if isinstance(owner_process, dict)
                    else "unknown"
                )
            except (FileNotFoundError, OSError, SessionError):
                owner_liveness = "unknown"
                existing_owner = {}
            if owner_liveness == "dead" and _reap_dead_session_lease(
                lease,
                reaper,
                expected_nonce=existing_owner.get("nonce"),
            ):
                continue
            if time.perf_counter() >= deadline:
                raise SessionError(
                    "Timed out waiting for the cross-platform session lease",
                    code="session_lock_timeout",
                ) from None
            time.sleep(_SESSION_LEASE_POLL_SECONDS)

        yield
        try:
            current_owner = _read_json(owner_path)
        except (FileNotFoundError, OSError, SessionError) as exc:
            raise SessionError(
                "Cross-platform session lease ownership was lost",
                code="session_lock_lost",
            ) from exc
        if current_owner.get("nonce") != nonce:
            raise SessionError(
                "Cross-platform session lease was replaced",
                code="session_lock_lost",
            )
    finally:
        if acquired:
            try:
                current_owner = _read_json(owner_path)
            except (FileNotFoundError, OSError, SessionError):
                current_owner = {}
            if current_owner.get("nonce") == nonce:
                _release_owned_session_lease(lease, nonce)
        try:
            (candidate / "owner.json").unlink(missing_ok=True)
            candidate.rmdir()
        except OSError:
            pass


def _release_owned_session_lease(lease: Path, nonce: str) -> None:
    """Atomically free the canonical lease name before best-effort cleanup."""

    tombstone = lease.with_name(f"{lease.name}.released.{nonce}.{uuid.uuid4().hex}")
    last_error: OSError | None = None
    for attempt in range(_SESSION_LEASE_RELEASE_ATTEMPTS):
        try:
            lease.rename(tombstone)
            break
        except OSError as exc:
            last_error = exc
            if attempt + 1 < _SESSION_LEASE_RELEASE_ATTEMPTS:
                time.sleep(_SESSION_LEASE_POLL_SECONDS)
    else:
        raise SessionError(
            "Cannot atomically release the session lease",
            code="session_lock_release_failed",
        ) from last_error
    owner_path = tombstone / "owner.json"
    try:
        owner = _read_json(owner_path)
    except (FileNotFoundError, OSError, SessionError):
        return
    if owner.get("nonce") != nonce:
        raise SessionError(
            "Released session lease has an unexpected owner",
            code="session_lock_lost",
        )
    with suppress(OSError):
        owner_path.unlink(missing_ok=True)
        tombstone.rmdir()


def _reap_dead_session_lease(
    lease: Path,
    reaper: Path,
    *,
    expected_nonce: object,
) -> bool:
    """Remove one exactly identified dead-owner lease under an atomic reaper gate."""

    if not isinstance(expected_nonce, str):
        return False
    try:
        reaper.mkdir(mode=0o700)
    except FileExistsError:
        return False
    except OSError:
        return False
    tombstone = lease.with_name(f"{lease.name}.dead.{expected_nonce}.{uuid.uuid4().hex}")
    try:
        if is_link_like(lease):
            return False
        try:
            owner = _read_json(lease / "owner.json")
        except (FileNotFoundError, OSError, SessionError):
            return False
        if owner.get("nonce") != expected_nonce:
            return False
        process = owner.get("process")
        if (
            not isinstance(process, dict)
            or _bridge_process_liveness({"bridge_process": process}) != "dead"
        ):
            return False
        try:
            lease.rename(tombstone)
        except OSError:
            return False
        moved_owner = _read_json(tombstone / "owner.json")
        if moved_owner.get("nonce") != expected_nonce:
            raise SessionError(
                "Dead-owner lease changed during fenced recovery",
                code="session_lock_recovery_failed",
            )
        (tombstone / "owner.json").unlink(missing_ok=True)
        tombstone.rmdir()
        return True
    finally:
        with suppress(OSError):
            reaper.rmdir()


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


class SessionStore(RecordStore):
    def __init__(
        self,
        state_dir: Path,
        max_document_bytes: int = 128 * 1024 * 1024,
        *,
        allowed_roots: tuple[Path, ...] | None = None,
        retention: RetentionPolicy | None = None,
        clock: Clock = system_clock,
        active_ttl_seconds: int = DEFAULT_LIVE_SESSION_TTL_SECONDS,
    ):
        if active_ttl_seconds <= 0:
            raise ValueError("active_ttl_seconds must be greater than zero")
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
        self.active_ttl_seconds = active_ttl_seconds
        self._last_session_transition: dict[str, object] | None = None
        self._initialize_record_store(
            state_dir=state_dir,
            store_root=self.sessions_dir,
        )
        self.last_retention_report = self._initial_retention_report()

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
        if (
            not ensure_ascii
            and indent == 2
            and not sort_keys
            and trailing_newline
        ):
            # Keep the lifecycle module's fault-injection and ordering seam;
            # the common base has already validated confinement.
            _atomic_write_json(path, value)
            return
        super()._atomic_write_store_json(
            path,
            value,
            ensure_ascii=ensure_ascii,
            indent=indent,
            sort_keys=sort_keys,
            trailing_newline=trailing_newline,
        )

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
        try:
            original = self._read_original_bytes(session_id)
        except SessionError as exc:
            raise SessionError(
                "Session original XML is unavailable or redirected",
                code="session_state_invalid",
            ) from exc
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
        status = metadata.get("status")
        if (
            metadata.get("session_id") != session_id
            or status not in {"applied", "cancelled", "abandoned"}
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
        if status == "abandoned" and not isinstance(metadata.get("abandon_reason"), str):
            return None
        finished_at = parse_retention_timestamp(metadata.get("finished_at"))
        if finished_at is None:
            return None
        try:
            if (
                metadata.get("original_sha256")
                != sha256_bytes(self._read_original_bytes(session_id))
                or metadata.get("working_sha256")
                != sha256_bytes(self._read_working_bytes(session_id))
            ):
                return None
        except (InvalidRecordPath, OSError, SessionError, ValueError):
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

    def session_id_for_working_path(self, path: Path) -> str | None:
        """Resolve a confined session working path even after it becomes terminal."""

        absolute = Path(os.path.abspath(path))
        try:
            relative = absolute.relative_to(Path(os.path.abspath(self.sessions_dir)))
        except ValueError:
            return None
        if len(relative.parts) != 2 or relative.name != "working.xml":
            return None
        try:
            session_id = require_record_id(relative.parts[0], "session")
            confined = require_confined_record_file(
                self.sessions_dir,
                session_id,
                kind="session",
                record_filename="working.xml",
            )
        except (FileNotFoundError, InvalidRecordId, InvalidRecordPath):
            return None
        if os.path.normcase(os.path.abspath(confined)) != os.path.normcase(
            os.path.abspath(absolute)
        ):
            return None
        return session_id

    def _read_original_bytes(self, session_id: str) -> bytes:
        original_path = self.original_path(session_id)
        try:
            require_confined_file(self.session_dir(session_id), original_path)
        except (FileNotFoundError, InvalidRecordPath) as exc:
            raise SessionError(
                "Session original XML is unavailable or redirected",
                code="path_access_denied",
            ) from exc
        return _stable_regular_file_bytes(
            original_path,
            self.max_document_bytes,
            purpose="session original XML",
        )

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
        self._write_store_json(
            self.metadata_path(session_id),
            metadata,
            trailing_newline=True,
        )
        return metadata

    def _clock_now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    def _clock_timestamp(self) -> str:
        return self._clock_now().isoformat()

    def _clear_active_reference_unlocked(self, session_id: str) -> None:
        if not self.active_file.exists() and not is_link_like(self.active_file):
            return
        active = self._read_active()
        if active.get("session_id") == session_id:
            self.active_file.unlink(missing_ok=True)

    def _abandon_session_unlocked(
        self,
        metadata: dict[str, Any],
        *,
        reason: str,
        automatic: bool,
    ) -> dict[str, Any]:
        session_id = str(metadata["session_id"])
        if metadata.get("status") != "active":
            raise SessionError(f"Session is not active: {session_id}")
        state_incomplete = False
        try:
            working_sha256 = sha256_bytes(self._read_working_bytes(session_id))
        except SessionError:
            # Abandonment never consumes or applies working XML. A crashed bridge
            # must still be recoverable when that state file is missing or unsafe;
            # the incomplete record then fails closed out of automatic retention.
            state_incomplete = True
            recorded_sha256 = metadata.get("working_sha256")
            working_sha256 = (
                recorded_sha256
                if isinstance(recorded_sha256, str)
                else ""
            )
        finished_at = self._clock_timestamp()
        abandoned = self.update_metadata(
            session_id,
            status="abandoned",
            updated_at=finished_at,
            finished_at=finished_at,
            abandoned_at=finished_at,
            abandon_reason=reason,
            abandonment_automatic=automatic,
            abandonment_state_incomplete=state_incomplete,
            working_sha256=working_sha256,
        )
        self._last_session_transition = {
            "session_id": session_id,
            "status": "abandoned",
            "reason": reason,
            "automatic": automatic,
            "finished_at": finished_at,
        }
        self.clear_finish_request(session_id)
        self._clear_active_reference_unlocked(session_id)
        return abandoned

    def last_session_transition(self) -> dict[str, object] | None:
        """Return the latest local lifecycle transition without filesystem paths."""

        if self._last_session_transition is None:
            return None
        return dict(self._last_session_transition)

    def _active_metadata_unlocked(self) -> dict[str, Any] | None:
        if not self.active_file.exists() and not is_link_like(self.active_file):
            return None
        active = self._read_active()
        session_id = str(active["session_id"])
        metadata = self.read_metadata(session_id)
        if metadata.get("status") != "active":
            self._clear_active_reference_unlocked(session_id)
            return None

        liveness = _bridge_process_liveness(metadata)
        if liveness == "dead":
            self._abandon_session_unlocked(
                metadata,
                reason="bridge_process_not_alive",
                automatic=True,
            )
            return None

        last_activity = parse_retention_timestamp(metadata.get("updated_at"))
        expires_at = (
            last_activity + timedelta(seconds=self.active_ttl_seconds)
            if liveness == "unknown" and last_activity is not None
            else None
        )
        if expires_at is not None and self._clock_now() >= expires_at:
            self._abandon_session_unlocked(
                metadata,
                reason="active_session_ttl_expired",
                automatic=True,
            )
            return None
        self._read_working_bytes(session_id)
        return {
            **metadata,
            "bridge_liveness": liveness,
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
        }

    def active_metadata(self) -> dict[str, Any] | None:
        with _exclusive_session_lock(self.lock_file):
            return self._active_metadata_unlocked()

    def abandon_active(self, reason: str) -> dict[str, Any]:
        normalized = reason.strip()
        if not normalized:
            raise SessionError(
                "An abandonment reason is required",
                code="invalid_request",
            )
        if len(normalized) > 500:
            raise SessionError(
                "The abandonment reason exceeds 500 characters",
                code="invalid_request",
            )
        with _exclusive_session_lock(self.lock_file):
            return self._abandon_active_unlocked(
                normalized,
            )

    def _abandon_active_unlocked(
        self,
        reason: str,
    ) -> dict[str, Any]:
        if not self.active_file.exists() and not is_link_like(self.active_file):
            raise SessionError("There is no active DipTrace session")
        active = self._read_active()
        metadata = self.read_metadata(str(active["session_id"]))
        if metadata.get("status") != "active":
            self._clear_active_reference_unlocked(str(active["session_id"]))
            raise SessionError("There is no active DipTrace session")
        return self._abandon_session_unlocked(
            metadata,
            reason=reason,
            automatic=False,
        )

    def create(self, exchange_path: Path) -> dict[str, Any]:
        with _exclusive_session_lock(self.lock_file):
            return self._create_unlocked(exchange_path)

    def _create_unlocked(self, exchange_path: Path) -> dict[str, Any]:
        current = self._active_metadata_unlocked()
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
        bridge_process = _current_bridge_process_identity()
        metadata: dict[str, Any] = {
            "session_id": session_id,
            "status": "active",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "bridge_pid": bridge_process["pid"],
            "bridge_process": bridge_process,
            "exchange_path": str(exchange_path),
            "working_path": str(working),
            "source_type": document.source_type,
            "version": document.version,
            "units": document.units,
            "bridge_import_mode": bridge_import_mode,
            "apply_supported": bridge_import_mode == "All",
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
        self._write_store_json(
            self.metadata_path(session_id),
            metadata,
            trailing_newline=True,
        )
        _atomic_write_json(self.active_file, {"session_id": session_id})
        return metadata

    def _require_mutable_working_unlocked(
        self,
        session_id: str,
        *,
        expected_sha256: str,
    ) -> tuple[dict[str, Any], bytes]:
        metadata = self.read_metadata(session_id)
        if metadata.get("status") != "active":
            raise SessionError(
                f"Session is not active: {session_id}",
                code="session_state_invalid",
            )
        active = self._read_active()
        if active.get("session_id") != session_id:
            raise SessionError(
                "Session is not the active bridge session",
                code="session_state_invalid",
            )
        control_path = self.control_path(session_id)
        if (
            metadata.get("finish_requested") is not None
            or control_path.exists()
            or is_link_like(control_path)
        ):
            raise SessionError(
                "Live working XML is frozen because session finish was requested",
                code="session_finish_pending",
            )
        current = self._read_working_bytes(session_id)
        current_sha256 = sha256_bytes(current)
        if current_sha256 != expected_sha256:
            raise Sha256MismatchError(
                "Live working XML changed before the guarded mutation",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": current_sha256,
                },
            )
        return metadata, current

    def _record_edit_unlocked(
        self,
        metadata: dict[str, Any],
        *,
        working_sha256: str,
        backup: Path,
    ) -> None:
        updated = {
            **metadata,
            "working_sha256": working_sha256,
            "updated_at": self._clock_timestamp(),
            "edit_count": int(metadata.get("edit_count", 0)) + 1,
            "last_backup": str(backup),
        }
        self._require_safe_root()
        self._write_store_json(
            self.metadata_path(str(metadata["session_id"])),
            updated,
            trailing_newline=True,
        )

    def _store_working_backup_unlocked(
        self,
        session_id: str,
        current: bytes,
    ) -> Path:
        destination = self.backups_dir(session_id)
        destination.mkdir(parents=True, exist_ok=True)
        current_sha256 = sha256_bytes(current)
        stamp = self._clock_now().strftime("%Y%m%dT%H%M%S.%fZ")
        backup = (
            destination
            / f"working.xml.{stamp}.{current_sha256[:12]}.{uuid.uuid4().hex}.bak"
        )
        atomic_write_bytes(backup, current)
        return backup

    @contextmanager
    def guard_working_mutation(
        self,
        session_id: str,
        *,
        expected_sha256: str,
    ) -> Iterator[LiveWorkingGuard]:
        """Hold lifecycle exclusion through file, metadata and caller state changes."""

        with _exclusive_session_lock(self.lock_file):
            metadata, current = self._require_mutable_working_unlocked(
                session_id,
                expected_sha256=expected_sha256,
            )
            guard = LiveWorkingGuard(
                store=self,
                session_id=session_id,
                metadata_before=metadata,
                working_before=current,
            )
            try:
                yield guard
            except BaseException:
                if guard.recorded_sha256 is not None and not guard.committed:
                    try:
                        current_after_error = self._read_working_bytes(session_id)
                        if sha256_bytes(current_after_error) == guard.recorded_sha256:
                            atomic_write_bytes(self.working_path(session_id), current)
                    finally:
                        self._require_safe_root()
                        self._write_store_json(
                            self.metadata_path(session_id),
                            metadata,
                            trailing_newline=True,
                        )
                raise

    def record_edit(self, session_id: str, working_sha256: str, backup: Path) -> None:
        """Record an already-written edit only while lifecycle state is mutable."""

        with self.guard_working_mutation(
            session_id,
            expected_sha256=working_sha256,
        ) as guard:
            guard.record_edit(
                working_sha256=working_sha256,
                backup=backup,
            )

    def mutate_working(
        self,
        session_id: str,
        *,
        expected_sha256: str,
        replacement: bytes,
        backup_path: Path | None = None,
        after_write: Callable[[LiveWorkingMutation], None] | None = None,
    ) -> LiveWorkingMutation:
        """Atomically bind one working-file write and metadata edit to lifecycle state."""

        if len(replacement) > self.max_document_bytes:
            raise SessionError(
                "Replacement working XML exceeds the configured document-size limit",
                code="document_too_large",
            )
        replacement_document = DipTraceDocument.from_bytes(
            self.working_path(session_id),
            replacement,
        )
        with self.guard_working_mutation(
            session_id,
            expected_sha256=expected_sha256,
        ) as guard:
            if replacement_document.source_type != guard.metadata_before.get(
                "source_type"
            ):
                raise SessionError("Working XML type differs from the original session")
            current_sha256 = sha256_bytes(guard.working_before)
            replacement_sha256 = sha256_bytes(replacement)
            backup = backup_path
            if backup is None:
                backup = self._store_working_backup_unlocked(
                    session_id,
                    guard.working_before,
                )

            working_path = self.working_path(session_id)
            atomic_write_bytes(working_path, replacement)
            guard.recorded_sha256 = replacement_sha256
            written = self._read_working_bytes(session_id)
            if sha256_bytes(written) != replacement_sha256:
                raise SessionError(
                    "Live working XML does not match the guarded replacement",
                    code="sha256_mismatch",
                )
            guard.record_edit(
                working_sha256=replacement_sha256,
                backup=backup,
            )
            mutation = LiveWorkingMutation(
                session_id=session_id,
                before_sha256=current_sha256,
                after_sha256=replacement_sha256,
                backup=backup,
            )
            if after_write is not None:
                after_write(mutation)
            guard.commit()
            return mutation

    def _live_write_impact(
        self,
        metadata: dict[str, Any],
        working: bytes,
    ) -> WriteImpact:
        session_id = str(metadata["session_id"])
        original = self._read_original_bytes(session_id)
        recorded_original_sha256 = metadata.get("original_sha256")
        if recorded_original_sha256 != sha256_bytes(original):
            raise SessionError(
                "Session metadata does not match the captured original XML",
                code="session_state_invalid",
            )
        original_document = DipTraceDocument.from_bytes(
            self.original_path(session_id),
            original,
        )
        working_document = DipTraceDocument.from_bytes(
            self.working_path(session_id),
            working,
        )
        source_type = metadata.get("source_type")
        if (
            original_document.source_type != source_type
            or working_document.source_type != source_type
        ):
            raise SessionError("Working XML type differs from the original session")
        return write_impact(original_document, working_document)

    def live_preview_summary(
        self,
        session_id: str,
        *,
        changed_id_limit: int = LIVE_PREVIEW_CHANGED_ID_LIMIT,
    ) -> dict[str, Any]:
        if changed_id_limit <= 0:
            raise ValueError("changed_id_limit must be greater than zero")
        metadata = self.read_metadata(session_id)
        working = self._read_working_bytes(session_id)
        working_sha256 = sha256_bytes(working)
        impact = self._live_write_impact(metadata, working)
        changed_ids = list(impact.changed_ids[:changed_id_limit])
        changed_ids_complete = len(changed_ids) == len(impact.changed_ids)
        return {
            "available": True,
            "complete": changed_ids_complete,
            "working_sha256": working_sha256,
            "modified": working_sha256 != metadata.get("original_sha256"),
            "normalized_object_count": impact.normalized_object_count,
            "structural_element_count": impact.structural_element_count,
            "object_count": impact.object_count,
            "changed_ids": changed_ids,
            "changed_id_count": len(impact.changed_ids),
            "changed_ids_complete": changed_ids_complete,
            "limitations": (
                []
                if changed_ids_complete
                else [
                    f"changed_ids contains only the first {changed_id_limit} stable ids"
                ]
            ),
        }

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
        metadata = self._active_metadata_unlocked()
        if metadata is None:
            raise SessionError("There is no active DipTrace session")
        if action == "apply":
            _require_apply_supported(metadata)
        session_id = str(metadata["session_id"])
        pending = self._pending_finish_request_unlocked(metadata)
        if pending is not None:
            if pending.get("action") == action and (
                action == "cancel"
                or pending.get("expected_sha256") == expected_sha256
            ):
                return {"session_id": session_id, **pending}
            raise SessionError(
                "A different live-session finish request is already pending",
                code="session_finish_pending",
            )
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
            require_write_impact(
                self._live_write_impact(metadata, working),
                operation="live_session_apply",
            )
            self._read_bound_exchange(metadata)
        request = {
            "request_id": str(uuid.uuid4()),
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
            finish_request_id=request["request_id"],
        )
        self._require_safe_root()
        try:
            self._write_store_json(
                self.control_path(session_id),
                request,
                trailing_newline=True,
            )
        except Exception:
            self.update_metadata(
                session_id,
                finish_requested=None,
                finish_requested_at=None,
                finish_request_id=None,
            )
            raise
        return {"session_id": session_id, **request}

    def _pending_finish_request_unlocked(
        self,
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None:
        session_id = str(metadata["session_id"])
        control_path = self.control_path(session_id)
        metadata_action = metadata.get("finish_requested")
        metadata_request_id = metadata.get("finish_request_id")
        has_control = control_path.exists() or is_link_like(control_path)
        has_metadata = metadata_action is not None or metadata_request_id is not None
        if not has_control and not has_metadata:
            return None
        if not has_control or not has_metadata:
            raise SessionError(
                "Live-session finish request state is incomplete",
                code="session_state_invalid",
            )
        request = _read_json(control_path)
        if (
            request.get("action") != metadata_action
            or request.get("request_id") != metadata_request_id
            or request.get("action") not in {"apply", "cancel"}
            or not isinstance(request.get("expected_sha256"), str)
        ):
            raise SessionError(
                "Live-session finish request state is inconsistent",
                code="session_state_invalid",
            )
        return request

    def wait_for_finish_outcome(
        self,
        request: dict[str, Any],
        *,
        timeout_seconds: float = DEFAULT_FINISH_ACK_WAIT_SECONDS,
    ) -> dict[str, Any]:
        """Wait only for local bridge finalization; DipTrace provides no host ACK."""

        if timeout_seconds < 0:
            raise ValueError("timeout_seconds cannot be negative")
        session_id = str(request["session_id"])
        deadline = time.monotonic() + timeout_seconds
        metadata = self.read_metadata(session_id)
        while metadata.get("status") == "active" and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(_FINISH_POLL_SECONDS, remaining))
            metadata = self.read_metadata(session_id)

        local_status = str(metadata.get("status", "unknown"))
        outcome: FinishOutcome
        request_matches = (
            metadata.get("finished_request_id") == request.get("request_id")
            and metadata.get("finished_action") == request.get("action")
        )
        if local_status == "applied" and request_matches:
            outcome = "applied"
        elif local_status == "cancelled" and request_matches:
            outcome = "cancelled"
        else:
            outcome = "not_acknowledged"
        if outcome == "applied":
            message = (
                "The bridge finalized the local exchange XML; DipTrace host import "
                "acknowledgement is unavailable."
            )
        elif outcome == "cancelled":
            message = (
                "The bridge finalized cancellation locally; no exchange XML was replaced."
            )
        elif local_status == "abandoned":
            message = (
                "The session was abandoned terminally without replacing the exchange XML."
            )
        elif local_status in {"applied", "cancelled"}:
            message = (
                "The session was finalized by a different finish request; this request "
                "will not complete."
            )
        else:
            message = (
                "The bridge did not finalize within the bounded wait. The request may "
                "still be finalized later; inspect session status."
            )
        return {
            "session_id": session_id,
            "requested_action": request.get("action"),
            "requested_at": request.get("requested_at"),
            "expected_sha256": request.get("expected_sha256"),
            "outcome": outcome,
            "local_bridge_status": local_status,
            "written": outcome == "applied",
            "diptrace_host_acknowledged": False,
            "acknowledgement_scope": "local_bridge_exchange_only",
            "message": message,
        }

    def read_finish_request(self, session_id: str) -> dict[str, Any] | None:
        path = self.control_path(session_id)
        if not path.exists():
            return None
        raw = _stable_regular_file_bytes(
            path,
            64 * 1024,
            purpose="live-session finish request",
        )
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            request = {}
            request["_parse_error"] = str(exc)[:240]
        if not isinstance(request, dict):
            request = {"_parse_error": "finish request is not a JSON object"}
        request["_control_sha256"] = sha256_bytes(raw)
        return request

    def clear_finish_request(self, session_id: str) -> None:
        self.control_path(session_id).unlink(missing_ok=True)

    def reject_finish_request(
        self,
        session_id: str,
        message: str,
        *,
        expected_request_id: str,
    ) -> None:
        """Clear both halves of a rejected request so later edits are not frozen."""

        with _exclusive_session_lock(self.lock_file):
            metadata = self.read_metadata(session_id)
            if metadata.get("status") != "active":
                raise SessionError(f"Session is not active: {session_id}")
            pending = self._pending_finish_request_unlocked(metadata)
            if (
                pending is None
                or pending.get("request_id") != expected_request_id
            ):
                raise SessionError(
                    "Refusing to clear a different finish request",
                    code="session_finish_pending",
                )
            self.clear_finish_request(session_id)
            self.update_metadata(
                session_id,
                finish_requested=None,
                finish_requested_at=None,
                finish_request_id=None,
                last_error=message[:500],
                updated_at=self._clock_timestamp(),
            )

    def reject_malformed_finish_request(
        self,
        session_id: str,
        message: str,
        *,
        expected_control_sha256: str,
    ) -> None:
        """CAS-clear only the exact malformed control payload the bridge inspected."""

        with _exclusive_session_lock(self.lock_file):
            metadata = self.read_metadata(session_id)
            if metadata.get("status") != "active":
                raise SessionError(f"Session is not active: {session_id}")
            control_path = self.control_path(session_id)
            raw = _stable_regular_file_bytes(
                control_path,
                64 * 1024,
                purpose="malformed live-session finish request",
            )
            if sha256_bytes(raw) != expected_control_sha256:
                raise SessionError(
                    "Refusing to clear a changed finish request",
                    code="session_finish_pending",
                )
            self.clear_finish_request(session_id)
            self.update_metadata(
                session_id,
                finish_requested=None,
                finish_requested_at=None,
                finish_request_id=None,
                last_error=message[:500],
                updated_at=self._clock_timestamp(),
            )

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
        pending = self._pending_finish_request_unlocked(metadata)
        if pending is not None and (
            pending.get("action") != action
            or (
                action == "apply"
                and pending.get("expected_sha256") != expected_sha256
            )
        ):
            raise SessionError(
                "Finalization does not match the pending finish request",
                code="session_finish_pending",
            )
        if action == "apply":
            _require_apply_supported(metadata)

        working = self._read_working_bytes(session_id)
        current_sha256 = sha256_bytes(working)

        exchange_path: Path | None = None
        exchange_before = b""
        if action == "apply":
            if expected_sha256 is None:
                raise SessionError(
                    "expected_sha256 of the finish request is required when action=apply",
                    code="confirmation_required",
                )
            if current_sha256 != expected_sha256:
                # A valid oversized replacement must still trip the independent
                # bridge-side object cap even when it was introduced after the
                # finish request. Malformed tampering retains the stronger,
                # already-established hash-mismatch contract.
                try:
                    changed_impact = self._live_write_impact(metadata, working)
                except (DocumentError, SessionError):
                    changed_impact = None
                if changed_impact is not None:
                    require_write_impact(
                        changed_impact,
                        operation="live_session_apply",
                    )
                raise SessionError(
                    "Working XML changed after the finish request",
                    code="sha256_mismatch",
                    details={
                        "expected_sha256": expected_sha256,
                        "current_sha256": current_sha256,
                    },
                )
            # Recompute the impact independently at the bridge checkpoint. This
            # catches cumulative live edits even if individual MCP writes stayed
            # below the per-write bound.
            require_write_impact(
                self._live_write_impact(metadata, working),
                operation="live_session_apply",
            )
            exchange_path, exchange_before = self._read_bound_exchange(metadata)
        elif self.allowed_roots is not None:
            # A prior failed apply can never be reported later as a cancellation.
            self._read_bound_exchange(metadata)
        status = "applied" if action == "apply" else "cancelled"
        try:
            if action == "apply":
                assert exchange_path is not None
                atomic_write_bytes(exchange_path, working)
                _post_write_path, applied = self._read_exchange_path(exchange_path)
                applied_sha256 = sha256_bytes(applied)
                if applied_sha256 != current_sha256:
                    raise SessionError(
                        "Exchange-file SHA-256 does not match the applied working XML",
                        code="sha256_mismatch",
                        details={
                            "expected_sha256": current_sha256,
                            "current_sha256": applied_sha256,
                        },
                    )
            metadata = self.update_metadata(
                session_id,
                status=status,
                updated_at=utc_now(),
                finished_at=utc_now(),
                working_sha256=current_sha256,
                finished_action=action,
                finished_request_id=(
                    pending.get("request_id") if pending is not None else None
                ),
            )
        except Exception:
            latest = self.read_metadata(session_id)
            state_persisted = (
                latest.get("status") == status
                and latest.get("working_sha256") == current_sha256
                and latest.get("finished_action") == action
                and latest.get("finished_request_id")
                == (pending.get("request_id") if pending is not None else None)
            )
            if state_persisted:
                metadata = latest
            elif action == "apply":
                assert exchange_path is not None
                current_exchange_sha256: str | None = None
                try:
                    _current_path, exchange_after = self._read_exchange_path(
                        exchange_path
                    )
                    current_exchange_sha256 = sha256_bytes(exchange_after)
                    if exchange_after == working:
                        atomic_write_bytes(exchange_path, exchange_before)
                        _restored_path, restored = self._read_exchange_path(
                            exchange_path
                        )
                        current_exchange_sha256 = sha256_bytes(restored)
                        if restored != exchange_before:
                            raise OSError("exchange compensation verification failed")
                    elif exchange_after != exchange_before:
                        raise OSError("unexpected exchange bytes block compensation")
                except Exception as compensation_exc:
                    raise SessionError(
                        "Apply failed and exchange-file state is uncertain",
                        code="session_apply_state_uncertain",
                        details={
                            "expected_working_sha256": current_sha256,
                            "original_exchange_sha256": sha256_bytes(exchange_before),
                            "current_exchange_sha256": current_exchange_sha256,
                        },
                    ) from compensation_exc
                raise
            else:
                raise
        self.clear_finish_request(session_id)
        self._clear_active_reference_unlocked(session_id)
        return metadata
