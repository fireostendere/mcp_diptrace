from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected source block not found in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/diptrace_mcp/external_adapters.py",
    '''        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
''',
    '''        try:
            if cancel.is_set():
                raise JobCancelledError(
                    "External autorouter job was cancelled", jobid=jobid
                )
            with log_path.open("wb") as log:
                process = subprocess.Popen(
''',
)
replace_once(
    "src/diptrace_mcp/external_adapters.py",
    '''                return_code = process.returncode
            elapsed = time.monotonic() - started
            if return_code != 0:
''',
    '''                if cancel.is_set():
                    raise JobCancelledError(
                        "External autorouter job was cancelled", jobid=jobid
                    )
                return_code = process.returncode
            elapsed = time.monotonic() - started
            if return_code != 0:
''',
)
replace_once(
    "src/diptrace_mcp/external_adapters.py",
    '''        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
''',
    '''        try:
            if cancel.is_set():
                raise JobCancelledError("ngspice job was cancelled", jobid=jobid)
            with log_path.open("wb") as log:
                process = subprocess.Popen(
''',
)
replace_once(
    "src/diptrace_mcp/external_adapters.py",
    '''                return_code = process.returncode
            elapsed = time.monotonic() - started
            self._bound_log(log_path)
            log_bytes = log_path.read_bytes() if log_path.is_file() else b""
''',
    '''                if cancel.is_set():
                    raise JobCancelledError("ngspice job was cancelled", jobid=jobid)
                return_code = process.returncode
            elapsed = time.monotonic() - started
            self._bound_log(log_path)
            log_bytes = log_path.read_bytes() if log_path.is_file() else b""
''',
)
replace_once(
    "src/diptrace_mcp/external_adapters.py",
    '''        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
''',
    '''        try:
            if cancel.is_set():
                raise JobCancelledError("openEMS job was cancelled", jobid=jobid)
            with log_path.open("wb") as log:
                process = subprocess.Popen(
''',
)
replace_once(
    "src/diptrace_mcp/external_adapters.py",
    '''                return_code = process.returncode
            elapsed = time.monotonic() - started
            self._bound_log(log_path)
            if return_code != 0:
''',
    '''                if cancel.is_set():
                    raise JobCancelledError("openEMS job was cancelled", jobid=jobid)
                return_code = process.returncode
            elapsed = time.monotonic() - started
            self._bound_log(log_path)
            if return_code != 0:
''',
)
replace_once(
    "tests/test_specctra.py",
    '''    jobid = service.run_external_autorouter(str(board), dsn_path=str(dsn))["job"]["jobid"]

    service.cancel_job(jobid)
''',
    '''    jobid = service.run_external_autorouter(str(board), dsn_path=str(dsn))["job"]["jobid"]

    deadline = time.monotonic() + 2.0
    while jobid not in service.external_jobs._processes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert jobid in service.external_jobs._processes

    service.cancel_job(jobid)
''',
)
