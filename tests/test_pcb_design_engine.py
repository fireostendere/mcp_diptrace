from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import PlacementError
from diptrace_mcp.operations import MoveComponentsOperation
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
    build_pcb_design_intent,
    intent_confidence,
)
from diptrace_mcp.pcb_placement import (
    PCBPlacementV2Config,
    analyze_pcb_placement_v2,
    plan_pcb_placement_v2,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot(name: str = "pcb.xml"):
    return build_snapshot(DipTraceDocument.load(FIXTURES / name, 10_000_000))


def _board_with_names(*, first_net: str, second_net: str) -> bytes:
    root = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    nets = root.findall("./Board/Nets/Net")
    assert len(nets) == 2
    first = nets[0].find("./Name")
    second = nets[1].find("./Name")
    assert first is not None and second is not None
    first.text = first_net
    second.text = second_net
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _spread_board() -> bytes:
    root = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    resistor = root.find("./Board/Components/Component[@Id='0']")
    controller = root.find("./Board/Components/Component[@Id='1']")
    assert resistor is not None and controller is not None
    resistor.set("X", "2")
    resistor.set("Y", "4")
    controller.set("X", "38")
    controller.set("Y", "18")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def test_generation_a_builds_engineering_intent_and_support_blocks() -> None:
    intent = build_pcb_design_intent(_snapshot())
    components = {item.refdes: item for item in intent.components}
    nets = {item.name: item for item in intent.nets}

    assert components["U1"].role == "controller"
    assert components["R1"].role == "support"
    assert components["R1"].anchor_component_id == components["U1"].component_id
    assert components["R1"].block_id == components["U1"].block_id
    assert nets["VCC"].roles == ["power"]
    assert nets["SIGNAL"].roles == ["digital"]
    assert nets["VCC"].component_ids == sorted(
        [components["R1"].component_id, components["U1"].component_id]
    )
    assert {item.strategy for item in intent.power_ground} == {"local_plane_or_pour_candidate"}
    assert 0.0 < intent_confidence(intent) <= 1.0
    assert any("never infers a split/star ground" in item for item in intent.assumptions)


def test_generation_a_keeps_unknown_physics_explicit_and_accepts_operator_facts() -> None:
    snapshot = _snapshot()
    intent = build_pcb_design_intent(
        snapshot,
        PCBIntentOverrides(
            components=[
                PCBComponentOverride(
                    selector="U1",
                    role="power_converter",
                    noise_emission=97,
                    placement_priority=100,
                )
            ],
            nets=[
                PCBNetOverride(
                    selector="VCC",
                    roles=["power"],
                    constraints=PCBElectricalConstraints(
                        current_a=1.5,
                        edge_rate_ns=2.0,
                        max_vias=1,
                    ),
                    return_strategy="explicit_star",
                )
            ],
        ),
    )
    u1 = next(item for item in intent.components if item.refdes == "U1")
    vcc = next(item for item in intent.nets if item.name == "VCC")
    topology = next(item for item in intent.power_ground if item.net_id == vcc.net_id)

    assert u1.role == "power_converter"
    assert u1.noise_emission == 97
    assert u1.thermal_role == "potential_heat_source"
    assert set(vcc.roles) == {"power", "high_current_power"}
    assert vcc.constraints.current_a == 1.5
    assert vcc.criticality >= 90
    assert topology.strategy == "explicit_star"
    assert topology.explicit is True
    signal = next(item for item in intent.nets if item.name == "SIGNAL")
    assert signal.constraints.edge_rate_ns is None
    assert signal.constraints.current_a is None
    assert signal.constraints.target_impedance_ohm is None


def test_generation_a_ground_policy_prefers_continuous_plane_without_auto_split(
    tmp_path: Path,
) -> None:
    board = tmp_path / "ground.xml"
    board.write_bytes(_board_with_names(first_net="AGND", second_net="ADC_REF"))
    intent = build_pcb_design_intent(build_snapshot(DipTraceDocument.load(board, 10_000_000)))
    nets = {item.name: item for item in intent.nets}
    strategies = {item.name: item.strategy for item in intent.power_ground}

    assert nets["AGND"].roles == ["ground"]
    assert strategies["AGND"] == "continuous_plane_preferred"
    assert {"analog", "precision_analog", "reference"}.issubset(nets["ADC_REF"].roles)
    assert nets["ADC_REF"].noise_sensitivity == 100


def test_generation_a_uses_exported_differential_pair_as_high_confidence_evidence() -> None:
    intent = build_pcb_design_intent(_snapshot("diff_pair_pcb.xml"))
    nets = {item.name: item for item in intent.nets}

    for name in ("USB_D+", "USB_D-"):
        net = nets[name]
        assert "differential" in net.roles
        assert net.confidence == 0.98
        assert net.criticality >= 90
        assert net.reference_plane_required is True
        assert net.constraints.max_length_mm == 10.0
        assert net.constraints.max_skew_mm == 0.25
    ground = next(item for item in intent.power_ground if item.name == "GND")
    assert ground.strategy == "continuous_plane_preferred"


@pytest.mark.parametrize(
    ("first_net", "expected_role", "strategy"),
    [
        ("SW", "switching_node", "local_copper_minimized"),
        ("ISNS", "current_sense", "kelvin_candidate"),
        ("CHASSIS", "shield", "chassis_or_shield"),
    ],
)
def test_generation_a_special_return_domains_are_not_flattened(
    tmp_path: Path,
    first_net: str,
    expected_role: str,
    strategy: str,
) -> None:
    board = tmp_path / f"{expected_role}.xml"
    board.write_bytes(_board_with_names(first_net=first_net, second_net="GPIO1"))
    intent = build_pcb_design_intent(build_snapshot(DipTraceDocument.load(board, 10_000_000)))
    net = next(item for item in intent.nets if item.name == first_net)
    topology = next(item for item in intent.power_ground if item.net_id == net.net_id)

    assert expected_role in net.roles
    assert topology.strategy == strategy


def test_generation_a_reports_unresolved_overrides_without_guessing() -> None:
    intent = build_pcb_design_intent(
        _snapshot(),
        PCBIntentOverrides(
            components=[PCBComponentOverride(selector="DOES_NOT_EXIST")],
            nets=[PCBNetOverride(selector="NO_SUCH_NET")],
        ),
    )

    assert len(intent.warnings) == 2
    assert all("did not resolve uniquely" in item for item in intent.warnings)


def test_placement_v2_moves_support_toward_fixed_functional_anchor(tmp_path: Path) -> None:
    board = tmp_path / "spread.xml"
    board.write_bytes(_spread_board())
    snapshot = build_snapshot(DipTraceDocument.load(board, 10_000_000))
    overrides = PCBIntentOverrides(
        components=[PCBComponentOverride(selector="U1", mechanical_anchor=True)]
    )

    plan = plan_pcb_placement_v2(
        snapshot,
        overrides=overrides,
        config=PCBPlacementV2Config(
            grid_mm=0.5,
            search_radius_steps=8,
            max_candidates_per_component=160,
        ),
    )

    assert plan.changed_component_ids
    assert plan.after.score.total < plan.before.score.total
    assert plan.after.geometry_violations == []
    assert all(isinstance(item, MoveComponentsOperation) for item in plan.operations)
    u1_id = next(
        component.component_id
        for component in plan.after.intent.components
        if component.refdes == "U1"
    )
    assert all(item.selector.ids != [u1_id] for item in plan.operations)
    assert plan.after.score.support_adjacency < plan.before.score.support_adjacency


def test_placement_v2_analysis_exposes_decomposed_score() -> None:
    analysis = analyze_pcb_placement_v2(_snapshot())

    assert analysis.score.total == pytest.approx(
        analysis.score.geometry
        + analysis.score.block_cohesion
        + analysis.score.support_adjacency
        + analysis.score.critical_connection
        + analysis.score.noise_coupling
        + analysis.score.compactness
        + analysis.score.centering
        + analysis.score.symmetry
        + analysis.score.hot_loop
    )
    assert analysis.limitations
    assert "field or thermal solver" in analysis.assumptions[0]


def test_placement_v2_respects_bounded_component_budget() -> None:
    with pytest.raises(PlacementError, match="component count"):
        plan_pcb_placement_v2(
            _snapshot(),
            config=PCBPlacementV2Config(max_components=1),
        )
