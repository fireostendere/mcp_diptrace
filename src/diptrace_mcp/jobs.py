from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

from .domain import JobRecord, JobStatus
from .errors import ObjectNotFoundError
from .record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    is_link_like,
    iter_valid_record_files,
    require_confined_file,
    require_confined_record_directory,
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
from .xml_document import atomic_write_bytes, utc_now


@dataclass(slots=True)
class JobStore(RecordStore):
    state_dir: Path
    retention: RetentionPolicy = dataclass_field(default_factory=RetentionPolicy)
    clock: Clock = dataclass_field(default=system_clock, repr=False)
    jobs_dir: Path = dataclass_field(init=False)
    last_retention_report: RetentionReport = dataclass_field(init=False)
    _lock: threading.RLock = dataclass_field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.jobs_dir = self.state_dir / "jobs"
        self._initialize_record_store(
            state_dir=self.state_dir,
            store_root=self.jobs_dir,
        )
        self._lock = threading.RLock()
        # Inspect persisted status before interrupted running jobs are failed:
        # queued/running records must survive this construction cycle.
        self.last_retention_report = self._initial_retention_report()
        self._fail_interrupted_jobs()

    def _prune_retention(self) -> RetentionReport:
        candidates: list[RetentionCandidate] = []
        paths = sorted(self.jobs_dir.glob("job_*/job.json"))
        for path_jobid, path in iter_valid_record_files(
            self.jobs_dir,
            paths,
            kind="job",
            record_filename="job.json",
        ):
            try:
                record = JobRecord.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                continue
            timestamp = parse_retention_timestamp(record.completed_at)
            if (
                record.jobid != path_jobid
                or record.status not in {"completed", "failed", "cancelled"}
                or timestamp is None
            ):
                continue
            candidates.append(
                RetentionCandidate(
                    identifier=record.jobid,
                    path=path.parent,
                    timestamp=timestamp,
                )
            )
        return prune_terminal_records(
            state_root=self.state_dir,
            store_root=self.jobs_dir,
            candidates=candidates,
            policy=self.retention,
            clock=self.clock,
        )

    def job_dir(self, jobid: str) -> Path:
        try:
            validated = require_record_id(jobid, "job")
        except InvalidRecordId:
            raise ObjectNotFoundError("Invalid job id", jobid=jobid) from None
        return self.jobs_dir / validated

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
        self.read(jobid)
        try:
            directory = require_confined_record_directory(
                self.jobs_dir,
                jobid,
                kind="job",
            )
            path = directory / name
            if is_link_like(path):
                raise InvalidRecordPath(f"Job artifact is redirected: {path}")
            if path.exists():
                require_confined_file(self.jobs_dir, path)
        except (InvalidRecordId, InvalidRecordPath, OSError) as exc:
            raise ObjectNotFoundError(
                "Job artifact path is redirected or outside its store",
                jobid=jobid,
            ) from exc
        return path

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
            self._require_safe_root()
            self.job_dir(record.jobid).mkdir(parents=True, exist_ok=False)
            self.write(record)
        return record

    def read(self, jobid: str) -> JobRecord:
        try:
            path = require_confined_record_file(
                self.jobs_dir,
                jobid,
                kind="job",
                record_filename="job.json",
            )
            # Windows does not permit opening the destination while os.replace()
            # is swapping an atomic-write temporary file into place. Serialize
            # reads with updates so callers never observe that transient lock.
            with self._lock:
                payload = path.read_bytes()
            record = JobRecord.model_validate_json(payload)
        except InvalidRecordId:
            raise ObjectNotFoundError("Invalid job id", jobid=jobid) from None
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Job was not found: {jobid}", jobid=jobid) from exc
        except InvalidRecordPath as exc:
            raise ObjectNotFoundError(
                "Job state path is redirected or outside its store",
                jobid=jobid,
            ) from exc
        except (OSError, ValueError) as exc:
            raise ObjectNotFoundError("Job state is corrupt", jobid=jobid) from exc
        if record.jobid != jobid:
            raise ObjectNotFoundError(
                "Job state id does not match the requested job",
                jobid=jobid,
            )
        return record

    def write(self, record: JobRecord) -> None:
        self._write_store_json(
            self.record_path(record.jobid),
            record.model_dump(mode="json"),
            sort_keys=True,
        )

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
        paths = sorted(self.jobs_dir.glob("job_*/job.json"))
        for path_jobid, path in iter_valid_record_files(
            self.jobs_dir,
            paths,
            kind="job",
            record_filename="job.json",
        ):
            try:
                with self._lock:
                    payload = path.read_bytes()
                record = JobRecord.model_validate_json(payload)
            except (OSError, ValueError):
                continue
            if record.jobid != path_jobid:
                continue
            if status is None or record.status == status:
                records.append(record)
        return records

    def store_artifact(self, jobid: str, name: str, data: bytes) -> Path:
        self._require_safe_root()
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
