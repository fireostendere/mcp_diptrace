from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest

import diptrace_mcp.sessions as sessions_module
from diptrace_mcp import bridge
from diptrace_mcp.capability_model import MAX_WRITE_OBJECTS
from diptrace_mcp.config import DEFAULT_LIVE_SESSION_TTL_SECONDS, Settings
from diptrace_mcp.errors import DocumentError, EditError, SessionError
from diptrace_mcp.retention import RetentionPolicy
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.sessions import SessionAction, SessionStore
from diptrace_mcp.xml_document import XmlEdit, sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def _store(
    tmp_path: Path,
    *,
    clock: Any | None = None,
    ttl: int = 2 * 60 * 60,
) -> tuple[SessionStore, Path, str]:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(
        tmp_path / "state",
        10_000_000,
        allowed_roots=(tmp_path,),
        active_ttl_seconds=ttl,
        **({"clock": clock} if clock is not None else {}),
    )
    metadata = store.create(exchange)
    return store, exchange, str(metadata["session_id"])


def _future_items(count: int) -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        b"<Board><Future>"
        + b"<Item/>" * count
        + b"</Future></Board></Source>\n"
    )


def _empty_board() -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
        b"<Board/></Source>\n"
    )


def test_live_session_ttl_configuration_is_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIPTRACE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("DIPTRACE_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("DIPTRACE_MCP_SESSION_TTL_SECONDS", "3600")
    settings = Settings.from_env()
    service = DipTraceService(settings)

    assert DEFAULT_LIVE_SESSION_TTL_SECONDS == 7200
    assert settings.live_session_ttl_seconds == 3600
    assert settings.as_dict()["live_session_ttl_seconds"] == 3600
    assert service.get_capabilities()["limits"]["live_session_ttl_seconds"] == 3600


@pytest.mark.skipif(sessions_module.os.name == "nt", reason="POSIX liveness semantics")
def test_liveness_helpers_fail_closed_on_unprovable_process_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sessions_module._bridge_process_liveness({"bridge_pid": 123}) == "unknown"
    assert (
        sessions_module._bridge_process_liveness(
            {
                "bridge_process": {
                    "pid": 0,
                    "platform": sessions_module.sys.platform,
                    "pid_namespace": sessions_module._pid_namespace(),
                }
            }
        )
        == "unknown"
    )
    identity = {
        "bridge_process": {
            "pid": 123,
            "platform": sessions_module.sys.platform,
            "pid_namespace": "same",
            "start_token": None,
        }
    }
    monkeypatch.setattr(sessions_module, "_pid_namespace", lambda: "same")

    monkeypatch.setattr(
        sessions_module.os,
        "kill",
        lambda _pid, _signal: (_ for _ in ()).throw(ProcessLookupError()),
    )
    assert sessions_module._bridge_process_liveness(identity) == "dead"
    monkeypatch.setattr(
        sessions_module.os,
        "kill",
        lambda _pid, _signal: (_ for _ in ()).throw(PermissionError()),
    )
    assert sessions_module._bridge_process_liveness(identity) == "unknown"
    monkeypatch.setattr(
        sessions_module.os,
        "kill",
        lambda _pid, _signal: (_ for _ in ()).throw(OSError()),
    )
    assert sessions_module._bridge_process_liveness(identity) == "unknown"
    monkeypatch.setattr(sessions_module.os, "kill", lambda _pid, _signal: None)
    assert sessions_module._bridge_process_liveness(identity) == "unknown"
    identity["bridge_process"]["start_token"] = "same-start"
    monkeypatch.setattr(
        sessions_module,
        "_linux_process_start_token",
        lambda _pid: "same-start",
    )
    assert sessions_module._bridge_process_liveness(identity) == "alive"


@pytest.mark.skipif(sessions_module.os.name != "nt", reason="Windows PID semantics")
def test_windows_current_process_identity_is_creation_time_bound() -> None:
    process = sessions_module._current_bridge_process_identity()
    assert isinstance(process["start_token"], str)
    assert (
        sessions_module._bridge_process_liveness({"bridge_process": process}) == "alive"
    )
    assert (
        sessions_module._bridge_process_liveness(
            {"bridge_process": {**process, "start_token": None}}
        )
        == "unknown"
    )
    assert (
        sessions_module._bridge_process_liveness(
            {"bridge_process": {**process, "start_token": "reused"}}
        )
        == "dead"
    )


@pytest.mark.skipif(
    not sessions_module.sys.platform.startswith("linux"),
    reason="Linux /proc fallback test",
)
def test_linux_pid_identity_read_failures_are_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text

    def fail_boot_id(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == Path("/proc/sys/kernel/random/boot_id"):
            raise OSError("unavailable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_boot_id)
    assert sessions_module._pid_namespace() == "linux:unavailable"
    assert sessions_module._linux_process_start_token(2**31 - 1) is None


@pytest.mark.skipif(
    not sessions_module.sys.platform.startswith("linux"),
    reason="Linux namespace fallback test",
)
def test_unavailable_linux_pid_namespace_never_proves_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sessions_module, "_pid_namespace", lambda: "linux:unavailable")
    monkeypatch.setattr(sessions_module.os, "kill", lambda _pid, _signal: None)
    monkeypatch.setattr(
        sessions_module,
        "_linux_process_start_token",
        lambda _pid: "different-start",
    )

    assert (
        sessions_module._bridge_process_liveness(
            {
                "bridge_process": {
                    "pid": 123,
                    "platform": sessions_module.sys.platform,
                    "pid_namespace": "linux:unavailable",
                    "start_token": "recorded-start",
                }
            }
        )
        == "unknown"
    )


def test_lifecycle_argument_validation_is_typed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="active_ttl_seconds"):
        SessionStore(tmp_path / "invalid", active_ttl_seconds=0)

    store = SessionStore(tmp_path / "state")
    with pytest.raises(SessionError, match="reason is required"):
        store.abandon_active("   ")
    with pytest.raises(SessionError, match="exceeds 500"):
        store.abandon_active("x" * 501)
    with pytest.raises(SessionError, match="no active"):
        store.abandon_active("operator request")
    with pytest.raises(ValueError, match="changed_id_limit"):
        store.live_preview_summary("00000000-0000-0000-0000-000000000000", changed_id_limit=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        store.wait_for_finish_outcome(
            {"session_id": "00000000-0000-0000-0000-000000000000"},
            timeout_seconds=-1,
        )


def test_dead_bridge_is_abandoned_and_no_longer_blocks_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, exchange, session_id = _store(tmp_path)
    monkeypatch.setattr(
        sessions_module,
        "_bridge_process_liveness",
        lambda _metadata: "dead",
    )

    assert store.active_metadata() is None
    abandoned = store.read_metadata(session_id)
    assert abandoned["status"] == "abandoned"
    assert abandoned["abandon_reason"] == "bridge_process_not_alive"
    assert abandoned["abandonment_automatic"] is True
    assert not store.active_file.exists()

    replacement = store.create(exchange)
    assert replacement["session_id"] != session_id


def test_dead_bridge_with_missing_working_file_can_still_be_abandoned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, exchange, session_id = _store(tmp_path)
    store.working_path(session_id).unlink()
    monkeypatch.setattr(
        sessions_module,
        "_bridge_process_liveness",
        lambda _metadata: "dead",
    )

    assert store.active_metadata() is None
    abandoned = store.read_metadata(session_id)
    assert abandoned["status"] == "abandoned"
    assert abandoned["abandonment_state_incomplete"] is True
    assert store.create(exchange)["session_id"] != session_id


def test_status_discloses_automatic_abandon_transition_without_exchange_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    monkeypatch.setattr(
        sessions_module,
        "_bridge_process_liveness",
        lambda _metadata: "dead",
    )

    status = service.status()

    assert status["active_session"] is None
    transition = status["last_session_transition"]
    assert transition == {
        "session_id": metadata["session_id"],
        "status": "abandoned",
        "reason": "bridge_process_not_alive",
        "automatic": True,
        "finished_at": transition["finished_at"],
    }
    assert "exchange_path" not in transition
    assert str(exchange) not in str(transition)


def test_pid_namespace_mismatch_is_unknown_without_signalling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_kill(_pid: int, _signal: int) -> None:
        pytest.fail("cross-namespace PID must never be signalled")

    monkeypatch.setattr(sessions_module.os, "kill", forbidden_kill)
    metadata = {
        "bridge_process": {
            "pid": 1234,
            "platform": sessions_module.sys.platform,
            "pid_namespace": "different-namespace",
            "start_token": "1",
        }
    }

    assert sessions_module._bridge_process_liveness(metadata) == "unknown"


@pytest.mark.skipif(
    not sessions_module.sys.platform.startswith("linux"),
    reason="Linux /proc start token test",
)
def test_reused_pid_with_different_start_token_is_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sessions_module.os, "kill", lambda _pid, _signal: None)
    monkeypatch.setattr(
        sessions_module,
        "_linux_process_start_token",
        lambda _pid: "new-start",
    )
    metadata = {
        "bridge_process": {
            "pid": 1234,
            "platform": sessions_module.sys.platform,
            "pid_namespace": sessions_module._pid_namespace(),
            "start_token": "old-start",
        }
    }

    assert sessions_module._bridge_process_liveness(metadata) == "dead"


@pytest.mark.parametrize(
    ("opened", "last_error", "exit_code", "expected"),
    [
        (False, 87, None, "dead"),
        (False, 5, None, "unknown"),
        (True, 0, None, "unknown"),
        (True, 0, 259, "alive"),
        (True, 0, 0, "dead"),
    ],
)
def test_windows_process_result_is_fail_closed(
    opened: bool,
    last_error: int,
    exit_code: int | None,
    expected: str,
) -> None:
    assert (
        sessions_module._classify_windows_process(
            opened=opened,
            last_error=last_error,
            exit_code=exit_code,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("liveness", "expected_token", "current_token", "expected"),
    [
        ("dead", None, None, "dead"),
        ("alive", None, "current", "unknown"),
        ("alive", "expected", None, "unknown"),
        ("alive", "expected", "expected", "alive"),
        ("alive", "expected", "reused", "dead"),
        ("unknown", "expected", "expected", "unknown"),
    ],
)
def test_process_start_token_prevents_pid_reuse(
    liveness: str,
    expected_token: str | None,
    current_token: str | None,
    expected: str,
) -> None:
    assert (
        sessions_module._classify_process_identity(
            liveness,  # type: ignore[arg-type]
            expected_start_token=expected_token,
            current_start_token=current_token,
        )
        == expected
    )


def test_active_session_ttl_marks_unknown_liveness_abandoned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moments = [NOW]
    store, _exchange, session_id = _store(
        tmp_path,
        clock=lambda: moments[0],
        ttl=60,
    )
    metadata = store.read_metadata(session_id)
    metadata["updated_at"] = NOW.isoformat()
    sessions_module._atomic_write_json(store.metadata_path(session_id), metadata)
    monkeypatch.setattr(
        sessions_module,
        "_bridge_process_liveness",
        lambda _metadata: "unknown",
    )
    moments[0] = NOW + timedelta(seconds=61)

    assert store.active_metadata() is None
    abandoned = store.read_metadata(session_id)
    assert abandoned["status"] == "abandoned"
    assert abandoned["abandon_reason"] == "active_session_ttl_expired"


def test_confirmed_alive_bridge_is_not_abandoned_past_ttl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moments = [NOW]
    store, _exchange, session_id = _store(
        tmp_path,
        clock=lambda: moments[0],
        ttl=60,
    )
    metadata = store.read_metadata(session_id)
    metadata["updated_at"] = NOW.isoformat()
    sessions_module._atomic_write_json(store.metadata_path(session_id), metadata)
    monkeypatch.setattr(
        sessions_module,
        "_bridge_process_liveness",
        lambda _metadata: "alive",
    )
    moments[0] = NOW + timedelta(days=1)

    active = store.active_metadata()
    assert active is not None
    assert active["session_id"] == session_id
    assert active["bridge_liveness"] == "alive"
    assert active["expires_at"] is None


def test_unknown_liveness_uses_last_edit_activity_for_ttl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moments = [NOW]
    store, _exchange, session_id = _store(
        tmp_path,
        clock=lambda: moments[0],
        ttl=60,
    )
    metadata = store.read_metadata(session_id)
    metadata["updated_at"] = NOW.isoformat()
    sessions_module._atomic_write_json(store.metadata_path(session_id), metadata)
    monkeypatch.setattr(
        sessions_module,
        "_bridge_process_liveness",
        lambda _metadata: "unknown",
    )

    moments[0] = NOW + timedelta(seconds=50)
    store.record_edit(session_id, store.working_sha256(session_id), tmp_path / "backup")
    refreshed = store.read_metadata(session_id)
    refreshed["updated_at"] = moments[0].isoformat()
    sessions_module._atomic_write_json(store.metadata_path(session_id), refreshed)
    moments[0] = NOW + timedelta(seconds=100)

    active = store.active_metadata()
    assert active is not None
    assert active["session_id"] == session_id
    assert active["bridge_liveness"] == "unknown"


def test_manual_abandon_never_replaces_exchange(tmp_path: Path) -> None:
    store, exchange, session_id = _store(tmp_path)
    original = exchange.read_bytes()
    store.working_path(session_id).write_bytes(
        original.replace(b"<Value>10k</Value>", b"<Value>22k</Value>")
    )

    result = store.abandon_active("operator confirmed bridge process exited")

    assert result["status"] == "abandoned"
    assert result["abandonment_automatic"] is False
    assert exchange.read_bytes() == original
    assert store.active_metadata() is None


def test_service_abandon_result_is_local_and_nonwriting(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    original = (FIXTURES / "pcb.xml").read_bytes()
    exchange.write_bytes(original)
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    service.sessions.create(exchange)

    result = service.abandon_live_session("operator confirmed crash")

    assert result["outcome"] == "abandoned"
    assert result["written"] is False
    assert result["diptrace_host_acknowledged"] is False
    assert exchange.read_bytes() == original


def test_abandoned_session_is_terminal_for_retention(tmp_path: Path) -> None:
    store, _exchange, session_id = _store(tmp_path)
    store.abandon_active("bridge crashed")
    metadata = store.read_metadata(session_id)
    metadata.update(
        {
            "updated_at": "2020-01-01T00:00:00+00:00",
            "finished_at": "2020-01-01T00:00:00+00:00",
            "abandoned_at": "2020-01-01T00:00:00+00:00",
        }
    )
    sessions_module._atomic_write_json(store.metadata_path(session_id), metadata)

    reopened = SessionStore(
        store.state_dir,
        10_000_000,
        allowed_roots=(tmp_path,),
        retention=RetentionPolicy(max_records=1, max_age_days=1),
        clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert not reopened.session_dir(session_id).exists()
    assert reopened.last_retention_report.removed


@pytest.mark.parametrize(
    ("action", "expected_outcome", "written"),
    [
        ("apply", "applied", True),
        ("cancel", "cancelled", False),
    ],
)
def test_bounded_finish_wait_reports_only_local_bridge_outcome(
    tmp_path: Path,
    action: str,
    expected_outcome: str,
    written: bool,
) -> None:
    store, _exchange, session_id = _store(tmp_path)
    expected_sha256 = store.working_sha256(session_id)
    typed_action = cast(SessionAction, action)
    request = store.request_finish(
        typed_action,
        expected_sha256 if action == "apply" else None,
    )

    worker = threading.Thread(
        target=lambda: store.finalize(
            session_id,
            typed_action,
            str(request["expected_sha256"]),
        )
    )
    worker.start()
    result = store.wait_for_finish_outcome(request, timeout_seconds=2)
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert result["outcome"] == expected_outcome
    assert result["written"] is written
    assert result["diptrace_host_acknowledged"] is False
    assert result["acknowledgement_scope"] == "local_bridge_exchange_only"


def test_finish_timeout_is_not_acknowledged_but_late_finalize_still_works(
    tmp_path: Path,
) -> None:
    store, _exchange, session_id = _store(tmp_path)
    request = store.request_finish("cancel")

    result = store.wait_for_finish_outcome(request, timeout_seconds=0)
    assert result["outcome"] == "not_acknowledged"
    assert result["written"] is False
    assert store.read_metadata(session_id)["status"] == "active"

    terminal = store.finalize(session_id, "cancel", str(request["expected_sha256"]))
    assert terminal["status"] == "cancelled"


def test_first_finish_request_wins_and_correlates_its_outcome(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store(tmp_path)
    original = exchange.read_bytes()
    cancel_request = store.request_finish("cancel")
    repeated = store.request_finish("cancel")
    assert repeated["request_id"] == cancel_request["request_id"]

    with pytest.raises(SessionError) as conflicting_request:
        store.request_finish("apply", store.working_sha256(session_id))
    assert conflicting_request.value.payload.code == "session_finish_pending"
    with pytest.raises(SessionError) as conflicting_finalize:
        store.finalize(
            session_id,
            "apply",
            str(cancel_request["expected_sha256"]),
        )
    assert conflicting_finalize.value.payload.code == "session_finish_pending"

    store.finalize(session_id, "cancel")
    outcome = store.wait_for_finish_outcome(cancel_request, timeout_seconds=0)
    assert outcome["requested_action"] == "cancel"
    assert outcome["outcome"] == "cancelled"
    assert outcome["written"] is False
    assert exchange.read_bytes() == original


def test_finish_rejection_is_cas_bound_to_request_id(tmp_path: Path) -> None:
    store, _exchange, session_id = _store(tmp_path)
    first = store.request_finish("cancel")
    store.reject_finish_request(
        session_id,
        "first request rejected",
        expected_request_id=str(first["request_id"]),
    )
    second = store.request_finish("cancel")

    with pytest.raises(SessionError) as stale_reject:
        store.reject_finish_request(
            session_id,
            "stale bridge result",
            expected_request_id=str(first["request_id"]),
        )

    assert stale_reject.value.payload.code == "session_finish_pending"
    pending = store.read_finish_request(session_id)
    assert pending is not None
    assert pending["request_id"] == second["request_id"]


def test_abandoned_finish_request_has_terminal_message(tmp_path: Path) -> None:
    store, _exchange, _session_id = _store(tmp_path)
    request = store.request_finish("cancel")
    store.abandon_active("operator cancelled crashed bridge state")

    outcome = store.wait_for_finish_outcome(request, timeout_seconds=0)

    assert outcome["outcome"] == "not_acknowledged"
    assert outcome["local_bridge_status"] == "abandoned"
    assert "abandoned terminally" in outcome["message"]
    assert "still be finalized later" not in outcome["message"]


def test_apply_metadata_failure_restores_exchange_before_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, exchange, session_id = _store(tmp_path)
    original = exchange.read_bytes()
    modified = original.replace(b"<Value>10k</Value>", b"<Value>47k</Value>")
    store.working_path(session_id).write_bytes(modified)
    request = store.request_finish("apply", sha256_bytes(modified))
    metadata_path = store.metadata_path(session_id)
    real_write_json = sessions_module._atomic_write_json

    def fail_applied_metadata(path: Path, value: dict[str, Any]) -> None:
        if path == metadata_path and value.get("status") == "applied":
            raise OSError("injected applied-state failure")
        real_write_json(path, value)

    monkeypatch.setattr(sessions_module, "_atomic_write_json", fail_applied_metadata)
    with pytest.raises(OSError, match="applied-state"):
        store.finalize(
            session_id,
            "apply",
            str(request["expected_sha256"]),
        )

    assert exchange.read_bytes() == original
    assert store.read_metadata(session_id)["status"] == "active"
    assert store.control_path(session_id).exists()

    monkeypatch.setattr(sessions_module, "_atomic_write_json", real_write_json)
    store.reject_finish_request(
        session_id,
        "apply state was compensated",
        expected_request_id=str(request["request_id"]),
    )
    cancelled = store.finalize(session_id, "cancel")
    assert cancelled["status"] == "cancelled"
    assert exchange.read_bytes() == original


def test_abandon_and_cancel_finalize_race_leaves_one_terminal_state(
    tmp_path: Path,
) -> None:
    store, exchange, session_id = _store(tmp_path)
    original = exchange.read_bytes()
    store.request_finish("cancel")
    peer = SessionStore(
        store.state_dir,
        10_000_000,
        allowed_roots=(tmp_path,),
    )
    barrier = threading.Barrier(2)

    def abandon() -> str:
        barrier.wait()
        try:
            return str(peer.abandon_active("operator recovery")["status"])
        except SessionError:
            return "rejected"

    def cancel() -> str:
        barrier.wait()
        try:
            return str(store.finalize(session_id, "cancel")["status"])
        except SessionError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        abandon_future = executor.submit(abandon)
        cancel_future = executor.submit(cancel)
        outcomes = {abandon_future.result(), cancel_future.result()}

    assert outcomes in ({"abandoned", "rejected"}, {"cancelled", "rejected"})
    assert store.read_metadata(session_id)["status"] in {"abandoned", "cancelled"}
    assert store.active_metadata() is None
    assert exchange.read_bytes() == original


def test_public_finish_and_abandon_tools_expose_honest_local_contract(
    tmp_path: Path,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    service = DipTraceService(settings)
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])

    def bridge_worker() -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            request = service.sessions.read_finish_request(session_id)
            if request is not None:
                service.sessions.finalize(
                    session_id,
                    "cancel",
                    str(request["expected_sha256"]),
                )
                return
            time.sleep(0.01)

    worker = threading.Thread(target=bridge_worker)
    worker.start()
    result = service.finish_live_session("cancel")
    worker.join(timeout=2)

    assert result["outcome"] == "cancelled"
    assert result["diptrace_host_acknowledged"] is False
    assert not worker.is_alive()

    tools = create_server()._tool_manager._tools
    assert "abandon_live_session" in tools
    reason = tools["abandon_live_session"].parameters["properties"]["reason"]
    assert reason["minLength"] == 1
    assert reason["maxLength"] == 500
    assert "without applying" in (tools["abandon_live_session"].description or "")
    for name in ("finish_live_session", "abandon_live_session"):
        schema = tools[name].output_schema
        assert schema["additionalProperties"] is False
        assert schema["properties"]["written"]["type"] == "boolean"
        assert schema["properties"]["diptrace_host_acknowledged"]["const"] is False


def test_explicit_working_path_is_frozen_after_finish_request(
    tmp_path: Path,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    working = service.sessions.working_path(session_id)
    original = working.read_bytes()
    expected_sha256 = sha256_bytes(original)
    service.sessions.request_finish("cancel")

    with pytest.raises(SessionError) as caught:
        service.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component[RefDes='R1']/Value",
                    value="47k",
                )
            ],
            path=str(working),
            dry_run=False,
            expected_sha256=expected_sha256,
        )

    assert caught.value.payload.code == "session_finish_pending"
    assert working.read_bytes() == original


def test_live_raw_edit_trust_failure_restores_working_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    working = service.sessions.working_path(session_id)
    original = working.read_bytes()
    expected_sha256 = sha256_bytes(original)
    sidecar = working.with_suffix(working.suffix + ".provenance.json")
    real_write_sidecar = service._write_provenance_sidecar

    def write_sidecar_then_fail(path: Path, provenance: Any) -> None:
        real_write_sidecar(path, provenance)
        raise OSError("injected trust-sidecar failure")

    monkeypatch.setattr(
        service,
        "_write_provenance_sidecar",
        write_sidecar_then_fail,
    )

    with pytest.raises(OSError, match="trust-sidecar"):
        service.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component[RefDes='R1']/Value",
                    value="47k",
                )
            ],
            dry_run=False,
            expected_sha256=expected_sha256,
        )

    restored = service.sessions.read_metadata(session_id)
    assert working.read_bytes() == original
    assert restored["working_sha256"] == expected_sha256
    assert restored["edit_count"] == 0
    assert not sidecar.exists()


def test_live_raw_edit_metadata_failure_restores_working(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    working = service.sessions.working_path(session_id)
    original = working.read_bytes()
    expected_sha256 = sha256_bytes(original)
    metadata_path = service.sessions.metadata_path(session_id)
    real_write_json = sessions_module._atomic_write_json
    failed_once = False

    def fail_updated_metadata(path: Path, value: dict[str, Any]) -> None:
        nonlocal failed_once
        if (
            path == metadata_path
            and value.get("working_sha256") != expected_sha256
            and not failed_once
        ):
            failed_once = True
            raise OSError("injected metadata failure")
        real_write_json(path, value)

    monkeypatch.setattr(sessions_module, "_atomic_write_json", fail_updated_metadata)

    with pytest.raises(OSError, match="metadata"):
        service.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component[RefDes='R1']/Value",
                    value="47k",
                )
            ],
            dry_run=False,
            expected_sha256=expected_sha256,
        )

    assert working.read_bytes() == original
    restored = service.sessions.read_metadata(session_id)
    assert restored["working_sha256"] == expected_sha256
    assert restored["edit_count"] == 0


@pytest.mark.parametrize("terminal_action", ["apply", "cancel"])
def test_terminal_live_session_refuses_staged_transaction_commit(
    tmp_path: Path,
    terminal_action: str,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    working = service.sessions.working_path(session_id)
    original = working.read_bytes()
    preview = service.set_component_value(
        {"refdes": ["R1"]},
        "47k",
        dry_run=True,
    )
    txid = str(preview["transaction"]["txid"])
    expected_sha256 = str(preview["transaction"]["expected_sha256"])
    action = cast(SessionAction, terminal_action)
    request = service.sessions.request_finish(
        action,
        expected_sha256 if terminal_action == "apply" else None,
    )
    service.sessions.finalize(
        session_id,
        action,
        str(request["expected_sha256"]),
    )

    with pytest.raises(SessionError, match="not active"):
        service.commit_transaction(txid, expected_sha256)

    assert working.read_bytes() == original
    assert service.transactions.read(txid).status == "validated"
    assert service.sessions.read_metadata(session_id)["status"] == (
        "applied" if terminal_action == "apply" else "cancelled"
    )


def test_applied_live_transaction_cannot_be_rolled_back_behind_host(
    tmp_path: Path,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    preview = service.set_component_value(
        {"refdes": ["R1"]},
        "47k",
        dry_run=True,
    )
    txid = str(preview["transaction"]["txid"])
    source_sha256 = str(preview["transaction"]["expected_sha256"])
    committed = service.commit_transaction(txid, source_sha256)
    committed_sha256 = str(committed["transaction"]["committed_sha256"])
    working = service.sessions.working_path(session_id)
    committed_bytes = working.read_bytes()
    request = service.sessions.request_finish("apply", committed_sha256)
    service.sessions.finalize(
        session_id,
        "apply",
        str(request["expected_sha256"]),
    )

    with pytest.raises(SessionError, match="not active"):
        service.rollback_transaction(txid, committed_sha256)

    assert exchange.read_bytes() == committed_bytes
    assert working.read_bytes() == committed_bytes
    assert service.transactions.read(txid).status == "committed"
    assert service.sessions.read_metadata(session_id)["status"] == "applied"


def test_unknown_import_mode_is_read_only(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    original = (
        b'<Source Type="DipTrace-Future" Version="1" Units="mm"><Data/></Source>'
    )
    exchange.write_bytes(original)
    store = SessionStore(
        tmp_path / "state",
        allowed_roots=(tmp_path,),
    )
    metadata = store.create(exchange)

    assert metadata["bridge_import_mode"] == "Unknown"
    assert metadata["apply_supported"] is False
    with pytest.raises(SessionError, match="no shipped bridge import policy") as caught:
        store.request_finish(
            "apply",
            store.working_sha256(str(metadata["session_id"])),
        )
    assert caught.value.payload.code == "capability_unavailable"
    assert exchange.read_bytes() == original


def test_live_apply_accepts_exact_object_boundary_and_refuses_one_more(
    tmp_path: Path,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes(_empty_board())
    store = SessionStore(
        tmp_path / "state",
        allowed_roots=(tmp_path,),
    )
    exact = store.create(exchange)
    exact_id = str(exact["session_id"])
    # The new Future container plus 499 Item elements changes exactly 500
    # structural elements and no normalized objects.
    store.working_path(exact_id).write_bytes(_future_items(MAX_WRITE_OBJECTS - 1))
    request = store.request_finish("apply", store.working_sha256(exact_id))
    assert store.live_preview_summary(exact_id)["object_count"] == MAX_WRITE_OBJECTS
    store.reject_finish_request(
        exact_id,
        "test cleanup after exact-boundary request",
        expected_request_id=str(request["request_id"]),
    )
    store.finalize(exact_id, "cancel")

    oversized = store.create(exchange)
    oversized_id = str(oversized["session_id"])
    store.working_path(oversized_id).write_bytes(_future_items(MAX_WRITE_OBJECTS))
    with pytest.raises(EditError) as caught:
        store.request_finish("apply", store.working_sha256(oversized_id))
    assert caught.value.payload.code == "write_object_limit_exceeded"
    assert not store.control_path(oversized_id).exists()


def test_finalize_rechecks_object_cap_after_finish_request_tamper(
    tmp_path: Path,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    original = _empty_board()
    exchange.write_bytes(original)
    store = SessionStore(
        tmp_path / "state",
        allowed_roots=(tmp_path,),
    )
    metadata = store.create(exchange)
    session_id = str(metadata["session_id"])
    request = store.request_finish("apply", store.working_sha256(session_id))
    store.working_path(session_id).write_bytes(_future_items(MAX_WRITE_OBJECTS))

    with pytest.raises(EditError) as caught:
        store.finalize(session_id, "apply", str(request["expected_sha256"]))

    assert caught.value.payload.code == "write_object_limit_exceeded"
    assert exchange.read_bytes() == original
    assert store.read_metadata(session_id)["status"] == "active"


def test_malformed_live_working_xml_has_unavailable_preview_and_cannot_apply(
    tmp_path: Path,
) -> None:
    controller, exchange = _bridge_controller(tmp_path)
    original = exchange.read_bytes()
    controller.working_path.write_bytes(b"<Source>")

    summary = controller.preview_summary()
    assert summary["available"] is False
    assert summary["complete"] is False
    assert summary["changed_ids_complete"] is False

    with pytest.raises(DocumentError):
        controller.store.request_finish("apply", controller.current_sha256())
    assert exchange.read_bytes() == original


def _bridge_controller(tmp_path: Path) -> tuple[bridge.BridgeController, Path]:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    return bridge.BridgeController(exchange, settings), exchange


def test_bridge_preview_summary_is_cached_by_payload_sha_across_read_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _exchange = _bridge_controller(tmp_path)
    old_sha256 = controller.current_sha256()
    real_summary = controller.store.live_preview_summary
    real_current = controller.current_sha256
    summary_calls = 0
    current_calls = 0

    def current_with_first_old_value() -> str:
        nonlocal current_calls
        current_calls += 1
        return old_sha256 if current_calls == 1 else real_current()

    def mutate_then_summarize(session_id: str) -> dict[str, Any]:
        nonlocal summary_calls
        summary_calls += 1
        working = controller.working_path
        working.write_bytes(
            working.read_bytes().replace(
                b"<Value>10k</Value>",
                b"<Value>22k</Value>",
            )
        )
        return real_summary(session_id)

    monkeypatch.setattr(controller, "current_sha256", current_with_first_old_value)
    monkeypatch.setattr(
        controller.store,
        "live_preview_summary",
        mutate_then_summarize,
    )

    first = controller.preview_summary()
    new_sha256 = sha256_bytes(controller.working_path.read_bytes())
    assert first["working_sha256"] == new_sha256
    assert new_sha256 != old_sha256
    assert controller._preview_sha256 == new_sha256

    second = controller.preview_summary()
    assert second is first
    assert summary_calls == 1


def test_bridge_preview_refuses_unbound_payload_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _exchange = _bridge_controller(tmp_path)
    monkeypatch.setattr(
        controller.store,
        "live_preview_summary",
        lambda _session_id: {
            "available": True,
            "working_sha256": "not-a-sha",
        },
    )

    summary = controller.preview_summary()

    assert summary["available"] is False
    assert summary["complete"] is False
    assert summary["reason"] == "invalid working_sha256 in preview summary"
    assert controller._preview_payload is None


def test_unavailable_preview_clears_previous_apply_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _exchange = _bridge_controller(tmp_path)
    assert controller.preview_summary()["available"] is True
    controller.working_path.write_bytes(
        controller.working_path.read_bytes().replace(
            b"<Value>10k</Value>",
            b"<Value>47k</Value>",
        )
    )
    monkeypatch.setattr(
        controller.store,
        "live_preview_summary",
        lambda _session_id: {
            "available": False,
            "working_sha256": "invalid",
        },
    )

    assert controller.preview_summary()["available"] is False
    assert controller.inspected_sha256() is None


def test_bridge_apply_is_bound_to_the_displayed_preview_sha(tmp_path: Path) -> None:
    controller, exchange = _bridge_controller(tmp_path)
    original = exchange.read_bytes()
    displayed = controller.preview_summary()
    displayed_sha256 = str(displayed["working_sha256"])
    controller.working_path.write_bytes(
        original.replace(b"<Value>10k</Value>", b"<Value>47k</Value>")
    )

    with pytest.raises(SessionError) as caught:
        controller.finish("apply", controller.inspected_sha256())

    assert caught.value.payload.code == "sha256_mismatch"
    assert displayed_sha256 != controller.current_sha256()
    assert exchange.read_bytes() == original
    assert controller.finished is False

    refreshed = controller.preview_summary()
    assert refreshed["working_sha256"] == controller.current_sha256()
    controller.finish("apply", controller.inspected_sha256())
    assert exchange.read_bytes() == controller.working_path.read_bytes()
    assert controller.finished is True


def test_commit_state_failure_finishes_only_after_source_compensation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    working = service.sessions.working_path(session_id)
    original = working.read_bytes()
    source_sha256 = sha256_bytes(original)
    preview = service.set_component_value(
        {"refdes": ["R1"]},
        "47k",
        dry_run=True,
    )
    txid = str(preview["transaction"]["txid"])
    entered_state_write = threading.Event()
    allow_state_failure = threading.Event()
    finish_completed = threading.Event()
    transaction_store_type = type(service.transactions)

    def fail_mark_committed(
        _store: object,
        _txid: str,
        **_changes: Any,
    ) -> Any:
        entered_state_write.set()
        assert allow_state_failure.wait(timeout=2)
        raise OSError("injected state failure")

    monkeypatch.setattr(
        transaction_store_type,
        "mark_committed",
        fail_mark_committed,
    )

    def commit() -> str:
        try:
            service.commit_transaction(txid, source_sha256)
        except Exception as exc:
            return type(exc).__name__
        return "unexpected_success"

    def finish() -> str:
        result = service.sessions.finalize(session_id, "apply", source_sha256)
        finish_completed.set()
        return str(result["status"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        commit_future = executor.submit(commit)
        assert entered_state_write.wait(timeout=2)
        finish_future = executor.submit(finish)
        assert not finish_completed.wait(timeout=0.1)
        allow_state_failure.set()
        assert commit_future.result(timeout=2) == "TransactionConflictError"
        assert finish_future.result(timeout=2) == "applied"

    assert exchange.read_bytes() == original
    assert working.read_bytes() == original
    assert service.transactions.read(txid).status == "validated"
    terminal = service.sessions.read_metadata(session_id)
    assert terminal["status"] == "applied"
    assert terminal["working_sha256"] == source_sha256


def test_rollback_state_failure_finishes_only_after_commit_compensation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
    )
    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    preview = service.set_component_value(
        {"refdes": ["R1"]},
        "47k",
        dry_run=True,
    )
    txid = str(preview["transaction"]["txid"])
    source_sha256 = str(preview["transaction"]["expected_sha256"])
    committed = service.commit_transaction(txid, source_sha256)
    committed_sha256 = str(committed["transaction"]["committed_sha256"])
    working = service.sessions.working_path(session_id)
    committed_bytes = working.read_bytes()
    entered_state_write = threading.Event()
    allow_state_failure = threading.Event()
    finish_completed = threading.Event()
    transaction_store_type = type(service.transactions)

    def fail_mark_rolled_back(
        _store: object,
        _txid: str,
        *,
        rolled_back_sha256: str | None,
        reason: str = "",
    ) -> Any:
        entered_state_write.set()
        assert allow_state_failure.wait(timeout=2)
        raise OSError("injected rollback state failure")

    monkeypatch.setattr(
        transaction_store_type,
        "mark_rolled_back",
        fail_mark_rolled_back,
    )

    def rollback() -> str:
        try:
            service.rollback_transaction(txid, committed_sha256)
        except Exception as exc:
            return type(exc).__name__
        return "unexpected_success"

    def finish() -> str:
        result = service.sessions.finalize(
            session_id,
            "apply",
            committed_sha256,
        )
        finish_completed.set()
        return str(result["status"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        rollback_future = executor.submit(rollback)
        assert entered_state_write.wait(timeout=2)
        finish_future = executor.submit(finish)
        assert not finish_completed.wait(timeout=0.1)
        allow_state_failure.set()
        assert rollback_future.result(timeout=2) == "TransactionConflictError"
        assert finish_future.result(timeout=2) == "applied"

    assert exchange.read_bytes() == committed_bytes
    assert working.read_bytes() == committed_bytes
    assert service.transactions.read(txid).status == "committed"
    terminal = service.sessions.read_metadata(session_id)
    assert terminal["status"] == "applied"
    assert terminal["working_sha256"] == committed_sha256


def test_live_preview_bounds_first_changed_stable_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, _exchange, session_id = _store(tmp_path)
    ids = tuple(f"object-{index:02d}" for index in range(25))
    monkeypatch.setattr(
        store,
        "_live_write_impact",
        lambda _metadata, _working: sessions_module.WriteImpact(
            changed_ids=ids,
            normalized_object_count=25,
            structural_element_count=0,
        ),
    )

    summary = store.live_preview_summary(session_id, changed_id_limit=5)

    assert summary["changed_ids"] == list(ids[:5])
    assert summary["changed_id_count"] == 25
    assert summary["changed_ids_complete"] is False
    assert summary["complete"] is False
    assert "first 5" in summary["limitations"][0]


def test_gui_details_disclose_preview_completeness() -> None:
    text = bridge._preview_details_text(
        "session-id",
        {
            "available": True,
            "complete": False,
            "modified": True,
            "normalized_object_count": 4,
            "structural_element_count": 3,
            "object_count": 7,
            "changed_ids": ["component-a", "trace-b"],
        },
    )
    unavailable = bridge._preview_details_text(
        "session-id",
        {"available": False, "reason": "invalid XML"},
    )

    assert "4 normalized, 3 structural" in text
    assert "component-a, trace-b" in text
    assert "incomplete/truncated" in text
    assert "unavailable/incomplete" in unavailable
