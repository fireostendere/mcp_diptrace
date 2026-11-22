from __future__ import annotations

import argparse
import os
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from queue import Empty, Queue
from typing import Any

import anyio
from mcp import types
from mcp.shared.message import SessionMessage

from . import __version__, tools
from .config import Settings
from .server_inputs import (
    DipTraceFastMCP,
)
from .service import DipTraceService


def create_server(
    settings: Settings | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> DipTraceFastMCP:
    service = DipTraceService(settings or Settings.from_env())
    mcp = DipTraceFastMCP(
        name="DipTrace MCP",
        instructions=(
            "Inspect and safely edit DipTrace XML. Without a path, tools use the active live "
            "DipTrace bridge session. Prefer semantic tools with preview/commit/rollback. "
            "Low-level XML edits remain available for expert use. Stable object ids come from "
            "query_objects or normalized model/list tools; transaction, plan, report, export and "
            "job ids come from their corresponding create/run tools."
        ),
        json_response=True,
        host=host,
        port=port,
        version=__version__,
    )
    for module in tools.MODULES:
        module.register(mcp, service)

    from .tool_capabilities import tool_capability_mapping

    tool_capability_mapping(mcp.tool_bodies)
    service.set_workflow_prompt_names(tuple(mcp.prompt_names))
    return mcp
@asynccontextmanager
async def _robust_stdio_server() -> AsyncIterator[tuple[Any, Any]]:
    """Provide MCP stdio streams without anyio's stdin file wrapper.

    Some Windows/WSL combinations do not wake an ``anyio.wrap_file`` worker
    reliably for an inherited pipe. A dedicated reader thread keeps the
    protocol transport line-oriented while the MCP lifecycle remains owned by
    the pinned SDK server.
    """

    incoming: Queue[SessionMessage | Exception | None] = Queue()
    read_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_reader = anyio.create_memory_object_stream(0)

    def read_stdin() -> None:
        binary_stdin = getattr(sys.stdin, "buffer", sys.stdin)
        for raw_line in binary_stdin:
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else raw_line
            )
            try:
                message = types.JSONRPCMessage.model_validate_json(line)
            except Exception as exc:  # protocol error is returned through MCP handling
                incoming.put(exc)
            else:
                incoming.put(SessionMessage(message))
        incoming.put(None)

    async def forward_input() -> None:
        # A blocking get on a private worker thread wakes as soon as a line
        # arrives instead of polling at 100 Hz; the timeout bounds shutdown.
        # The private limiter keeps busy tool threads from starving input.
        reader_limiter = anyio.CapacityLimiter(1)
        try:
            while True:
                try:
                    message = await anyio.to_thread.run_sync(
                        incoming.get,
                        True,
                        0.5,
                        limiter=reader_limiter,
                    )
                except Empty:
                    continue
                if message is None:
                    return
                await read_writer.send(message)
        finally:
            await read_writer.aclose()

    async def forward_output() -> None:
        async with write_reader:
            async for message in write_reader:
                payload = message.message.model_dump_json(by_alias=True, exclude_none=True)
                binary_stdout = getattr(sys.stdout, "buffer", None)
                if binary_stdout is not None:
                    binary_stdout.write((payload + "\n").encode("utf-8"))
                    binary_stdout.flush()
                else:  # StringIO and other text-only test streams.
                    sys.stdout.write(payload + "\n")
                    sys.stdout.flush()

    threading.Thread(target=read_stdin, name="diptrace-mcp-stdin", daemon=True).start()
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(forward_input)
        task_group.start_soon(forward_output)
        yield read_stream, write_stream
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server for DipTrace XML and live projects")
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("DIPTRACE_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("DIPTRACE_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DIPTRACE_MCP_PORT", "8765")),
    )
    args = parser.parse_args(argv)
    server = create_server(host=args.host, port=args.port)
    use_frozen_stdio = bool(getattr(sys, "frozen", False)) or os.environ.get(
        "DIPTRACE_MCP_FROZEN_STDIO", ""
    ).strip().casefold() in {"1", "true", "yes"}
    if args.transport == "stdio" and use_frozen_stdio:
        server.stdio_streams = _robust_stdio_server
    server.run(transport=args.transport)
if __name__ == "__main__":
    main()
