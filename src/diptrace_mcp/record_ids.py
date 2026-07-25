from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Literal

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


def require_record_id(value: str, kind: RecordIdKind) -> str:
    """Return an exact generated record id or reject it before path construction."""

    if _RECORD_ID_PATTERNS[kind].fullmatch(value) is None:
        raise InvalidRecordId(kind)
    return value


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
                or path.parent.is_symlink()
            ):
                continue
            record_id = path.parent.name
        try:
            require_record_id(record_id, kind)
            if path.is_symlink() or not path.is_file():
                continue
            path.resolve(strict=True).relative_to(resolved_root)
        except (InvalidRecordId, OSError, ValueError):
            continue
        yield record_id, path
