from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .domain import DocumentInfo, JobRecord
from .errors import (
    ExternalToolFailedError,
    ExternalToolUnavailableError,
    JobCancelledError,
    JobTimeoutError,
)
from .jobs import JobStore, job_resources
from .xml_document import atomic_write_bytes, sha256_bytes, utc_now

_NET_CLASS = re.compile(r"^[A-Za-z0-9_.:+/ -]{1,128}$")


@dataclass(frozen=True, slots=True)
class FreeroutingProbe:
    available: bool
    mode: str | None
    executable: str | None
    java: str | None
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "mode": self.mode,
            "executable": self.executable,
            "java": self.java,
            "reason": self.reason,
            "cli_contract": "Freerouting -de input.dsn -do output.ses --gui.enabled=false",
        }


class FreeroutingAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def probe(self) -> FreeroutingProbe:
        executable = self.settings.freerouting_executable
        if executable is None:
            return FreeroutingProbe(
                False,
                None,
                None,
                str(self.settings.java_executable) if self.settings.java_executable else None,
                "DIPTRACE_MCP_FREEROUTING is not configured.",
            )
        if not executable.is_file():
            return FreeroutingProbe(
                False,
                None,
                str(executable),
                str(self.settings.java_executable) if self.settings.java_executable else None,
                "Configured Freerouting executable does not exist.",
            )
        if executable.suffix.casefold() == ".jar":
            java = self.settings.java_executable
            if java is None or not java.is_file():
                return FreeroutingProbe(
                    False,
                    "jar",
                    str(executable),
                    str(java) if java else None,
                    "A Java executable is required for the configured Freerouting JAR.",
                )
            return FreeroutingProbe(True, "jar", str(executable), str(java), None)
        if os.name != "nt" and not os.access(executable, os.X_OK):
            return FreeroutingProbe(
                False, "native", str(executable), None, "Configured executable is not executable."
            )
        return FreeroutingProbe(True, "native", str(executable), None, None)

    def command(
        self,
        input_path: Path,
        output_path: Path,
        *,
        max_passes: int,
        threads: int,
        ignore_net_classes: list[str],
    ) -> list[str]:
        if not 1 <= max_passes <= 10_000:
            raise ExternalToolFailedError("max_passes must be between 1 and 10000")
        if not 1 <= threads <= 64:
            raise ExternalToolFailedError("threads must be between 1 and 64")
        if len(ignore_net_classes) > 100 or any(
            not _NET_CLASS.fullmatch(item) for item in ignore_net_classes
        ):
            raise ExternalToolFailedError("Invalid ignore_net_classes value")
        probe = self.probe()
        if not probe.available or probe.executable is None:
            raise ExternalToolUnavailableError(
                probe.reason or "Freerouting is unavailable", details=probe.as_dict()
            )
        prefix = (
            [probe.java or "", "-jar", probe.executable]
            if probe.mode == "jar"
            else [probe.executable]
        )
        command = [
            *prefix,
            "-de",
            str(input_path),
            "-do",
            str(output_path),
            "-mp",
            str(max_passes),
            "-mt",
            str(threads),
            "--gui.enabled=false",
        ]
        if ignore_net_classes:
            command.extend(["-inc", ",".join(ignore_net_classes)])
        return command


class ExternalJobManager:
    def __init__(self, settings: Settings, store: JobStore) -> None:
        self.settings = settings
        self.store = store
        self.freerouting = FreeroutingAdapter(settings)
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def create_export_job(
        self,
        info: DocumentInfo,
        target_path: Path,
        dsn: bytes,
        *,
        manifest: dict[str, Any],
    ) -> JobRecord:
        record = self.store.create(
            job_type="dsn_export",
            document_id=info.document_id,
            source_sha256=info.sha256,
            target_path=target_path,
        )
        self.store.store_artifact(record.jobid, "input.dsn", dsn)
        self.store.store_artifact(
            record.jobid,
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
        return self.store.update(
            record.jobid,
            status="completed",
            phase="exported",
            progress=1.0,
            started_at=record.created_at,
            completed_at=utc_now(),
            artifacts={
                "dsn": f"diptrace://job/{record.jobid}/input.dsn",
                "manifest": f"diptrace://job/{record.jobid}/manifest.json",
            },
            result={"dsn_sha256": sha256_bytes(dsn), "size_bytes": len(dsn)},
        )

    def start_freerouting(
        self,
        info: DocumentInfo,
        target_path: Path,
        dsn: bytes,
        *,
        max_passes: int,
        threads: int,
        timeout_seconds: int | None,
        ignore_net_classes: list[str],
    ) -> JobRecord:
        probe = self.freerouting.probe()
        if not probe.available:
            raise ExternalToolUnavailableError(
                probe.reason or "Freerouting is unavailable", details=probe.as_dict()
            )
        timeout = timeout_seconds or self.settings.external_timeout_seconds
        if not 1 <= timeout <= self.settings.external_timeout_seconds:
            raise ExternalToolFailedError(
                f"timeout_seconds must be between 1 and {self.settings.external_timeout_seconds}"
            )
        record = self.store.create(
            job_type="freerouting",
            document_id=info.document_id,
            source_sha256=info.sha256,
            target_path=target_path,
        )
        input_path = self.store.store_artifact(record.jobid, "input.dsn", dsn)
        output_path = self.store.artifact_path(record.jobid, "output.ses")
        command = self.freerouting.command(
            input_path,
            output_path,
            max_passes=max_passes,
            threads=threads,
            ignore_net_classes=ignore_net_classes,
        )
        manifest = {
            "adapter": "freerouting",
            "document_id": info.document_id,
            "source_sha256": info.sha256,
            "dsn_sha256": sha256_bytes(dsn),
            "options": {
                "max_passes": max_passes,
                "threads": threads,
                "timeout_seconds": timeout,
                "ignore_net_classes": ignore_net_classes,
            },
        }
        self.store.store_artifact(
            record.jobid,
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
        record = self.store.update(
            record.jobid,
            command=command,
            artifacts={
                "dsn": f"diptrace://job/{record.jobid}/input.dsn",
                "manifest": f"diptrace://job/{record.jobid}/manifest.json",
            },
        )
        cancel = threading.Event()
        with self._lock:
            self._cancel[record.jobid] = cancel
        thread = threading.Thread(
            target=self._run,
            args=(record.jobid, command, output_path, timeout, cancel),
            name=f"diptrace-{record.jobid}",
            daemon=True,
        )
        thread.start()
        return record

    def cancel(self, jobid: str) -> JobRecord:
        record = self.store.read(jobid)
        if record.status in {"completed", "failed", "cancelled"}:
            return record
        with self._lock:
            event = self._cancel.get(jobid)
            process = self._processes.get(jobid)
        if event is not None:
            event.set()
        if process is not None and process.poll() is None:
            process.terminate()
        return self.store.update(jobid, phase="cancelling")

    def _run(
        self,
        jobid: str,
        command: list[str],
        output_path: Path,
        timeout: int,
        cancel: threading.Event,
    ) -> None:
        started = time.monotonic()
        log_path = self.store.artifact_path(jobid, "log.txt")
        self.store.update(
            jobid,
            status="running",
            phase="external_execution",
            progress=0.05,
            started_at=utc_now(),
        )
        allowed_env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP"}
        }
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    cwd=self.store.job_dir(jobid),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    env=allowed_env,
                )
                with self._lock:
                    self._processes[jobid] = process
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    if cancel.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        raise JobCancelledError(
                            "External autorouter job was cancelled", jobid=jobid
                        )
                    if elapsed > timeout:
                        process.kill()
                        raise JobTimeoutError(
                            f"External autorouter exceeded {timeout} seconds", jobid=jobid
                        )
                    self.store.update(jobid, elapsed_seconds=elapsed, progress=0.1)
                    time.sleep(0.1)
                return_code = process.returncode
            elapsed = time.monotonic() - started
            if return_code != 0:
                raise ExternalToolFailedError(
                    f"Freerouting exited with status {return_code}",
                    details={"return_code": return_code},
                    jobid=jobid,
                )
            if not output_path.is_file() or output_path.stat().st_size == 0:
                raise ExternalToolFailedError(
                    "Freerouting did not produce a non-empty SES file", jobid=jobid
                )
            if output_path.stat().st_size > self.settings.max_document_bytes:
                raise ExternalToolFailedError("Freerouting SES output exceeds the size limit")
            self._bound_log(log_path)
            self.store.update(
                jobid,
                status="completed",
                phase="completed",
                progress=1.0,
                elapsed_seconds=elapsed,
                completed_at=utc_now(),
                artifacts={
                    **self.store.read(jobid).artifacts,
                    "ses": f"diptrace://job/{jobid}/output.ses",
                    "log": f"diptrace://job/{jobid}/log",
                },
                result={
                    "return_code": return_code,
                    "ses_size_bytes": output_path.stat().st_size,
                    "ses_sha256": sha256_bytes(output_path.read_bytes()),
                    "resources": job_resources(jobid),
                },
            )
        except (JobCancelledError, JobTimeoutError, ExternalToolFailedError) as exc:
            self._bound_log(log_path)
            status = "cancelled" if isinstance(exc, JobCancelledError) else "failed"
            self.store.update(
                jobid,
                status=status,
                phase=status,
                elapsed_seconds=time.monotonic() - started,
                completed_at=utc_now(),
                error=exc.payload.as_dict(),
            )
        except OSError as exc:
            self.store.update(
                jobid,
                status="failed",
                phase="failed",
                elapsed_seconds=time.monotonic() - started,
                completed_at=utc_now(),
                error=ExternalToolFailedError(
                    f"Could not execute Freerouting: {exc}", jobid=jobid
                ).payload.as_dict(),
            )
        finally:
            with self._lock:
                self._processes.pop(jobid, None)
                self._cancel.pop(jobid, None)

    def _bound_log(self, path: Path) -> None:
        if not path.exists() or path.stat().st_size <= self.settings.max_external_log_bytes:
            return
        with path.open("rb") as stream:
            stream.seek(-self.settings.max_external_log_bytes, os.SEEK_END)
            tail = stream.read()
        atomic_write_bytes(path, b"[log truncated to bounded tail]\n" + tail)
