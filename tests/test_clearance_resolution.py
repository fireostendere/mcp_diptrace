from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.clearance import resolve_clearance
from diptrace_mcp.errors import (
    CapabilityUnavailableError,
    InvalidArgumentError,
    NetClassResolutionError,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURE = Path(__file__).parent / "fixtures" / "pcb.xml"


def _document(mutator) -> DipTraceDocument:
    original = DipTraceDocument.load(FIXTURE, 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    mutator(root)
    return DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _net(snapshot, name: str):
    assert snapshot.board is not None
    return next(item for item in snapshot.board.nets if item.name == name)


def test_one_netclass_rule_is_required_and_explicit_cannot_lower_it() -> None:
    document = _document(
        lambda root: root.find("./Board/NetClasses/NetClass/LayProperties/LayProperty").set(
            "Clearance", "0.35"
        )
    )
    snapshot = build_snapshot(document)
    resolution = resolve_clearance(snapshot, ["0"], 0.1, nets=[_net(snapshot, "VCC")])

    assert resolution.required_clearance_mm == pytest.approx(0.35)
    assert resolution.effective_clearance_mm == pytest.approx(0.35)
    assert resolution.netclass_rules_applied is True
    assert resolution.netclass_rules_ignored is False
    assert resolution.clearance_rule_status["clearance_source"] == "netclass_promoted"


def test_two_nets_from_different_classes_use_the_maximum_rule() -> None:
    def mutate(root: ET.Element) -> None:
        classes = root.find("./Board/NetClasses")
        assert classes is not None
        net_class = ET.SubElement(classes, "NetClass", {"Id": "1"})
        ET.SubElement(net_class, "Name").text = "HighVoltage"
        properties = ET.SubElement(net_class, "LayProperties")
        layer_property = ET.SubElement(properties, "LayProperty", {"Clearance": "0.8"})
        layer_name = ET.SubElement(layer_property, "LayerName")
        assert layer_name is not None
        layer_name.text = "Top"
        net = root.find("./Board/Nets/Net[@Id='1']")
        assert net is not None
        net.set("NetClass", "1")

    snapshot = build_snapshot(_document(mutate))
    resolution = resolve_clearance(
        snapshot,
        ["0"],
        None,
        nets=[_net(snapshot, "VCC"), _net(snapshot, "SIGNAL")],
    )

    assert resolution.required_clearance_mm == pytest.approx(0.8)
    assert resolution.effective_clearance_mm == pytest.approx(0.8)
    assert {
        item["net_class_id"]
        for item in resolution.clearance_sources
        if item["kind"] == "netclass"
    } == {
        "0",
        "1",
    }


def test_explicit_larger_than_required_wins_and_resolution_is_deterministic() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURE, 10_000_000))
    net = _net(snapshot, "VCC")

    first = resolve_clearance(snapshot, ["0", "1"], 0.9, nets=[net])
    second = resolve_clearance(snapshot, ["0", "1"], 0.9, nets=[net])

    assert first.as_dict() == second.as_dict()
    assert first.required_clearance_mm == pytest.approx(0.2)
    assert first.effective_clearance_mm == pytest.approx(0.9)
    assert first.clearance_rule_status["clearance_source"] == "caller"


def test_unassigned_net_uses_board_default_and_missing_rule_fails_closed() -> None:
    def unassigned(root: ET.Element) -> None:
        net = root.find("./Board/Nets/Net[@Id='0']")
        assert net is not None
        net.attrib.pop("NetClass", None)

    snapshot = build_snapshot(_document(unassigned))
    assert resolve_clearance(
        snapshot, ["0"], None, nets=[_net(snapshot, "VCC")]
    ).effective_clearance_mm == pytest.approx(0.2)

    def no_rules(root: ET.Element) -> None:
        root.find("./Board/DRC/LayClearances/LayClearance").attrib.pop("TraceToTrace")
        root.find("./Board/NetClasses/NetClass/LayProperties/LayProperty").attrib.pop("Clearance")

    empty_snapshot = build_snapshot(_document(no_rules))
    with pytest.raises(CapabilityUnavailableError):
        resolve_clearance(empty_snapshot, ["0"], None, nets=[_net(empty_snapshot, "VCC")])


def test_unknown_netclass_reference_fails_closed_without_guessing() -> None:
    def unknown(root: ET.Element) -> None:
        net = root.find("./Board/Nets/Net[@Id='0']")
        assert net is not None
        net.set("NetClass", "does-not-exist")

    snapshot = build_snapshot(_document(unknown))
    with pytest.raises(NetClassResolutionError, match="unknown NetClass"):
        resolve_clearance(snapshot, ["0"], 0.2, nets=[_net(snapshot, "VCC")])


def test_document_units_are_normalized_to_millimetres() -> None:
    def inches(root: ET.Element) -> None:
        root.set("Units", "inch")
        rule = root.find("./Board/DRC/LayClearances/LayClearance")
        assert rule is not None
        rule.set("TraceToTrace", "0.01")

    snapshot = build_snapshot(_document(inches))
    resolution = resolve_clearance(snapshot, ["0"], None, nets=[])
    assert resolution.effective_clearance_mm == pytest.approx(0.254)


@pytest.mark.parametrize("requested", [-0.001, float("nan"), float("inf")])
def test_requested_clearance_rejects_negative_and_non_finite_values(
    requested: float,
) -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURE, 10_000_000))

    with pytest.raises(InvalidArgumentError):
        resolve_clearance(snapshot, ["0"], requested, nets=[])
