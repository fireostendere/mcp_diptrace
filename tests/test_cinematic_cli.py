from __future__ import annotations

import json

from diptrace_mcp.cinematic_cli import main


def test_cli_capture_compile_roundtrip(tmp_path, capsys) -> None:
    capture = tmp_path / "demo.jsonl"
    manifest = tmp_path / "demo.json"

    assert main(["init", str(capture), "--title", "PCB demo", "--preset", "gif"]) == 0
    assert main(["event", str(capture), "route_trace", "--target", "CLK"]) == 0
    assert main(["event", str(capture), "create_schematic_wire", "--target", "RESET"]) == 0
    assert main(["compile", str(capture), "--output", str(manifest)]) == 0

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["cue_count"] == 2
    assert [cue["event"]["domain"] for cue in payload["cues"]] == ["pcb", "schematic"]
    capsys.readouterr()


def test_cli_payload_is_ignored_unless_capture_opted_in(tmp_path) -> None:
    capture = tmp_path / "demo.jsonl"

    assert main(["init", str(capture), "--title", "Safe demo"]) == 0
    assert (
        main(
            [
                "event",
                str(capture),
                "review_bom",
                "--payload-json",
                '{"token":"secret"}',
            ]
        )
        == 0
    )

    assert "secret" not in capture.read_text(encoding="utf-8")
