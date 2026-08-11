from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field

from .domain import StrictModel


class CinematicSafetyBudget(StrictModel):
    max_cues: int = Field(default=5_000, ge=1, le=100_000)
    max_duration_ms: int = Field(default=3_600_000, ge=1, le=86_400_000)
    max_payload_bytes_per_cue: int = Field(default=1_000_000, ge=1, le=32_000_000)
    max_desktop_commands: int = Field(default=20_000, ge=1, le=1_000_000)
    max_path_points: int = Field(default=100_000, ge=1, le=2_000_000)
    max_text_characters: int = Field(default=100_000, ge=1, le=10_000_000)
    max_hotkey_keys: int = Field(default=8, ge=1, le=32)
    max_settle_gap_ms: int = Field(default=60_000, ge=0, le=600_000)


class CinematicPreflightResult(StrictModel):
    content_sha256: str
    cue_count: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    desktop_command_count: int = Field(ge=0)
    path_point_count: int = Field(ge=0)
    text_character_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


def _canonical_content(manifest: Mapping[str, Any]) -> bytes:
    content = {
        key: value
        for key, value in manifest.items()
        if key not in {"session_id", "created_at", "recorded_at"}
    }
    return json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def cinematic_content_sha256(manifest: Mapping[str, Any]) -> str:
    """Stable content identity independent of randomized recording/session identity."""

    return hashlib.sha256(_canonical_content(manifest)).hexdigest()


def _desktop_steps(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    desktop = payload.get("desktop")
    if desktop is None:
        return []
    if not isinstance(desktop, Mapping):
        raise ValueError("cinematic desktop payload must be an object")
    raw_steps = desktop.get("steps")
    if raw_steps is None:
        return [desktop]
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes)):
        raise ValueError("cinematic desktop.steps must be an array")
    if not raw_steps:
        raise ValueError("cinematic desktop.steps must not be empty")
    steps: list[Mapping[str, Any]] = []
    for index, item in enumerate(raw_steps):
        if not isinstance(item, Mapping):
            raise ValueError(f"cinematic desktop.steps[{index}] must be an object")
        steps.append(item)
    return steps


def preflight_cinematic_manifest(
    manifest: Mapping[str, Any],
    budget: CinematicSafetyBudget | None = None,
) -> CinematicPreflightResult:
    budget = budget or CinematicSafetyBudget()
    if manifest.get("format") != "diptrace-cinematic-v1":
        raise ValueError("cinematic manifest format must be diptrace-cinematic-v1")
    cues = manifest.get("cues")
    if not isinstance(cues, list):
        raise ValueError("cinematic manifest has no cues array")
    if len(cues) > budget.max_cues:
        raise ValueError(f"cinematic cue count exceeds {budget.max_cues}")
    declared_count = manifest.get("cue_count")
    if declared_count is not None and int(declared_count) != len(cues):
        raise ValueError("cinematic cue_count does not match cues array")

    previous_settle = 0
    desktop_commands = 0
    path_points = 0
    text_characters = 0
    warnings: list[str] = []
    observed_duration = 0
    for index, cue in enumerate(cues):
        if not isinstance(cue, Mapping):
            raise ValueError(f"invalid cinematic cue at index {index}")
        cue_index = int(cue.get("index", index))
        if cue_index != index:
            raise ValueError(f"cinematic cue index mismatch at {index}")
        start_ms = int(cue.get("start_ms", 0))
        end_ms = int(cue.get("end_ms", start_ms))
        settle_ms = int(cue.get("settle_until_ms", end_ms))
        if min(start_ms, end_ms, settle_ms) < 0:
            raise ValueError(f"cinematic cue {index} has negative timing")
        if not (previous_settle <= start_ms <= end_ms <= settle_ms):
            raise ValueError(f"cinematic cue {index} has overlapping or invalid timing")
        if settle_ms - end_ms > budget.max_settle_gap_ms:
            raise ValueError(
                f"cinematic cue {index} settle gap exceeds "
                f"{budget.max_settle_gap_ms} ms"
            )
        previous_settle = settle_ms
        observed_duration = settle_ms

        event = cue.get("event")
        if not isinstance(event, Mapping):
            raise ValueError(f"cinematic cue {index} has no event object")
        payload = event.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise ValueError(f"cinematic cue {index} payload must be an object")
        payload_size = len(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        if payload_size > budget.max_payload_bytes_per_cue:
            raise ValueError(
                f"cinematic cue {index} payload exceeds "
                f"{budget.max_payload_bytes_per_cue} bytes"
            )
        for step in _desktop_steps(payload):
            desktop_commands += 1
            path = step.get("path")
            if path is not None:
                if not isinstance(path, Sequence) or isinstance(path, (str, bytes)):
                    raise ValueError("cinematic desktop.path must be an array")
                path_points += len(path)
            text = step.get("text")
            if text is not None:
                if not isinstance(text, str):
                    raise ValueError("cinematic desktop.text must be a string")
                text_characters += len(text)
            hotkey = step.get("hotkey")
            if hotkey is not None:
                if not isinstance(hotkey, Sequence) or isinstance(hotkey, (str, bytes)):
                    raise ValueError("cinematic desktop.hotkey must be an array")
                if len(hotkey) > budget.max_hotkey_keys:
                    raise ValueError(
                        "cinematic desktop hotkey exceeds "
                        f"{budget.max_hotkey_keys} keys"
                    )

    declared_duration = int(manifest.get("duration_ms", observed_duration))
    if declared_duration != observed_duration:
        raise ValueError("cinematic duration_ms does not match final cue timing")
    if declared_duration > budget.max_duration_ms:
        raise ValueError(f"cinematic duration exceeds {budget.max_duration_ms} ms")
    if desktop_commands > budget.max_desktop_commands:
        raise ValueError("cinematic desktop command count exceeds safety budget")
    if path_points > budget.max_path_points:
        raise ValueError("cinematic desktop path-point count exceeds safety budget")
    if text_characters > budget.max_text_characters:
        raise ValueError("cinematic typed-text count exceeds safety budget")
    if desktop_commands == 0:
        warnings.append(
            "Manifest contains no desktop commands; playback will be "
            "presentation-only/no-op for operations without host macros."
        )
    return CinematicPreflightResult(
        content_sha256=cinematic_content_sha256(manifest),
        cue_count=len(cues),
        duration_ms=declared_duration,
        desktop_command_count=desktop_commands,
        path_point_count=path_points,
        text_character_count=text_characters,
        warnings=warnings,
    )
