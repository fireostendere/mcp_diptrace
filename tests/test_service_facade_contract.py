from __future__ import annotations

import inspect
import json
from pathlib import Path
from shutil import copyfile

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.error_boundary import (
    error_result_to_mcp_result,
    exception_to_error_result,
)
from diptrace_mcp.errors import ObjectNotFoundError
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT = Path(__file__).parents[1] / "reference" / "mcp-tools-list.snapshot.json"


def _service(tmp_path: Path) -> DipTraceService:
    project = tmp_path / "project"
    project.mkdir()
    copyfile(FIXTURES / "pcb.xml", project / "board.dip")
    copyfile(FIXTURES / "schematic.xml", project / "schematic.dip")
    settings = Settings(
        workspace=project,
        allowed_roots=(project,),
        state_dir=tmp_path / "state",
        max_document_bytes=10_000_000,
    )
    return DipTraceService(settings)


def _state_entries(service: DipTraceService) -> set[str]:
    if not service.settings.state_dir.exists():
        return set()
    return {
        str(path.relative_to(service.settings.state_dir))
        for path in service.settings.state_dir.rglob("*")
    }


def test_facade_exposes_extracted_methods_with_stable_signatures() -> None:
    expected = {
        "board_model": ["self", "path", "section", "offset", "limit"],
        "query_objects": ["self", "path", "selector", "offset", "limit", "sort_by"],
        "get_bom": ["self", "path", "grouped", "include_dnp"],
        "compare_bom_to_design": ["self", "external_records", "path"],
        "run_review": ["self", "path", "profile", "categories"],
        "validate_impedance_constraints": ["self", "constraints", "path"],
    }

    for name, parameter_names in expected.items():
        method = getattr(DipTraceService, name, None)
        assert method is not None
        assert list(inspect.signature(method).parameters) == parameter_names


def test_facade_assembles_each_service_once_and_shares_store_instances(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    domain_services = (
        service._document_service,
        service._bom_service,
        service._review_service,
        service._export_service,
        service._external_jobs_service,
        service._routing_service,
        service._placement_service,
        service._scaffolding_service,
        service._evidence_service,
        service._xml_write_service,
        service._live_session_service,
        service._synchronization_service,
        service._semantic_engine_service,
        service._semantic_operations_service,
        service._transaction_service,
    )
    assert len({id(item) for item in domain_services}) == len(domain_services)

    for domain_service in domain_services:
        assert domain_service.context.model_cache is service.models
        assert domain_service.context.session_store is service.sessions
        assert domain_service.context.transaction_store is service.transactions
    assert service._review_service.context.finding_store is service.findings

    gateway_services = (
        service._document_service,
        service._bom_service,
        service._review_service,
        service._export_service,
        service._external_jobs_service,
        service._routing_service,
        service._placement_service,
        service._evidence_service,
        service._xml_write_service,
        service._synchronization_service,
        service._semantic_engine_service,
        service._semantic_operations_service,
        service._transaction_service,
    )
    assert all(item.gateway is service._document_gateway for item in gateway_services)

    assert service._transaction_service.transaction_store is service.transactions
    assert service._transaction_service.session_store is service.sessions
    assert service._xml_write_service.session_store is service.sessions
    assert service._live_session_service.session_store is service.sessions
    assert service._external_jobs_service.plan_store is service.plans
    assert service._placement_service.plan_store is service.plans
    assert service._routing_service.plan_store is service.plans

    assert service._document_targets is service._document_gateway.targets


def test_facade_and_direct_domain_bom_payloads_are_identical(tmp_path: Path) -> None:
    service = _service(tmp_path)

    facade_result = service.get_bom("schematic.dip", grouped=True, include_dnp=False)
    direct_result = service._bom_service.get_bom(
        "schematic.dip", grouped=True, include_dnp=False
    )

    assert facade_result == direct_result


def test_facade_and_direct_document_and_analysis_payloads_are_identical(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    assert service.board_model("board.dip") == service._document_service.board_model(
        "board.dip"
    )
    assert service.get_stackup("board.dip") == service._review_service.get_stackup(
        "board.dip"
    )

    report = service.run_review("board.dip", profile="board_review")
    report_id = report["result"]["summary"]["report_id"]
    assert service.get_findings(report_id) == service._review_service.get_findings(report_id)
    assert service.review_resource(report_id) == service._review_service.review_resource(
        report_id
    )


def test_read_only_facade_calls_do_not_create_store_records(tmp_path: Path) -> None:
    service = _service(tmp_path)
    before = _state_entries(service)

    service.get_bom("board.dip")
    service.query_objects("board.dip", selector={})
    service.get_stackup("board.dip")

    assert _state_entries(service) == before


def test_exceptions_pass_through_facade_without_wrapping(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ObjectNotFoundError) as facade_error:
        service.get_bom("missing.dip")
    with pytest.raises(ObjectNotFoundError) as direct_error:
        service._bom_service.get_bom("missing.dip")

    assert type(facade_error.value) is type(direct_error.value)
    assert str(facade_error.value) == str(direct_error.value)


def test_server_tools_and_thread_offload_contract_match_snapshot(tmp_path: Path) -> None:
    service = _service(tmp_path)
    server = create_server(service.settings)
    actual_tools = server._tool_manager._tools
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert len(actual_tools) == 159
    assert sorted(actual_tools) == sorted(item["name"] for item in snapshot["tools"])
    assert all(
        getattr(tool.fn, "__diptrace_mcp_thread_offload__", False)
        and tool.is_async
        for tool in actual_tools.values()
    )

    error = error_result_to_mcp_result(
        exception_to_error_result(
            ObjectNotFoundError("missing", details={"path": "/private/missing.dip"})
        )
    )
    assert error.isError is True
    assert error.structuredContent["error"]["code"] == "OBJECT_NOT_FOUND"
