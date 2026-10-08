from __future__ import annotations

import io
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import anyio
from mcp import types
from mcp.shared.message import SessionMessage

import diptrace_mcp.server_runtime as runtime
from diptrace_mcp.server_inputs import DipTraceFastMCP


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
    calls: list[str] = []
    server = SimpleNamespace(
        stdio_streams=None,
        run=lambda *, transport: calls.append(transport),
    )
    monkeypatch.setattr(runtime, "create_server", lambda **_kwargs: server)
    monkeypatch.setenv("DIPTRACE_MCP_FROZEN_STDIO", "YES")

    runtime.main(["--transport", "stdio"])

    assert calls == ["stdio"]
    assert server.stdio_streams is runtime._robust_stdio_server


def test_custom_stdio_streams_serve_the_project_version() -> None:
    """A real initialize handshake over project-provided streams."""

    async def exercise() -> dict[str, Any]:
        server = DipTraceFastMCP(name="stdio-test", version="9.9.9")
        to_server, server_reads = anyio.create_memory_object_stream[Any](10)
        server_writes, from_server = anyio.create_memory_object_stream[Any](10)

        @asynccontextmanager
        async def streams() -> Any:
            yield server_reads, server_writes

        server.stdio_streams = streams
        request = types.JSONRPCMessage(
            types.JSONRPCRequest(
                jsonrpc="2.0",
                id=1,
                method="initialize",
                params={
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            )
        )
        with anyio.fail_after(10):
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(server.run_stdio_async)
                await to_server.send(SessionMessage(request))
                reply = await from_server.receive()
                await to_server.aclose()
        return cast(dict[str, Any], reply.message.root.result)

    result = anyio.run(exercise)

    assert result["serverInfo"] == {"name": "stdio-test", "version": "9.9.9"}


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


def test_streamable_http_app_serves_the_project_version() -> None:
    import httpx

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"},
        },
    }

    async def exercise() -> httpx.Response:
        server = DipTraceFastMCP(name="http-test", version="9.9.9", json_response=True)
        app = server.streamable_http_app()
        # The default localhost transport security only admits loopback hosts.
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1:8765",
            ) as client,
        ):
            return await client.post(
                "/mcp",
                json=request,
                headers={"Accept": "application/json, text/event-stream"},
            )

    response = anyio.run(exercise)

    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"] == {"name": "http-test", "version": "9.9.9"}
