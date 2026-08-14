from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import diptrace_mcp.services.placement as placement_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import CapabilityUnavailableError, EditError
from diptrace_mcp.operations import AddWireOperation
from diptrace_mcp.pattern_recommendation import PatternRequirement
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.server_runtime import create_server
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
COPIED = ("pcb.xml", "schematic.xml", "pattern_library.xml", "component_library.xml")
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
    """Build a schematic that already contains explicit routed wires."""
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
    part_id = next(part.stable_id for part in snapshot.schematic.parts if part.xml_id == "1")
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
            end={"type": "Pin", "part_id": part_id, "pin": 0},
        )
    ]
    return apply_semantic_operations(document, operations).document.raw_bytes


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


def test_plan_and_apply_schematic_placement_repair_round_trip(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    original_sha = service.document_info(path)["result"]["sha256"]

    plan_response = service.plan_schematic_placement_repair(path)
    plan = plan_response["result"]["plan"]
    assert plan["plan_type"] == "schematic_placement_repair"
    assert plan["operations"]
    assert plan_response["ok"] is True

    dry_run = service.apply_schematic_placement_repair_plan(plan["plan_id"], dry_run=True)
    assert dry_run["ok"] is True

    committed = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert committed["ok"] is True
    assert committed["result"]["changed_ids"]

    updated_info = service.document_info(path)
    assert updated_info["result"]["sha256"] != original_sha


def test_plan_schematic_placement_repair_is_graceful_when_nothing_to_repair(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)

    plan_response = service.plan_schematic_placement_repair(str(workspace / "schematic.xml"))

    assert plan_response["ok"] is True
    assert plan_response["result"]["plan"]["operations"] == []


def test_plan_schematic_placement_repair_works_on_wired_schematic(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")

    plan_response = service.plan_schematic_placement_repair(path)

    assert plan_response["ok"] is True
    plan = plan_response["result"]["plan"]
    assert plan["operations"]
    kinds = {operation["kind"] for operation in plan["operations"]}
    assert "move_components" in kinds


def test_plan_schematic_placement_repair_honours_moves_as_fixed_constraints(
    tmp_path: Path,
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    path = str(workspace / "wired.xml")
    snapshot = build_snapshot(DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES))
    assert snapshot.schematic is not None
    part = snapshot.schematic.parts[0]
    target = {"part": part.refdes or part.stable_id, "x_mm": 111.0, "y_mm": 44.0}

    plan_response = service.plan_schematic_placement_repair(path, moves=[target])
    plan = plan_response["result"]["plan"]

    committed = service.apply_schematic_placement_repair_plan(
        plan["plan_id"], dry_run=False, expected_sha256=plan["source_sha256"]
    )
    assert committed["ok"] is True

    after = build_snapshot(DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES))
    assert after.schematic is not None
    moved = next(item for item in after.schematic.parts if item.stable_id == part.stable_id)
    assert moved.position == {"x": 111.0, "y": 44.0}


def test_plan_schematic_placement_repair_rejects_moves_for_unknown_part(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    path = str(workspace / "schematic.xml")

    with pytest.raises(EditError, match="unknown part"):
        service.plan_schematic_placement_repair(
            path, moves=[{"part": "X9", "x_mm": 1.0, "y_mm": 2.0}]
        )


def test_plan_schematic_placement_repair_fails_closed_on_transaction_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())
    monkeypatch.setattr(
        placement_module,
        "MAX_TRANSACTION_OPERATIONS",
        1,
    )

    with pytest.raises(EditError, match="operations transaction limit"):
        service.plan_schematic_placement_repair(str(workspace / "wired.xml"))


def test_plan_schematic_placement_repair_requires_schematic_document(tmp_path: Path) -> None:
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


def test_capabilities_report_truthful_availability(tmp_path: Path) -> None:
    _, workspace = _service(tmp_path)
    (workspace / "wired.xml").write_bytes(_wired_schematic_bytes())

    wired = DipTraceDocument.load(workspace / "wired.xml", MAX_BYTES)
    unwired = DipTraceDocument.load(workspace / "schematic.xml", MAX_BYTES)
    board = DipTraceDocument.load(workspace / "pcb.xml", MAX_BYTES)

    read_capabilities = get_capabilities(wired).read_capabilities
    assert read_capabilities["schematic_placement_candidate_ranking"] is False
    assert read_capabilities["release_readiness"] is False

    unwired_capabilities = get_capabilities(unwired).read_capabilities
    assert unwired_capabilities["schematic_placement_candidate_ranking"] is True

    board_capabilities = get_capabilities(board).read_capabilities
    assert board_capabilities["release_readiness"] is True
    assert board_capabilities["pcb_placement_candidate_ensemble"] is True
