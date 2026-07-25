"""Tests for the DipTrace XML specification inventory and format coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path

_INVENTORY_PATH = Path("reference/diptrace-xml/spec_inventory.json")
_COVERAGE_PATH = Path("docs/FORMAT_COVERAGE.md")
_OPEN_QUESTIONS_PATH = Path("docs/OPEN_QUESTIONS.md")
_XML_COMPATIBILITY_PATH = Path("docs/XML_COMPATIBILITY.md")
_IMPLEMENTATION_REFERENCE_PATH = Path("reference/diptrace-xml/REFERENCE.md")
_EVIDENCE_CAPTURE_PATH = Path("docs/EVIDENCE_CAPTURE.md")


def _open_question_blocks() -> list[tuple[int, str, str]]:
    content = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
    headers = list(
        re.finditer(
            r"^## Q(?P<number>\d+): (?P<title>.+)$",
            content,
            flags=re.MULTILINE,
        )
    )
    blocks: list[tuple[int, str, str]] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        blocks.append(
            (
                int(header.group("number")),
                header.group("title").strip(),
                content[header.end() : end],
            )
        )
    return blocks


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

    def test_inventory_has_measured_floor(self) -> None:
        """The inventory must not silently lose most elements or attributes."""
        inventory = _load_inventory()
        assert len(inventory["elements"]) >= 250
        assert sum(
            len(element["attributes"])
            for element in inventory["elements"].values()
        ) >= 500

    def test_inventory_elements_have_required_fields(self) -> None:
        """Every element must have documents, pages, attributes, and children."""
        inventory = _load_inventory()
        for name, elem in inventory["elements"].items():
            assert "documents" in elem, f"Element {name} missing 'documents'"
            assert "pages" in elem, f"Element {name} missing 'pages'"
            assert "attributes" in elem, f"Element {name} missing 'attributes'"
            assert "text_content" in elem, f"Element {name} missing 'text_content'"
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

    def test_text_content_is_not_modelled_as_same_name_attribute(self) -> None:
        """Scalar element values must not inflate the attribute denominator."""
        inventory = _load_inventory()
        collisions = {
            name
            for name, element in inventory["elements"].items()
            if name in element["attributes"]
        }
        assert collisions == set()

    def test_documented_unit_sentinels(self) -> None:
        """Keep the three explicit unit facts and the one unknown distinct."""
        elements = _load_inventory()["elements"]
        expected_units = {
            ("Source", "Units"): "document_units",
            ("Library", "Units"): "document_units",
            ("Component", "Angle"): "unknown",
            ("Shape", "Angle"): "radians",
            ("Table", "Orientation"): "degrees",
        }
        for (element, attribute), units in expected_units.items():
            assert elements[element]["attributes"][attribute]["units"] == units
        assert elements["Source"]["attributes"]["Units"]["enum"] == [
            "mm",
            "inch",
            "mil",
        ]

    def test_only_source_documented_omission_clauses_are_recorded(self) -> None:
        """Do not invent absent/default rules missing from the public PDFs."""
        inventory = _load_inventory()
        omissions = {
            (element_name, attribute_name)
            for element_name, element in inventory["elements"].items()
            for attribute_name, attribute in element["attributes"].items()
            if attribute["omitted_when"] is not None
        }
        assert omissions == {
            ("Component", "Type"),
            ("Component", "Angle"),
            ("Component", "PlacementClearance"),
            ("Net", "MeanderGap"),
        }

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


class TestDocumentationEvidenceClasses:
    """Keep source authority separate from observations and open questions."""

    def test_compatibility_baseline_labels_each_evidence_class(self) -> None:
        content = _XML_COMPATIBILITY_PATH.read_text(encoding="utf-8")
        for heading in (
            "### Public specification evidence",
            "### Observed compatibility evidence",
            "### Open unknowns",
        ):
            assert heading in content
        assert "standalone Component Library or Pattern Library XML format reference" in content
        assert "official standalone `<Library>` root validation" not in content

    def test_implementation_reference_labels_unverified_semantics(self) -> None:
        content = _IMPLEMENTATION_REFERENCE_PATH.read_text(encoding="utf-8")
        for label in (
            "**Public specification:**",
            "**Observed compatibility:**",
            "**Open question / safety model:**",
        ):
            assert label in content
        assert "`ImpMode=All` replaces lists." not in content
        assert "public specification inventory records these MainStack shapes" not in content
        assert "**Writer policy:** preserve unknown XML and existing IDs." not in content
        assert "outside the operation-owned region" in content

    def test_capture_guidance_keeps_gui_controls_and_screenshots_bounded(self) -> None:
        content = _EVIDENCE_CAPTURE_PATH.read_text(encoding="utf-8")
        assert "## Designing a controlled recipe" in content
        assert "one intentional GUI change per probe" in content
        assert "unchanged controls" in content
        assert "Screenshots may support" in content
        assert "never the authoritative format artifact" in content


class TestOpenQuestions:
    """Tests for the open questions document."""

    def test_open_questions_exists(self) -> None:
        """The open questions file must exist."""
        assert _OPEN_QUESTIONS_PATH.exists(), f"{_OPEN_QUESTIONS_PATH} does not exist"

    def test_questions_are_sequential_and_have_nonempty_required_sections(self) -> None:
        """Every question must carry the evidence-oriented structure."""
        blocks = _open_question_blocks()
        assert len(blocks) >= 13
        assert [number for number, _, _ in blocks] == list(
            range(1, len(blocks) + 1)
        )
        for number, title, block in blocks:
            assert title.endswith("?"), f"Q{number} title is not a question"
            for label in (
                "Question",
                "Why the code depends on it",
                "Experiment",
                "Who can perform",
            ):
                match = re.search(
                    rf"\*\*{re.escape(label)}:\*\*\s*(.+?)"
                    r"(?=\n\n\*\*|\n\n---|\Z)",
                    block,
                    flags=re.DOTALL,
                )
                assert match is not None, f"Q{number} missing {label}"
                assert match.group(1).strip(), f"Q{number} has empty {label}"

    def test_each_dependency_section_has_a_stable_code_symbol(self) -> None:
        """Line numbers drift; every dependency must cite a stable symbol."""
        for number, _, block in _open_question_blocks():
            why = re.search(
                r"\*\*Why the code depends on it:\*\*\s*(.+?)"
                r"(?=\n\n\*\*|\n\n---|\Z)",
                block,
                flags=re.DOTALL,
            )
            assert why is not None
            assert re.search(
                r"`src/diptrace_mcp/[a-z0-9_]+\.py::"
                r"[A-Za-z_][A-Za-z0-9_.]*`",
                why.group(1),
            ), f"Q{number} lacks a stable code-symbol reference"

    def test_required_human_gated_unknowns_are_present(self) -> None:
        """Keep every high-consequence unknown named by the work order."""
        content = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
        question_six = next(
            title
            for number, title, _ in _open_question_blocks()
            if number == 6
        )
        assert 'Selected="Y"' in question_six
        required = (
            "ImpMode=All",
            "9.6e-09",
            "copper-pour fill data",
            "routing_compiler.py::_write_points",
            "standalone Component and Pattern Editor XML",
            "preserve the source encoding and BOM",
        )
        for phrase in required:
            assert phrase in content
        assert "does not state whether selection/highlighting persists" in content
        assert "16 trace-point" in content

    def test_library_question_keeps_identity_and_source_binding_open(self) -> None:
        """Q11 must cover each unresolved library-evidence boundary."""
        question_eleven = next(
            block
            for number, _, block in _open_question_blocks()
            if number == 11
        )
        for phrase in (
            "`UID32`",
            "partial/current-component",
            "full-save/re-export",
            "`input_artifacts`",
        ):
            assert phrase in question_eleven
        assert re.search(r"binary\s+SHA-256", question_eleven)

    def test_answered_and_duplicate_questions_are_absent(self) -> None:
        """Do not retain questions answered by the spec or duplicate numeric format."""
        content = _OPEN_QUESTIONS_PATH.read_text(encoding="utf-8")
        assert "Does DipTrace write `Component/@Angle` when the value is 0?" not in content
        assert "maximum number of significant digits" not in content
        assert "lists every fact" not in content
        assert "not exhaustive" in content
