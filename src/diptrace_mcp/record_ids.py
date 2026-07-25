from __future__ import annotations

import re
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

_UUID4 = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_RECORD_ID_PATTERNS: dict[RecordIdKind, re.Pattern[str]] = {
    "transaction": re.compile(rf"tx_{_UUID4}"),
    "job": re.compile(r"job_[0-9a-f]{32}"),
    "plan": re.compile(r"plan_[0-9a-f]{32}"),
    "export": re.compile(r"export_[0-9a-f]{32}"),
    "session": re.compile(_UUID4),
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
