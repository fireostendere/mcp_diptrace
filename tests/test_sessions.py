from pathlib import Path

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
