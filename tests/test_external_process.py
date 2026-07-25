from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import pytest

import diptrace_mcp.external_adapters as external_adapters_module
import diptrace_mcp.external_process as external_process_module
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import (
    ExternalToolFailedError,
    JobCancelledError,
    JobTimeoutError,
)
from diptrace_mcp.external_process import ExternalProcessResult, ExternalProcessRunner
from diptrace_mcp.service import DipTraceService


def _runner(*, max_concurrent: int = 1, max_log_bytes: int = 4096) -> ExternalProcessRunner:
    return ExternalProcessRunner(
        max_concurrent=max_concurrent,
        max_log_bytes=max_log_bytes,
        poll_interval_seconds=0.01,
        termination_grace_seconds=0.1,
    )


def _run_command(
    runner: ExternalProcessRunner,
    tmp_path: Path,
    command: list[str],
    *,
    timeout: float = 5.0,
    cancel: threading.Event | None = None,
    log_name: str = "log.txt",
    on_started: Callable[[subprocess.Popen[bytes]], None] | None = None,
) -> ExternalProcessResult:
    reservation = runner.reserve(jobid="job_process_test")
    return runner.run(
        reservation,
        command,
        cwd=tmp_path,
        env={"PATH": os.environ.get("PATH", "")},
        log_path=tmp_path / log_name,
        timeout_seconds=timeout,
        cancel=cancel or threading.Event(),
        jobid="job_process_test",
        cancellation_message="test process was cancelled",
        timeout_message="test process timed out",
        on_started=on_started,
    )


def _process_tree_command(pid_path: Path) -> list[str]:
    child_code = "import time; time.sleep(60)"
    root_code = f"""\
import os
import subprocess
import sys
import time
from pathlib import Path

grandchild = subprocess.Popen([{sys.executable!r}, "-c", {child_code!r}])
Path({str(pid_path)!r}).write_text(
    f"{{os.getpid()}} {{grandchild.pid}}",
    encoding="ascii",
)
print("tree-ready", flush=True)
time.sleep(60)
"""
    return [sys.executable, "-c", root_code]


def _wait_for_path(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.is_file()


def _is_live_process(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat_path = Path(f"/proc/{pid}/stat")
    if stat_path.is_file():
        fields = stat_path.read_text(encoding="ascii").split()
        if len(fields) > 2 and fields[2] == "Z":
            return False
    return True


def _assert_process_stopped(pid: int, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while _is_live_process(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _is_live_process(pid), f"process {pid} remained alive"


def _cleanup_processes(pids: list[int]) -> None:
    for pid in pids:
        if _is_live_process(pid):
            with suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


def _is_live_windows_process(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    open_process.restype = ctypes.c_void_p
    get_exit_code = kernel32.GetExitCodeProcess
    get_exit_code.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    get_exit_code.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    handle = open_process(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == 259
    finally:
        close_handle(handle)


def _assert_windows_process_stopped(pid: int, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while _is_live_windows_process(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _is_live_windows_process(pid), f"process {pid} remained alive"


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group and waitpid assertion")
def test_timeout_kills_child_and_grandchild_and_reaps_root(tmp_path: Path) -> None:
    runner = _runner()
    pid_path = tmp_path / "tree.pids"
    started_pids: list[int] = []
    tree_pids: list[int] = []
    try:
        with pytest.raises(JobTimeoutError, match="timed out"):
            _run_command(
                runner,
                tmp_path,
                _process_tree_command(pid_path),
                timeout=0.5,
                on_started=lambda process: started_pids.append(process.pid),
            )
        _wait_for_path(pid_path)
        tree_pids = [int(value) for value in pid_path.read_text(encoding="ascii").split()]
        assert started_pids == [tree_pids[0]]
        for pid in tree_pids:
            _assert_process_stopped(pid)
        with pytest.raises(ChildProcessError):
            os.waitpid(tree_pids[0], os.WNOHANG)
        assert runner.active_slots == 0
    finally:
        _cleanup_processes(tree_pids or started_pids)


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group assertion")
def test_cancellation_kills_child_and_grandchild(tmp_path: Path) -> None:
    runner = _runner()
    pid_path = tmp_path / "cancel-tree.pids"
    cancel = threading.Event()
    failures: list[BaseException] = []
    tree_pids: list[int] = []

    def execute() -> None:
        try:
            _run_command(
                runner,
                tmp_path,
                _process_tree_command(pid_path),
                timeout=10,
                cancel=cancel,
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=execute)
    worker.start()
    try:
        _wait_for_path(pid_path)
        tree_pids = [int(value) for value in pid_path.read_text(encoding="ascii").split()]
        cancel.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert len(failures) == 1
        assert isinstance(failures[0], JobCancelledError)
        for pid in tree_pids:
            _assert_process_stopped(pid)
        assert runner.active_slots == 0
    finally:
        cancel.set()
        worker.join(timeout=2)
        _cleanup_processes(tree_pids)


@pytest.mark.skipif(os.name != "nt", reason="native Windows Job Object assertion")
def test_windows_normal_root_exit_kills_inherited_output_child(tmp_path: Path) -> None:
    runner = _runner()
    child_pid_path = tmp_path / "windows-child.pid"
    child_code = "import time; time.sleep(60)"
    root_code = f"""\
import subprocess
import sys
from pathlib import Path

child = subprocess.Popen([{sys.executable!r}, "-c", {child_code!r}])
Path({str(child_pid_path)!r}).write_text(str(child.pid), encoding="ascii")
print("root-complete", flush=True)
"""
    started = time.monotonic()
    result = _run_command(
        runner,
        tmp_path,
        [sys.executable, "-c", root_code],
    )
    elapsed = time.monotonic() - started
    _wait_for_path(child_pid_path)
    child_pid = int(child_pid_path.read_text(encoding="ascii"))
    try:
        assert result.return_code == 0
        assert result.log_bytes.splitlines() == [b"root-complete"]
        assert elapsed < 5
        _assert_windows_process_stopped(child_pid)
    finally:
        if _is_live_windows_process(child_pid):
            os.kill(child_pid, signal.SIGTERM)


def test_high_output_is_drained_to_bounded_tail_during_execution(tmp_path: Path) -> None:
    runner = _runner(max_log_bytes=4096)
    log_path = tmp_path / "high-output.log"
    result: list[ExternalProcessResult] = []
    failures: list[BaseException] = []
    observed_log_sizes: list[int] = []
    code = """\
import os
import time
for index in range(256):
    os.write(1, b"A" * 65536)
    if index % 16 == 0:
        time.sleep(0.005)
os.write(2, b"TAIL-SENTINEL\\n")
"""

    def execute() -> None:
        try:
            result.append(
                _run_command(
                    runner,
                    tmp_path,
                    [sys.executable, "-c", code],
                    log_name=log_path.name,
                )
            )
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=execute)
    worker.start()
    while worker.is_alive():
        if log_path.exists():
            observed_log_sizes.append(log_path.stat().st_size)
        time.sleep(0.002)
    worker.join()
    observed_log_sizes.append(log_path.stat().st_size)

    assert failures == []
    assert len(result) == 1
    assert result[0].total_output_bytes >= 16 * 1024 * 1024
    assert result[0].peak_retained_output_bytes <= 4096
    assert max(observed_log_sizes) <= 4096
    assert len(result[0].log_bytes) <= 4096
    assert result[0].log_bytes.startswith(b"[log truncated")
    assert result[0].log_bytes.endswith(b"TAIL-SENTINEL\n")
    assert log_path.read_bytes() == result[0].log_bytes


def test_concurrency_refusal_is_typed_and_slot_recovers_after_timeout(
    tmp_path: Path,
) -> None:
    runner = _runner(max_concurrent=1)
    first = runner.reserve(jobid="job_first")
    with pytest.raises(ExternalToolFailedError) as exc_info:
        runner.reserve(jobid="job_refused")
    assert exc_info.value.payload.code == "external_tool_failed"
    assert exc_info.value.details == {"max_external_processes": 1}

    with pytest.raises(JobTimeoutError):
        runner.run(
            first,
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            env={"PATH": os.environ.get("PATH", "")},
            log_path=tmp_path / "timeout.log",
            timeout_seconds=0.1,
            cancel=threading.Event(),
            jobid="job_first",
            cancellation_message="cancelled",
            timeout_message="timed out",
        )
    assert runner.active_slots == 0

    recovered = _run_command(
        runner,
        tmp_path,
        [sys.executable, "-c", "print('recovered')"],
        log_name="recovered.log",
    )
    assert recovered.return_code == 0
    assert recovered.log_bytes.splitlines() == [b"recovered"]
    assert runner.active_slots == 0


def test_slot_is_released_even_if_bounded_log_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()

    def fail_write(_path: Path, _data: bytes) -> None:
        raise OSError("simulated log write failure")

    monkeypatch.setattr(external_process_module, "atomic_write_bytes", fail_write)
    with pytest.raises(OSError, match="simulated log write failure"):
        _run_command(runner, tmp_path, [sys.executable, "-c", "print('done')"])
    assert runner.active_slots == 0
    reservation = runner.reserve(jobid="job_after_log_failure")
    reservation.release()


def test_output_reader_start_failure_is_typed_and_releases_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()

    def fail_start(_thread: threading.Thread) -> None:
        raise RuntimeError("simulated thread resource exhaustion")

    monkeypatch.setattr(external_process_module.threading.Thread, "start", fail_start)
    with pytest.raises(
        ExternalToolFailedError,
        match="Could not start external process output reader",
    ):
        _run_command(
            runner,
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(5)"],
        )

    assert runner.active_slots == 0
    recovered = runner.reserve(jobid="job_after_reader_failure")
    recovered.release()


def test_windows_process_is_suspended_assigned_then_resumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen_calls: list[dict[str, object]] = []
    events: list[object] = []

    class FakeStdout:
        def close(self) -> None:
            events.append("stdout-close")

    class FakeProcess:
        pid = 1234
        stdout = FakeStdout()

        def poll(self) -> int | None:
            return None

        def kill(self) -> None:
            events.append("kill")

        def wait(self) -> int:
            events.append("wait")
            return 1

    process = FakeProcess()

    class FakeJob:
        @classmethod
        def create(cls) -> FakeJob:
            events.append("create-job")
            return cls()

        def assign(self, pid: int) -> None:
            events.append(("assign", pid))

        def terminate_and_close(self) -> None:
            events.append("close-job")

    def fake_popen(_command: list[str], **kwargs: object) -> FakeProcess:
        popen_calls.append(kwargs)
        events.append("popen")
        return process

    def fake_resume(pid: int) -> None:
        events.append(("resume", pid))

    monkeypatch.setattr(external_process_module.os, "name", "nt")
    monkeypatch.setattr(
        external_process_module.subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        512,
        raising=False,
    )
    monkeypatch.setattr(
        external_process_module.subprocess,
        "CREATE_SUSPENDED",
        4,
        raising=False,
    )
    monkeypatch.setattr(external_process_module, "KillOnCloseJob", FakeJob)
    monkeypatch.setattr(external_process_module, "resume_suspended_process", fake_resume)
    monkeypatch.setattr(external_process_module.subprocess, "Popen", fake_popen)

    started_process = external_process_module._start_process(
        ["solver.exe"],
        cwd=tmp_path,
        env={"PATH": "C:\\Windows"},
    )
    external_process_module._close_windows_job(started_process)

    assert started_process is process
    assert popen_calls[0]["creationflags"] == 516
    assert popen_calls[0]["shell"] is False
    assert events == [
        "create-job",
        "popen",
        ("assign", 1234),
        ("resume", 1234),
        "close-job",
    ]


def test_windows_assignment_failure_kills_suspended_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakeStdout:
        def close(self) -> None:
            events.append("stdout-close")

    class FakeProcess:
        pid = 4321
        stdout = FakeStdout()
        killed = False

        def poll(self) -> int | None:
            return 1 if self.killed else None

        def kill(self) -> None:
            self.killed = True
            events.append("kill-root")

        def wait(self) -> int:
            events.append("wait-root")
            return 1

    class FailingJob:
        @classmethod
        def create(cls) -> FailingJob:
            events.append("create-job")
            return cls()

        def assign(self, _pid: int) -> None:
            events.append("assign-failed")
            raise OSError("simulated assignment failure")

        def terminate_and_close(self) -> None:
            events.append("close-job")

    monkeypatch.setattr(external_process_module.os, "name", "nt")
    monkeypatch.setattr(external_process_module, "KillOnCloseJob", FailingJob)
    monkeypatch.setattr(
        external_process_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FakeProcess(),
    )

    with pytest.raises(OSError, match="simulated assignment failure"):
        external_process_module._start_process(
            ["solver.exe"],
            cwd=tmp_path,
            env={"PATH": "C:\\Windows"},
        )

    assert events == [
        "create-job",
        "assign-failed",
        "close-job",
        "kill-root",
        "wait-root",
        "stdout-close",
    ]


def test_process_start_failure_is_typed_and_releases_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _runner()

    def fail_start(
        _command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> subprocess.Popen[bytes]:
        del cwd, env
        raise OSError("simulated Windows Job Object setup failure")

    monkeypatch.setattr(external_process_module, "_start_process", fail_start)

    with pytest.raises(
        ExternalToolFailedError,
        match="Could not start external process.*Job Object setup failure",
    ) as exc_info:
        _run_command(runner, tmp_path, ["solver.exe"])

    assert exc_info.value.payload.code == "external_tool_failed"
    assert runner.active_slots == 0


def test_configured_process_cap_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DIPTRACE_MCP_MAX_EXTERNAL_PROCESSES", "3")

    settings = Settings.from_env()

    assert settings.max_external_processes == 3
    assert settings.as_dict()["max_external_processes"] == 3


def test_worker_thread_construction_failure_releases_reservation_and_fails_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
            max_external_processes=1,
        )
    )
    record = service.jobs.create(job_type="constructor_failure")

    def fail_thread(*_args: object, **_kwargs: object) -> threading.Thread:
        raise RuntimeError("simulated thread constructor failure")

    monkeypatch.setattr(external_adapters_module.threading, "Thread", fail_thread)
    with pytest.raises(ExternalToolFailedError, match="Could not start external job worker"):
        service.external_jobs._launch_worker(
            record,
            target=lambda *_args: None,
            args=(),
        )

    failed = service.jobs.read(record.jobid)
    assert failed.status == "failed"
    assert failed.phase == "failed"
    assert service.external_jobs._runner.active_slots == 0
    assert record.jobid not in service.external_jobs._cancel


def test_cancel_before_worker_registration_is_terminal_and_prevents_launch(
    tmp_path: Path,
) -> None:
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
            max_external_processes=1,
        )
    )
    record = service.jobs.create(job_type="cancel_before_launch")
    invoked = threading.Event()

    cancelled = service.external_jobs.cancel(record.jobid)
    relaunched = service.external_jobs._launch_worker(
        cancelled,
        target=lambda *_args: invoked.set(),
        args=(),
    )

    assert cancelled.status == "cancelled"
    assert relaunched.status == "cancelled"
    assert not invoked.is_set()
    assert service.external_jobs._runner.active_slots == 0
    assert record.jobid not in service.external_jobs._cancel


def test_post_create_setup_failure_does_not_leave_queued_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "fake_ngspice.py"
    executable.write_text("print('No. of Data Rows : 1')\n")
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
            ngspice_executable=executable,
            active_policy="automation",
        )
    )

    def fail_command(_path: Path) -> list[str]:
        raise RuntimeError("simulated executable race")

    monkeypatch.setattr(service.external_jobs.ngspice, "command", fail_command)
    with pytest.raises(RuntimeError, match="simulated executable race"):
        service.run_ngspice_simulation(netlist="* setup failure\n.end\n")

    records = service.jobs.list()
    assert len(records) == 1
    assert records[0].status == "failed"
    assert records[0].phase == "failed"
    assert records[0].error is not None


def test_unexpected_runner_failure_is_persisted_as_failed_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "fake_ngspice.py"
    executable.write_text("print('No. of Data Rows : 1')\n")
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
            ngspice_executable=executable,
            active_policy="automation",
        )
    )

    def fail_runner(*_args: object, **_kwargs: object) -> ExternalProcessResult:
        raise RuntimeError("simulated runner failure")

    monkeypatch.setattr(service.external_jobs._runner, "run", fail_runner)
    response = service.run_ngspice_simulation(netlist="* runner failure\n.end\n")
    jobid = response["job"]["jobid"]
    deadline = time.monotonic() + 3
    while service.jobs.read(jobid).status not in {"failed", "cancelled"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)

    failed = service.jobs.read(jobid)
    assert failed.status == "failed"
    assert failed.error is not None
    assert "simulated runner failure" in failed.error["message"]


def test_service_refuses_over_cap_and_recovers_after_cancel(tmp_path: Path) -> None:
    executable = tmp_path / "fake_ngspice.py"
    executable.write_text("import time\ntime.sleep(10)\nprint('No. of Data Rows : 1')\n")
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
            ngspice_executable=executable,
            external_timeout_seconds=20,
            max_external_processes=1,
            max_external_log_bytes=2048,
            active_policy="automation",
        )
    )
    first = service.run_ngspice_simulation(netlist="* first\n.end\n")
    first_jobid = first["job"]["jobid"]
    deadline = time.monotonic() + 3
    while first_jobid not in service.external_jobs._processes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert first_jobid in service.external_jobs._processes

    with pytest.raises(ExternalToolFailedError) as exc_info:
        service.run_ngspice_simulation(netlist="* refused\n.end\n")
    assert exc_info.value.payload.code == "external_tool_failed"
    assert exc_info.value.details == {"max_external_processes": 1}

    service.cancel_job(first_jobid)
    deadline = time.monotonic() + 5
    while service.jobs.read(first_jobid).status not in {"cancelled", "failed"}:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert service.jobs.read(first_jobid).status == "cancelled"

    executable.write_text("print('No. of Data Rows : 2')\n")
    third = service.run_ngspice_simulation(netlist="* recovered\n.end\n")
    third_jobid = third["job"]["jobid"]
    deadline = time.monotonic() + 5
    while service.jobs.read(third_jobid).status not in {"completed", "failed"}:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert service.jobs.read(third_jobid).status == "completed"
