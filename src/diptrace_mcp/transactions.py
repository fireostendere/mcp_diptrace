from __future__ import annotations

import builtins
import json
import re
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Literal

from .domain import DocumentInfo, RiskClass, TransactionRecord, TransactionRisk
from .errors import TransactionConflictError, TransactionNotFoundError
from .xml_document import atomic_write_bytes, sha256_bytes, utc_now

_TXID = re.compile(
    r"^tx_[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TRANSITIONS: dict[str, frozenset[str]] = {
    "planned": frozenset({"staged", "rolled_back", "failed"}),
    "staged": frozenset({"staged", "validated", "rolled_back", "failed"}),
    "validated": frozenset({"staged", "validated", "committed", "rolled_back", "failed"}),
    "committed": frozenset({"rolled_back"}),
    "rolled_back": frozenset(),
    "failed": frozenset({"rolled_back"}),
}


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(path, data)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TransactionNotFoundError(
            f"Transaction does not exist: {path.parent.name}",
            txid=path.parent.name,
        ) from exc
    if not isinstance(data, dict):
        raise TransactionConflictError(
            f"Transaction file must contain a JSON object: {path}",
            txid=path.parent.name,
        )
    return data


@dataclass(slots=True)
class TransactionStore:
    state_dir: Path
    transactions_dir: Path = dataclass_field(init=False)
    _lock: threading.RLock = dataclass_field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.transactions_dir = self.state_dir / "transactions"
        self.transactions_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def tx_dir(self, txid: str) -> Path:
        if not _TXID.fullmatch(txid):
            raise TransactionNotFoundError(f"Invalid transaction id: {txid}", txid=txid)
        return self.transactions_dir / txid

    def record_path(self, txid: str) -> Path:
        return self.tx_dir(txid) / "transaction.json"

    def snapshot_path(self, txid: str) -> Path:
        return self.tx_dir(txid) / "snapshot.xml"

    def preview_svg_path(self, txid: str) -> Path:
        return self.tx_dir(txid) / "preview.svg"

    def preview_json_path(self, txid: str) -> Path:
        return self.tx_dir(txid) / "preview.json"

    def diff_path(self, txid: str) -> Path:
        return self.tx_dir(txid) / "diff.txt"

    def backup_path(self, txid: str) -> Path:
        return self.tx_dir(txid) / "backup.xml"

    def create(
        self,
        document: DocumentInfo,
        target_path: Path,
        *,
        source_sha256: str,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> TransactionRecord:
        txid = f"tx_{uuid.uuid4()}"
        with self._lock:
            self.tx_dir(txid).mkdir(parents=True, exist_ok=False)
            record = TransactionRecord(
                txid=txid,
                document_id=document.document_id,
                status="planned",
                source_sha256=source_sha256,
                target_path=str(target_path),
                created_at=utc_now(),
                updated_at=utc_now(),
                expected_sha256=expected_sha256,
                notes=list(notes or []),
            )
            self.write(record)
        return record

    def read(self, txid: str) -> TransactionRecord:
        return TransactionRecord.model_validate(_read_json(self.record_path(txid)))

    def write(self, record: TransactionRecord) -> None:
        _atomic_write_json(self.record_path(record.txid), record.model_dump(mode="json"))

    def update(self, txid: str, **changes: Any) -> TransactionRecord:
        with self._lock:
            record = self.read(txid)
            requested_status = changes.get("status", record.status)
            if requested_status != record.status:
                self._check_transition(record.status, requested_status, txid)
            payload = record.model_dump(mode="python")
            payload.update({"updated_at": utc_now(), **changes})
            updated = TransactionRecord.model_validate(payload)
            self.write(updated)
            return updated

    def list(self) -> list[TransactionRecord]:
        items: list[TransactionRecord] = []
        for path in sorted(self.transactions_dir.glob("tx_*/transaction.json")):
            try:
                items.append(TransactionRecord.model_validate(_read_json(path)))
            except (OSError, ValueError):
                continue
        return items

    def store_snapshot(self, txid: str, raw_bytes: bytes) -> Path:
        path = self.snapshot_path(txid)
        atomic_write_bytes(path, raw_bytes)
        return path

    def store_preview(self, txid: str, svg: str, preview: dict[str, Any], diff: str) -> None:
        atomic_write_bytes(self.preview_svg_path(txid), svg.encode("utf-8"))
        _atomic_write_json(self.preview_json_path(txid), preview)
        atomic_write_bytes(self.diff_path(txid), diff.encode("utf-8"))

    def store_backup(self, txid: str, raw_bytes: bytes) -> Path:
        path = self.backup_path(txid)
        atomic_write_bytes(path, raw_bytes)
        return path

    def mark_committed(
        self,
        txid: str,
        *,
        committed_sha256: str,
        changed_ids: builtins.list[str],
        compiled_patch_count: int,
        preview_resources: builtins.list[str],
        backup_path: Path,
    ) -> TransactionRecord:
        return self.update(
            txid,
            status="committed",
            committed_sha256=committed_sha256,
            changed_ids=changed_ids,
            compiled_patch_count=compiled_patch_count,
            preview_resources=preview_resources,
            backup_path=str(backup_path),
        )

    def mark_rolled_back(
        self,
        txid: str,
        *,
        rolled_back_sha256: str | None,
        reason: str = "",
    ) -> TransactionRecord:
        record = self.read(txid)
        notes = [*record.notes]
        if reason:
            notes.append(reason)
        return self.update(
            txid,
            status="rolled_back",
            rolled_back_sha256=rolled_back_sha256,
            notes=notes,
        )

    def mark_failed(self, txid: str, error: dict[str, Any]) -> TransactionRecord:
        return self.update(txid, status="failed", error=error)

    @staticmethod
    def _check_transition(current: str, requested: str, txid: str) -> None:
        if requested not in _TRANSITIONS[current]:
            raise TransactionConflictError(
                f"Invalid transaction transition: {current} -> {requested}",
                details={"current_status": current, "requested_status": requested},
                txid=txid,
            )


def default_risk(risk_class: RiskClass, *reasons: str) -> TransactionRisk:
    level: Literal["low", "medium", "high"] = "low"
    if risk_class in {"limited_write", "external_execution"}:
        level = "medium"
    elif risk_class in {"elevated_write", "manufacturing_export"}:
        level = "high"
    return TransactionRisk(level=level, risk_class=risk_class, reasons=list(reasons))


def tx_preview_resources(txid: str) -> list[str]:
    return [
        f"diptrace://transaction/{txid}/preview.svg",
        f"diptrace://transaction/{txid}/preview.json",
        f"diptrace://transaction/{txid}/diff",
    ]


def tx_summary_resources(txid: str) -> list[str]:
    return [
        f"diptrace://transaction/{txid}/summary",
        f"diptrace://transaction/{txid}/operations",
        f"diptrace://transaction/{txid}/diff",
    ]


def sha_from_bytes(raw_bytes: bytes) -> str:
    return sha256_bytes(raw_bytes)
