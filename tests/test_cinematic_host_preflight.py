from __future__ import annotations

import pytest

from diptrace_mcp.cinematic import CinematicTimeline
from diptrace_mcp.cinematic_host import DryRunDesktopDriver, play_manifest


def test_play_manifest_preflights_before_any_driver_action() -> None:
    timeline = CinematicTimeline(title="Preflight boundary", preset="gif")
    timeline.operation(
        "route_trace",
        payload={"desktop": {"move_to": [0.4, 0.5], "click": "left"}},
    )
    manifest = timeline.manifest()
    manifest["duration_ms"] = int(manifest["duration_ms"]) + 1
    driver = DryRunDesktopDriver()

    with pytest.raises(ValueError, match="duration_ms"):
        play_manifest(manifest, driver, sleep=lambda _seconds: None)

    assert driver.commands == []
