#!/usr/bin/env python3
"""Manually probe whether WSL flock and Windows FileStream.Lock interoperate."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import platform
import subprocess
import uuid
from pathlib import Path, PureWindowsPath
from typing import BinaryIO

_PROBE_DIR_PREFIX = "mcp-diptrace-lock-probe-"
_POWERSHELL_UTF8 = (
    "$utf8 = [System.Text.UTF8Encoding]::new($false)\n"
    "[Console]::OutputEncoding = $utf8\n"
    "[Console]::InputEncoding = $utf8\n"
    "$OutputEncoding = $utf8\n"
)
_WINDOWS_ATTEMPT = r"""
$ErrorActionPreference = "Stop"
$stream = $null
$locked = $false
try {
    $stream = [System.IO.File]::Open(
        $env:DIPTRACE_LOCK_PROBE_FILE,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $stream.Lock(0, 1)
        $locked = $true
        [Console]::Out.WriteLine("ACQUIRED")
    }
    catch [System.IO.IOException] {
        [Console]::Out.WriteLine("BLOCKED")
    }
}
catch {
    $kind = $_.Exception.GetBaseException().GetType().FullName
    [Console]::Out.WriteLine("ERROR:" + $kind)
    exit 4
}
finally {
    if ($locked -and $null -ne $stream) {
        $stream.Unlock(0, 1)
    }
    if ($null -ne $stream) {
        $stream.Dispose()
    }
}
"""
_WINDOWS_HOLDER = r"""
$ErrorActionPreference = "Stop"
$stream = $null
$locked = $false
try {
    $stream = [System.IO.File]::Open(
        $env:DIPTRACE_LOCK_PROBE_FILE,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $stream.Lock(0, 1)
        $locked = $true
        [Console]::Out.WriteLine("LOCKED")
        [Console]::Out.Flush()
        [Console]::In.ReadLine() | Out-Null
    }
    catch [System.IO.IOException] {
        [Console]::Out.WriteLine("BLOCKED")
        [Console]::Out.Flush()
        exit 3
    }
}
catch {
    $kind = $_.Exception.GetBaseException().GetType().FullName
    [Console]::Out.WriteLine("ERROR:" + $kind)
    [Console]::Out.Flush()
    exit 4
}
finally {
    if ($locked -and $null -ne $stream) {
        $stream.Unlock(0, 1)
    }
    if ($null -ne $stream) {
        $stream.Dispose()
    }
}
"""


class ProbeError(RuntimeError):
    """Raised when the manual interoperability probe cannot complete safely."""


def parse_status(output: str, *, allowed: frozenset[str]) -> str:
    """Parse one exact status line from a PowerShell probe."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) != 1 or lines[0] not in allowed:
        raise ProbeError("PowerShell returned an unexpected probe status")
    return lines[0]


def _safe_powershell_failure(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) == 1 and lines[0].startswith("ERROR:"):
        kind = lines[0].removeprefix("ERROR:")
        if kind and all(character.isalnum() or character in "._" for character in kind):
            return kind
    return "unknown_error"


def _powershell(
    script: str,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"{_POWERSHELL_UTF8}\n{script}",
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=20,
    )


def _powershell_value(script: str) -> str:
    completed = _powershell(script)
    if completed.returncode != 0:
        raise ProbeError("PowerShell could not provide host metadata")
    values = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(values) != 1:
        raise ProbeError("PowerShell returned unexpected host metadata")
    return values[0]


def _windows_temp_paths() -> tuple[PureWindowsPath, Path]:
    windows_temp = PureWindowsPath(_powershell_value("[System.IO.Path]::GetTempPath()"))
    converted = subprocess.run(
        ["wslpath", "-u", str(windows_temp)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if converted.returncode != 0:
        raise ProbeError("wslpath could not translate Windows Temp")
    wsl_temp = Path(converted.stdout.strip())
    if not wsl_temp.is_absolute() or not wsl_temp.is_dir():
        raise ProbeError("Windows Temp did not translate to an existing WSL directory")
    return windows_temp, wsl_temp


def _probe_paths() -> tuple[PureWindowsPath, Path, Path]:
    windows_temp, wsl_temp = _windows_temp_paths()
    name = f"{_PROBE_DIR_PREFIX}{uuid.uuid4()}"
    windows_dir = windows_temp / name
    wsl_dir = wsl_temp / name
    if (
        wsl_dir.parent.resolve() != wsl_temp.resolve()
        or not wsl_dir.name.startswith(_PROBE_DIR_PREFIX)
    ):
        raise ProbeError("Refusing an unsafe temporary probe path")
    wsl_dir.mkdir(mode=0o700)
    lock_file = wsl_dir / "lock.bin"
    try:
        lock_file.write_bytes(b"0")
    except BaseException:
        lock_file.unlink(missing_ok=True)
        wsl_dir.rmdir()
        raise
    return windows_dir / "lock.bin", wsl_dir, lock_file


def _environment(windows_file: PureWindowsPath) -> dict[str, str]:
    environment = os.environ.copy()
    environment["DIPTRACE_LOCK_PROBE_FILE"] = str(windows_file)
    shared = [item for item in environment.get("WSLENV", "").split(":") if item]
    if not any(item.split("/", maxsplit=1)[0] == "DIPTRACE_LOCK_PROBE_FILE" for item in shared):
        shared.append("DIPTRACE_LOCK_PROBE_FILE")
    environment["WSLENV"] = ":".join(shared)
    return environment


def _probe_windows_contender(
    windows_file: PureWindowsPath,
    lock_file: Path,
) -> dict[str, object]:
    with lock_file.open("r+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            completed = _powershell(
                _WINDOWS_ATTEMPT,
                environment=_environment(windows_file),
            )
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    if completed.returncode != 0:
        kind = _safe_powershell_failure(completed.stdout)
        raise ProbeError(f"Windows FileStream contender failed ({kind})")
    contender_result = parse_status(
        completed.stdout,
        allowed=frozenset({"ACQUIRED", "BLOCKED"}),
    ).lower()
    return {
        "direction": "wsl_flock_to_windows_filestream",
        "holder": "wsl_flock",
        "contender": "windows_filestream_lock",
        "contender_result": contender_result,
        "compatible": contender_result == "blocked",
    }


def _try_wsl_flock(handle: BinaryIO) -> str:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in {errno.EACCES, errno.EAGAIN}:
            return "blocked"
        raise
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return "acquired"


def _stop_holder(process: subprocess.Popen[str]) -> None:
    if process.stdin is not None:
        try:
            process.stdin.write("\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        process.stdin.close()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _probe_wsl_contender(
    windows_file: PureWindowsPath,
    lock_file: Path,
) -> dict[str, object]:
    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"{_POWERSHELL_UTF8}\n{_WINDOWS_HOLDER}",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        env=_environment(windows_file),
    )
    try:
        if process.stdout is None:
            raise ProbeError("Windows FileStream holder has no output stream")
        holder_status = parse_status(
            process.stdout.readline(),
            allowed=frozenset({"LOCKED", "BLOCKED"}),
        )
        if holder_status != "LOCKED":
            raise ProbeError("Windows FileStream could not acquire the control lock")
        with lock_file.open("r+b") as handle:
            contender_result = _try_wsl_flock(handle)
    finally:
        _stop_holder(process)
    if process.returncode != 0:
        raise ProbeError("Windows FileStream holder failed")
    return {
        "direction": "windows_filestream_to_wsl_flock",
        "holder": "windows_filestream_lock",
        "contender": "wsl_flock",
        "contender_result": contender_result,
        "compatible": contender_result == "blocked",
    }


def _host_metadata() -> dict[str, str]:
    windows = _powershell_value(
        "(Get-CimInstance Win32_OperatingSystem).Caption + '|' + "
        "[System.Environment]::OSVersion.Version.ToString() + '|' + "
        "$PSVersionTable.PSVersion.ToString()"
    )
    parts = windows.split("|")
    if len(parts) != 3:
        raise ProbeError("PowerShell returned incomplete host metadata")
    return {
        "windows_product": parts[0],
        "windows_version": parts[1],
        "powershell_version": parts[2],
        "wsl_kernel": platform.release(),
        "python_version": platform.python_version(),
    }


def build_report(
    *,
    host: dict[str, str],
    results: list[dict[str, object]],
    cleanup: str,
) -> dict[str, object]:
    """Build the stable, path-free JSON report."""
    return {
        "schema_version": 1,
        "probe": "windows_wsl_file_lock_interop",
        "host": host,
        "results": results,
        "overall_compatible": all(result["compatible"] is True for result in results),
        "cleanup": cleanup,
    }


def run_probe() -> dict[str, object]:
    windows_file: PureWindowsPath | None = None
    probe_dir: Path | None = None
    lock_file: Path | None = None
    results: list[dict[str, object]] = []
    cleanup = "not_started"
    caught: BaseException | None = None
    try:
        windows_file, probe_dir, lock_file = _probe_paths()
        results.append(_probe_windows_contender(windows_file, lock_file))
        results.append(_probe_wsl_contender(windows_file, lock_file))
    except BaseException as exc:
        caught = exc
    finally:
        cleanup = "completed"
        try:
            if lock_file is not None:
                lock_file.unlink(missing_ok=True)
            if probe_dir is not None:
                probe_dir.rmdir()
        except OSError:
            cleanup = "failed"
    if caught is not None:
        if cleanup == "failed":
            raise ProbeError(
                "Probe failed and its temporary directory could not be cleaned"
            ) from caught
        raise caught
    if cleanup != "completed":
        raise ProbeError("Temporary probe directory could not be cleaned")
    return build_report(host=_host_metadata(), results=results, cleanup=cleanup)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        report = run_probe()
    except (OSError, ProbeError, UnicodeError, subprocess.SubprocessError) as exc:
        failure = {
            "schema_version": 1,
            "probe": "windows_wsl_file_lock_interop",
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc) if isinstance(exc, ProbeError) else "host_interop_error",
        }
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
