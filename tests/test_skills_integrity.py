"""Content-neutral JSON checks for the optional skill-package artifacts."""

from __future__ import annotations

import json
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _skill_dirs() -> list[Path]:
    return sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def test_optional_skill_json_artifacts_are_valid() -> None:
    """Every JSON artifact that a skill chooses to ship must parse."""
    errors: list[str] = []
    for skill_dir in _skill_dirs():
        for path in skill_dir.rglob("*.json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{path.relative_to(SKILLS_DIR)}: {exc}")
    assert not errors, "Invalid JSON in skill artifacts:\n" + "\n".join(errors)


def test_capability_map_is_valid_json() -> None:
    cap_map_path = SKILLS_DIR / "capability-map.json"
    assert cap_map_path.exists()
    assert isinstance(json.loads(cap_map_path.read_text(encoding="utf-8")), dict)
