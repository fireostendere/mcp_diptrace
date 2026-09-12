from pathlib import Path

from scripts.record_quality_gate_memory import append_event, event_id, render_event


def test_memory_event_is_idempotent_and_rag_readable(tmp_path: Path):
    report = {
        "captured_at": "2026-08-26T00:00:00+00:00",
        "project": "/work/dut-controller",
        "handoff": "/work/dut-controller/PCB_BUILD.md",
        "status": "BLOCKED",
        "gates": [{"number": 7, "status": "PARTIAL"}],
        "artifacts": {"board": {"path": "board.dipxml", "sha256": "abc"}},
        "quality": {
            "hard_error_count": 1,
            "warning_count": 0,
            "unrouted_connection_count": 2,
            "score": 1.0,
            "findings": [{"severity": "error", "code": "ROUTE", "message": "unrouted"}],
        },
        "blocked": ["QC error [ROUTE] unrouted"],
        "pending": ["gate 8 (Pours)"],
    }
    path = tmp_path / "memory.md"
    assert event_id(report)
    assert append_event(path, report)
    assert not append_event(path, report)
    text = path.read_text(encoding="utf-8")
    assert "PARTIAL" in text
    assert "unrouted" in text
    assert render_event(report).startswith("<!-- quality-gate-event:")
