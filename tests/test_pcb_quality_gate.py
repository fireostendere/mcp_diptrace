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


def test_partial_gate_is_open_and_blocks_later_pass():
    assert check_order({1: ("Placement", "PARTIAL"), 2: ("Routing", "PASS")})


def _schematic_project(tmp_path: Path) -> Path:
    import hashlib
    import shutil

    schematic = tmp_path / "board.dchxml"
    shutil.copy(Path(__file__).parent / "fixtures" / "schematic.xml", schematic)
    digest = hashlib.sha256(schematic.read_bytes()).hexdigest()
    (tmp_path / "PCB_BUILD.md").write_text(
        f"Input schematic SHA-256: `{digest}`\n| 1. Electrical checks | PENDING | todo |\n",
        encoding="utf-8",
    )
    return tmp_path


def _run_gate(monkeypatch, *argv: str) -> int:
    import sys

    from scripts import pcb_quality_gate

    monkeypatch.setattr(sys, "argv", ["pcb_quality_gate.py", *argv])
    return pcb_quality_gate.main()


def test_schematic_stage_needs_no_board_and_blocks_incomplete_review(tmp_path, monkeypatch, capsys):
    project = _schematic_project(tmp_path)
    assert _run_gate(monkeypatch, str(project), "--stage", "schematic") == 1
    out = capsys.readouterr().out
    assert "board" not in out.split("BLOCKED:")[1]
    assert "schematic review incomplete" in out


def test_schematic_stage_passes_a_clean_review(tmp_path, monkeypatch, capsys):
    from scripts import pcb_quality_gate

    project = _schematic_project(tmp_path)
    def clean_review(snapshot, categories):
        return [], {}, [], 10

    monkeypatch.setattr(pcb_quality_gate, "run_checks", clean_review)
    assert _run_gate(monkeypatch, str(project), "--stage", "schematic") == 0
    assert "schematic review clean" in capsys.readouterr().out
    # The default board stage still refuses a project without a board.
    assert _run_gate(monkeypatch, str(project)) == 1


def test_handoff_declares_stage_and_files(tmp_path, monkeypatch, capsys):
    import shutil

    from scripts import pcb_quality_gate

    project = _schematic_project(tmp_path)
    (project / "candidates").mkdir()
    shutil.move(project / "board.dchxml", project / "candidates" / "board.dchxml")
    (project / "historical.dchxml").write_text("<protected/>", encoding="utf-8")
    handoff = project / "PCB_BUILD.md"
    handoff.write_text(
        "Gate stage: schematic\nInput schematic: `candidates/board.dchxml`\n"
        "Current board: <path>\n" + handoff.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert pcb_quality_gate.parse_fields(handoff.read_text(encoding="utf-8")) == {
        "gate stage": "schematic",
        "input schematic": "candidates/board.dchxml",
    }

    def clean_review(snapshot, categories):
        return [], {}, [], 10

    monkeypatch.setattr(pcb_quality_gate, "run_checks", clean_review)
    # No flags: the declared candidate is gated, not the ambiguous root glob or a board.
    assert _run_gate(monkeypatch, str(project)) == 0
    assert "schematic review clean" in capsys.readouterr().out
    text = handoff.read_text(encoding="utf-8")
    text = text.replace("Gate stage: schematic", "Gate stage: layout")
    handoff.write_text(text, encoding="utf-8")
    assert _run_gate(monkeypatch, str(project)) == 1
    assert "unknown Gate stage" in capsys.readouterr().out
