from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import diptrace_mcp.services.placement as placement_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import (
    CapabilityUnavailableError,
    EditError,
    Sha256MismatchError,
)
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.pattern_recommendation import PatternRequirement
from diptrace_mcp.reference_rules import EngineeringRulePack
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.server_runtime import create_server
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
COPIED = (
    "pcb.xml",
    "schematic.xml",
    "pattern_library.xml",
    "component_library.xml",
)
MAX_BYTES = 10_000_000


def _service(tmp_path: Path) -> tuple[DipTraceService, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in COPIED:
        shutil.copyfile(FIXTURES / name, workspace / name)
    return (
        DipTraceService(
            Settings(
                workspace=workspace,
                allowed_roots=(workspace,),
                state_dir=tmp_path / "state",
                max_document_bytes=MAX_BYTES,
            )
        ),
        workspace,
    )


def _wired_schematic_bytes() -> bytes:
    """A schematic with two sheet-local wired nets: VCC (R1.pin0 - part1.pin0)
    and SIGNAL (R1.pin1 - part2.pin0). Part2 touches only SIGNAL."""
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)
    library = DipTraceDocument.load(FIXTURES / "component_library.xml", MAX_BYTES)
    root = ET.fromstring(schematic.raw_bytes)
    existing = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert existing is not None
    index = list(root).index(existing)
    root.remove(existing)
    root.insert(index, ET.fromstring(library.raw_bytes))
    document = DipTraceDocument.from_bytes(
        schematic.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    pid1 = next(part.stable_id for part in snapshot.schematic.parts if part.xml_id == "1")
    pid2 = next(part.stable_id for part in snapshot.schematic.parts if part.xml_id == "2")
    operations = [
        AddWireOperation(
            net="VCC",
            sheet=0,
            points=[
                {"x": 10.0, "y": 20.0},
                {"x": 20.0, "y": 20.0},
                {"x": 30.0, "y": 20.0},
            ],
            start={"type": "Pin", "refdes": "R1", "pin": 0},
            end={"type": "Pin", "part_id": pid1, "pin": 0},
        ),
        AddWireOperation(
            net="SIGNAL",
            sheet=0,
            points=[
                {"x": 10.0, "y": 30.0},
                {"x": 25.0, "y": 30.0},
                {"x": 40.0, "y": 30.0},
            ],
            start={"type": "Pin", "refdes": "R1", "pin": 1},
            end={"type": "Pin", "part_id": pid2, "pin": 0},
        ),
    ]
    return apply_semantic_operations(document, operations).document.raw_bytes


def _signal_only_part(document: DipTraceDocument) -> str:
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    return next(part.stable_id for part in snapshot.schematic.parts if part.xml_id == "2")


def _wire_ids_by_net(document: DipTraceDocument) -> dict[str, list[str]]:
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    result: dict[str, list[str]] = {}
    for wire in snapshot.schematic.wires:
        result.setdefault(wire.net_name or wire.net_id or "", []).append(wire.stable_id)
    return result


def test_rank_schematic_placement_candidates_selects_ranked_candidate(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.rank_schematic_placement_candidates(str(workspace / "schematic.xml"))

    assert result["ok"] is True
    payload = result["result"]
    assert payload["selected"]["candidate"]["candidate_id"]
    assert payload["candidates"]
    ranked = [
        (tuple(item["rank_key"]), item["candidate"]["candidate_id"])
        for item in payload["candidates"]
    ]
    assert ranked == sorted(ranked)
    assert (
        payload["candidates"][0]["candidate"]["candidate_id"]
        == payload["selected"]["candidate"]["candidate_id"]
    )
    assert any(
        "builtin" in limitation for limitation in result["limitations"]
    )


def test_clean_wired_schematic_repair_is_noop_without_spurious_motion(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    original_sha = service.document_info(path)["result"]["sha256"]

    plan_response = service.plan_schematic_placement_repair(path)

    assert plan_response["ok"] is True
    assert plan_response["result"]["no_changes"] is True
    plan = plan_response["result"]["plan"]
    assert plan["operations"] == []
    assert plan["status"] == "noop"
    assert plan["metrics"]["repair"]["improved"] is False

    committed = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert committed["ok"] is True
    assert committed["changed"] is False
    assert committed["changed_ids"] == []
    assert service.document_info(path)["result"]["sha256"] == original_sha

    repeated = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert repeated["ok"] is True
    assert repeated["changed"] is False
    assert service.document_info(path)["result"]["sha256"] == original_sha


def test_wired_repair_detects_real_route_problem_and_keeps_fixed_move(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    moved_id = _signal_only_part(document)

    plan_response = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": moved_id, "x_mm": 220.0, "y_mm": 160.0}],
    )
    plan = plan_response["result"]["plan"]
    assert plan_response["result"]["no_changes"] is False
    assert plan["metrics"]["repair"]["feedback_edge_count"] >= 1
    assert plan["metrics"]["repair"]["improved"] is True

    committed = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert committed["ok"] is True

    after = build_snapshot(DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES))
    assert after.schematic is not None
    moved = next(part for part in after.schematic.parts if part.stable_id == moved_id)
    assert moved.position == {"x": 220.0, "y": 160.0}


def test_wired_repair_keeps_unaffected_nets_outside_replaced_geometry(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    moved_id = _signal_only_part(document)
    wires_before = _wire_ids_by_net(document)
    vcc_wires = wires_before["VCC"]

    plan_response = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": moved_id, "x_mm": 220.0, "y_mm": 160.0}],
    )
    plan = plan_response["result"]["plan"]
    moved_part_ids = {
        part_id
        for op in plan["operations"]
        if op["kind"] == "move_components"
        for part_id in op["selector"]["ids"]
    }
    assert moved_id in moved_part_ids
    deleted_wire_ids = [
        wire_id
        for op in plan["operations"]
        if op["kind"] == "delete_wire"
        for wire_id in op["selector"]["ids"]
    ]
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    nets_of_moved = {
        pin.net_id
        for pin in snapshot.schematic.pins
        if pin.parent_id in moved_part_ids and pin.net_id is not None
    }
    # Every deleted wire must belong to a net touched by a moved part; wires of
    # untouched nets survive.
    wire_net = {wire.stable_id: wire for wire in snapshot.schematic.wires}
    for wire_id in deleted_wire_ids:
        assert wire_net[wire_id].net_id in nets_of_moved
    vcc_net_ids = {
        wire.net_id for wire in snapshot.schematic.wires if wire.net_name == "VCC"
    }
    if not (nets_of_moved & vcc_net_ids):
        assert not set(vcc_wires) & set(deleted_wire_ids)


def test_plan_and_apply_schematic_placement_repair_round_trip(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    original_sha = service.document_info(path)["result"]["sha256"]
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    moved_id = _signal_only_part(document)

    plan_response = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": moved_id, "x_mm": 95.0, "y_mm": 70.0}],
    )
    plan = plan_response["result"]["plan"]
    assert plan["plan_type"] == "schematic_placement_repair"
    assert plan["operations"]
    assert plan_response["result"]["no_changes"] is False

    dry_run = service.apply_schematic_placement_repair_plan(plan["plan_id"], dry_run=True)
    assert dry_run["ok"] is True

    committed = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert committed["ok"] is True
    assert committed["result"]["changed_ids"]

    assert service.document_info(path)["result"]["sha256"] != original_sha


def test_moves_resolution_unique_refdes_case_insensitive_and_stable_id(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")

    by_refdes = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": "r1", "x_mm": 12.0, "y_mm": 13.0}],
    )
    assert by_refdes["ok"] is True
    assert any(
        op["kind"] == "move_components" for op in by_refdes["result"]["plan"]["operations"]
    )

    by_stable_id = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": r1.stable_id, "x_mm": 14.0, "y_mm": 15.0}],
    )
    assert by_stable_id["ok"] is True
    assert any(
        op["kind"] == "move_components"
        for op in by_stable_id["result"]["plan"]["operations"]
    )


def test_moves_resolution_rejects_multipart_ambiguous_refdes(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())

    with pytest.raises(EditError, match="ambiguous"):
        service.plan_schematic_placement_repair(
            str(workspace / "wired.xml"),
            moves=[{"part": "U1", "x_mm": 10.0, "y_mm": 20.0}],
        )


def test_moves_resolution_rejects_duplicate_moves(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())

    with pytest.raises(EditError, match="duplicate"):
        service.plan_schematic_placement_repair(
            str(workspace / "wired.xml"),
            moves=[
                {"part": "R1", "x_mm": 10.0, "y_mm": 20.0},
                {"part": "R1", "x_mm": 10.0, "y_mm": 20.0},
            ],
        )
    with pytest.raises(EditError, match="duplicate"):
        service.plan_schematic_placement_repair(
            str(workspace / "wired.xml"),
            moves=[
                {"part": "R1", "x_mm": 10.0, "y_mm": 20.0},
                {"part": "r1", "x_mm": 30.0, "y_mm": 40.0},
            ],
        )


def test_plan_schematic_placement_repair_rejects_moves_for_unknown_part(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    path = str(workspace / "schematic.xml")

    with pytest.raises(EditError, match="unknown part"):
        service.plan_schematic_placement_repair(
            path, moves=[{"part": "X9", "x_mm": 1.0, "y_mm": 2.0}]
        )


def test_moves_on_locked_part_fail_closed(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    document = DipTraceDocument.from_bytes(
        workspace / "wired.xml", _wired_schematic_bytes()
    )
    root = ET.fromstring(document.raw_bytes)
    parts = root.findall("./Schematic/Components/Part")
    assert parts
    for part in parts:
        part.set("Locked", "Y")
    (workspace / "locked.xml").write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    snapshot = build_snapshot(DipTraceDocument.load(workspace / "locked.xml", MAX_BYTES))
    assert snapshot.schematic is not None
    moved_id = next(part.stable_id for part in snapshot.schematic.parts if part.xml_id == "2")

    with pytest.raises(CapabilityUnavailableError):
        service.plan_schematic_placement_repair(
            str(workspace / "locked.xml"),
            moves=[{"part": moved_id, "x_mm": 50.0, "y_mm": 60.0}],
        )


def test_plan_schematic_placement_repair_fails_closed_on_transaction_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    moved_id = _signal_only_part(document)
    monkeypatch.setattr(
        placement_module,
        "MAX_TRANSACTION_OPERATIONS",
        1,
    )

    with pytest.raises(EditError, match="operations transaction limit"):
        service.plan_schematic_placement_repair(
            str(workspace / "wired.xml"),
            moves=[{"part": moved_id, "x_mm": 220.0, "y_mm": 160.0}],
        )


def test_apply_schematic_placement_repair_rejects_expected_sha_mismatch(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    moved_id = _signal_only_part(document)

    plan = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": moved_id, "x_mm": 95.0, "y_mm": 70.0}],
    )["result"]["plan"]

    with pytest.raises(Sha256MismatchError):
        service.apply_schematic_placement_repair_plan(
            plan["plan_id"],
            dry_run=False,
            expected_sha256="0" * 64,
        )


def test_stale_plan_is_marked_obsolete_after_document_mutation(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    document = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    moved_id = _signal_only_part(document)

    plan = service.plan_schematic_placement_repair(
        path,
        moves=[{"part": moved_id, "x_mm": 95.0, "y_mm": 70.0}],
    )["result"]["plan"]

    mutated = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    snapshot = build_snapshot(mutated)
    assert snapshot.schematic is not None
    add_wire = AddWireOperation(
        net="SIGNAL",
        sheet=0,
        points=[
            {"x": 10.0, "y": 30.0},
            {"x": 25.0, "y": 38.0},
            {"x": 40.0, "y": 30.0},
        ],
        start={"type": "Pin", "refdes": "R1", "pin": 1},
        end={"type": "Pin", "part_id": moved_id, "pin": 0},
    )
    (workspace / "wired.xml").write_bytes(
        apply_semantic_operations(mutated, [add_wire]).document.raw_bytes
    )

    with pytest.raises(Sha256MismatchError):
        service.apply_schematic_placement_repair_plan(
            plan["plan_id"],
            dry_run=False,
            expected_sha256=plan["source_sha256"],
        )
    assert service.plans.read(plan["plan_id"]).status == "obsolete"


def test_plan_schematic_placement_repair_requires_schematic_document(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)

    with pytest.raises(CapabilityUnavailableError):
        service.plan_schematic_placement_repair(str(workspace / "pcb.xml"))


def test_compare_pcb_placement_candidates_ranks_profiles(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.compare_pcb_placement_candidates(str(workspace / "pcb.xml"))

    assert result["ok"] is True
    payload = result["result"]
    assert payload["selected_profile"]
    assert {item["profile"] for item in payload["candidates"]} >= {payload["selected_profile"]}
    assert payload["limitations"]


def test_candidate_tools_accept_sha_bound_engineering_rule_pack(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    rules = EngineeringRulePack.model_validate(
        {
            "sources": [
                {
                    "source_id": "project",
                    "kind": "project",
                    "title": "Project constraints",
                    "locator": "project://constraints/rev-a",
                    "sha256": "b" * 64,
                    "redistribution_allowed": True,
                }
            ],
            "pcb_nets": [
                {
                    "source_id": "project",
                    "override": {
                        "selector": "VCC",
                        "roles": ["power"],
                        "constraints": {"current_a": 0.75},
                    },
                }
            ],
        }
    )

    result = service.compare_pcb_placement_candidates(
        str(workspace / "pcb.xml"),
        engineering_rules=rules,
    )

    assert result["ok"] is True
    ingested = result["result"]["engineering_rules"]
    assert ingested["pack_sha256"]
    assert ingested["pcb_overrides"]["nets"][0]["constraints"]["current_a"] == 0.75
    assert ingested["provenance"][0]["source_sha256"] == "b" * 64


def test_recommend_patterns_applies_hard_filters(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.recommend_patterns(
        PatternRequirement(pad_count=2),
        str(workspace / "pattern_library.xml"),
        limit=5,
    )

    assert result["ok"] is True
    payload = result["result"]
    assert payload["total_patterns"] >= 1
    assert len(payload["candidates"]) <= 5
    for candidate in payload["candidates"]:
        assert candidate["features"]["pad_count"] == 2


def test_recommend_patterns_tool_schema_is_typed() -> None:
    server = create_server()
    tool = server._tool_manager._tools["recommend_patterns"]

    requirement_schema = tool.parameters["properties"]["requirement"]
    assert requirement_schema == {"$ref": "#/$defs/PatternRequirement"}
    defined = tool.parameters["$defs"]["PatternRequirement"]
    assert defined["type"] == "object"
    assert "pad_count" in defined["properties"]
    assert "width_mm" in defined["properties"]
    assert "required_pad_numbers" in defined["properties"]


def test_recommend_patterns_requires_library_document(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    with pytest.raises(CapabilityUnavailableError):
        service.recommend_patterns(
            PatternRequirement(pad_count=2), str(workspace / "pcb.xml")
        )


def test_analyze_release_readiness_reports_dfm_findings(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)

    result = service.analyze_release_readiness(str(workspace / "pcb.xml"))

    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"]
    assert isinstance(payload["findings"], list)
    assert payload["metrics"]


def test_capabilities_report_truthful_availability_per_document_kind(
    tmp_path: Path,
) -> None:
    _, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())

    wired = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    unwired = DipTraceDocument.load(workspace / "schematic.xml", MAX_BYTES)
    board = DipTraceDocument.load(workspace / "pcb.xml", MAX_BYTES)
    component_library = DipTraceDocument.load(
        workspace / "component_library.xml", MAX_BYTES
    )
    pattern_library = DipTraceDocument.load(
        workspace / "pattern_library.xml", MAX_BYTES
    )

    wired_read = get_capabilities(wired).read_capabilities
    assert wired_read["schematic_placement_candidate_ranking"] is False
    assert wired_read["release_readiness"] is False
    assert wired_read["pcb_placement_candidate_ensemble"] is False
    assert wired_read["pattern_recommendation"] is False

    unwired_read = get_capabilities(unwired).read_capabilities
    assert unwired_read["schematic_placement_candidate_ranking"] is True
    assert unwired_read["release_readiness"] is False
    assert unwired_read["pcb_placement_candidate_ensemble"] is False

    board_read = get_capabilities(board).read_capabilities
    assert board_read["release_readiness"] is True
    assert board_read["pcb_placement_candidate_ensemble"] is True
    assert board_read["schematic_placement_candidate_ranking"] is False

    for library_document in (component_library, pattern_library):
        library_read = get_capabilities(library_document).read_capabilities
        assert library_read["pattern_recommendation"] is True
        assert library_read["release_readiness"] is False
        assert library_read["pcb_placement_candidate_ensemble"] is False
        assert library_read["schematic_placement_candidate_ranking"] is False

    write_capabilities = get_capabilities(wired).write_capabilities
    assert write_capabilities["apply_schematic_placement_repair_plan"] is True
    assert (
        get_capabilities(board).write_capabilities["apply_schematic_placement_repair_plan"]
        is False
    )
