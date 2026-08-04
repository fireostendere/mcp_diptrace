from __future__ import annotations

import json
from typing import Any, cast

from ..config import Settings
from ..domain import (
    JobStatus,
)
from ..errors import (
    CapabilityUnavailableError,
    DocumentError,
)
from ..external_adapters import ExternalJobManager
from ..jobs import JobStore, job_resources


class JobService:
    def __init__(
        self, settings: Settings, job_store: JobStore, external_job_manager: ExternalJobManager
    ) -> None:
        self.settings = settings
        self.job_store = job_store
        self.external_job_manager = external_job_manager

    def get_job_status(self, jobid: str) -> dict[str, Any]:
        record = self.job_store.read(jobid)
        return {
            "ok": True,
            "document": None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": record.warnings,
            "limitations": [],
            "resources": job_resources(jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def get_job_result(self, jobid: str) -> dict[str, Any]:
        record = self.job_store.read(jobid)
        return {
            "ok": True,
            "document": None,
            "result": {
                "status": record.status,
                "result": record.result,
                "partial_result": record.partial_result,
                "error": record.error,
                "artifacts": record.artifacts,
            },
            "warnings": record.warnings,
            "limitations": [],
            "resources": job_resources(jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def cancel_job(self, jobid: str) -> dict[str, Any]:
        record = self.external_job_manager.cancel(jobid)
        return self.get_job_status(record.jobid)

    def list_jobs(self, status: str | None = None) -> dict[str, Any]:
        allowed = {None, "queued", "running", "completed", "failed", "cancelled"}
        if status not in allowed:
            raise DocumentError(f"Unknown job status: {status}")
        records = self.job_store.list(status=cast(JobStatus | None, status))
        return {
            "ok": True,
            "document": None,
            "result": {
                "matched_count": len(records),
                "jobs": [record.model_dump(mode="json") for record in records],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def job_resource(self, jobid: str, artifact: str) -> str:
        record = self.job_store.read(jobid)
        if artifact == "status":
            return json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if artifact == "result":
            return json.dumps(
                {"status": record.status, "result": record.result, "error": record.error},
                ensure_ascii=False,
                indent=2,
            )
        name = {
            "log": "log.txt",
            "input.dsn": "input.dsn",
            "output.ses": "output.ses",
            "field_solver_input.json": "field_solver_input.json",
            "field_solver_result.json": "field_solver_result.json",
            "manifest.json": "manifest.json",
        }.get(artifact)
        if name is None:
            raise CapabilityUnavailableError(f"Unknown job resource: {artifact}")
        artifact_path = self.job_store.artifact_path(jobid, name)
        if not artifact_path.exists():
            return ""
        data = artifact_path.read_bytes()
        if artifact == "log" and len(data) > self.settings.max_external_log_bytes:
            data = data[-self.settings.max_external_log_bytes :]
        return data.decode("utf-8", errors="replace")
