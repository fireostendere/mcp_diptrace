from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path) -> tuple[DipTraceService, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("pcb.xml", "pcb_4layer.xml", "schematic.xml", "diff_pair_pcb.xml"):
        shutil.copyfile(FIXTURES / name, workspace / name)
    return (
        DipTraceService(
            Settings(
                workspace=workspace,
                allowed_roots=(workspace,),
                state_dir=tmp_path / "state",
                max_document_bytes=10_000_000,
            )
        ),
        workspace,
    )


def test_review_board_only_methods_fail_closed_on_schematic(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    schematic = str(workspace / "schematic.xml")

    for call in (
        lambda: service.get_stackup(schematic),
        lambda: service.measure_net_lengths(schematic),
        lambda: service.list_differential_pairs(schematic),
        lambda: service.analyze_differential_pairs(schematic),
        lambda: service.analyze_stackup_for_impedance(schematic),
        lambda: service.list_copper_pours(schematic),
        lambda: service.validate_impedance_constraints(
            [
                {
                    "net": "VCC",
                    "layer": "Top",
                    "target_ohm": 50.0,
                    "tolerance_ohm": 5.0,
                }
            ],
            path=schematic,
        ),
    ):
        with pytest.raises(DocumentError):
            call()


def test_review_length_and_pagination_validation_paths(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb.xml")

    measured = service.measure_net_lengths(
        board,
        nets=["VCC"],
        effective_dielectric_constant=4.0,
    )
    assert measured["result"]["matched_count"] == 1
    assert measured["result"]["measurements"][0]["geometric_length_mm"] >= 0

    group = service.analyze_length_group(
        ["VCC", "SIGNAL"],
        tolerance_mm=100.0,
        path=board,
    )
    assert group["result"]["within_tolerance"] is True
    assert group["result"]["maximum_length_mm"] >= group["result"]["minimum_length_mm"]

    with pytest.raises(DocumentError, match="at least two nets"):
        service.analyze_length_group(["VCC"], path=board)
    with pytest.raises(DocumentError, match="cannot be negative"):
        service.analyze_length_group(["VCC", "SIGNAL"], tolerance_mm=-0.1, path=board)
    with pytest.raises(DocumentError, match="offset"):
        service.list_differential_pairs(board, offset=-1)
    with pytest.raises(DocumentError, match="limit"):
        service.list_copper_pours(board, limit=0)


def test_review_impedance_success_and_validation_edges(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb_4layer.xml")

    stackup = service.get_stackup(board)
    assert stackup["ok"] is True
    assert stackup["result"]

    impedance = service.calculate_impedance(
        structure="microstrip",
        width_mm=0.25,
        copper_thickness_mm=0.035,
        dielectric_height_mm=0.18,
        dielectric_constant=4.2,
        target_ohm=50.0,
        tolerance_ohm=10.0,
    )
    assert impedance["ok"] is True
    assert impedance["result"]["estimated_impedance_ohm"] > 0

    synthesized = service.suggest_trace_geometry_for_impedance(
        target_ohm=50.0,
        copper_thickness_mm=0.035,
        dielectric_height_mm=0.18,
        dielectric_constant=4.2,
        minimum_width_mm=0.05,
        maximum_width_mm=1.0,
        tolerance_ohm=0.1,
    )
    assert synthesized["ok"] is True
    assert synthesized["result"]["result"]["estimated_impedance_ohm"] == pytest.approx(
        50.0, abs=0.1
    )

    analyzed = service.analyze_stackup_for_impedance(board)
    assert analyzed["ok"] is True
    assert "microstrip_candidates" in analyzed["result"]

    with pytest.raises(DocumentError, match="At least one"):
        service.validate_impedance_constraints([], path=board)
    with pytest.raises(DocumentError, match="At most 1000"):
        service.validate_impedance_constraints([{}] * 1001, path=board)
    with pytest.raises(DocumentError, match="requires net and layer"):
        service.validate_impedance_constraints([{"net": "VCC"}], path=board)
    with pytest.raises(DocumentError, match="invalid target"):
        service.validate_impedance_constraints(
            [
                {
                    "net": "VCC",
                    "layer": "Top",
                    "target_ohm": 0.0,
                    "tolerance_ohm": 1.0,
                }
            ],
            path=board,
        )

    result = service.validate_impedance_constraints(
        [
            {
                "net": "VCC",
                "layer": "Top",
                "target_ohm": 50.0,
                "tolerance_ohm": 20.0,
                "width_mm": 0.25,
            }
        ],
        path=board,
    )
    assert result["result"]["constraint_count"] == 1
    assert result["result"]["evaluated_count"] + result["result"]["skipped_count"] == 1

    alias = service.analyze_controlled_impedance_nets(
        [
            {
                "net": "VCC",
                "layer": "Top",
                "target_ohm": 50.0,
                "tolerance_ohm": 20.0,
                "width_mm": 0.25,
            }
        ],
        path=board,
    )
    assert alias["result"]["constraint_count"] == 1


def test_review_diff_pair_and_return_path_read_paths(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    pair_board = str(workspace / "diff_pair_pcb.xml")
    board = str(workspace / "pcb.xml")

    pairs = service.list_differential_pairs(pair_board)
    assert pairs["result"]["matched_count"] >= 1
    pair_ref = pairs["result"]["items"][0]["stable_id"]

    pair = service.get_differential_pair(pair_ref, pair_board)
    assert pair["ok"] is True
    analysis = service.analyze_differential_pair(pair_ref, pair_board)
    assert analysis["ok"] is True
    validated = service.validate_differential_pair(pair_ref, pair_board)
    assert validated["result"]["status"] in {"valid", "invalid", "incomplete"}
    all_pairs = service.analyze_differential_pairs(pair_board)
    assert all_pairs["result"]["matched_count"] >= 1

    pours = service.list_copper_pours(board)
    assert pours["ok"] is True
    continuity = service.analyze_plane_continuity(board)
    assert continuity["ok"] is True
    return_path = service.analyze_return_path(board, stitching_radius_mm=2.0)
    assert return_path["ok"] is True


def test_findings_resource_filters_by_document(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    first = service.run_review(str(workspace / "pcb.xml"), profile="board")
    second = service.run_review(str(workspace / "schematic.xml"), profile="schematic")

    first_id = first["result"]["summary"]["report_id"]
    second_id = second["result"]["summary"]["report_id"]
    document_id = first["document"]["document_id"]

    assert first_id in service.review_resource(first_id)
    assert second_id in service.review_resource(second_id)
    payload = service.findings_resource(document_id)
    assert first_id in payload
    assert second_id not in payload
