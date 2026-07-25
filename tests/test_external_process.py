from __future__ import annotations

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


def test_windows_process_creation_and_tree_kill_are_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    popen_calls: list[dict[str, object]] = []
    run_calls: list[tuple[list[str], dict[str, object]]] = []
    sentinel = object()

    def fake_popen(_command: list[str], **kwargs: object) -> object:
        popen_calls.append(kwargs)
        return sentinel

    def fake_run(command: list[str], **kwargs: object) -> object:
        run_calls.append((command, kwargs))
        return object()

    monkeypatch.setattr(external_process_module.os, "name", "nt")
    monkeypatch.setattr(
        external_process_module.subprocess,
        "CREATE_NEW_PROCESS_GROUP",
        512,
        raising=False,
    )
    monkeypatch.setattr(external_process_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(external_process_module.subprocess, "run", fake_run)

    process = external_process_module._start_process(
        ["solver.exe"],
        cwd=tmp_path,
        env={"PATH": "C:\\Windows"},
    )
    external_process_module._taskkill_process_tree(1234)

    assert process is sentinel
    assert popen_calls[0]["creationflags"] == 512
    assert popen_calls[0]["shell"] is False
    assert run_calls[0][0] == ["taskkill.exe", "/PID", "1234", "/T", "/F"]
    assert run_calls[0][1]["shell"] is False


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
