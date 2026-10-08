from __future__ import annotations

from types import SimpleNamespace

import pytest

from diptrace_mcp import pcb_design_intent as intent
from diptrace_mcp.domain import ObjectRecord
from diptrace_mcp.errors import CapabilityUnavailableError


def _component(refdes: str, value: str = "") -> ObjectRecord:
    return ObjectRecord(
        stable_id=f"component_{len(refdes):016x}",
        kind="component",
        refdes=refdes,
        value=value,
    )


@pytest.mark.parametrize(
    ("refdes", "value", "role"),
    [
        ("SW1", "", "mechanical_anchor"),
        ("U1", "BUCK REGULATOR", "power_converter"),
        ("U2", "USB PHY", "interface"),
        ("U3", "IMU SENSOR", "sensor"),
        ("U4", "MCU", "controller"),
        ("Y1", "", "timing"),
        ("F1", "", "protection"),
        ("C1", "", "power_support"),
        ("R1", "", "support"),
        ("Q1", "", "interface"),
        ("Z1", "", "other"),
    ],
)
def test_component_role_matrix(refdes: str, value: str, role: str) -> None:
    assert intent._component_role(_component(refdes, value))[0] == role


def test_component_defaults_cover_each_specialized_role() -> None:
    for role in (
        "power_converter",
        "timing",
        "sensor",
        "controller",
        "interface",
        "connector",
        "protection",
        "support",
        "other",
    ):
        assert len(intent._component_defaults(role)) == 5


@pytest.mark.parametrize(
    ("name", "differential", "expected"),
    [
        (None, False, "unknown"),
        ("USB_DP", False, "differential"),
        ("PAIR", True, "differential"),
        ("ADC_REF", False, "reference"),
        ("CURRENT_SENSE", False, "current_sense"),
        ("REG_FB", False, "feedback"),
        ("ADC_AIN", False, "analog"),
        ("RF_ANT", False, "rf"),
        ("NRST", False, "reset"),
        ("GPIO_EN", False, "control"),
        ("DATA", False, "digital"),
        ("CLK_OUT", False, "clock"),
    ],
)
def test_net_role_matrix(name: str | None, differential: bool, expected: str) -> None:
    roles, confidence, reasons = intent._roles_for_net(name, differential=differential)
    assert expected in roles and confidence > 0 and reasons


def test_criticality_and_risk_thresholds() -> None:
    constraints = intent.PCBElectricalConstraints
    assert intent._criticality(["digital"], constraints(edge_rate_ns=0.5)) == 100
    assert intent._criticality(["digital"], constraints(edge_rate_ns=4)) == 90
    assert intent._criticality(["digital"], constraints(edge_rate_ns=15)) == 70
    assert intent._criticality(["digital"], constraints(signal_frequency_hz=200e6)) == 90
    assert intent._criticality(["digital"], constraints(signal_frequency_hz=20e6)) == 70
    assert intent._criticality(["digital"], constraints(current_a=2)) == 90
    assert intent._criticality(["digital"], constraints(current_a=0.5)) == 70
    assert intent._criticality(["digital"], constraints(max_skew_mm=0)) == 80
    assert intent._net_risk(["precision_analog"]) == (15, 100)
    assert intent._net_risk(["rf"]) == (90, 80)
    assert intent._net_risk(["differential"])[1] == 60


def test_require_board_and_component_resolution_guards() -> None:
    with pytest.raises(CapabilityUnavailableError, match="PCB document"):
        intent._require_board(SimpleNamespace(board=None))
    component = _component("U1")
    snapshot = SimpleNamespace(board=SimpleNamespace(components=[component, component]))
    assert intent._resolve_component(snapshot, "U1") is None
