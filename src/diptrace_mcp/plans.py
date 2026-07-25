from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from .domain import PlanRecord, PlanStatus
from .errors import ObjectNotFoundError
from .record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    iter_valid_record_files,
    require_confined_record_file,
    require_record_id,
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
from .xml_document import atomic_write_bytes, utc_now


@dataclass(slots=True)
class PlanStore:
    state_dir: Path
    retention: RetentionPolicy = dataclass_field(default_factory=RetentionPolicy)
    clock: Clock = dataclass_field(default=system_clock, repr=False)
    plans_dir: Path = dataclass_field(init=False)
    last_retention_report: RetentionReport = dataclass_field(init=False)
    _lock: threading.RLock = dataclass_field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.plans_dir = self.state_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.last_retention_report = self._prune_retention()

    def _prune_retention(self) -> RetentionReport:
        candidates: list[RetentionCandidate] = []
        paths = sorted(self.plans_dir.glob("plan_*/plan.json"))
        for path_plan_id, path in iter_valid_record_files(
            self.plans_dir,
            paths,
            kind="plan",
            record_filename="plan.json",
        ):
            try:
                record = PlanRecord.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                continue
            timestamp = parse_retention_timestamp(record.updated_at)
            if (
                record.plan_id != path_plan_id
                or record.status not in {"committed", "obsolete"}
                or timestamp is None
            ):
                continue
            candidates.append(
                RetentionCandidate(
                    identifier=record.plan_id,
                    path=path.parent,
                    timestamp=timestamp,
                )
            )
        return prune_terminal_records(
            state_root=self.state_dir,
            store_root=self.plans_dir,
            candidates=candidates,
            policy=self.retention,
            clock=self.clock,
        )

    def plan_dir(self, plan_id: str) -> Path:
        try:
            validated = require_record_id(plan_id, "plan")
        except InvalidRecordId:
            raise ObjectNotFoundError("Invalid plan id") from None
        return self.plans_dir / validated

    def record_path(self, plan_id: str) -> Path:
        return self.plan_dir(plan_id) / "plan.json"

    def preview_svg_path(self, plan_id: str) -> Path:
        return self.plan_dir(plan_id) / "preview.svg"

    def preview_json_path(self, plan_id: str) -> Path:
        return self.plan_dir(plan_id) / "preview.json"

    def diff_path(self, plan_id: str) -> Path:
        return self.plan_dir(plan_id) / "diff.txt"

    def create(
        self,
        *,
        plan_type: str,
        document_id: str,
        source_sha256: str,
        target_path: Path,
        config: dict[str, Any],
        operations: list[dict[str, Any]],
        changed_ids: list[str],
        unresolved: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        score: dict[str, float],
        metrics: dict[str, Any],
        assumptions: list[str],
        warnings: list[str],
        limitations: list[str],
    ) -> PlanRecord:
        now = utc_now()
        record = PlanRecord(
            plan_id=f"plan_{uuid.uuid4().hex}",
            plan_type=plan_type,
            document_id=document_id,
            source_sha256=source_sha256,
            target_path=str(target_path),
            created_at=now,
            updated_at=now,
            config=config,
            operations=operations,
            changed_ids=changed_ids,
            unresolved=unresolved,
            candidates=candidates,
            score=score,
            metrics=metrics,
            assumptions=assumptions,
            warnings=warnings,
            limitations=limitations,
        )
        with self._lock:
            self.plan_dir(record.plan_id).mkdir(parents=True, exist_ok=False)
            self.write(record)
        return record

    def read(self, plan_id: str) -> PlanRecord:
        try:
            path = require_confined_record_file(
                self.plans_dir,
                plan_id,
                kind="plan",
                record_filename="plan.json",
            )
            record = PlanRecord.model_validate_json(path.read_bytes())
        except InvalidRecordId:
            raise ObjectNotFoundError("Invalid plan id") from None
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Plan was not found: {plan_id}") from exc
        except InvalidRecordPath as exc:
            raise ObjectNotFoundError(
                "Plan state path is redirected or outside its store"
            ) from exc
        except (OSError, ValueError) as exc:
            raise ObjectNotFoundError("Plan state is corrupt") from exc
        if record.plan_id != plan_id:
            raise ObjectNotFoundError(
                "Plan state id does not match the requested plan"
            )
        return record

    def write(self, record: PlanRecord) -> None:
        payload = json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        atomic_write_bytes(self.record_path(record.plan_id), payload)

    def update(
        self,
        plan_id: str,
        *,
        status: PlanStatus,
        transaction_id: str | None,
    ) -> PlanRecord:
        with self._lock:
            record = self.read(plan_id)
            updated = PlanRecord.model_validate(
                {
                    **record.model_dump(mode="python"),
                    "status": status,
                    "transaction_id": transaction_id,
                    "updated_at": utc_now(),
                }
            )
            self.write(updated)
            return updated

    def store_preview(
        self,
        plan_id: str,
        *,
        svg: str,
        geometry: dict[str, Any],
        diff: str,
    ) -> list[str]:
        atomic_write_bytes(self.preview_svg_path(plan_id), svg.encode("utf-8"))
        atomic_write_bytes(
            self.preview_json_path(plan_id),
            json.dumps(geometry, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
        atomic_write_bytes(self.diff_path(plan_id), diff.encode("utf-8"))
        resources = plan_preview_resources(plan_id)
        record = self.read(plan_id)
        self.write(
            PlanRecord.model_validate(
                {**record.model_dump(mode="python"), "preview_resources": resources}
            )
        )
        return resources


def plan_preview_resources(plan_id: str) -> list[str]:
    return [
        f"diptrace://plan/{plan_id}/summary",
        f"diptrace://plan/{plan_id}/preview.svg",
        f"diptrace://plan/{plan_id}/preview.json",
        f"diptrace://plan/{plan_id}/diff",
    ]
