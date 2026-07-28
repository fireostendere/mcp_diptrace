#!/usr/bin/env python3
"""Exercise the real headless bridge process and its file-control handshake."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.xml_document import sha256_bytes

_SOURCE = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm"></Source>\n'
)
_MODIFIED = _SOURCE.replace(b"</Source>", b"<!-- headless CI smoke --></Source>")


def _wait_for_active(store: SessionStore, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"bridge exited before publishing a session ({process.returncode}): "
                f"{stdout}{stderr}"
            )
        metadata = store.active_metadata()
        if metadata is not None:
            return metadata
        time.sleep(0.05)
    raise RuntimeError("bridge did not publish an active session within 10 seconds")


def run_smoke() -> None:
    with tempfile.TemporaryDirectory(prefix="diptrace-bridge-smoke-") as raw_tmp:
        root = Path(raw_tmp)
        exchange = root / "plugin_exchange.xml"
        state = root / "state"
        exchange.write_bytes(_SOURCE)
        environment = os.environ.copy()
        environment.update(
            {
                "DIPTRACE_MCP_WORKSPACE": str(root),
                "DIPTRACE_MCP_ALLOWED_ROOTS": str(root),
                "DIPTRACE_MCP_STATE_DIR": str(state),
            }
        )
        command = [
            sys.executable,
            "-m",
            "diptrace_mcp.bridge",
            "--headless",
            "--timeout",
            "15",
            str(exchange),
        ]
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            store = SessionStore(state, allowed_roots=(root,))
            metadata = _wait_for_active(store, process)
            session_id = str(metadata["session_id"])
            store.working_path(session_id).write_bytes(_MODIFIED)
            store.request_finish(
                "apply",
                sha256_bytes(store.working_path(session_id).read_bytes()),
            )
            stdout, stderr = process.communicate(timeout=10)
        except Exception:
            process.kill()
            process.communicate()
            raise

        if process.returncode != 0:
            raise RuntimeError(
                f"headless bridge failed with {process.returncode}: {stdout}{stderr}"
            )
        if exchange.read_bytes() != _MODIFIED:
            raise RuntimeError("headless bridge did not apply the controlled working XML")
        result = store.read_metadata(session_id)
        if result.get("status") != "applied" or store.active_metadata() is not None:
            raise RuntimeError("headless bridge did not finalize and clear its session")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        run_smoke()
    except (OSError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("OK: headless bridge applied controlled XML and finalized its session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
