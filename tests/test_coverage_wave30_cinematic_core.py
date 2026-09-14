from __future__ import annotations

import json
from pathlib import Path

import pytest

from diptrace_mcp.cinematic import (
    CinematicEvent,
    CinematicRecorder,
    CinematicTimeline,
    ffmpeg_commands,
)


def test_cinematic_event_and_timeline_validation_matrix() -> None:
    for kwargs, message in (
        ({"label": ""}, "label"),
        ({"label": "x", "domain": "bad"}, "domain"),
        ({"label": "x", "phase": "bad"}, "phase"),
        ({"label": "x", "duration_ms": -1}, "duration"),
        ({"label": "x", "settle_ms": -1}, "settle"),
    ):
        with pytest.raises(ValueError, match=message):
            CinematicEvent(kind="focus", **kwargs)  # type: ignore[arg-type]
    for kwargs, message in (
        ({"title": "x", "preset": "bad"}, "preset"),
        ({"title": "x", "domain": "bad"}, "domain"),
        ({"title": " "}, "title"),
    ):
        with pytest.raises(ValueError, match=message):
            CinematicTimeline(**kwargs)  # type: ignore[arg-type]


def test_timeline_event_helpers_and_duration_branches(tmp_path: Path) -> None:
    timeline = CinematicTimeline(title="Demo", domain="pcb")
    event = timeline.add(CinematicEvent(kind="focus", label="General"))
    assert event.domain == "pcb"
    timeline.reveal("Reveal")
    timeline.marker("Mark")
    timeline.annotate("Note")
    timeline.pause(100_000)
    timeline.operation("pcb_route", duration_ms=1)
    kinds = [cue.event.kind for cue in timeline.compile()]
    assert kinds == ["focus", "reveal", "marker", "annotation", "pause", "operation"]
    with pytest.raises(ValueError, match="pause duration"):
        timeline.pause(-1)
    path = timeline.write_manifest(tmp_path / "manifest.json")
    assert json.loads(path.read_text(encoding="utf-8"))["cue_count"] == 6
    with pytest.raises(ValueError, match="preset"):
        ffmpeg_commands("input", output_stem="output", preset="bad")


def test_cinematic_capture_validation_observation_and_load_errors(tmp_path: Path) -> None:
    for kwargs, message in (
        ({"title": "x", "preset": "bad"}, "preset"),
        ({"title": "x", "domain": "bad"}, "domain"),
        ({"title": " "}, "title"),
    ):
        with pytest.raises(ValueError, match=message):
            CinematicRecorder(tmp_path / "capture", **kwargs)  # type: ignore[arg-type]

    path = tmp_path / "capture.jsonl"
    capture = CinematicRecorder(path, title="Demo", include_payload=True)
    capture.initialize()
    with pytest.raises(FileExistsError):
        capture.initialize()
    with pytest.raises(ValueError, match="phase"):
        capture.observe_tool("tool", phase="bad")  # type: ignore[arg-type]
    capture.observe_tool("pcb_route", label="Route", target="N", payload={"x": 1})
    assert CinematicRecorder.load(path).events

    for raw, message in (
        ("", "empty"),
        ("[]\n", "header"),
        (
            json.dumps(
                {
                    "type": "diptrace-cinematic-capture",
                    "title": "Demo",
                    "preset": "cinematic",
                    "domain": "auto",
                }
            )
            + "\n\n[]\n",
            "event at line",
        ),
    ):
        path.write_text(raw, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            CinematicRecorder.load(path)
