from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from .domain import JobRecord, JobStatus
from .errors import ObjectNotFoundError
from .xml_document import atomic_write_bytes, utc_now

_JOB_ID = re.compile(r"^job_[0-9a-f]{32}$")


@dataclass(slots=True)
class JobStore:
    state_dir: Path
    jobs_dir: Path = dataclass_field(init=False)
    _lock: threading.RLock = dataclass_field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.jobs_dir = self.state_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._fail_interrupted_jobs()

    def job_dir(self, jobid: str) -> Path:
        if not _JOB_ID.fullmatch(jobid):
            raise ObjectNotFoundError(f"Invalid job id: {jobid}", jobid=jobid)
        return self.jobs_dir / jobid

    def record_path(self, jobid: str) -> Path:
        return self.job_dir(jobid) / "job.json"

    def artifact_path(self, jobid: str, name: str) -> Path:
        if name not in {
            "input.dsn",
            "output.ses",
            "input.cir",
            "field_solver_input.json",
            "field_solver_result.json",
            "log.txt",
            "manifest.json",
        }:
            raise ObjectNotFoundError(f"Unknown job artifact: {name}", jobid=jobid)
        return self.job_dir(jobid) / name

    def create(
        self,
        *,
        job_type: str,
        document_id: str | None = None,
        source_sha256: str | None = None,
        target_path: Path | None = None,
    ) -> JobRecord:
        now = utc_now()
        record = JobRecord(
            jobid=f"job_{uuid.uuid4().hex}",
            job_type=job_type,
            status="queued",
            created_at=now,
            updated_at=now,
            document_id=document_id,
            source_sha256=source_sha256,
            target_path=str(target_path) if target_path is not None else None,
        )
        with self._lock:
            self.job_dir(record.jobid).mkdir(parents=True, exist_ok=False)
            self.write(record)
        return record

    def read(self, jobid: str) -> JobRecord:
        try:
            # Windows does not permit opening the destination while os.replace()
            # is swapping an atomic-write temporary file into place. Serialize
            # reads with updates so callers never observe that transient lock.
            with self._lock:
                payload = self.record_path(jobid).read_bytes()
            return JobRecord.model_validate_json(payload)
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Job was not found: {jobid}", jobid=jobid) from exc

    def write(self, record: JobRecord) -> None:
        payload = json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        atomic_write_bytes(self.record_path(record.jobid), payload)

    def update(self, jobid: str, **changes: Any) -> JobRecord:
        with self._lock:
            record = self.read(jobid)
            payload = record.model_dump(mode="python")
            payload.update({"updated_at": utc_now(), **changes})
            updated = JobRecord.model_validate(payload)
            self.write(updated)
            return updated

    def list(self, *, status: JobStatus | None = None) -> list[JobRecord]:
        records: list[JobRecord] = []
        for path in sorted(self.jobs_dir.glob("job_*/job.json")):
            try:
                with self._lock:
                    payload = path.read_bytes()
                record = JobRecord.model_validate_json(payload)
            except (OSError, ValueError):
                continue
            if status is None or record.status == status:
                records.append(record)
        return records

    def store_artifact(self, jobid: str, name: str, data: bytes) -> Path:
        path = self.artifact_path(jobid, name)
        atomic_write_bytes(path, data)
        return path

    def _fail_interrupted_jobs(self) -> None:
        for record in self.list():
            if record.status not in {"queued", "running"}:
                continue
            self.update(
                record.jobid,
                status="failed",
                phase="interrupted",
                completed_at=utc_now(),
                error={
                    "code": "external_tool_failed",
                    "message": "Server restarted while the external job was active.",
                    "recoverable": True,
                },
            )


def job_resources(jobid: str) -> list[str]:
    return [
        f"diptrace://job/{jobid}/status",
        f"diptrace://job/{jobid}/result",
        f"diptrace://job/{jobid}/log",
    ]
