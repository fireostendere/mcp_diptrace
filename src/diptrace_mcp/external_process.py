from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .errors import (
    ExternalToolFailedError,
    JobCancelledError,
    JobTimeoutError,
)
from .windows_job import KillOnCloseJob, resume_suspended_process
from .xml_document import atomic_write_bytes

_LOG_TRUNCATION_MARKER = b"[log truncated to bounded tail]\n"
_WINDOWS_JOBS: dict[subprocess.Popen[bytes], KillOnCloseJob] = {}
_WINDOWS_JOBS_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class ExternalProcessResult:
    return_code: int
    elapsed_seconds: float
    log_bytes: bytes
    total_output_bytes: int
    peak_retained_output_bytes: int


class _BoundedByteTail:
    """Drain an unbounded stream while retaining no more than a fixed byte tail."""

    def __init__(self, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        self.max_bytes = max_bytes
        self.total_bytes = 0
        self.peak_retained_bytes = 0
        self._tail = bytearray()

    def append(self, chunk: bytes) -> None:
        self.total_bytes += len(chunk)
        if len(chunk) >= self.max_bytes:
            self._tail[:] = chunk[-self.max_bytes :]
        else:
            self._tail.extend(chunk)
            excess = len(self._tail) - self.max_bytes
            if excess > 0:
                del self._tail[:excess]
        self.peak_retained_bytes = max(self.peak_retained_bytes, len(self._tail))

    def render(self) -> bytes:
        if self.total_bytes <= self.max_bytes:
            return bytes(self._tail)
        if self.max_bytes <= len(_LOG_TRUNCATION_MARKER):
            return _LOG_TRUNCATION_MARKER[: self.max_bytes]
        tail_size = self.max_bytes - len(_LOG_TRUNCATION_MARKER)
        return _LOG_TRUNCATION_MARKER + bytes(self._tail[-tail_size:])


class ExternalProcessReservation:
    """One idempotently releasable slot from an ExternalProcessRunner."""

    def __init__(self, runner: ExternalProcessRunner) -> None:
        self._runner = runner
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._runner._release_slot()


class ExternalProcessRunner:
    """Run fixed commands with bounded output and whole-process-tree cancellation."""

    def __init__(
        self,
        *,
        max_concurrent: int,
        max_log_bytes: int,
        poll_interval_seconds: float = 0.05,
        termination_grace_seconds: float = 1.0,
    ) -> None:
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be greater than zero")
        if max_log_bytes <= 0:
            raise ValueError("max_log_bytes must be greater than zero")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be greater than zero")
        if termination_grace_seconds <= 0:
            raise ValueError("termination_grace_seconds must be greater than zero")
        self.max_concurrent = max_concurrent
        self.max_log_bytes = max_log_bytes
        self.poll_interval_seconds = poll_interval_seconds
        self.termination_grace_seconds = termination_grace_seconds
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._slot_lock = threading.Lock()
        self._active_slots = 0

    @property
    def active_slots(self) -> int:
        with self._slot_lock:
            return self._active_slots

    def reserve(self, *, jobid: str | None = None) -> ExternalProcessReservation:
        if not self._slots.acquire(blocking=False):
            raise ExternalToolFailedError(
                "External process concurrency limit reached",
                details={"max_external_processes": self.max_concurrent},
                jobid=jobid,
            )
        with self._slot_lock:
            self._active_slots += 1
        return ExternalProcessReservation(self)

    def _release_slot(self) -> None:
        with self._slot_lock:
            self._active_slots -= 1
        self._slots.release()

    def run(
        self,
        reservation: ExternalProcessReservation,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        log_path: Path,
        timeout_seconds: float,
        cancel: threading.Event,
        jobid: str,
        cancellation_message: str,
        timeout_message: str,
        on_started: Callable[[subprocess.Popen[bytes]], None] | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> ExternalProcessResult:
        started = time.monotonic()
        capture = _BoundedByteTail(self.max_log_bytes)
        process: subprocess.Popen[bytes] | None = None
        reader: threading.Thread | None = None
        reader_error: list[Exception] = []
        try:
            # Preserve the existing live-log resource contract while keeping
            # the file bounded from its first observable byte.
            atomic_write_bytes(log_path, b"")
            if cancel.is_set():
                raise JobCancelledError(cancellation_message, jobid=jobid)
            try:
                process = _start_process(command, cwd=cwd, env=env)
            except (OSError, ValueError) as exc:
                raise ExternalToolFailedError(
                    f"Could not start external process: {exc}",
                    jobid=jobid,
                ) from exc
            if process.stdout is None:
                raise ExternalToolFailedError(
                    "External process did not expose its output pipe",
                    jobid=jobid,
                )
            if on_started is not None:
                on_started(process)
            candidate_reader = threading.Thread(
                target=_drain_output,
                args=(process.stdout, capture, reader_error, log_path),
                name=f"diptrace-output-{jobid}",
                daemon=True,
            )
            try:
                candidate_reader.start()
            except (OSError, RuntimeError) as exc:
                raise ExternalToolFailedError(
                    f"Could not start external process output reader: {exc}",
                    jobid=jobid,
                ) from exc
            reader = candidate_reader

            while process.poll() is None:
                elapsed = time.monotonic() - started
                if cancel.is_set():
                    self._terminate_process_tree(process)
                    raise JobCancelledError(cancellation_message, jobid=jobid)
                if elapsed > timeout_seconds:
                    self._terminate_process_tree(process)
                    raise JobTimeoutError(timeout_message, jobid=jobid)
                if on_progress is not None:
                    on_progress(elapsed)
                cancel.wait(self.poll_interval_seconds)

            # The process can exit between the loop condition and the next
            # deadline check. Preserve timeout/cancellation precedence instead
            # of misclassifying that boundary race as an external-tool failure.
            elapsed = time.monotonic() - started
            if cancel.is_set():
                self._stop_remaining_descendants(process)
                raise JobCancelledError(cancellation_message, jobid=jobid)
            if elapsed > timeout_seconds:
                self._stop_remaining_descendants(process)
                raise JobTimeoutError(timeout_message, jobid=jobid)

            return_code = process.wait()
            self._stop_remaining_descendants(process)
            if cancel.is_set():
                self._terminate_process_tree(process)
                raise JobCancelledError(cancellation_message, jobid=jobid)
            self._finish_reader(process, reader)
            if reader_error:
                raise OSError(f"Could not read external process output: {reader_error[0]}")
            log_bytes = capture.render()
            return ExternalProcessResult(
                return_code=return_code,
                elapsed_seconds=time.monotonic() - started,
                log_bytes=log_bytes,
                total_output_bytes=capture.total_bytes,
                peak_retained_output_bytes=capture.peak_retained_bytes,
            )
        except BaseException:
            if process is not None and process.poll() is None:
                self._terminate_process_tree(process)
            raise
        finally:
            try:
                if process is not None:
                    if process.poll() is None:
                        self._terminate_process_tree(process)
                    elif os.name == "nt":
                        _close_windows_job(process)
                    process.wait()
                    self._finish_reader(process, reader)
            finally:
                try:
                    atomic_write_bytes(log_path, capture.render())
                finally:
                    reservation.release()

    def _finish_reader(
        self,
        process: subprocess.Popen[bytes],
        reader: threading.Thread | None,
    ) -> None:
        if reader is None:
            return
        reader.join(timeout=self.termination_grace_seconds)
        if reader.is_alive():
            # A descendant can inherit stdout and outlive a root process that
            # exited normally. Tear down the process tree before closing the
            # local pipe so the drain thread cannot keep the job alive.
            self._signal_process_tree(process, force=True)
            reader.join(timeout=self.termination_grace_seconds)
        if reader.is_alive() and process.stdout is not None:
            process.stdout.close()
            reader.join(timeout=self.termination_grace_seconds)

    def _terminate_process_tree(self, process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            _close_windows_job(process)
            if process.poll() is None:
                process.kill()
            process.wait()
            return

        self._signal_process_tree(process, force=False)
        if process.poll() is None:
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=self.termination_grace_seconds)
        self._signal_process_tree(process, force=True)
        if process.poll() is None:
            process.kill()
        process.wait()

    def _stop_remaining_descendants(self, process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            _close_windows_job(process)
        else:
            self._signal_process_tree(process, force=True)

    @staticmethod
    def _signal_process_tree(process: subprocess.Popen[bytes], *, force: bool) -> None:
        if os.name == "nt":
            _close_windows_job(process)
            if process.poll() is None:
                process.kill()
            return
        process_signal = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.killpg(process.pid, process_signal)
        except ProcessLookupError:
            return
        except OSError:
            if process.poll() is None:
                process.send_signal(process_signal)


def _start_process(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> subprocess.Popen[bytes]:
    if os.name == "nt":
        creation_flag = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        suspended_flag = int(getattr(subprocess, "CREATE_SUSPENDED", 0x00000004))
        job = KillOnCloseJob.create()
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                env=dict(env),
                creationflags=creation_flag | suspended_flag,
            )
            job.assign(process.pid)
            resume_suspended_process(process.pid)
        except BaseException:
            job.terminate_and_close()
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                if process.stdout is not None:
                    process.stdout.close()
            raise
        with _WINDOWS_JOBS_LOCK:
            _WINDOWS_JOBS[process] = job
        return process
    return subprocess.Popen(
        list(command),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        env=dict(env),
        start_new_session=True,
    )


def _close_windows_job(process: subprocess.Popen[bytes]) -> None:
    with _WINDOWS_JOBS_LOCK:
        job = _WINDOWS_JOBS.pop(process, None)
    if job is not None:
        job.terminate_and_close()


def _drain_output(
    stream: BinaryIO,
    capture: _BoundedByteTail,
    errors: list[Exception],
    log_path: Path,
) -> None:
    next_flush = 0.0
    live_log_failed = False
    try:
        while chunk := os.read(stream.fileno(), 64 * 1024):
            capture.append(chunk)
            now = time.monotonic()
            if not live_log_failed and now >= next_flush:
                try:
                    atomic_write_bytes(log_path, capture.render())
                except OSError as exc:
                    errors.append(exc)
                    live_log_failed = True
                next_flush = now + 0.1
    except (OSError, ValueError) as exc:
        # Closing stdout is an intentional last-resort unblock in _finish_reader.
        # Do not turn that cleanup race into a false process-output failure.
        if not stream.closed:
            errors.append(exc)
    finally:
        with suppress(OSError, ValueError):
            stream.close()
