from pathlib import Path
from typing import Any

import diptrace_mcp.sessions as sessions_module
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
