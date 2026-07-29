from __future__ import annotations

import json
import multiprocessing
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty
from typing import Any

import pytest

import diptrace_mcp.sessions as sessions_module
from diptrace_mcp.errors import SessionError
from diptrace_mcp.sessions import SessionStore

FIXTURES = Path(__file__).parent / "fixtures"


def _capture_call(
    barrier: threading.Barrier,
    operation: Callable[[], dict[str, Any]],
) -> tuple[str, str]:
    barrier.wait()
    try:
        result = operation()
    except SessionError as exc:
        return "error", exc.payload.code
    return "ok", str(result["session_id"])


def _process_create(
    state_dir: str,
    exchange_path: str,
    barrier: Any,
    results: Any,
    release: Any,
) -> None:
    barrier.wait()
    try:
        store = SessionStore(Path(state_dir), 10_000_000)
        metadata = store.create(Path(exchange_path))
    except SessionError as exc:
        results.put(("error", exc.payload.code))
    else:
        results.put(("ok", str(metadata["session_id"])))
        # Keep the winning bridge PID alive while the parent verifies that the
        # single active record is not mistaken for a crashed bridge.
        release.wait(timeout=30)


def _assert_session_json_is_consistent(
    store: SessionStore,
    session_id: str,
    *,
    expected_status: str,
) -> None:
    metadata = json.loads(store.metadata_path(session_id).read_text(encoding="utf-8"))
    assert metadata["session_id"] == session_id
    assert metadata["status"] == expected_status
    if store.control_path(session_id).exists():
        control = json.loads(store.control_path(session_id).read_text(encoding="utf-8"))
        assert control["action"] in {"apply", "cancel"}
        assert len(control["expected_sha256"]) == 64


def test_two_threads_create_exactly_one_active_session(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state_dir = tmp_path / "state"
    stores = [
        SessionStore(state_dir, 10_000_000),
        SessionStore(state_dir, 10_000_000),
    ]
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_capture_call, barrier, lambda store=store: store.create(exchange))
            for store in stores
        ]
    results = [future.result() for future in futures]

    winners = [value for status, value in results if status == "ok"]
    errors = [value for status, value in results if status == "error"]
    assert len(winners) == 1
    assert errors == [SessionError.code]
    store = stores[0]
    active = store.active_metadata()
    assert active is not None
    assert active["session_id"] == winners[0]
    _assert_session_json_is_consistent(store, winners[0], expected_status="active")

    store.finalize(winners[0], "cancel")
    replacement = store.create(exchange)
    assert replacement["session_id"] != winners[0]
    store.finalize(str(replacement["session_id"]), "cancel")


def test_two_processes_create_exactly_one_active_session(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state_dir = tmp_path / "state"
    SessionStore(state_dir, 10_000_000)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    release = context.Event()
    processes = [
        context.Process(
            target=_process_create,
            args=(str(state_dir), str(exchange), barrier, results, release),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    try:
        try:
            outcomes = [results.get(timeout=5) for _ in processes]
        except Empty:
            pytest.fail("A session-create worker exited without reporting an outcome")

        winners = [value for status, value in outcomes if status == "ok"]
        errors = [value for status, value in outcomes if status == "error"]
        assert len(winners) == 1
        assert errors == [SessionError.code]
        store = SessionStore(state_dir, 10_000_000)
        active = store.active_metadata()
        assert active is not None
        assert active["session_id"] == winners[0]
        _assert_session_json_is_consistent(store, winners[0], expected_status="active")

        store.finalize(winners[0], "cancel")
        replacement = store.create(exchange)
        assert replacement["session_id"] != winners[0]
        store.finalize(str(replacement["session_id"]), "cancel")
    finally:
        release.set()
        for process in processes:
            process.join(timeout=5)
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=5)
        assert all(process.exitcode == 0 for process in processes)
        results.close()
        results.join_thread()


def test_two_threads_finalize_once_and_leave_valid_state(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state_dir = tmp_path / "state"
    initial_store = SessionStore(state_dir, 10_000_000)
    metadata = initial_store.create(exchange)
    session_id = str(metadata["session_id"])
    request = initial_store.request_finish("cancel")
    stores = [
        SessionStore(state_dir, 10_000_000),
        SessionStore(state_dir, 10_000_000),
    ]
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _capture_call,
                barrier,
                lambda store=store: store.finalize(
                    session_id,
                    "cancel",
                    str(request["expected_sha256"]),
                ),
            )
            for store in stores
        ]
    results = [future.result() for future in futures]

    assert len([value for status, value in results if status == "ok"]) == 1
    assert [value for status, value in results if status == "error"] == [SessionError.code]
    _assert_session_json_is_consistent(
        initial_store,
        session_id,
        expected_status="cancelled",
    )
    assert not initial_store.active_file.exists()
    assert not initial_store.control_path(session_id).exists()

    replacement = initial_store.create(exchange)
    initial_store.finalize(str(replacement["session_id"]), "cancel")


def test_request_and_finalize_race_leaves_terminal_valid_state(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state_dir = tmp_path / "state"
    initial_store = SessionStore(state_dir, 10_000_000)
    metadata = initial_store.create(exchange)
    session_id = str(metadata["session_id"])
    stores = [
        SessionStore(state_dir, 10_000_000),
        SessionStore(state_dir, 10_000_000),
    ]
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        request_future = executor.submit(
            _capture_call,
            barrier,
            lambda: stores[0].request_finish("cancel"),
        )
        finalize_future = executor.submit(
            _capture_call,
            barrier,
            lambda: stores[1].finalize(session_id, "cancel"),
        )
    request_result = request_future.result()
    finalize_result = finalize_future.result()

    assert finalize_result == ("ok", session_id)
    assert request_result in {
        ("ok", session_id),
        ("error", SessionError.code),
    }
    _assert_session_json_is_consistent(
        initial_store,
        session_id,
        expected_status="cancelled",
    )
    assert not initial_store.active_file.exists()
    assert not initial_store.control_path(session_id).exists()

    replacement = initial_store.create(exchange)
    initial_store.finalize(str(replacement["session_id"]), "cancel")


def test_redirected_lock_path_is_rejected(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state_dir = tmp_path / "state"
    store = SessionStore(state_dir, 10_000_000)
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"")
    try:
        store.lock_file.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is not permitted on this platform")

    with pytest.raises(SessionError, match="lock path is redirected"):
        store.create(exchange)
    assert outside.read_bytes() == b""


def test_hardlinked_lock_path_is_rejected_without_mutating_target(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    state_dir = tmp_path / "state"
    store = SessionStore(state_dir, 10_000_000)
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"")
    try:
        os.link(outside, store.lock_file)
    except OSError:
        pytest.skip("Creating hardlinks is not permitted on this platform")

    with pytest.raises(SessionError, match="lock path is redirected"):
        store.create(exchange)
    assert outside.read_bytes() == b""


def test_dead_same_namespace_lease_is_reclaimed(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "state", 10_000_000)
    lease = store.lock_file.with_name(f"{store.lock_file.name}.lease")
    lease.mkdir()
    sessions_module._atomic_write_json(
        lease / "owner.json",
        {
            "nonce": "dead-owner",
            "process": {
                "pid": 2**31 - 1,
                "platform": sessions_module.sys.platform,
                "pid_namespace": sessions_module._pid_namespace(),
                "start_token": "not-running",
            },
        },
    )

    with sessions_module._exclusive_session_lock(store.lock_file):
        assert lease.exists()

    assert not lease.exists()


def test_dead_lease_rename_failure_times_out_without_spinning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(tmp_path / "state", 10_000_000)
    lease = store.lock_file.with_name(f"{store.lock_file.name}.lease")
    lease.mkdir()
    sessions_module._atomic_write_json(
        lease / "owner.json",
        {
            "nonce": "dead-owner",
            "process": {
                "pid": 2**31 - 1,
                "platform": sessions_module.sys.platform,
                "pid_namespace": sessions_module._pid_namespace(),
                "start_token": "not-running",
            },
        },
    )
    real_rename = Path.rename

    def refuse_lease_rename(path: Path, target: Path) -> Path:
        if path == lease:
            raise OSError("injected sharing violation")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", refuse_lease_rename)
    monkeypatch.setattr(sessions_module, "_SESSION_LEASE_WAIT_SECONDS", 0.0)

    with (
        pytest.raises(SessionError) as caught,
        sessions_module._exclusive_session_lock(store.lock_file),
    ):
        pytest.fail("unreclaimable lease cannot be acquired")

    assert caught.value.payload.code == "session_lock_timeout"
    assert lease.exists()


def test_unknown_cross_namespace_lease_is_never_time_expired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(tmp_path / "state", 10_000_000)
    lease = store.lock_file.with_name(f"{store.lock_file.name}.lease")
    lease.mkdir()
    sessions_module._atomic_write_json(
        lease / "owner.json",
        {
            "nonce": "foreign-owner",
            "process": {
                "pid": 123,
                "platform": "foreign-platform",
                "pid_namespace": "foreign-namespace",
                "start_token": "unknown",
            },
            "acquired_at": 0.0,
        },
    )
    monkeypatch.setattr(sessions_module, "_SESSION_LEASE_WAIT_SECONDS", 0.0)

    with (
        pytest.raises(SessionError) as caught,
        sessions_module._exclusive_session_lock(store.lock_file),
    ):
        pytest.fail("unknown cross-namespace lease must not be reclaimed")

    assert caught.value.payload.code == "session_lock_timeout"
    assert lease.exists()
    assert sessions_module._read_json(lease / "owner.json")["nonce"] == "foreign-owner"


def test_orphaned_reaper_gate_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(tmp_path / "state", 10_000_000)
    reaper = store.lock_file.with_name(f"{store.lock_file.name}.reaper")
    reaper.mkdir()
    monkeypatch.setattr(sessions_module, "_SESSION_LEASE_WAIT_SECONDS", 0.0)

    with (
        pytest.raises(SessionError) as caught,
        sessions_module._exclusive_session_lock(store.lock_file),
    ):
        pytest.fail("orphaned recovery gate must block lifecycle mutation")

    assert caught.value.payload.code == "session_lock_timeout"
    assert reaper.exists()


def test_release_failure_is_typed_and_keeps_identified_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(tmp_path / "state", 10_000_000)
    lease = store.lock_file.with_name(f"{store.lock_file.name}.lease")
    real_rename = Path.rename

    def refuse_release(path: Path, target: Path) -> Path:
        if path == lease and ".released." in target.name:
            raise OSError("injected release sharing violation")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", refuse_release)

    with (
        pytest.raises(SessionError) as caught,
        sessions_module._exclusive_session_lock(store.lock_file),
    ):
        assert lease.exists()

    assert caught.value.payload.code == "session_lock_release_failed"
    owner = sessions_module._read_json(lease / "owner.json")
    assert isinstance(owner["nonce"], str)


def test_transient_release_sharing_violation_is_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SessionStore(tmp_path / "state", 10_000_000)
    lease = store.lock_file.with_name(f"{store.lock_file.name}.lease")
    real_rename = Path.rename
    release_attempts = 0

    def fail_first_release(path: Path, target: Path) -> Path:
        nonlocal release_attempts
        if path == lease and ".released." in target.name:
            release_attempts += 1
            if release_attempts == 1:
                raise OSError("transient sharing violation")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_first_release)

    with sessions_module._exclusive_session_lock(store.lock_file):
        assert lease.exists()

    assert release_attempts == 2
    assert not lease.exists()


def test_explicit_abandon_refuses_unknown_lease_without_fencing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = str(metadata["session_id"])
    lease = store.lock_file.with_name(f"{store.lock_file.name}.lease")
    lease.mkdir()
    sessions_module._atomic_write_json(
        lease / "owner.json",
        {
            "nonce": "crashed-foreign-owner",
            "process": {
                "pid": 123,
                "platform": "foreign-platform",
                "pid_namespace": "foreign-namespace",
                "start_token": "unknown",
            },
        },
    )
    monkeypatch.setattr(sessions_module, "_SESSION_LEASE_WAIT_SECONDS", 0.0)

    with pytest.raises(SessionError) as caught:
        store.abandon_active("operator suspects cross-namespace crash")

    assert caught.value.payload.code == "session_lock_timeout"
    assert store.read_metadata(session_id)["status"] == "active"
    assert lease.exists()
