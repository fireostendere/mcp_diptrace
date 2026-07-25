from __future__ import annotations

import json
import os
import re
import threading
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import EditError
from .record_ids import is_link_like
from .retention import (
    Clock,
    RetentionCandidate,
    RetentionPolicy,
    RetentionReport,
    prune_terminal_records,
    system_clock,
)
from .xml_document import atomic_write_bytes, sha256_bytes

_TARGET_KEY = re.compile(r"^[0-9a-f]{64}$")
_BACKUP_NAME = re.compile(
    r"^backup\."
    r"(?P<stamp>[0-9]{8}T[0-9]{6}\.[0-9]{6}Z)\."
    r"(?P<sha256>[0-9a-f]{64})\."
    r"(?P<nonce>[0-9a-f]{32})\.bak$"
)
_TARGET_METADATA = "target.json"
_SCHEMA_VERSION = 1


def canonical_target_path(path: Path) -> str:
    """Return the stable filesystem identity used to isolate backup histories."""

    # ``strict=False`` keeps the same key usable after the design is deleted.
    # Do not lowercase paths on POSIX/WSL: distinct case-sensitive files must
    # not share a history merely because their spelling differs.
    return os.path.normcase(os.fspath(path.resolve(strict=False)))


def backup_target_key(canonical_path: str) -> str:
    return sha256_bytes(canonical_path.encode("utf-8"))


class BackupStore:
    """State-directory backup histories isolated by canonical target path."""

    def __init__(
        self,
        state_dir: Path,
        *,
        retention: RetentionPolicy | None = None,
        clock: Clock = system_clock,
    ) -> None:
        self.state_dir = state_dir
        self.root = state_dir / "offline_backups"
        # Read-only server startup remains usable for discovery. The first
        # offline write fails explicitly in _prepare_target_dir instead.
        with suppress(OSError):
            self.root.mkdir(parents=True, exist_ok=True)
        self.retention = retention or RetentionPolicy()
        self.clock = clock
        self._lock = threading.RLock()
        self.last_retention_reports = self._prune_all()

    def write_with_backup(self, path: Path, data: bytes) -> Path:
        """Back up an existing target, replace it atomically, then prune its history."""

        original = path.read_bytes()
        with self._lock:
            key, canonical_path = self._target_binding(path)
            target_dir = self.root / key
            self._prepare_target_dir(target_dir, key, canonical_path)
            created_at = self._next_backup_timestamp(target_dir, key, canonical_path)
            stamp = created_at.strftime("%Y%m%dT%H%M%S.%fZ")
            digest = sha256_bytes(original)
            backup = target_dir / f"backup.{stamp}.{digest}.{uuid.uuid4().hex}.bak"
            atomic_write_bytes(backup, original)
            # If replacement fails, the new recovery point remains untouched.
            atomic_write_bytes(path, data)
            self._prune_target(target_dir, key, canonical_path)
        return backup

    def _next_backup_timestamp(
        self,
        target_dir: Path,
        key: str,
        canonical_path: str,
    ) -> datetime:
        requested = _aware_utc(self.clock())
        existing = self._validated_candidates(target_dir, key, canonical_path)
        latest = max(
            (candidate.timestamp for candidate in existing),
            default=None,
        )
        if latest is not None and requested <= latest:
            return latest + timedelta(microseconds=1)
        return requested

    def backups_for(self, path: Path) -> tuple[Path, ...]:
        """Return integrity-validated backups for one target, newest first."""

        with self._lock:
            key, canonical_path = self._target_binding(path)
            target_dir = self.root / key
            candidates = self._validated_candidates(target_dir, key, canonical_path)
        candidates.sort(
            key=lambda candidate: (candidate.timestamp, candidate.identifier),
            reverse=True,
        )
        return tuple(candidate.path for candidate in candidates)

    def _target_binding(self, path: Path) -> tuple[str, str]:
        """Reuse a proven existing identity without case-folding POSIX paths."""

        canonical_path = canonical_target_path(path)
        key = backup_target_key(canonical_path)
        direct = self.root / key
        # A corrupt or redirected direct binding must remain visible to
        # _prepare_target_dir rather than being bypassed via another history.
        if direct.exists() or is_link_like(direct) or not self._safe_root():
            return key, canonical_path
        try:
            path_exists = path.exists()
            directories = tuple(self.root.iterdir())
        except OSError:
            return key, canonical_path
        if not path_exists:
            return key, canonical_path
        for target_dir in directories:
            metadata = self._validated_target_metadata(target_dir, target_dir.name)
            if metadata is None:
                continue
            recorded_path = metadata["canonical_target_path"]
            try:
                if os.path.samefile(path, recorded_path):
                    return target_dir.name, recorded_path
            except OSError:
                continue
        return key, canonical_path

    def _prepare_target_dir(
        self,
        target_dir: Path,
        key: str,
        canonical_path: str,
    ) -> None:
        if not self._safe_root():
            raise EditError(
                "Offline backup root is not a safe state directory",
                code="backup_state_invalid",
                details={"backup_root": str(self.root)},
            )
        if is_link_like(target_dir):
            raise EditError(
                "Offline backup directory is redirected",
                code="backup_state_invalid",
                details={"backup_directory": str(target_dir)},
            )
        if target_dir.exists():
            if self._validated_target_metadata(target_dir, key, canonical_path) is None:
                raise EditError(
                    "Offline backup metadata is corrupt or does not match the target",
                    code="backup_state_invalid",
                    details={"backup_directory": str(target_dir)},
                )
            return
        target_dir.mkdir()
        payload = {
            "schema_version": _SCHEMA_VERSION,
            "target_key": key,
            "canonical_target_path": canonical_path,
        }
        atomic_write_bytes(
            target_dir / _TARGET_METADATA,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            + b"\n",
        )

    def _prune_all(self) -> dict[str, RetentionReport]:
        reports: dict[str, RetentionReport] = {}
        if not self._safe_root():
            return reports
        try:
            directories = tuple(self.root.iterdir())
        except OSError:
            return reports
        for target_dir in directories:
            key = target_dir.name
            metadata = self._validated_target_metadata(target_dir, key)
            if metadata is None:
                continue
            canonical_path = metadata["canonical_target_path"]
            reports[key] = self._prune_target(target_dir, key, canonical_path)
        return reports

    def _prune_target(
        self,
        target_dir: Path,
        key: str,
        canonical_path: str,
    ) -> RetentionReport:
        candidates = self._validated_candidates(target_dir, key, canonical_path)
        # The limit is per target history. Age expiry applies even to the sole
        # or newest backup; retaining it unconditionally would make max_age
        # advisory rather than enforced.
        report = prune_terminal_records(
            state_root=self.state_dir,
            store_root=target_dir,
            candidates=candidates,
            policy=self.retention,
            clock=self.clock,
        )
        self._remove_empty_history(target_dir, key, canonical_path)
        return report

    def _remove_empty_history(
        self,
        target_dir: Path,
        key: str,
        canonical_path: str,
    ) -> None:
        """Remove a validated history directory after its last backup expires."""

        if self._validated_target_metadata(target_dir, key, canonical_path) is None:
            return
        metadata_path = target_dir / _TARGET_METADATA
        metadata_bytes: bytes | None = None
        try:
            entries = tuple(target_dir.iterdir())
            if (
                entries != (metadata_path,)
                or is_link_like(metadata_path)
                or not metadata_path.is_file()
            ):
                return
            metadata_bytes = metadata_path.read_bytes()
            metadata_path.unlink()
            target_dir.rmdir()
        except OSError:
            # Retention is fail-safe. A concurrent addition or disappearance
            # is not an error and must not trigger broader cleanup. Restore the
            # binding if the directory remained and is still safely confined.
            try:
                if (
                    metadata_bytes is not None
                    and self._safe_root()
                    and target_dir.parent == self.root
                    and not is_link_like(target_dir)
                    and target_dir.is_dir()
                    and not metadata_path.exists()
                    and not is_link_like(metadata_path)
                ):
                    target_dir.resolve(strict=True).relative_to(
                        self.root.resolve(strict=True)
                    )
                    atomic_write_bytes(metadata_path, metadata_bytes)
            except (OSError, ValueError):
                pass
            return

    def _validated_candidates(
        self,
        target_dir: Path,
        key: str,
        canonical_path: str,
    ) -> list[RetentionCandidate]:
        if self._validated_target_metadata(target_dir, key, canonical_path) is None:
            return []
        candidates: list[RetentionCandidate] = []
        try:
            paths = tuple(target_dir.glob("backup.*.bak"))
        except OSError:
            return candidates
        for path in paths:
            match = _BACKUP_NAME.fullmatch(path.name)
            if match is None or is_link_like(path) or not path.is_file():
                continue
            try:
                path.resolve(strict=True).relative_to(target_dir.resolve(strict=True))
                timestamp = datetime.strptime(
                    match.group("stamp"),
                    "%Y%m%dT%H%M%S.%fZ",
                ).replace(tzinfo=timezone.utc)
                if sha256_bytes(path.read_bytes()) != match.group("sha256"):
                    continue
            except (OSError, ValueError):
                continue
            candidates.append(
                RetentionCandidate(
                    identifier=path.name,
                    path=path,
                    timestamp=timestamp,
                )
            )
        return candidates

    def _validated_target_metadata(
        self,
        target_dir: Path,
        key: str,
        canonical_path: str | None = None,
    ) -> dict[str, str] | None:
        if _TARGET_KEY.fullmatch(key) is None:
            return None
        metadata_path = target_dir / _TARGET_METADATA
        try:
            if (
                target_dir.parent != self.root
                or is_link_like(target_dir)
                or not target_dir.is_dir()
                or is_link_like(metadata_path)
                or not metadata_path.is_file()
            ):
                return None
            target_dir.resolve(strict=True).relative_to(self.root.resolve(strict=True))
            payload: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
            return None
        recorded_key = payload.get("target_key")
        recorded_path = payload.get("canonical_target_path")
        if (
            recorded_key != key
            or not isinstance(recorded_path, str)
            or not Path(recorded_path).is_absolute()
            or backup_target_key(recorded_path) != key
            or (canonical_path is not None and recorded_path != canonical_path)
        ):
            return None
        return {"canonical_target_path": recorded_path}

    def _safe_root(self) -> bool:
        try:
            if is_link_like(self.root) or not self.root.is_dir():
                return False
            self.root.resolve(strict=True).relative_to(self.state_dir.resolve(strict=True))
        except (OSError, ValueError):
            return False
        return True


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
