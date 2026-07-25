"""Tests for the DipTrace XML specification inventory and format coverage."""

from __future__ import annotations

import json
from pathlib import Path

_INVENTORY_PATH = Path("reference/diptrace-xml/spec_inventory.json")
_COVERAGE_PATH = Path("docs/FORMAT_COVERAGE.md")
_OPEN_QUESTIONS_PATH = Path("docs/OPEN_QUESTIONS.md")


def _load_inventory() -> dict:
    """Load the spec inventory JSON."""
    with open(_INVENTORY_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestSpecInventory:
    """Tests for the spec inventory file."""

    def test_inventory_exists(self) -> None:
        """The inventory file must exist."""
        assert _INVENTORY_PATH.exists(), f"{_INVENTORY_PATH} does not exist"

    def test_inventory_schema_version(self) -> None:
        """The inventory must have the correct schema version."""
        inventory = _load_inventory()
        assert inventory["schema_version"] == "diptrace-spec-inventory-v1"

    def test_inventory_has_sources(self) -> None:
        """The inventory must list at least one source."""
        inventory = _load_inventory()
        assert len(inventory["sources"]) >= 2  # PCB + Schematic specs

    def test_inventory_has_elements(self) -> None:
        """The inventory must contain at least 50 elements."""
        inventory = _load_inventory()
        assert len(inventory["elements"]) >= 50

    def test_inventory_elements_have_required_fields(self) -> None:
        """Every element must have documents, pages, attributes, and children."""
        inventory = _load_inventory()
        for name, elem in inventory["elements"].items():
            assert "documents" in elem, f"Element {name} missing 'documents'"
            assert "pages" in elem, f"Element {name} missing 'pages'"
            assert "attributes" in elem, f"Element {name} missing 'attributes'"
            assert "children" in elem, f"Element {name} missing 'children'"
            assert isinstance(elem["documents"], list), f"Element {name} documents not a list"
            assert len(elem["documents"]) > 0, f"Element {name} has no documents"

    def test_inventory_attributes_have_required_fields(self) -> None:
        """Every attribute must have type, description, enum, units, and omitted_when."""
        inventory = _load_inventory()
        for elem_name, elem in inventory["elements"].items():
            for attr_name, attr in elem["attributes"].items():
                assert "type" in attr, f"{elem_name}.{attr_name} missing 'type'"
                assert attr["type"] in ("Int", "Real", "Text", "Bool"), (
                    f"{elem_name}.{attr_name} has invalid type: {attr['type']}"
                )
                assert "description" in attr, f"{elem_name}.{attr_name} missing 'description'"
                assert "units" in attr, f"{elem_name}.{attr_name} missing 'units'"
                assert "omitted_when" in attr, f"{elem_name}.{attr_name} missing 'omitted_when'"

    def test_key_elements_present(self) -> None:
        """Key elements from both PCB and Schematic specs must be present."""
        inventory = _load_inventory()
        required_elements = [
            "Source", "Component", "Trace", "Point", "Net", "Pad",
            "CopperPour", "Shape", "Ratline", "BoardOutline",
            "Panel", "DRC", "NetClass", "ViaStyle", "CopperLayers",
            "DifferentialPair", "Segment", "CenterPoint",
            "Part", "Wire", "Bus", "Sheet",
        ]
        for elem_name in required_elements:
            assert elem_name in inventory["elements"], (
                f"Required element '{elem_name}' not found in inventory"
            )

    def test_source_sha256_are_hex(self) -> None:
        """Source SHA-256 hashes must be valid hex strings."""
        inventory = _load_inventory()
        for source in inventory["sources"]:
            sha = source["sha256"]
            assert len(sha) == 64, f"SHA-256 for {source['file']} is not 64 chars"
            assert all(c in "0123456789abcdef" for c in sha), (
                f"SHA-256 for {source['file']} contains non-hex chars"
            )


class TestFormatCoverage:
    """Tests for the format coverage report."""

    def test_coverage_file_exists(self) -> None:
        """The coverage file must exist."""
        assert _COVERAGE_PATH.exists(), f"{_COVERAGE_PATH} does not exist"

    def test_coverage_file_is_nonempty(self) -> None:
        """The coverage file must not be empty."""
        content = _COVERAGE_PATH.read_text(encoding="utf-8")
        assert len(content) > 100

    def test_coverage_has_summary_table(self) -> None:
        """The coverage file must contain a summary table."""
        content = _COVERAGE_PATH.read_text(encoding="utf-8")
        assert "Total elements in spec" in content
        assert "Normalized" in content
        assert "Written" in content
        assert "Mentioned only" in content
        assert "Passthrough" in content
        assert "Coverage" in content


class TestOpenQuestions:
    """Tests for the open questions document."""

    def test_open_questions_exists(self) -> None:
        """The open questions file must exist."""
        assert _OPEN_QUESTIONS_PATH.exists(), f"{_OPEN_QUESTIONS_PATH} does not exist"

    def test_open_questions_has_entries(self) -> None:
        """The open questions file must have at least 5 entries."""
        content = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
        # Count entries by looking for "## Q" headers
        q_count = content.count("## Q")
        assert q_count >= 5, f"Expected at least 5 open questions, found {q_count}"

    def test_open_questions_have_experiment(self) -> None:
        """Each open question must have an experiment section."""
        content = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
        assert "Experiment:" in content
        assert "Who can perform:" in content

    def test_component_angle_question_present(self) -> None:
        """The Component/@Angle question must be present."""
        content = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
        assert "Component" in content and "Angle" in content and "radians" in content
