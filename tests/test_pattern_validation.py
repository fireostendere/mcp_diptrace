"""Pattern validation tests against synthetic PCB with embedded pattern library.

The fixture has 4 embedded patterns:
  - PatType0 / RES_0603 / RES_0603_Pattern (2 pads, SMD)
  - PatType1 / RES_0402 / RES_0402_Pattern (2 pads, SMD)
  - PatType2 / CONN_2PIN / CONN_2PIN_Pattern (2 pads, Through)
  - PatType3 / IC_SO8 / IC_SO8_Pattern (8 pads, SMD)

And 4 components:
  - R1 (PatType0, 2 pads: 1, 2)
  - R2 (PatType1, 2 pads: 1, 2)
  - J1 (PatType2, 2 pads: 1, 2)
  - U1 (PatType3, 8 pads: 1..8)

Tests exercise:
  - SetComponentPatternOperation with strict_embedded_pattern mode
  - Pattern lookup by style name, pattern name, unique name
  - Pad mapping validation (must match)
  - External pattern reference rejection (external_pattern_reference mode)
  - Non-existent pattern rejection
  - Multiple component updates in one operation
  - PatternStyle attribute update in XML
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.errors import CapabilityUnavailableError, ObjectNotFoundError
from diptrace_mcp.operations import SetComponentPatternOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load_patterns() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "pcb_patterns.xml", 10_000_000)


def _snapshot():
    return build_snapshot(_load_patterns())


class TestPatternLookup:
    """Pattern matching by style, name, and unique name."""

    def test_match_by_style_name(self) -> None:
        """PatType0 matches R1 (which uses PatType0)."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="PatType0",
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        comp = root.find("./Board/Components/Component[@Id='0']")
        assert comp is not None
        assert comp.get("PatternStyle") == "PatType0"

    def test_match_by_pattern_name(self) -> None:
        """RES_0603 matches PatType0 pattern (its Name)."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="RES_0603",
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        comp = root.find("./Board/Components/Component[@Id='0']")
        assert comp is not None
        assert comp.get("PatternStyle") == "PatType0"

    def test_match_by_unique_name(self) -> None:
        """RES_0603_Pattern matches PatType0 pattern (its Name_Unique)."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="RES_0603_Pattern",
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        comp = root.find("./Board/Components/Component[@Id='0']")
        assert comp is not None
        assert comp.get("PatternStyle") == "PatType0"


class TestPatternRejection:
    """Non-existent and external patterns are rejected."""

    def test_nonexistent_pattern_strict(self) -> None:
        """strict_embedded_pattern rejects unknown pattern."""
        doc = _load_patterns()
        with pytest.raises(ObjectNotFoundError, match="embedded pattern was not found"):
            apply_semantic_operations(
                doc,
                [
                    SetComponentPatternOperation(
                        selector=QuerySelector(refdes=["R1"]),
                        pattern_style="NONEXISTENT",
                        validation_mode="strict_embedded_pattern",
                    )
                ],
            )

    def test_external_pattern_reference_rejected(self) -> None:
        """external_pattern_reference mode always rejects (no external resolver)."""
        doc = _load_patterns()
        with pytest.raises(CapabilityUnavailableError, match="external pattern resolution"):
            apply_semantic_operations(
                doc,
                [
                    SetComponentPatternOperation(
                        selector=QuerySelector(refdes=["R1"]),
                        pattern_style="NONEXISTENT",
                        validation_mode="external_pattern_reference",
                    )
                ],
            )


class TestPadMappingValidation:
    """Pattern swap must preserve pad count and pad numbers."""

    def test_swap_2pad_resistor(self) -> None:
        """Swap R1 from PatType0 to PatType1 (both 2-pad, same numbers)."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="PatType1",
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        comp = root.find("./Board/Components/Component[@Id='0']")
        assert comp is not None
        assert comp.get("PatternStyle") == "PatType1"
        pads = comp.findall("./Pads/Pad")
        assert len(pads) == 2

    def test_same_pattern_noop(self) -> None:
        """Setting the same pattern is a no-op but still valid."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="PatType0",
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        comp = root.find("./Board/Components/Component[@Id='0']")
        assert comp is not None
        assert comp.get("PatternStyle") == "PatType0"


class TestMultipleUpdates:
    """Multiple components can be updated in one or separate operations."""

    def test_update_two_components(self) -> None:
        """Update R1 and R2 simultaneously."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="PatType1",
                ),
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R2"]),
                    pattern_style="PatType0",
                ),
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        r1 = root.find("./Board/Components/Component[@Id='0']")
        r2 = root.find("./Board/Components/Component[@Id='1']")
        assert r1 is not None
        assert r2 is not None
        assert r1.get("PatternStyle") == "PatType1"
        assert r2.get("PatternStyle") == "PatType0"

    def test_update_preserves_other_components(self) -> None:
        """Updating R1 does not touch R2, J1, or U1."""
        doc = _load_patterns()
        result = apply_semantic_operations(
            doc,
            [
                SetComponentPatternOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    pattern_style="PatType1",
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        r2 = root.find("./Board/Components/Component[@Id='1']")
        j1 = root.find("./Board/Components/Component[@Id='2']")
        u1 = root.find("./Board/Components/Component[@Id='3']")
        assert r2 is not None
        assert j1 is not None
        assert u1 is not None
        assert r2.get("PatternStyle") == "PatType1"
        assert j1.get("PatternStyle") == "PatType2"
        assert u1.get("PatternStyle") == "PatType3"
