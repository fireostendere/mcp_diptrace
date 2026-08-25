from pathlib import Path

from scripts.pcb_quality_gate import check_order, parse_handoff


def test_parses_gates_and_shas():
    text = "\n".join(
        [
            "# PCB build handoff",
            "Current board SHA-256: `" + "a" * 64 + "`",
            "| Gate | Status | Evidence |",
            "|---|---|---|",
            "| 1. ERC | PASS | ok |",
            "| 2. Evidence | PENDING | todo |",
        ]
    )
    gates, shas = parse_handoff(text)
    assert gates == {1: ("ERC", "PASS"), 2: ("Evidence", "PENDING")}
    assert shas == {"current board": "a" * 64}


def test_pass_above_pending_is_violation():
    gates = {1: ("ERC", "PENDING"), 2: ("Routing", "PASS")}
    violations = check_order(gates)
    assert any("gate 2 (Routing) is PASS" in item for item in violations)


def test_monotonic_handoff_has_no_violations(tmp_path: Path):
    gates = {1: ("ERC", "PASS"), 2: ("Native DRC", "PENDING"), 3: ("Media", "PENDING")}
    assert check_order(gates) == []


def test_unknown_status_fails_closed():
    assert check_order({1: ("ERC", "probably fine")}) != []
