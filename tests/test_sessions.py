from pathlib import Path
from typing import Any

import pytest

import diptrace_mcp.sessions as sessions_module
from diptrace_mcp.errors import SessionError
from diptrace_mcp.sessions import SessionStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_live_session_apply_cycle(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "schematic.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = metadata["session_id"]
    working = store.working_path(session_id)
    working.write_bytes(working.read_bytes().replace(b"<Value>10k</Value>", b"<Value>22k</Value>"))

    request = store.request_finish("apply")
    result = store.finalize(session_id, "apply", request["expected_sha256"])

    assert result["status"] == "applied"
    assert b"<Value>22k</Value>" in exchange.read_bytes()
    assert store.active_metadata() is None


def test_live_session_cancel_keeps_exchange(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    original = (FIXTURES / "pcb.xml").read_bytes()
    exchange.write_bytes(original)
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    working = store.working_path(metadata["session_id"])
    working.write_bytes(working.read_bytes().replace(b"<Value>10k</Value>", b"<Value>99k</Value>"))

    store.finalize(metadata["session_id"], "cancel")

    assert exchange.read_bytes() == original


def test_finish_request_publishes_control_after_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "schematic.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    writes: list[Path] = []
    original_write = sessions_module._atomic_write_json

    def record_write(path: Path, value: dict[str, Any]) -> None:
        writes.append(path)
        original_write(path, value)

    monkeypatch.setattr(sessions_module, "_atomic_write_json", record_write)

    store.request_finish("apply")

    assert writes == [
        store.metadata_path(metadata["session_id"]),
        store.control_path(metadata["session_id"]),
    ]


def test_session_state_read_retries_transient_os_errors(
    tmp_path: Path, monkeypatch: Any
) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "schematic.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    metadata_path = store.metadata_path(metadata["session_id"])
    original_read_text = Path.read_text
    attempts = 0

    def transient_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        nonlocal attempts
        if path == metadata_path and attempts < 2:
            attempts += 1
            raise OSError("temporary sharing violation")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(sessions_module, "_JSON_READ_RETRY_SECONDS", 0.0)
    monkeypatch.setattr(Path, "read_text", transient_read_text)

    assert store.read_metadata(metadata["session_id"])["status"] == "active"
    assert attempts == 2


def test_stale_active_json_is_ignored_when_session_not_active(
    tmp_path: Path,
) -> None:
    """If the process crashed leaving active.json, a new session should work."""
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = metadata["session_id"]

    # Simulate crash: finalize without cleaning active.json
    store.finalize(session_id, "cancel")

    # active.json still references the old (now cancelled) session.
    # New session creation should succeed because active_metadata()
    # checks status == "active" and finds "cancelled".
    metadata2 = store.create(exchange)
    assert metadata2["session_id"] != session_id
    assert metadata2["status"] == "active"


def test_double_finish_is_idempotent(tmp_path: Path) -> None:
    """Calling finalize twice on the same session raises on the second call."""
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = metadata["session_id"]

    store.finalize(session_id, "cancel")
    with pytest.raises(SessionError, match="not active"):
        store.finalize(session_id, "cancel")


def test_apply_rejects_source_type_mismatch(tmp_path: Path) -> None:
    """Apply must refuse if the working XML source type changes mid-session."""
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = metadata["session_id"]

    # Tamper: replace working XML with a different source type
    working = store.working_path(session_id)
    working.write_bytes(
        working.read_bytes().replace(
            b'DipTrace-PCB', b'DipTrace-Schematic'
        )
    )

    with pytest.raises(SessionError, match="type differs"):
        store.request_finish("apply")


def test_finish_rejects_tampered_working_xml(tmp_path: Path) -> None:
    """Apply must refuse if working XML changed after the finish request."""
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)
    session_id = metadata["session_id"]

    request = store.request_finish("apply")

    # Tamper after request
    working = store.working_path(session_id)
    working.write_bytes(working.read_bytes() + b"<Tampered/>")

    with pytest.raises(SessionError, match="changed after the finish request"):
        store.finalize(session_id, "apply", request["expected_sha256"])


def test_create_rejects_duplicate_active_session(tmp_path: Path) -> None:
    """Cannot create a second session while one is active."""
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    store.create(exchange)

    with pytest.raises(SessionError, match="session is active"):
        store.create(exchange)


def test_finalize_clears_active_json(tmp_path: Path) -> None:
    """After finalization, active.json should be removed."""
    exchange = tmp_path / "plugin_exchange.xml"
    exchange.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    store = SessionStore(tmp_path / "state", 10_000_000)
    metadata = store.create(exchange)

    store.finalize(metadata["session_id"], "cancel")

    assert not store.active_file.exists()
