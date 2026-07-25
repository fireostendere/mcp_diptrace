from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .record_ids import is_link_like

DEFAULT_RETENTION_MAX_RECORDS = 500
DEFAULT_RETENTION_MAX_AGE_DAYS = 180

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    max_records: int = DEFAULT_RETENTION_MAX_RECORDS
    max_age_days: int = DEFAULT_RETENTION_MAX_AGE_DAYS

    def __post_init__(self) -> None:
        if self.max_records <= 0:
            raise ValueError("max_records must be greater than zero")
        if self.max_age_days <= 0:
            raise ValueError("max_age_days must be greater than zero")


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    identifier: str
    path: Path
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class RetentionReport:
    removed: tuple[Path, ...] = ()


def parse_retention_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def prune_terminal_records(
    *,
    state_root: Path,
    store_root: Path,
    candidates: Iterable[RetentionCandidate],
    policy: RetentionPolicy,
    clock: Clock = system_clock,
    protected_paths: Iterable[Path] = (),
) -> RetentionReport:
    """Delete only prevalidated terminal candidates confined to one state store."""

    if not _safe_store_root(state_root, store_root):
        return RetentionReport()
    safe_candidates = [
        candidate
        for candidate in candidates
        if _safe_candidate_path(state_root, store_root, candidate.path)
    ]
    safe_candidates.sort(
        key=lambda candidate: (candidate.timestamp, candidate.identifier),
        reverse=True,
    )
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(days=policy.max_age_days)
    doomed = {
        candidate.path
        for candidate in safe_candidates
        if candidate.timestamp <= cutoff
    }
    doomed.update(candidate.path for candidate in safe_candidates[policy.max_records :])
    protected = {_resolved_if_possible(path) for path in protected_paths}

    removed: list[Path] = []
    for candidate in reversed(safe_candidates):
        if candidate.path not in doomed:
            continue
        resolved_candidate = _resolved_if_possible(candidate.path)
        if resolved_candidate in protected:
            continue
        if not _safe_candidate_path(state_root, store_root, candidate.path):
            continue
        try:
            if candidate.path.is_dir():
                shutil.rmtree(candidate.path)
            else:
                candidate.path.unlink()
        except OSError:
            continue
        removed.append(candidate.path)
    return RetentionReport(removed=tuple(removed))


def _safe_store_root(state_root: Path, store_root: Path) -> bool:
    try:
        if is_link_like(store_root) or not store_root.is_dir():
            return False
        store_root.resolve(strict=True).relative_to(state_root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def _safe_candidate_path(state_root: Path, store_root: Path, candidate: Path) -> bool:
    try:
        if candidate.parent != store_root or not candidate.exists():
            return False
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(state_root.resolve(strict=True))
        resolved.relative_to(store_root.resolve(strict=True))
        if _tree_contains_link_like(candidate):
            return False
    except (OSError, ValueError):
        return False
    return True


def _tree_contains_link_like(path: Path) -> bool:
    if is_link_like(path):
        return True
    if not path.is_dir():
        return False
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    child = Path(entry.path)
                    if entry.is_symlink() or is_link_like(child):
                        return True
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(child)
        except OSError:
            return True
    return False


def _resolved_if_possible(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except (OSError, ValueError):
        return path
