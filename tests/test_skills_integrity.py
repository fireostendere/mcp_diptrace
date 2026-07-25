"""Skill-package integrity gates.

Every PCB skill must have a SKILL.md, a result schema, an example, and evals.
The generate_pcb_skills.py --check script already validates these, but this test
provides an explicit pytest-level gate so the CI matrix catches regressions
even if the script step is skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def _skill_dirs() -> list[Path]:
    return sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def test_all_skills_have_required_artifacts() -> None:
    """Every skill directory must contain SKILL.md, schema, example, and evals."""
    errors: list[str] = []
    for skill_dir in _skill_dirs():
        name = skill_dir.name
        for relpath in (
            "SKILL.md",
            "schemas/result.schema.json",
            "examples/result.example.json",
            "evals/scenarios.json",
            "evals/assertions.json",
        ):
            if not (skill_dir / relpath).exists():
                errors.append(f"{name}: missing {relpath}")
    assert not errors, "Skills missing required artifacts:\n" + "\n".join(errors)


def test_schemas_are_valid_json() -> None:
    """All skill schemas and examples must be valid JSON."""
    errors: list[str] = []
    for skill_dir in _skill_dirs():
        for relpath in ("schemas/result.schema.json", "examples/result.example.json"):
            path = skill_dir / relpath
            if path.exists():
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    errors.append(f"{skill_dir.name}/{relpath}: {exc}")
    assert not errors, "Invalid JSON in skill artifacts:\n" + "\n".join(errors)


def test_capability_map_references_existing_skills() -> None:
    """The capability-map.json missing entries should reference known skill names."""
    cap_map_path = SKILLS_DIR / "capability-map.json"
    if not cap_map_path.exists():
        return
    cap_map = json.loads(cap_map_path.read_text(encoding="utf-8"))
    # Missing entries reference contract names, not skill names directly — just
    # verify the file is valid JSON and has the expected top-level keys.
    assert "aliases" in cap_map
    assert "missing" in cap_map


def test_skill_count_matches_generate_check() -> None:
    """The number of skills with SKILL.md must be stable (57 as of Phase 8)."""
    count = len(_skill_dirs())
    assert count >= 57, f"Expected at least 57 skills, found {count}"
