from __future__ import annotations

import json
import shlex
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

CinematicDomain = Literal["auto", "general", "pcb", "schematic"]
CinematicKind = Literal[
    "chapter",
    "focus",
    "operation",
    "reveal",
    "pause",
    "marker",
    "annotation",
]
CinematicPhase = Literal["before", "after", "single"]


@dataclass(frozen=True, slots=True)
class CinematicPreset:
    name: str
    fps: int
    operation_ms: int
    focus_ms: int
    reveal_ms: int
    settle_ms: int
    chapter_ms: int
    max_pause_ms: int
    gif_fps: int
    gif_width: int


PRESETS: dict[str, CinematicPreset] = {
    "cinematic": CinematicPreset(
        name="cinematic",
        fps=60,
        operation_ms=420,
        focus_ms=360,
        reveal_ms=520,
        settle_ms=180,
        chapter_ms=850,
        max_pause_ms=1800,
        gif_fps=20,
        gif_width=1280,
    ),
    "timelapse": CinematicPreset(
        name="timelapse",
        fps=60,
        operation_ms=120,
        focus_ms=90,
        reveal_ms=160,
        settle_ms=35,
        chapter_ms=350,
        max_pause_ms=600,
        gif_fps=24,
        gif_width=1280,
    ),
    "tutorial": CinematicPreset(
        name="tutorial",
        fps=60,
        operation_ms=700,
        focus_ms=550,
        reveal_ms=800,
        settle_ms=400,
        chapter_ms=1300,
        max_pause_ms=2600,
        gif_fps=15,
        gif_width=1280,
    ),
    "gif": CinematicPreset(
        name="gif",
        fps=30,
        operation_ms=220,
        focus_ms=180,
        reveal_ms=260,
        settle_ms=80,
        chapter_ms=420,
        max_pause_ms=900,
        gif_fps=18,
        gif_width=960,
    ),
}

_PCB_HINTS = (
    "pcb",
    "board",
    "route",
    "trace",
    "via",
    "copper",
    "silkscreen",
    "placement",
    "component_position",
    "testpoint",
    "panel",
    "keepout",
)
_SCHEMATIC_HINTS = (
    "schematic",
    "wire",
    "symbol",
    "junction",
    "net_label",
    "component_pin",
    "erc",
)


@dataclass(slots=True)
class CinematicEvent:
    kind: CinematicKind
    label: str
    domain: Literal["general", "pcb", "schematic"] = "general"
    phase: CinematicPhase = "single"
    tool: str | None = None
    target: str | None = None
    duration_ms: int | None = None
    settle_ms: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("cinematic event label must not be empty")
        if self.domain not in {"general", "pcb", "schematic"}:
            raise ValueError(f"unknown cinematic event domain: {self.domain}")
        if self.phase not in {"before", "after", "single"}:
            raise ValueError(f"unknown cinematic event phase: {self.phase}")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms must be >= 0")
        if self.settle_ms is not None and self.settle_ms < 0:
            raise ValueError("settle_ms must be >= 0")


@dataclass(frozen=True, slots=True)
class CompiledCue:
    index: int
    start_ms: int
    end_ms: int
    settle_until_ms: int
    event: CinematicEvent

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event"] = asdict(self.event)
        return result


class PlaybackDriver(Protocol):
    """Host-specific adapter used by the generic cinematic player."""

    def handle(self, event: CinematicEvent) -> None: ...


class CinematicTimeline:
    """Deterministic, host-agnostic storyboard for PCB, schematic or generic work."""

    def __init__(
        self,
        *,
        title: str,
        preset: str = "cinematic",
        domain: CinematicDomain = "auto",
        session_id: str | None = None,
    ) -> None:
        if preset not in PRESETS:
            raise ValueError(f"unknown cinematic preset: {preset}")
        if domain not in {"auto", "general", "pcb", "schematic"}:
            raise ValueError(f"unknown cinematic domain: {domain}")
        if not title.strip():
            raise ValueError("cinematic title must not be empty")
        self.title = title.strip()
        self.preset = PRESETS[preset]
        self.domain = domain
        self.session_id = session_id or f"cin_{uuid.uuid4().hex}"
        self.events: list[CinematicEvent] = []

    def add(self, event: CinematicEvent) -> CinematicEvent:
        if self.domain != "auto" and event.domain == "general":
            event.domain = self.domain
        self.events.append(event)
        return event

    def chapter(self, label: str, *, domain: CinematicDomain = "auto") -> CinematicEvent:
        return self.add(
            CinematicEvent(
                kind="chapter",
                label=label,
                domain=self._resolve_domain(None, domain),
            )
        )

    def focus(
        self,
        label: str,
        *,
        target: str | None = None,
        domain: CinematicDomain = "auto",
        duration_ms: int | None = None,
    ) -> CinematicEvent:
        return self.add(
            CinematicEvent(
                kind="focus",
                label=label,
                target=target,
                domain=self._resolve_domain(None, domain),
                duration_ms=duration_ms,
            )
        )

    def operation(
        self,
        tool: str,
        *,
        label: str | None = None,
        target: str | None = None,
        domain: CinematicDomain = "auto",
        phase: CinematicPhase = "single",
        payload: Mapping[str, Any] | None = None,
        duration_ms: int | None = None,
        settle_ms: int | None = None,
    ) -> CinematicEvent:
        return self.add(
            CinematicEvent(
                kind="operation",
                label=label or humanize_tool_name(tool),
                tool=tool,
                target=target,
                domain=self._resolve_domain(tool, domain),
                phase=phase,
                payload=dict(payload or {}),
                duration_ms=duration_ms,
                settle_ms=settle_ms,
            )
        )

    def reveal(
        self,
        label: str,
        *,
        target: str | None = None,
        domain: CinematicDomain = "auto",
        payload: Mapping[str, Any] | None = None,
    ) -> CinematicEvent:
        return self.add(
            CinematicEvent(
                kind="reveal",
                label=label,
                target=target,
                domain=self._resolve_domain(None, domain),
                payload=dict(payload or {}),
            )
        )

    def pause(self, duration_ms: int, *, label: str = "Pause") -> CinematicEvent:
        if duration_ms < 0:
            raise ValueError("pause duration must be >= 0")
        return self.add(
            CinematicEvent(
                kind="pause",
                label=label,
                duration_ms=min(duration_ms, self.preset.max_pause_ms),
            )
        )

    def marker(self, label: str, *, payload: Mapping[str, Any] | None = None) -> CinematicEvent:
        return self.add(
            CinematicEvent(kind="marker", label=label, payload=dict(payload or {}))
        )

    def annotate(
        self,
        label: str,
        *,
        target: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> CinematicEvent:
        return self.add(
            CinematicEvent(
                kind="annotation",
                label=label,
                target=target,
                payload=dict(payload or {}),
            )
        )

    def observe_tool(
        self,
        tool: str,
        *,
        phase: CinematicPhase = "single",
        label: str | None = None,
        target: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> CinematicEvent:
        """Record an arbitrary MCP/service action without knowing its implementation."""

        return self.operation(
            tool,
            label=label,
            target=target,
            phase=phase,
            payload=payload,
        )

    def compile(self) -> list[CompiledCue]:
        cursor_ms = 0
        cues: list[CompiledCue] = []
        for index, event in enumerate(self.events):
            duration_ms = self._duration_for(event)
            settle_ms = self.preset.settle_ms if event.settle_ms is None else event.settle_ms
            if event.kind in {"pause", "marker"}:
                settle_ms = 0
            cue = CompiledCue(
                index=index,
                start_ms=cursor_ms,
                end_ms=cursor_ms + duration_ms,
                settle_until_ms=cursor_ms + duration_ms + settle_ms,
                event=event,
            )
            cues.append(cue)
            cursor_ms = cue.settle_until_ms
        return cues

    def duration_ms(self) -> int:
        cues = self.compile()
        return cues[-1].settle_until_ms if cues else 0

    def manifest(self) -> dict[str, Any]:
        cues = self.compile()
        return {
            "format": "diptrace-cinematic-v1",
            "session_id": self.session_id,
            "title": self.title,
            "preset": self.preset.name,
            "domain": self.domain,
            "fps": self.preset.fps,
            "duration_ms": self.duration_ms(),
            "cue_count": len(cues),
            "cues": [cue.as_dict() for cue in cues],
            "recording": recording_profile(self.preset),
        }

    def write_manifest(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_text(json.dumps(self.manifest(), indent=2, ensure_ascii=False) + "\n")
        return target

    def _resolve_domain(
        self,
        tool: str | None,
        requested: CinematicDomain,
    ) -> Literal["general", "pcb", "schematic"]:
        if requested != "auto":
            return requested
        if self.domain != "auto":
            return self.domain
        return infer_domain(tool or "")

    def _duration_for(self, event: CinematicEvent) -> int:
        if event.duration_ms is not None:
            return event.duration_ms
        if event.kind == "chapter":
            return self.preset.chapter_ms
        if event.kind == "focus":
            return self.preset.focus_ms
        if event.kind == "reveal":
            return self.preset.reveal_ms
        if event.kind == "pause":
            return 0
        if event.kind == "marker":
            return 0
        if event.kind == "annotation":
            return self.preset.focus_ms
        return self.preset.operation_ms


def infer_domain(tool_name: str) -> Literal["general", "pcb", "schematic"]:
    normalized = tool_name.lower()
    if any(token in normalized for token in _SCHEMATIC_HINTS):
        return "schematic"
    if any(token in normalized for token in _PCB_HINTS):
        return "pcb"
    return "general"


def humanize_tool_name(tool_name: str) -> str:
    value = tool_name.strip().replace("-", "_")
    return " ".join(piece for piece in value.split("_") if piece).strip().title() or "Operation"


def recording_profile(preset: CinematicPreset) -> dict[str, Any]:
    return {
        "video": {
            "container": "mp4",
            "fps": preset.fps,
            "codec": "h264",
            "pixel_format": "yuv420p",
            "capture_hint": "record the DipTrace window at native resolution; crop in post",
        },
        "gif": {
            "fps": preset.gif_fps,
            "width": preset.gif_width,
            "palette": "two-pass palettegen/paletteuse",
            "loop": 0,
        },
    }


def ffmpeg_commands(
    input_video: str | Path,
    *,
    output_stem: str | Path,
    preset: str = "cinematic",
) -> dict[str, str]:
    if preset not in PRESETS:
        raise ValueError(f"unknown cinematic preset: {preset}")
    profile = PRESETS[preset]
    input_q = shlex.quote(str(input_video))
    output = str(output_stem)
    mp4_q = shlex.quote(output + ".mp4")
    palette_q = shlex.quote(output + ".palette.png")
    gif_q = shlex.quote(output + ".gif")
    scale = f"fps={profile.gif_fps},scale={profile.gif_width}:-1:flags=lanczos"
    return {
        "video": (
            f"ffmpeg -y -i {input_q} -c:v libx264 -preset medium -crf 18 "
            f"-pix_fmt yuv420p -movflags +faststart {mp4_q}"
        ),
        "gif_palette": (
            f"ffmpeg -y -i {input_q} -vf {shlex.quote(scale + ',palettegen=stats_mode=diff')} "
            f"{palette_q}"
        ),
        "gif": (
            f"ffmpeg -y -i {input_q} -i {palette_q} "
            f"-lavfi {shlex.quote(scale + ' [x]; [x][1:v] paletteuse=dither=sierra2_4a')} "
            f"-loop 0 {gif_q}"
        ),
    }


def play(
    timeline: CinematicTimeline,
    driver: PlaybackDriver,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Replay a compiled timeline with deterministic pacing through a host driver."""

    for cue in timeline.compile():
        event = cue.event
        driver.handle(event)
        duration_ms = cue.end_ms - cue.start_ms
        settle_ms = cue.settle_until_ms - cue.end_ms
        if duration_ms:
            sleep(duration_ms / 1000.0)
        if settle_ms:
            sleep(settle_ms / 1000.0)


def timeline_from_events(
    events: Iterable[Mapping[str, Any]],
    *,
    title: str,
    preset: str = "cinematic",
    domain: CinematicDomain = "auto",
) -> CinematicTimeline:
    timeline = CinematicTimeline(title=title, preset=preset, domain=domain)
    for raw in events:
        tool = str(raw.get("tool") or raw.get("name") or "operation")
        timeline.observe_tool(
            tool,
            phase=str(raw.get("phase") or "single"),  # type: ignore[arg-type]
            label=str(raw["label"]) if raw.get("label") is not None else None,
            target=str(raw["target"]) if raw.get("target") is not None else None,
            payload=raw.get("payload") if isinstance(raw.get("payload"), Mapping) else None,
        )
    return timeline


class CinematicRecorder:
    """Append-only JSONL recorder suitable for wrapping any MCP or service workflow."""

    def __init__(
        self,
        path: str | Path,
        *,
        title: str,
        preset: str = "cinematic",
        domain: CinematicDomain = "auto",
        include_payload: bool = False,
    ) -> None:
        if preset not in PRESETS:
            raise ValueError(f"unknown cinematic preset: {preset}")
        if domain not in {"auto", "general", "pcb", "schematic"}:
            raise ValueError(f"unknown cinematic domain: {domain}")
        self.path = Path(path)
        self.title = title.strip()
        self.preset = preset
        self.domain = domain
        self.include_payload = include_payload
        if not self.title:
            raise ValueError("cinematic title must not be empty")

    def initialize(self, *, overwrite: bool = False) -> Path:
        if self.path.exists() and not overwrite:
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        header = {
            "type": "diptrace-cinematic-capture",
            "version": 1,
            "title": self.title,
            "preset": self.preset,
            "domain": self.domain,
            "include_payload": self.include_payload,
        }
        self.path.write_text(json.dumps(header, ensure_ascii=False) + "\n", encoding="utf-8")
        return self.path

    def observe_tool(
        self,
        tool: str,
        *,
        phase: CinematicPhase = "single",
        label: str | None = None,
        target: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        if phase not in {"before", "after", "single"}:
            raise ValueError(f"unknown cinematic event phase: {phase}")
        record: dict[str, Any] = {
            "type": "event",
            "tool": tool,
            "phase": phase,
        }
        if label is not None:
            record["label"] = label
        if target is not None:
            record["target"] = target
        if self.include_payload and payload is not None:
            record["payload"] = dict(payload)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> CinematicTimeline:
        source = Path(path)
        lines = source.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise ValueError("cinematic capture is empty")
        header = json.loads(lines[0])
        if not isinstance(header, dict) or header.get("type") != "diptrace-cinematic-capture":
            raise ValueError("cinematic capture header is invalid")
        events: list[Mapping[str, Any]] = []
        for line_number, line in enumerate(lines[1:], start=2):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or record.get("type") != "event":
                raise ValueError(f"invalid cinematic event at line {line_number}")
            events.append(record)
        return timeline_from_events(
            events,
            title=str(header.get("title") or "Cinematic capture"),
            preset=str(header.get("preset") or "cinematic"),
            domain=str(header.get("domain") or "auto"),  # type: ignore[arg-type]
        )
