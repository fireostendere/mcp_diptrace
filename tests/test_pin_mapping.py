"""Synthetic regression data: not real-DipTrace acceptance evidence."""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.design_compare import compare_schematic_to_pcb
from diptrace_mcp.pin_mapping import schematic_pin_pad_numbers
from diptrace_mcp.scaffolding import build_pcb_document
from diptrace_mcp.synchronization import ComponentSyncMapping, build_sync_plan
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _pair() -> tuple[ET.Element, ET.Element]:
    schematic = ET.fromstring((FIXTURES / "schematic.xml").read_bytes())
    library = schematic.find("./Library")
    assert library is not None
    schematic.remove(library)
    schematic.insert(0, ET.fromstring((FIXTURES / "component_library.xml").read_bytes()))
    parts = schematic.find("./Schematic/Components")
    assert parts is not None
    for part in list(parts)[1:]:
        parts.remove(part)
    for net in schematic.findall("./Schematic/Nets/Net"):
        pins = net.find("./Pins")
        assert pins is not None
        for item in list(pins)[1:]:
            pins.remove(item)
    pcb = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    components = pcb.find("./Board/Components")
    assert components is not None
    for component in list(components)[1:]:
        components.remove(component)
    for net in pcb.findall("./Board/Nets/Net"):
        pads = net.find("./Pads")
        assert pads is not None
        for item in list(pads)[1:]:
            pads.remove(item)
    return schematic, pcb


def _document(root: ET.Element) -> DipTraceDocument:
    return DipTraceDocument.from_bytes(Path("synthetic.xml"), ET.tostring(root))


def _compare(roots: tuple[ET.Element, ET.Element]) -> dict:
    return compare_schematic_to_pcb(*(build_snapshot(_document(root)) for root in roots))


def test_exact_cached_mapping_compares_physical_numbers_not_indices() -> None:
    roots = _pair()
    result = _compare(roots)
    assert result["matches"] is True
    assert result["comparison_complete"] is True
    assert result["comparison_basis"] == "explicit_physical_pad_numbers"
    assert result["sources"]["schematic_sha256"] == _document(roots[0]).sha256


@pytest.mark.parametrize("net_name", ["", "SAME"])
def test_duplicate_or_empty_net_names_cannot_produce_false_match(net_name: str) -> None:
    roots = _pair()
    for root in roots:
        for name in root.findall(".//Nets/Net/Name"):
            name.text = net_name
    result = _compare(roots)
    assert result["matches"] is False
    assert result["comparison_complete"] is False
    assert any(item["code"] == "missing_or_duplicate_net_name" for item in result["ambiguities"])


def test_unresolved_endpoint_cannot_match_another_unresolved_endpoint() -> None:
    roots = _pair()
    for root, tag, key in ((roots[0], "Pins", "Part"), (roots[1], "Pads", "Comp")):
        for item in root.findall(f".//Nets/Net/{tag}/Item"):
            item.set(key, "999")
    result = _compare(roots)
    assert result["matches"] is False
    assert result["status"] == "inconclusive"


def test_missing_library_prevents_positive_electrical_match() -> None:
    roots = _pair()
    library = roots[0].find("./Library")
    assert library is not None
    roots[0].remove(library)
    assert _compare(roots)["matches"] is False


def test_remapped_symbol_pins_are_not_confused_with_their_indices() -> None:
    roots = _pair()
    pins = roots[0].findall("./Library/Components/Component/Part/Pins/Pin")
    for index, pin in enumerate(pins):
        pin.set("PadId", str(1 - index))
        number = pin.find("./PadNumber")
        assert number is not None
        number.text = str(2 - index)
    result = _compare(roots)
    assert result["comparison_complete"] is True
    assert result["matches"] is False
    assert len(result["nets"]["endpoint_mismatches"]) == 2
    for net in roots[1].findall("./Board/Nets/Net"):
        for item in net.findall("./Pads/Item"):
            item.set("Pad", str(1 - int(item.get("Pad", "0"))))
    assert _compare(roots)["matches"] is True


def test_multi_unit_pin_zero_is_resolved_in_its_own_section() -> None:
    roots = _pair()
    schematic = roots[0]
    component = schematic.find("./Library/Components/Component")
    parts = schematic.find("./Schematic/Components")
    assert component is not None and parts is not None
    second_section = copy.deepcopy(component[0])
    second_pins = second_section.find("./Pins")
    assert second_pins is not None
    second_pins.remove(second_pins[0])
    second_pins[0].set("Id", "0")
    component.append(second_section)
    second_part = copy.deepcopy(parts[0])
    second_part.set("Id", "1")
    second_part.set("ComponentPart", "1")
    pins = second_part.find("./Pins")
    assert pins is not None
    pins.remove(pins[0])
    parts.append(second_part)
    bindings = schematic_pin_pad_numbers(_document(schematic))
    assert bindings[("0", 0)] == "1"
    assert bindings[("1", 0)] == "2"


def test_sync_uses_verified_cache_without_manual_mapping() -> None:
    roots = _pair()
    document = _document(roots[0])
    pcb = DipTraceDocument.from_bytes(Path("board.xml"), build_pcb_document())
    plan = build_sync_plan(
        document, pcb,
        mappings=[ComponentSyncMapping(refdes="R1", pattern_style="PatType0")],
        pattern_documents=[DipTraceDocument.load(FIXTURES / "pattern_library.xml", 10_000_000)],
    )
    assert plan.operation.nets[0].endpoints[0].pad_number == "1"
    assert plan.operation.nets[1].endpoints[0].pad_number == "2"


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("ComponentStyle", "CompType999"),
        ("ComponentPart", "999"),
        ("ComponentPart", "-1"),
        pytest.param("ComponentPart", "²", id="non-decimal-digit"),
        pytest.param("ComponentPart", "٠", id="non-native-digit"),
        pytest.param("ComponentPart", "9" * 5000, id="oversized-section"),
        pytest.param("ComponentStyle", "CompType" + "9" * 5000, id="oversized-style"),
    ],
)
def test_invalid_cache_binding_is_not_guessed(attribute: str, value: str) -> None:
    roots = _pair()
    part = roots[0].find("./Schematic/Components/Part")
    assert part is not None
    part.set(attribute, value)
    assert schematic_pin_pad_numbers(_document(roots[0])) == {}



def test_stale_pin_net_cache_prevents_positive_match() -> None:
    roots = _pair()
    pin = roots[0].find("./Schematic/Components/Part/Pins/Pin")
    assert pin is not None
    pin.set("NetId", "999")
    result = _compare(roots)
    assert result["matches"] is False
    assert any(item["code"] == "inconsistent_endpoint_netid" for item in result["ambiguities"])


def test_declared_no_connect_pin_cannot_be_certified_as_connected() -> None:
    roots = _pair()
    pin = roots[0].find("./Schematic/Components/Part/Pins/Pin")
    assert pin is not None
    pin.set("NotConnected", "Y")
    result = _compare(roots)
    assert result["matches"] is False
    assert any(item["code"] == "explicit_nc_pin_connected" for item in result["ambiguities"])


def test_ambiguity_output_is_bounded_without_hiding_incompleteness() -> None:
    roots = _pair()
    pins = roots[0].find("./Schematic/Nets/Net/Pins")
    assert pins is not None
    for index in range(250):
        ET.SubElement(pins, "Item", {"Part": str(1000 + index), "Pin": "0"})
    result = _compare(roots)
    assert result["matches"] is False
    assert len(result["ambiguities"]) == 200
    assert result["ambiguity_count"] == 250
    assert result["ambiguities_truncated"] is True
