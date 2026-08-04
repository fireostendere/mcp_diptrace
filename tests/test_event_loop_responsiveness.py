from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService
from scripts.audit_event_loop import HEAVY_TOOL_NAMES, audit_event_loop_boundary

FIXTURES = Path(__file__).parent / "fixtures"
_MAX_HEARTBEAT_LATENCY_SECONDS = 0.8


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        workspace=FIXTURES,
        allowed_roots=(FIXTURES,),
        state_dir=tmp_path,
    )


def test_all_public_tools_use_the_project_thread_offload_contract() -> None:
    audit = audit_event_loop_boundary()

    assert audit["status"] == "pass"
    assert audit["tool_count"] == audit["offloaded_tool_count"]
    assert audit["unprotected_sync_tools"] == []
    assert audit["unreviewed_async_tools"] == []
    assert audit["missing_heavy_tools"] == []
    assert audit["heavy_tools_without_offload"] == []
    assert set(audit["heavy_tools"]) == HEAVY_TOOL_NAMES


def _run_responsiveness_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    slow_implementation: Callable[[DipTraceService, threading.Event], dict[str, object]],
) -> float:
    async def verify() -> float:
        original = DipTraceService.get_capabilities
        started = threading.Event()

        def slow_get_capabilities(
            self: DipTraceService,
            path: str | None = None,
        ) -> dict[str, object]:
            del path
            result = slow_implementation(self, started)
            if result:
                return result
            return original(self, None)

        monkeypatch.setattr(DipTraceService, "get_capabilities", slow_get_capabilities)
        server = create_server(_settings(tmp_path))

        async with create_connected_server_and_client_session(server) as session:
            probe_started = time.perf_counter()
            slow_call = asyncio.create_task(session.call_tool("get_capabilities", {}))
            started_in_time = await asyncio.to_thread(started.wait, 3.0)
            assert started_in_time, "the synthetic slow MCP call never started"

            await asyncio.sleep(0.05)
            heartbeat_latency = time.perf_counter() - probe_started

            result = await asyncio.wait_for(slow_call, timeout=4.0)
            assert not result.isError
            return heartbeat_latency

    return asyncio.run(verify())


def test_blocking_io_tool_does_not_freeze_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    watchdog = threading.Timer(2.0, release.set)
    watchdog.daemon = True
    watchdog.start()

    def blocking_io(
        service: DipTraceService,
        started: threading.Event,
    ) -> dict[str, object]:
        del service
        started.set()
        if not release.wait(3.0):
            raise RuntimeError("synthetic blocking I/O probe timed out")
        return {}

    try:
        latency = _run_responsiveness_probe(tmp_path, monkeypatch, blocking_io)
    finally:
        release.set()
        watchdog.cancel()

    assert latency < _MAX_HEARTBEAT_LATENCY_SECONDS


def test_cpu_bound_tool_does_not_freeze_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cpu_bound(
        service: DipTraceService,
        started: threading.Event,
    ) -> dict[str, object]:
        del service
        started.set()
        deadline = time.perf_counter() + 1.25
        accumulator = 0
        while time.perf_counter() < deadline:
            accumulator = (accumulator * 33 + 17) % 1_000_003
        return {"probe_accumulator": accumulator}

    latency = _run_responsiveness_probe(tmp_path, monkeypatch, cpu_bound)

    assert latency < _MAX_HEARTBEAT_LATENCY_SECONDS
