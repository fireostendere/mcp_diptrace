from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.services.documents import (
    BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT,
    _bounded_board_item,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path) -> tuple[DipTraceService, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("pcb.xml", "schematic.xml", "component_library.xml"):
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


def test_bounded_board_item_summarizes_large_dict_and_string() -> None:
    huge = {
        "stable_id": "component_0123456789abcdef",
        "name": "name" * 200,
        **{f"field_{index}": "x" * 2000 for index in range(40)},
    }
    rendered, summarized = _bounded_board_item(
        huge,
        item_index=7,
        full_model_resource="diptrace://document/doc/board-model",
    )
    assert summarized is True
    assert rendered["stable_id"] == "component_0123456789abcdef"
    assert rendered["_payload"]["item_index"] == 7
    assert rendered["_payload"]["omitted_field_count"] >= 40
    assert rendered["_payload"]["omitted_fields_truncated"] is True

    text = "z" * (BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT + 1000)
    rendered_text, summarized_text = _bounded_board_item(
        text,
        item_index=3,
        full_model_resource="diptrace://document/doc/board-model",
    )
    assert summarized_text is True
    assert len(rendered_text["value_prefix"]) == 1000
    assert rendered_text["_payload"]["omitted_character_count"] > 0


def test_document_model_type_guards_and_summary_page(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb.xml")
    schematic = str(workspace / "schematic.xml")

    summary = service.board_model(board, section="summary")
    assert summary["result"]["contract_version"] == 1
    assert summary["result"]["serialized_response_bytes"] > 0

    components = service.board_model(board, section="components", offset=0, limit=1)
    assert components["result"]["section"] == "components"
    assert components["result"]["page"]["returned_count"] <= 1

    with pytest.raises(DocumentError, match="PCB model"):
        service.board_model(schematic)
    with pytest.raises(DocumentError, match="Schematic model"):
        service.schematic_model(board)
    with pytest.raises(DocumentError, match="Unknown board-model section"):
        service.board_model(board, section="not-a-section")


def test_document_queries_resources_and_xml_limits(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb.xml")
    library = str(workspace / "component_library.xml")

    info = service.document_info(board)
    document_id = info["document"]["document_id"]
    queried = service.query_objects(board, selector={"kinds": ["component"]}, limit=10)
    assert len(queried["result"]["items"]) >= 1
    stable_id = queried["result"]["items"][0]["stable_id"]
    obj = service.get_object(stable_id, board)
    assert obj["result"]["stable_id"] == stable_id
    assert obj["result"]["source_xml"] is not None

    graph = service.get_connectivity_graph(board)
    assert graph["ok"] is True
    assert json.loads(service.document_resource(document_id, "summary"))
    assert json.loads(service.document_resource(document_id, "board-model"))
    assert json.loads(service.document_resource(document_id, "stackup"))
    assert json.loads(service.document_resource(document_id, "connectivity"))
    with pytest.raises(DocumentError, match="Unknown document resource"):
        service.document_resource(document_id, "does-not-exist")

    library_info = service.document_info(library)
    library_id = library_info["document"]["document_id"]
    assert json.loads(service.document_resource(library_id, "library-model"))

    with pytest.raises(DocumentError, match="refdes cannot be empty"):
        service.component("   ", board)
    with pytest.raises(DocumentError, match="max_matches"):
        service.read_xml(board, max_matches=0)
    with pytest.raises(DocumentError, match="max_characters"):
        service.read_xml(board, max_characters=0)

    xml = service.read_xml(board, xpath=".//*", max_matches=100, max_characters=20)
    assert xml["truncated"] is True
    assert xml["xml"].endswith("... XML output truncated ...")


def test_document_inspector_facade_paths(tmp_path: Path) -> None:
    service, workspace = _service(tmp_path)
    board = str(workspace / "pcb.xml")

    assert service.summarize(board)["path"]
    assert service.components(board, query="U", limit=10)["live_session"] is False
    nets = service.nets(board, query="V", include_endpoints=False, limit=10)
    assert nets["live_session"] is False
    assert service.rules(board)["live_session"] is False
