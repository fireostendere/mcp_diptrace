from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import ImpedanceInput
from diptrace_mcp.geometry import Point, arc_through_points_length, trace_path_length
from diptrace_mcp.impedance import calculate_impedance, synthesize_microstrip_width
from diptrace_mcp.lengths import analyze_differential_pair, measure_net_length
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_arc_length_uses_diptrace_midpoint_semantics() -> None:
    start = Point(1.0, 0.0)
    middle = Point(0.0, 1.0)
    end = Point(-1.0, 0.0)

    assert arc_through_points_length(start, middle, end) == pytest.approx(math.pi)
    assert trace_path_length([start, middle, end], [False, True, False]) == pytest.approx(
        math.pi
    )


def test_stackup_and_differential_pair_are_normalized() -> None:
    document = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    assert snapshot.board is not None
    assert snapshot.board.stackup.completeness == "complete"
    assert snapshot.board.stackup.total_thickness_mm == pytest.approx(0.25)
    dielectric = snapshot.board.stackup.layers[1].material
    assert dielectric.dielectric_constant == 4.1
    assert len(snapshot.board.differential_pairs) == 1
    pair = snapshot.board.differential_pairs[0]
    assert pair.positive_net_name == "USB_D+"
    assert pair.negative_net_name == "USB_D-"
    assert pair.rules.layer_rules[0].gap_mm == pytest.approx(0.15)
    assert pair.pad_pairs[0].positive_pad_id is not None


def test_net_length_and_pair_geometry_metrics() -> None:
    document = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    positive = measure_net_length(snapshot, "USB_D+")
    pair = analyze_differential_pair(snapshot, "USB_D")

    assert positive.geometric_length_mm == pytest.approx(10.0)
    assert pair.positive.geometric_length_mm == pytest.approx(10.0)
    assert pair.negative.geometric_length_mm == pytest.approx(9.8)
    assert pair.absolute_skew_mm == pytest.approx(0.2)
    assert pair.coupled_length_mm == pytest.approx(9.8)
    assert pair.estimated_uncoupled_length_mm == pytest.approx(0.0)
    assert pair.gap_mm["weighted_average"] == pytest.approx(0.15)
    assert all(bool(check["passed"]) for check in pair.checks)


def test_same_layer_via_style_metadata_does_not_create_via_balance_failure() -> None:
    original = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    points = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace/Points")
    assert points is not None
    final = points.find("./Point[@Id='1']")
    assert final is not None
    final.set("Id", "2")
    final.set("X", "11")
    middle = ET.Element(
        "Point",
        {
            "Id": "1",
            "X": "6",
            "Y": "2",
            "Lay": "0",
            "Width": "0.2",
            "Arc": "N",
            "ViaStyle": "0",
        },
    )
    points.insert(1, middle)
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    snapshot = build_snapshot(document)
    pair = analyze_differential_pair(snapshot, "USB_D")

    assert snapshot.board is not None
    assert snapshot.board.vias == []
    assert pair.positive.via_count == 0
    assert pair.positive.layer_transition_count == 0
    assert pair.via_balance == 0
    assert next(
        check for check in pair.checks if check["check_id"] == "diff_pair.via_balance"
    )["passed"] is True


def test_static_via_is_physical_but_not_a_routed_layer_transition() -> None:
    original = DipTraceDocument.load(FIXTURES / "diff_pair_pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    components = root.find("./Board/Components")
    assert components is not None
    static_via = ET.SubElement(
        components,
        "Component",
        {"Id": "99", "Type": "Via", "ViaStyle": "0", "X": "5", "Y": "2"},
    )
    ET.SubElement(static_via, "RefDes").text = "StaticVia1"
    ET.SubElement(static_via, "Name").text = "Static Via"
    pads = ET.SubElement(static_via, "Pads")
    ET.SubElement(pads, "Pad", {"Id": "1", "NetId": "0"})
    document = DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )

    snapshot = build_snapshot(document)
    positive = measure_net_length(snapshot, "USB_D+")

    assert snapshot.board is not None
    assert len(snapshot.board.vias) == 1
    assert snapshot.board.vias[0].attributes["representation"] == "static_component"
    assert all(item.attributes.get("type") != "Via" for item in snapshot.board.components)
    assert positive.via_count == 1
    assert positive.layer_transition_count == 0


def test_hammerstad_jensen_microstrip_golden_and_synthesis() -> None:
    # Golden value follows the published Qucs Hammerstad-Jensen equations 11.4-11.25.
    result = calculate_impedance(
        ImpedanceInput(
            structure="microstrip",
            width_mm=1.0,
            copper_thickness_mm=0.0,
            dielectric_height_mm=1.0,
            dielectric_constant=4.0,
            target_ohm=74.0,
            tolerance_ohm=0.1,
        )
    )

    assert result.estimated_impedance_ohm == pytest.approx(74.05193045, abs=1e-8)
    assert result.effective_dielectric_constant == pytest.approx(2.91464294, abs=1e-8)
    assert result.within_tolerance is True
    assert result.preliminary_only is True
    assert result.sensitivity_ohm_per_percent["width_mm"] < 0
    synthesis = synthesize_microstrip_width(
        target_ohm=50.0,
        copper_thickness_mm=0.035,
        dielectric_height_mm=0.18,
        dielectric_constant=4.1,
        minimum_width_mm=0.1,
        maximum_width_mm=1.0,
    )
    assert synthesis["result"]["estimated_impedance_ohm"] == pytest.approx(50.0, abs=0.01)


def test_coupled_microstrip_physical_invariants() -> None:
    """Physical invariants for the coupled microstrip model.

    These invariants are derived from electromagnetic theory, not from
    snapshot values of the code being tested.
    """
    # Test geometry
    v = ImpedanceInput(
        structure="differential_microstrip",
        width_mm=0.2,
        gap_mm=0.15,
        copper_thickness_mm=0.0,
        dielectric_height_mm=0.18,
        dielectric_constant=4.1,
    )
    result = calculate_impedance(v)
    tolerance_result = calculate_impedance(
        v.model_copy(
            update={
                "target_ohm": result.estimated_impedance_ohm,
                "tolerance_ohm": 0.0,
            }
        )
    )

    assert tolerance_result.within_tolerance is True
    assert result.validity["inside_published_range"] is True
    assert result.sensitivity_ohm_per_percent["gap_mm"] > 0.0

    # INVARIANT 1: eps_eff ordering — odd < single < even
    # The odd mode has MORE field in air, so its eps_eff must be the LOWEST.
    # The even mode has MORE field in the dielectric, so its eps_eff must be the HIGHEST.
    from diptrace_mcp.impedance import _effective_dielectric_constant
    single_er = _effective_dielectric_constant(
        v.width_mm / v.dielectric_height_mm, v.dielectric_constant
    )
    odd_er = result.validity["odd_mode_effective_dielectric_constant"]
    even_er = result.validity["even_mode_effective_dielectric_constant"]
    assert odd_er < single_er < even_er, (
        f"eps_eff ordering violated: odd={odd_er:.3f} < single={single_er:.3f} < even={even_er:.3f}"
    )

    # INVARIANT 2: All three eps_eff must be between 1 and er
    er = v.dielectric_constant
    assert 1.0 < odd_er < er, f"odd eps_eff {odd_er} not in (1, {er})"
    assert 1.0 < single_er < er, f"single eps_eff {single_er} not in (1, {er})"
    assert 1.0 < even_er < er, f"even eps_eff {even_er} not in (1, {er})"

    # INVARIANT 3: Differential impedance should approach 2*Z0 as gap grows
    # For a large gap, the two lines are uncoupled and Zdiff ≈ 2*Z0
    v_far = ImpedanceInput(
        structure="differential_microstrip",
        width_mm=0.2,
        gap_mm=2.0,  # gap/height = 11.1, very loosely coupled
        copper_thickness_mm=0.0,
        dielectric_height_mm=0.18,
        dielectric_constant=4.1,
    )
    result_far = calculate_impedance(v_far)
    single_v_far = ImpedanceInput(
        structure="microstrip",
        width_mm=0.2,
        gap_mm=None,
        copper_thickness_mm=0.0,
        dielectric_height_mm=0.18,
        dielectric_constant=4.1,
    )
    single_result_far = calculate_impedance(single_v_far)
    ratio = result_far.estimated_impedance_ohm / single_result_far.estimated_impedance_ohm
    assert 1.9 < ratio < 2.1, (
        f"Zdiff/Z0 ratio {ratio:.3f} not close to 2.0 for loosely coupled lines"
    )


def test_coupled_model_marks_finite_thickness_as_unmodeled() -> None:
    result = calculate_impedance(
        ImpedanceInput(
            structure="differential_microstrip",
            width_mm=0.2,
            gap_mm=0.15,
            copper_thickness_mm=0.035,
            dielectric_height_mm=0.18,
            dielectric_constant=4.1,
        )
    )

    assert result.confidence == "low"
    assert any("Finite copper thickness" in warning for warning in result.warnings)


def test_symmetric_stripline_matches_ipc2141_closed_form() -> None:
    result = calculate_impedance(
        ImpedanceInput(
            structure="symmetric_stripline",
            width_mm=0.2,
            copper_thickness_mm=0.035,
            dielectric_height_mm=1.2,
            dielectric_constant=4.2,
            target_ohm=72.0,
            tolerance_ohm=0.5,
        )
    )

    expected = 60.0 / math.sqrt(4.2) * math.log(1.9 * 1.2 / (0.8 * 0.2 + 0.035))
    assert result.estimated_impedance_ohm == pytest.approx(expected, rel=1e-9)
    assert result.effective_dielectric_constant == pytest.approx(4.2)
    assert result.validity["inside_published_range"] is True
    assert result.within_tolerance is True
    assert result.preliminary_only is True


def test_symmetric_stripline_warns_outside_published_range() -> None:
    result = calculate_impedance(
        ImpedanceInput(
            structure="symmetric_stripline",
            width_mm=0.6,
            copper_thickness_mm=0.035,
            dielectric_height_mm=1.2,
            dielectric_constant=4.2,
        )
    )

    # W/(B-T) = 0.6/1.165 > 0.35 -> outside the IPC-2141 range.
    assert result.validity["inside_published_range"] is False
    assert result.confidence == "low"
    assert any("IPC-2141" in warning for warning in result.warnings)


def test_phase10_service_contract(tmp_path: Path) -> None:
    service = DipTraceService(
        Settings(workspace=FIXTURES, allowed_roots=(FIXTURES,), state_dir=tmp_path)
    )

    stackup = service.get_stackup("diff_pair_pcb.xml")
    lengths = service.measure_net_lengths("diff_pair_pcb.xml", nets=["USB_D+", "USB_D-"])
    pair = service.validate_differential_pair("USB_D", "diff_pair_pcb.xml")
    impedance_stackup = service.analyze_stackup_for_impedance("diff_pair_pcb.xml")
    impedance = service.validate_impedance_constraints(
        [
            {
                "net": "USB_D+",
                "layer": "0",
                "target_ohm": 75.0,
                "tolerance_ohm": 1.0,
            }
        ],
        path="diff_pair_pcb.xml",
    )

    assert stackup["ok"] is True
    assert stackup["result"]["completeness"] == "complete"
    assert lengths["result"]["matched_count"] == 2
    assert pair["result"]["valid"] is True
    assert impedance_stackup["result"]["microstrip_candidates"][0]["signal_layer"] == "Top"
    assert impedance["result"]["evaluated_count"] == 1
    assert impedance["result"]["items"][0]["status"] == "evaluated"
