from __future__ import annotations

import json
from pathlib import Path

import pytest

from diptrace_mcp import sessions
from diptrace_mcp.errors import SessionError, Sha256MismatchError
from diptrace_mcp.xml_document import sha256_bytes

FIXTURE = Path(__file__).parent / "fixtures" / "pcb.xml"


def _store(tmp_path: Path) -> tuple[sessions.SessionStore, str]:
    exchange = tmp_path / "exchange.xml"
    exchange.write_bytes(FIXTURE.read_bytes())
    store = sessions.SessionStore(tmp_path / "state", 10_000_000, allowed_roots=(tmp_path,))
    metadata = store.create(exchange)
    return store, str(metadata["session_id"])


def test_stable_file_and_json_readers_fail_closed(tmp_path: Path) -> None:
    malformed = tmp_path / "state.json"
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(SessionError, match="JSON object"):
        sessions._read_json(malformed)
    missing = tmp_path / "missing"
    with pytest.raises(SessionError, match="Cannot open"):
        sessions._stable_regular_file_bytes(missing, 10, purpose="fixture")
    large = tmp_path / "large"
    large.write_bytes(b"1234")
    with pytest.raises(SessionError, match="size limit"):
        sessions._stable_regular_file_bytes(large, 3, purpose="fixture")
    link = tmp_path / "link"
    link.symlink_to(large)
    with pytest.raises(SessionError, match="redirected"):
        sessions._stable_regular_file_bytes(link, 10, purpose="fixture")
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(SessionError, match="regular file"):
        sessions._stable_regular_file_bytes(directory, 10, purpose="fixture")


def test_session_path_and_metadata_tamper_guards(tmp_path: Path) -> None:
    store, session_id = _store(tmp_path)
    working = store.working_path(session_id)
    assert store.session_id_for_working_path(working) == session_id
    assert store.session_id_for_working_path(tmp_path / "outside.xml") is None
    assert store.session_id_for_working_path(working.parent / "other.xml") is None
    assert store.session_id_for_working_path(store.sessions_dir / "invalid" / "working.xml") is None

    metadata_path = store.metadata_path(session_id)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["session_id"] = "00000000-0000-4000-8000-000000000001"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(SessionError, match="does not match"):
        store.read_metadata(session_id)


def test_mutation_guards_cover_inactive_pending_and_hash_mismatch(tmp_path: Path) -> None:
    store, session_id = _store(tmp_path)
    working = store.working_path(session_id)
    original = working.read_bytes()
    digest = sha256_bytes(original)
    with pytest.raises(Sha256MismatchError, match="changed before"):
        store.mutate_working(
            session_id,
            expected_sha256="0" * 64,
            replacement=original,
        )

    store.request_finish("cancel")
    with pytest.raises(SessionError, match="frozen"):
        store.mutate_working(
            session_id,
            expected_sha256=digest,
            replacement=original,
        )

    store.clear_finish_request(session_id)
    store.update_metadata(session_id, finish_requested=None, status="cancelled")
    with pytest.raises(SessionError, match="not active"):
        store.mutate_working(
            session_id,
            expected_sha256=digest,
            replacement=original,
        )


def test_finish_rejection_compare_and_swap_guards(tmp_path: Path) -> None:
    store, session_id = _store(tmp_path)
    request = store.request_finish("cancel")
    with pytest.raises(SessionError, match="different finish request"):
        store.reject_finish_request(
            session_id,
            "bad",
            expected_request_id="request_00000000000000000000000000000000",
        )
    store.reject_finish_request(
        session_id,
        "retry",
        expected_request_id=str(request["request_id"]),
    )
    assert store.read_metadata(session_id)["last_error"] == "retry"

    control = store.control_path(session_id)
    control.write_text("{", encoding="utf-8")
    observed = store.read_finish_request(session_id)
    control.write_text("[]", encoding="utf-8")
    with pytest.raises(SessionError, match="changed finish request"):
        store.reject_malformed_finish_request(
            session_id,
            "bad",
            expected_control_sha256=str(observed["_control_sha256"]),
        )
    current = store.read_finish_request(session_id)
    store.reject_malformed_finish_request(
        session_id,
        "malformed",
        expected_control_sha256=str(current["_control_sha256"]),
    )
    assert not control.exists()


def test_terminal_timestamp_rejects_invalid_and_tampered_sessions(tmp_path: Path) -> None:
    store, session_id = _store(tmp_path)
    metadata_path = store.metadata_path(session_id)
    metadata = store.read_metadata(session_id)
    assert store._validated_terminal_timestamp(session_id, metadata_path, metadata) is None

    terminal = {
        **metadata,
        "status": "abandoned",
        "finished_at": metadata["updated_at"],
    }
    assert store._validated_terminal_timestamp(session_id, metadata_path, terminal) is None
    terminal["abandon_reason"] = "test"
    terminal["finished_at"] = "bad"
    assert store._validated_terminal_timestamp(session_id, metadata_path, terminal) is None
    terminal["finished_at"] = metadata["updated_at"]
    terminal["working_sha256"] = "0" * 64
    assert store._validated_terminal_timestamp(session_id, metadata_path, terminal) is None


def test_live_guard_rejects_unrecorded_file_hash(tmp_path: Path) -> None:
    store, session_id = _store(tmp_path)
    working = store.working_path(session_id)
    with (
        pytest.raises(Sha256MismatchError, match="guarded edit metadata"),
        store.guard_working_mutation(
            session_id, expected_sha256=sha256_bytes(working.read_bytes())
        ) as guard,
    ):
        guard.record_edit(working_sha256="0" * 64)


def test_session_lease_success_release_and_recovery_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "lock"
    with sessions._exclusive_session_lock(lock):
        assert lock.with_name("lock.lease").is_dir()
    assert not lock.with_name("lock.lease").exists()

    lease = tmp_path / "lease"
    lease.mkdir()
    (lease / "owner.json").write_text('{"nonce":"x"}', encoding="utf-8")
    sessions._release_owned_session_lease(lease, "x")
    assert not lease.exists()

    lease.mkdir()
    with pytest.raises(SessionError, match="unexpected owner"):
        (lease / "owner.json").write_text('{"nonce":"other"}', encoding="utf-8")
        sessions._release_owned_session_lease(lease, "x")

    lease = tmp_path / "dead.lease"
    reaper = tmp_path / "dead.reaper"
    assert not sessions._reap_dead_session_lease(lease, reaper, expected_nonce=None)
    reaper.mkdir()
    assert not sessions._reap_dead_session_lease(lease, reaper, expected_nonce="x")
    reaper.rmdir()

    lease.mkdir()
    (lease / "owner.json").write_text(
        json.dumps({"nonce": "x", "process": {"pid": 1}}), encoding="utf-8"
    )
    monkeypatch.setattr(sessions, "_bridge_process_liveness", lambda _value: "alive")
    assert not sessions._reap_dead_session_lease(lease, reaper, expected_nonce="x")
    monkeypatch.setattr(sessions, "_bridge_process_liveness", lambda _value: "dead")
    assert sessions._reap_dead_session_lease(lease, reaper, expected_nonce="x")
    assert not lease.exists()


def test_session_lease_detects_replaced_owner(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    with (
        pytest.raises(SessionError, match="was replaced"),
        sessions._exclusive_session_lock(lock),
    ):
        owner = lock.with_name("lock.lease") / "owner.json"
        value = json.loads(owner.read_text(encoding="utf-8"))
        value["nonce"] = "other"
        owner.write_text(json.dumps(value), encoding="utf-8")
