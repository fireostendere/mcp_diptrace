from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import Any

import pytest

from diptrace_mcp import windows_job as wj


class _FakeCall:
    def __init__(self, result: Any = None, handler: Callable[..., Any] | None = None) -> None:
        self.result = result
        self.handler = handler
        self.argtypes: Any = None
        self.restype: Any = None
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.handler is None:
            return self.result
        return self.handler(*args, **kwargs)


class _FakeKernel:
    def __init__(self) -> None:
        self.CreateJobObjectW = _FakeCall()
        self.SetInformationJobObject = _FakeCall()
        self.CloseHandle = _FakeCall()
        self.OpenProcess = _FakeCall()
        self.AssignProcessToJobObject = _FakeCall()
        self.TerminateJobObject = _FakeCall()
        self.CreateToolhelp32Snapshot = _FakeCall()
        self.Thread32First = _FakeCall()
        self.Thread32Next = _FakeCall()
        self.OpenThread = _FakeCall()
        self.ResumeThread = _FakeCall()


def _kernel() -> _FakeKernel:
    return _FakeKernel()


def test_load_kernel32_rejects_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wj.os, "name", "posix")

    with pytest.raises(OSError, match="Windows Job Objects are only available on Windows"):
        wj._load_kernel32()


def test_load_kernel32_rejects_missing_windll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wj.os, "name", "nt")
    monkeypatch.setattr(wj.ctypes, "WinDLL", None, raising=False)

    with pytest.raises(OSError, match="ctypes.WinDLL is unavailable"):
        wj._load_kernel32()


def test_create_job_object_success(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.CreateJobObjectW = _FakeCall(42)
    kernel.SetInformationJobObject = _FakeCall(True)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 0, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    job = wj.KillOnCloseJob.create()

    assert job._handle == 42
    assert bool(kernel.CreateJobObjectW.calls)


def test_create_job_object_fails_on_kernel_error(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.CreateJobObjectW = _FakeCall(0)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 87, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    with pytest.raises(OSError, match="CreateJobObjectW failed with Windows error 87"):
        wj.KillOnCloseJob.create()


def test_create_job_object_releases_handle_on_set_information_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _kernel()
    kernel.CreateJobObjectW = _FakeCall(17)
    kernel.SetInformationJobObject = _FakeCall(False)
    close = _FakeCall()
    kernel.CloseHandle = close
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 123, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    with pytest.raises(OSError, match="SetInformationJobObject failed with Windows error 123"):
        wj.KillOnCloseJob.create()

    assert close.calls and close.calls[0][0][0] == 17


def test_assign_process_raises_if_job_is_closed() -> None:
    job = wj.KillOnCloseJob(17)
    job._handle = None

    with pytest.raises(OSError, match="Windows Job Object is already closed"):
        job.assign(123)


def test_assign_process_success(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.OpenProcess = _FakeCall(99)
    kernel.AssignProcessToJobObject = _FakeCall(True)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 0, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    job = wj.KillOnCloseJob(17)
    job.assign(123)

    assert kernel.AssignProcessToJobObject.calls
    assert kernel.CloseHandle.calls[-1][0][0] == 99


def test_assign_process_fails_to_open(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.OpenProcess = _FakeCall(0)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    job = wj.KillOnCloseJob(17)

    with pytest.raises(OSError, match="OpenProcess failed with Windows error 5"):
        job.assign(123)


def test_assign_process_fails_to_attach(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.OpenProcess = _FakeCall(99)
    kernel.AssignProcessToJobObject = _FakeCall(False)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    job = wj.KillOnCloseJob(17)

    with pytest.raises(OSError, match="AssignProcessToJobObject failed with Windows error 5"):
        job.assign(123)

    assert kernel.CloseHandle.calls[-1][0][0] == 99


def test_terminate_and_close_job_returns_when_closed() -> None:
    job = wj.KillOnCloseJob(17)
    job._handle = None

    job.terminate_and_close()


def test_terminate_and_close_job(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.TerminateJobObject = _FakeCall(True)
    kernel.CloseHandle = _FakeCall(True)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    job = wj.KillOnCloseJob(17)
    job.terminate_and_close()

    assert job._handle is None


def test_resume_suspended_process_success(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()

    def thread_first(snapshot: int, entry_ptr: Any) -> bool:
        entry = ctypes.cast(entry_ptr, ctypes.POINTER(wj._ThreadEntry32)).contents
        entry.th32OwnerProcessID = 123
        entry.th32ThreadID = 321
        return True

    kernel.CreateToolhelp32Snapshot = _FakeCall(7)
    kernel.Thread32First = _FakeCall(handler=thread_first)
    kernel.OpenThread = _FakeCall(19)
    kernel.ResumeThread = _FakeCall(1)
    kernel.CloseHandle = _FakeCall(True)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    wj.resume_suspended_process(123)

    assert kernel.Thread32First.calls
    assert kernel.OpenThread.calls
    assert kernel.ResumeThread.calls


def test_resume_suspended_process_missing_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.CreateToolhelp32Snapshot = _FakeCall(0)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 99, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    with pytest.raises(OSError, match="CreateToolhelp32Snapshot failed with Windows error 99"):
        wj.resume_suspended_process(123)

    assert kernel.CreateToolhelp32Snapshot.calls


def test_resume_suspended_process_missing_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    kernel = _kernel()
    kernel.CreateToolhelp32Snapshot = _FakeCall(7)
    kernel.Thread32First = _FakeCall(False)
    kernel.CloseHandle = _FakeCall(True)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    with pytest.raises(OSError, match="Could not find the suspended primary thread"):
        wj.resume_suspended_process(123)

    assert kernel.Thread32First.calls


def test_resume_suspended_process_open_thread_or_resume_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel = _kernel()

    def thread_first(snapshot: int, entry_ptr: Any) -> bool:
        entry = ctypes.cast(entry_ptr, ctypes.POINTER(wj._ThreadEntry32)).contents
        entry.th32OwnerProcessID = 123
        entry.th32ThreadID = 321
        return True

    kernel.CreateToolhelp32Snapshot = _FakeCall(7)
    kernel.Thread32First = _FakeCall(handler=thread_first)
    kernel.OpenThread = _FakeCall(0)
    monkeypatch.setattr(wj.ctypes, "get_last_error", lambda: 15, raising=False)
    monkeypatch.setattr(wj, "_load_kernel32", lambda: kernel)

    with pytest.raises(OSError, match="OpenThread failed with Windows error 15"):
        wj.resume_suspended_process(123)

    kernel.OpenThread = _FakeCall(19)
    kernel.ResumeThread = _FakeCall(0xFFFFFFFF)
    with pytest.raises(OSError, match="ResumeThread failed with Windows error 15"):
        wj.resume_suspended_process(123)
