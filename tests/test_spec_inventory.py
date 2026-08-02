"""Public-tree tests for inventory and evidence documentation claims."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "reference/diptrace-xml/spec_inventory.json"


def test_inventory_is_project_authored_factual_data() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert inventory["schema_version"] == "diptrace-factual-inventory-v1"
    assert inventory["sources"]
    assert inventory["facts"]
    assert all(source["source_kind"] == "synthetic_fixture" for source in inventory["sources"])
    assert all(fact["confidence"] == "synthetic" for fact in inventory["facts"])
    assert all("description" not in fact for fact in inventory["facts"])
    assert all("text" not in fact for fact in inventory["facts"])


def test_removed_external_material_is_not_in_current_tree() -> None:
    assert not (ROOT / "reference/diptrace-xml/extracted_text").exists()
    assert not (ROOT / "reference/diptrace-xml/sources").exists()


def test_documentation_keeps_live_angle_and_trust_boundaries() -> None:
    reference = (ROOT / "reference/diptrace-xml/REFERENCE.md").read_text(encoding="utf-8")
    coverage = (ROOT / "docs/FORMAT_COVERAGE.md").read_text(encoding="utf-8")

    assert "clean-room factual inventory" in reference
    assert "Component/@Angle" in reference
    assert "not a normative DipTrace format specification" in coverage
