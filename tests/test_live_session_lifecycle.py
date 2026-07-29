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
from diptrace_mcp.xml_document import sha256_bytes

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
    store.finalize(exact_id, "cancel", str(request["expected_sha256"]))

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
