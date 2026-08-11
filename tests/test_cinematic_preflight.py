from __future__ import annotations

import copy

import pytest

from diptrace_mcp.cinematic import CinematicSession
from diptrace_mcp.cinematic_preflight import (
    CinematicSafetyBudget,
    cinematic_content_sha256,
    preflight_cinematic_manifest,
)


def _manifest() -> dict[str, object]:
    session = CinematicSession(title="safe demo", domain="schematic")
    session.operation(
        "add_wire",
        payload={
            "desktop": {
                "steps": [
                    {"move_to": [0.2, 0.3], "click": "left"},
                    {"text": "R1", "hotkey": ["ctrl", "a"]},
                ]
            }
        },
    )
    return session.manifest()


def test_cinematic_preflight_accepts_compiled_manifest_and_counts_desktop_work() -> None:
    result = preflight_cinematic_manifest(_manifest())

    assert result.cue_count == 1
    assert result.desktop_command_count == 2
    assert result.text_character_count == 2
    assert len(result.content_sha256) == 64


def test_cinematic_content_hash_ignores_random_session_identity_only() -> None:
    first = _manifest()
    second = copy.deepcopy(first)
    second["session_id"] = "different-session"

    assert cinematic_content_sha256(first) == cinematic_content_sha256(second)
    second["title"] = "different title"
    assert cinematic_content_sha256(first) != cinematic_content_sha256(second)


def test_cinematic_preflight_refuses_timing_and_payload_budget_drift() -> None:
    invalid = _manifest()
    invalid["duration_ms"] = int(invalid["duration_ms"]) + 1
    with pytest.raises(ValueError, match="duration_ms"):
        preflight_cinematic_manifest(invalid)

    manifest = _manifest()
    with pytest.raises(ValueError, match="payload exceeds"):
        preflight_cinematic_manifest(
            manifest,
            CinematicSafetyBudget(max_payload_bytes_per_cue=10),
        )


def test_cinematic_preflight_refuses_oversized_hotkey_chord() -> None:
    manifest = _manifest()
    cues = manifest["cues"]
    assert isinstance(cues, list)
    cue = cues[0]
    assert isinstance(cue, dict)
    event = cue["event"]
    assert isinstance(event, dict)
    payload = event["payload"]
    assert isinstance(payload, dict)
    desktop = payload["desktop"]
    assert isinstance(desktop, dict)
    steps = desktop["steps"]
    assert isinstance(steps, list)
    steps[1]["hotkey"] = ["ctrl"] * 9

    with pytest.raises(ValueError, match="hotkey exceeds"):
        preflight_cinematic_manifest(manifest)
