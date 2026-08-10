from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from diptrace_mcp.cinematic import (
    CinematicEvent,
    CinematicRecorder,
    CinematicTimeline,
    ffmpeg_commands,
    infer_domain,
    play,
    timeline_from_events,
)


def test_domain_inference_distinguishes_schematic_and_pcb_tools() -> None:
    assert infer_domain("route_trace") == "pcb"
    assert infer_domain("set_component_position") == "pcb"
    assert infer_domain("create_schematic_wire") == "schematic"
    assert infer_domain("review_bom") == "general"


def test_timeline_compiles_deterministically_and_caps_pause() -> None:
    timeline = CinematicTimeline(title="Demo", preset="gif")
    timeline.chapter("Power")
    timeline.focus("U1", target="U1", domain="schematic")
    timeline.operation("route_trace", target="VCC")
    timeline.pause(5_000)

    cues = timeline.compile()

    assert [cue.index for cue in cues] == [0, 1, 2, 3]
    assert cues[0].start_ms == 0
    assert cues[0].settle_until_ms == cues[1].start_ms
    assert cues[2].event.domain == "pcb"
    assert cues[3].event.duration_ms == 900
    assert timeline.duration_ms() == cues[-1].settle_until_ms


def test_manifest_contains_recording_profiles_for_video_and_gif() -> None:
    timeline = CinematicTimeline(title="Schematic", preset="cinematic", domain="schematic")
    timeline.operation("create_schematic_wire", target="NET1")

    manifest = timeline.manifest()

    assert manifest["format"] == "diptrace-cinematic-v1"
    assert manifest["domain"] == "schematic"
    assert manifest["cue_count"] == 1
    assert manifest["recording"]["video"]["fps"] == 60
    assert manifest["recording"]["gif"]["fps"] == 20


def test_timeline_from_arbitrary_events_supports_generic_process_capture() -> None:
    timeline = timeline_from_events(
        [
            {"tool": "review_bom", "label": "Inspect BOM"},
            {"tool": "route_trace", "target": "CLK"},
            {"tool": "create_schematic_wire", "target": "RESET"},
        ],
        title="Any MCP process",
    )

    assert [event.domain for event in timeline.events] == ["general", "pcb", "schematic"]
    assert [event.label for event in timeline.events] == [
        "Inspect BOM",
        "Route Trace",
        "Create Schematic Wire",
    ]


def test_invalid_event_phase_is_rejected() -> None:
    with pytest.raises(ValueError, match="phase"):
        CinematicEvent(kind="operation", label="bad", phase="later")  # type: ignore[arg-type]


@dataclass
class Driver:
    labels: list[str] = field(default_factory=list)

    def handle(self, event: CinematicEvent) -> None:
        self.labels.append(event.label)


def test_playback_driver_receives_events_in_order_without_real_sleep() -> None:
    timeline = CinematicTimeline(title="Replay", preset="timelapse")
    timeline.operation("route_trace", label="Trace A")
    timeline.operation("route_trace", label="Trace B")
    driver = Driver()
    sleeps: list[float] = []

    play(timeline, driver, sleep=sleeps.append)

    assert driver.labels == ["Trace A", "Trace B"]
    assert sleeps == [0.12, 0.035, 0.12, 0.035]


def test_ffmpeg_commands_include_two_pass_gif_pipeline() -> None:
    commands = ffmpeg_commands("capture file.mkv", output_stem="demo output", preset="gif")

    assert "libx264" in commands["video"]
    assert "palettegen" in commands["gif_palette"]
    assert "paletteuse" in commands["gif"]
    assert "capture file.mkv" in commands["video"]


def test_recorder_roundtrip_and_payload_is_opt_in(tmp_path) -> None:
    path = tmp_path / "capture.jsonl"
    recorder = CinematicRecorder(path, title="Public demo", preset="gif", domain="auto")
    recorder.initialize()
    recorder.observe_tool("route_trace", target="CLK", payload={"private": "not-recorded"})
    recorder.observe_tool("create_schematic_wire", target="RESET")

    text = path.read_text(encoding="utf-8")
    assert "not-recorded" not in text

    timeline = CinematicRecorder.load(path)
    assert timeline.preset.name == "gif"
    assert [event.domain for event in timeline.events] == ["pcb", "schematic"]
