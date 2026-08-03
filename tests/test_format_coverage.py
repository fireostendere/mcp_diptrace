from __future__ import annotations

import json
from pathlib import Path

from scripts.report_format_coverage import (
    ContainerRewrite,
    _container_rewrites,
    _partition_names,
    _scan_source,
    compute_coverage,
)

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "reference" / "diptrace-xml" / "spec_inventory.json"
SOURCE = ROOT / "src" / "diptrace_mcp"


def test_call_detector_separates_reads_writes_and_mentions() -> None:
    facts = _scan_source(
        '''
"""D"""
element.findall("./A/B")
ET.SubElement(element, "C")
'''
    )

    classes = _partition_names(
        {"A", "B", "C", "D"},
        facts.read_elements,
        facts.written_elements,
        facts.bare_literals,
    )

    assert classes == {
        "normalized": ["A", "B"],
        "written": ["C"],
        "mentioned_only": ["D"],
        "passthrough": [],
    }


def test_reader_call_changes_classification() -> None:
    before = _scan_source('"""AddFieldsGlobal"""')
    after = _scan_source('element.findall("./AddFieldsGlobal")')

    before_classes = _partition_names(
        {"AddFieldsGlobal"},
        before.read_elements,
        before.written_elements,
        before.bare_literals,
    )
    after_classes = _partition_names(
        {"AddFieldsGlobal"},
        after.read_elements,
        after.written_elements,
        after.bare_literals,
    )

    assert before_classes["mentioned_only"] == ["AddFieldsGlobal"]
    assert after_classes["normalized"] == ["AddFieldsGlobal"]


def test_real_coverage_spot_checks_and_partitions_inventory() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    coverage = compute_coverage(inventory, SOURCE)
    normalized = set(coverage["normalized_elements"])

    assert {"CopperPour", "DifferentialPair", "MaskPaste", "PadPoint", "PadPoints"} <= normalized
    assert "Id" not in normalized

    classes = [
        set(coverage["normalized_elements"]),
        set(coverage["written_elements"]),
        set(coverage["mentioned_only_elements"]),
        set(coverage["passthrough_elements"]),
    ]
    assert set().union(*classes) == set(inventory["elements"])
    assert sum(len(items) for items in classes) == len(inventory["elements"])


def test_container_rewrite_detector_finds_wholesale_removal(tmp_path: Path) -> None:
    source = tmp_path / "routing_compiler.py"
    source.write_text(
        """
def _write_points(trace):
    container = trace.find("./Points")
    for child in list(container):
        container.remove(child)
""",
        encoding="utf-8",
    )

    assert _container_rewrites(tmp_path) == [
        ContainerRewrite(
            module="routing_compiler.py",
            function="_write_points",
            container="Points",
            removed_children=None,
        )
    ]
