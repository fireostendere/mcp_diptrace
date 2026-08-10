from __future__ import annotations

import io
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import anyio
from mcp.shared.message import SessionMessage

import diptrace_mcp.server  # noqa: F401 - installs the stdio async-context-manager seam
import diptrace_mcp.server_runtime as runtime


def test_runtime_main_dispatches_http_and_plain_stdio(monkeypatch: Any) -> None:
    calls: list[tuple[object, ...]] = []

    class FakeServer:
        def run(self, *, transport: str) -> None:
            calls.append(("run", transport))

    def fake_create_server(*, host: str, port: int) -> FakeServer:
        calls.append(("create", host, port))
        return FakeServer()

    monkeypatch.setattr(runtime, "create_server", fake_create_server)
    monkeypatch.delenv("DIPTRACE_MCP_FROZEN_STDIO", raising=False)
    monkeypatch.delattr(runtime.sys, "frozen", raising=False)

    runtime.main(["--transport", "streamable-http", "--host", "127.0.0.2", "--port", "9001"])
    runtime.main(["--transport", "stdio"])

    assert ("create", "127.0.0.2", 9001) in calls
    assert ("run", "streamable-http") in calls
    assert ("run", "stdio") in calls


def test_runtime_main_uses_frozen_stdio_runner(monkeypatch: Any) -> None:
    server = SimpleNamespace()
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(runtime, "create_server", lambda **_kwargs: server)
    monkeypatch.setenv("DIPTRACE_MCP_FROZEN_STDIO", "YES")

    def fake_anyio_run(function: object, argument: object) -> None:
        calls.append((function, argument))

    monkeypatch.setattr(runtime.anyio, "run", fake_anyio_run)

    runtime.main(["--transport", "stdio"])

    assert calls == [(runtime._run_stdio, server)]


def test_run_stdio_uses_context_streams_and_initialization_options(monkeypatch: Any) -> None:
    seen: list[object] = []
    read_stream = object()
    write_stream = object()

    @asynccontextmanager
    async def fake_stdio() -> Any:
        seen.append("entered")
        yield read_stream, write_stream
        seen.append("exited")

    class InnerServer:
        def create_initialization_options(self) -> dict[str, bool]:
            seen.append("options")
            return {"ready": True}

        async def run(self, read: object, write: object, options: object) -> None:
            seen.append((read, write, options))

    monkeypatch.setattr(runtime, "_robust_stdio_server", fake_stdio)
    server = SimpleNamespace(_mcp_server=InnerServer())

    anyio.run(runtime._run_stdio, server)

    assert seen == [
        "entered",
        "options",
        (read_stream, write_stream, {"ready": True}),
        "exited",
    ]


def test_robust_stdio_forwards_valid_invalid_input_and_output(monkeypatch: Any) -> None:
    source = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n' 'not-json\n')
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdin", source)
    monkeypatch.setattr(runtime.sys, "stdout", output)

    class ImmediateThread:
        def __init__(self, *, target: object, **_kwargs: object) -> None:
            self.target = target

        def start(self) -> None:
            assert callable(self.target)
            self.target()

    monkeypatch.setattr(runtime.threading, "Thread", ImmediateThread)

    async def exercise() -> None:
        async with runtime._robust_stdio_server() as (read_stream, write_stream):
            first = await read_stream.receive()
            second = await read_stream.receive()
            assert isinstance(first, SessionMessage)
            assert isinstance(second, Exception)
            await write_stream.send(first)
            await write_stream.aclose()

    anyio.run(exercise)

    rendered = output.getvalue()
    assert '"jsonrpc":"2.0"' in rendered
    assert '"method":"ping"' in rendered
