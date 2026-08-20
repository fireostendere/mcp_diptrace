"""Exercise a frozen MCP server through JSON-RPC stdio using only stdlib."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


class SmokeError(RuntimeError):
    pass


def _reader(stream: Any, output: queue.Queue[str]) -> None:
    for line in iter(stream.readline, ""):
        output.put(line)
    output.put("")


def _read_message(output: queue.Queue[str], timeout: float) -> dict[str, Any]:
    try:
        line = output.get(timeout=timeout)
    except queue.Empty as exc:
        raise SmokeError("MCP server did not produce a response before timeout") from exc
    if not line:
        raise SmokeError("MCP server exited before completing stdio handshake")
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise SmokeError("MCP server wrote non-JSON data to stdout") from exc
    if not isinstance(message, dict):
        raise SmokeError("MCP server response was not an object")
    return message


def _stop_process(process: subprocess.Popen[str], shutdown_timeout: float) -> None:
    """Close stdin, then bound graceful shutdown before force-killing a hung child."""
    if process.stdin is not None:
        with contextlib.suppress(OSError):
            process.stdin.close()
    try:
        process.wait(timeout=shutdown_timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=shutdown_timeout)


def run_smoke(
    server: Path,
    workspace: Path,
    document: str,
    timeout: float,
    shutdown_timeout: float = 5.0,
) -> dict[str, Any]:
    if not server.is_file():
        raise SmokeError(f"server executable is missing: {server}")
    server = server.resolve()
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["DIPTRACE_MCP_WORKSPACE"] = str(workspace.resolve())
    with tempfile.TemporaryDirectory(prefix="diptrace-mcp-frozen-state-") as state_dir:
        environment["DIPTRACE_MCP_STATE_DIR"] = state_dir
        process = subprocess.Popen(
            [str(server)],
            cwd=str(server.parent),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        output: queue.Queue[str] = queue.Queue()
        error_output: queue.Queue[str] = queue.Queue()
        thread = threading.Thread(target=_reader, args=(process.stdout, output), daemon=True)
        error_thread = threading.Thread(
            target=_reader, args=(process.stderr, error_output), daemon=True
        )
        thread.start()
        error_thread.start()
        started_at = time.perf_counter()

        def send(message: dict[str, Any]) -> None:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()

        try:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "diptrace-frozen-smoke", "version": "1"},
                    },
                }
            )
            initialize = _read_message(output, timeout)
            initialize_seconds = time.perf_counter() - started_at
            if initialize.get("id") != 1 or "result" not in initialize:
                raise SmokeError("initialize did not return a result")
            send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools = _read_message(output, timeout)
            tools_list_seconds = time.perf_counter() - started_at
            if tools.get("id") != 2 or "result" not in tools:
                raise SmokeError("tools/list did not return a result")
            names = {item.get("name") for item in tools["result"].get("tools", [])}
            required = {"get_capabilities", "get_document_info"}
            if not required.issubset(names):
                raise SmokeError(
                    f"required read-only tools are missing: {sorted(required - names)}"
                )
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "get_capabilities", "arguments": {}},
                }
            )
            capabilities = _read_message(output, timeout)
            if capabilities.get("id") != 3 or "result" not in capabilities:
                raise SmokeError("get_capabilities did not return a result")
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "get_document_info", "arguments": {"path": document}},
                }
            )
            document_info = _read_message(output, timeout)
            if document_info.get("id") != 4 or "result" not in document_info:
                raise SmokeError("get_document_info did not return a result")
            return {
                "tools": len(names),
                "initialize": True,
                "tools_list": True,
                "initialize_seconds": round(initialize_seconds, 3),
                "tools_list_seconds": round(tools_list_seconds, 3),
                "get_capabilities": True,
                "get_document_info": True,
                "geometry_backend": capabilities["result"]
                .get("structuredContent", {})
                .get("geometry_backend"),
            }
        finally:
            _stop_process(process, shutdown_timeout)
            diagnostics: list[str] = []
            while True:
                try:
                    line = error_output.get_nowait()
                except queue.Empty:
                    break
                if line:
                    diagnostics.append(line.rstrip())
            if diagnostics:
                print("frozen server stderr:", file=sys.stderr)
                print("\n".join(diagnostics), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--document", default="pcb.xml")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=5.0,
        help="Seconds to allow graceful server shutdown before force-killing it.",
    )
    args = parser.parse_args(argv)
    try:
        print(
            json.dumps(
                run_smoke(
                    args.server,
                    args.workspace,
                    args.document,
                    args.timeout,
                    args.shutdown_timeout,
                ),
                sort_keys=True,
            )
        )
    except (OSError, SmokeError) as exc:
        print(f"frozen server smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
