from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any, ClassVar

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_TH32CS_SNAPTHREAD = 0x00000004
_THREAD_SUSPEND_RESUME = 0x0002
_INVALID_DWORD = 0xFFFFFFFF


class _IoCounters(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _load_kernel32() -> Any:
    if os.name != "nt":
        raise OSError("Windows Job Objects are only available on Windows")
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError("ctypes.WinDLL is unavailable")
    return loader("kernel32", use_last_error=True)


def _last_error(operation: str) -> OSError:
    get_last_error = getattr(ctypes, "get_last_error", None)
    error_code = int(get_last_error()) if get_last_error is not None else 0
    return OSError(error_code, f"{operation} failed with Windows error {error_code}")


class KillOnCloseJob:
    """A Windows Job Object whose members die when its owning handle closes."""

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    @classmethod
    def create(cls) -> KillOnCloseJob:
        kernel32 = _load_kernel32()
        create_job = kernel32.CreateJobObjectW
        create_job.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        create_job.restype = wintypes.HANDLE
        set_information = kernel32.SetInformationJobObject
        set_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        set_information.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        raw_handle = create_job(None, None)
        if not raw_handle:
            raise _last_error("CreateJobObjectW")
        handle = int(raw_handle)
        limits = _JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not set_information(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = _last_error("SetInformationJobObject")
            close_handle(handle)
            raise error
        return cls(handle)

    def assign(self, pid: int) -> None:
        if self._handle is None:
            raise OSError("Windows Job Object is already closed")
        kernel32 = _load_kernel32()
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        assign_process = kernel32.AssignProcessToJobObject
        assign_process.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        assign_process.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        raw_process_handle = open_process(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE,
            False,
            pid,
        )
        if not raw_process_handle:
            raise _last_error("OpenProcess")
        process_handle = int(raw_process_handle)
        try:
            if not assign_process(self._handle, process_handle):
                raise _last_error("AssignProcessToJobObject")
        finally:
            close_handle(process_handle)

    def terminate_and_close(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        kernel32 = _load_kernel32()
        terminate_job = kernel32.TerminateJobObject
        terminate_job.argtypes = [wintypes.HANDLE, wintypes.UINT]
        terminate_job.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        # KILL_ON_JOB_CLOSE is the kernel-backed guarantee. Terminate first so
        # descendants are stopped before the caller waits for pipe EOF.
        terminate_job(handle, 1)
        close_handle(handle)


def resume_suspended_process(pid: int) -> None:
    """Resume the sole primary thread of a newly created suspended process."""

    kernel32 = _load_kernel32()
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    create_snapshot.restype = wintypes.HANDLE
    thread_first = kernel32.Thread32First
    thread_first.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    thread_first.restype = wintypes.BOOL
    thread_next = kernel32.Thread32Next
    thread_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    thread_next.restype = wintypes.BOOL
    open_thread = kernel32.OpenThread
    open_thread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_thread.restype = wintypes.HANDLE
    resume_thread = kernel32.ResumeThread
    resume_thread.argtypes = [wintypes.HANDLE]
    resume_thread.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    raw_snapshot = create_snapshot(_TH32CS_SNAPTHREAD, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if not raw_snapshot or int(raw_snapshot) == invalid_handle:
        raise _last_error("CreateToolhelp32Snapshot")
    snapshot = int(raw_snapshot)
    try:
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        has_entry = bool(thread_first(snapshot, ctypes.byref(entry)))
        while has_entry:
            if int(entry.th32OwnerProcessID) == pid:
                raw_thread = open_thread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                if not raw_thread:
                    raise _last_error("OpenThread")
                thread = int(raw_thread)
                try:
                    if int(resume_thread(thread)) == _INVALID_DWORD:
                        raise _last_error("ResumeThread")
                finally:
                    close_handle(thread)
                return
            has_entry = bool(thread_next(snapshot, ctypes.byref(entry)))
    finally:
        close_handle(snapshot)
    raise OSError(f"Could not find the suspended primary thread for process {pid}")
