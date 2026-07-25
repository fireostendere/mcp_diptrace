from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal

RecordIdKind = Literal[
    "transaction",
    "job",
    "plan",
    "export",
    "session",
    "report",
    "finding",
]

UUID4_PATTERN = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
TRANSACTION_ID_PATTERN = rf"tx_{UUID4_PATTERN}"
_RECORD_ID_PATTERNS: dict[RecordIdKind, re.Pattern[str]] = {
    "transaction": re.compile(TRANSACTION_ID_PATTERN),
    "job": re.compile(r"job_[0-9a-f]{32}"),
    "plan": re.compile(r"plan_[0-9a-f]{32}"),
    "export": re.compile(r"export_[0-9a-f]{32}"),
    "session": re.compile(UUID4_PATTERN),
    "report": re.compile(r"report_[0-9a-f]{16}"),
    "finding": re.compile(r"finding_[0-9a-f]{16}"),
}


class InvalidRecordId(ValueError):
    """Internal signal translated by each store into its public error contract."""

    def __init__(self, kind: RecordIdKind) -> None:
        self.kind = kind
        super().__init__(f"Invalid {kind} identifier")


class InvalidRecordPath(ValueError):
    """A persisted record path is redirected or leaves its owning store."""


def prepare_safe_store_root(state_root: Path, store_root: Path) -> Path:
    """Create and validate one direct, non-redirected state-store directory.

    The state directory may be absent on first use.  It is validated before
    the child store is created so an existing state-root symlink or junction
    cannot redirect that creation.
    """

    try:
        state_root.mkdir(parents=True, exist_ok=True)
        if is_link_like(state_root) or not state_root.is_dir():
            raise InvalidRecordPath(f"State root is not a safe directory: {state_root}")
        if store_root.parent != state_root:
            raise InvalidRecordPath(
                f"Store root is not a direct child of the state root: {store_root}"
            )
        if is_link_like(store_root):
            raise InvalidRecordPath(f"Store root is redirected: {store_root}")
        store_root.mkdir(exist_ok=True)
    except InvalidRecordPath:
        raise
    except OSError as exc:
        raise InvalidRecordPath(f"Store root cannot be prepared safely: {store_root}") from exc
    return require_safe_store_root(state_root, store_root)


def require_safe_store_root(state_root: Path, store_root: Path) -> Path:
    """Return a direct state-store root only when it is not redirected."""

    try:
        if (
            store_root.parent != state_root
            or is_link_like(state_root)
            or not state_root.is_dir()
            or is_link_like(store_root)
            or not store_root.is_dir()
        ):
            raise InvalidRecordPath(f"Store root is not a safe directory: {store_root}")
        resolved_state = state_root.resolve(strict=True)
        resolved_store = store_root.resolve(strict=True)
        resolved_store.relative_to(resolved_state)
        if resolved_store.parent != resolved_state:
            raise InvalidRecordPath(
                f"Store root is not a direct child of the state root: {store_root}"
            )
    except InvalidRecordPath:
        raise
    except (OSError, ValueError) as exc:
        raise InvalidRecordPath(f"Store root is not safely confined: {store_root}") from exc
    return store_root


def require_record_id(value: str, kind: RecordIdKind) -> str:
    """Return an exact generated record id or reject it before path construction."""

    if _RECORD_ID_PATTERNS[kind].fullmatch(value) is None:
        raise InvalidRecordId(kind)
    return value


def is_link_like(path: Path) -> bool:
    """Return true for symbolic links and Windows reparse-point redirects."""

    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
        except FileNotFoundError:
            attributes = 0
        except OSError:
            return True
        if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return True
    junction_check: Any = getattr(path, "is_junction", None)
    if callable(junction_check):
        try:
            return bool(junction_check())
        except OSError:
            return True
    return False


def require_confined_file(root: Path, path: Path) -> Path:
    """Return one regular file confined below a non-redirected store root."""

    try:
        if is_link_like(root) or not root.is_dir():
            raise InvalidRecordPath(f"Record root is not a safe directory: {root}")
        if is_link_like(path):
            raise InvalidRecordPath(f"Record file is redirected: {path}")
        if not path.exists():
            raise FileNotFoundError(path)
        if not path.is_file():
            raise InvalidRecordPath(f"Record path is not a regular file: {path}")
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
        current = path.parent
        while current != root:
            if is_link_like(current):
                raise InvalidRecordPath(f"Record directory is redirected: {current}")
            parent = current.parent
            if parent == current:
                raise InvalidRecordPath(f"Record path is outside its store: {path}")
            current = parent
    except FileNotFoundError:
        raise
    except InvalidRecordPath:
        raise
    except (OSError, ValueError) as exc:
        raise InvalidRecordPath(f"Record path is outside its store: {path}") from exc
    return path


def require_confined_record_file(
    root: Path,
    record_id: str,
    *,
    kind: RecordIdKind,
    record_filename: str | None = None,
) -> Path:
    """Resolve the exact direct-file or directory-backed record for an id."""

    validated = require_record_id(record_id, kind)
    if record_filename is None:
        path = root / f"{validated}.json"
    else:
        directory = root / validated
        if is_link_like(directory):
            raise InvalidRecordPath(f"Record directory is redirected: {directory}")
        path = directory / record_filename
    return require_confined_file(root, path)


def require_confined_record_directory(
    root: Path,
    record_id: str,
    *,
    kind: RecordIdKind,
) -> Path:
    """Return the exact non-redirected immediate-child directory for an id."""

    validated = require_record_id(record_id, kind)
    directory = root / validated
    try:
        if (
            is_link_like(root)
            or not root.is_dir()
            or is_link_like(directory)
            or not directory.is_dir()
        ):
            raise InvalidRecordPath(f"Record directory is unsafe: {directory}")
        directory.resolve(strict=True).relative_to(root.resolve(strict=True))
    except InvalidRecordPath:
        raise
    except (OSError, ValueError) as exc:
        raise InvalidRecordPath(f"Record directory is outside its store: {directory}") from exc
    return directory


def require_confined_record_artifact(
    root: Path,
    record_id: str,
    artifact_name: str,
    *,
    kind: RecordIdKind,
) -> Path:
    """Return one exact regular artifact below a validated record directory."""

    if not artifact_name or Path(artifact_name).name != artifact_name:
        raise InvalidRecordPath("Record artifact name is invalid")
    directory = require_confined_record_directory(root, record_id, kind=kind)
    return require_confined_file(root, directory / artifact_name)


def iter_valid_record_files(
    root: Path,
    paths: Iterable[Path],
    *,
    kind: RecordIdKind,
    record_filename: str | None = None,
) -> Iterator[tuple[str, Path]]:
    """Yield confined, non-symlinked state records with exact generated ids.

    Direct-file stores, such as review reports, derive the id from ``path.stem``.
    Directory-backed stores derive it from the immediate parent directory and
    additionally require the expected record filename.
    """

    if is_link_like(root) or not root.is_dir():
        return
    resolved_root = root.resolve()
    for path in paths:
        if record_filename is None:
            if path.parent != root:
                continue
            record_id = path.stem
        else:
            if (
                path.name != record_filename
                or path.parent.parent != root
                or is_link_like(path.parent)
            ):
                continue
            record_id = path.parent.name
        try:
            require_record_id(record_id, kind)
            if is_link_like(path) or not path.is_file():
                continue
            path.resolve(strict=True).relative_to(resolved_root)
        except (InvalidRecordId, OSError, ValueError):
            continue
        yield record_id, path
