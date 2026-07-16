from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import ObjectRecord, QueryRequest, QuerySelector
from diptrace_mcp.errors import Sha256MismatchError, TransactionConflictError
from diptrace_mcp.operations import MoveComponentsOperation, SetComponentValueOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument, XmlEdit, sha256_bytes
from pydantic import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def service_for(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
            max_scan_files=100,
        )
    )


def test_models_reject_invalid_contracts() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(limit=501)
    with pytest.raises(ValidationError):
        QuerySelector(bbox={"min_x": 2, "min_y": 0, "max_x": 1, "max_y": 1})
    with pytest.raises(ValidationError):
        QuerySelector(refdes_regex="[")
    with pytest.raises(ValidationError):
        ObjectRecord(stable_id="bad", kind="component", unexpected=True)


def test_stable_ids_survive_value_refdes_and_content_changes(tmp_path: Path) -> None:
    path = tmp_path / "board.dip"
    path.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    original = DipTraceDocument.load(path, 10_000_000)
    before = build_snapshot(original)
    component_before = next(item for item in before.objects.values() if item.refdes == "R1")

    value_result = apply_semantic_operations(
        original,
        [
            SetComponentValueOperation(
                selector=QuerySelector(refdes=["R1"]),
                value="47k",
            )
        ],
    )
    after_value = build_snapshot(value_result.document)
    component_after_value = next(
        item for item in after_value.objects.values() if item.refdes == "R1"
    )

    refdes_bytes, _ = original.apply_edits(
        [
            XmlEdit(
                operation="set_text",
                xpath="./Board/Components/Component[@Id='0']/RefDes",
                value="R101",
            )
        ]
    )
    after_refdes = build_snapshot(DipTraceDocument.from_bytes(path, refdes_bytes))
    component_after_refdes = next(
        item for item in after_refdes.objects.values() if item.refdes == "R101"
    )

    assert before.info.document_id == after_value.info.document_id == after_refdes.info.document_id
    assert component_before.stable_id == component_after_value.stable_id
    assert component_before.stable_id == component_after_refdes.stable_id


def test_trace_via_text_geometry_and_unknown_xml_are_preserved() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)

    assert snapshot.board is not None
    assert len(snapshot.board.traces) == 1
    assert snapshot.board.traces[0].attributes["length_mm"] == 10.0
    assert snapshot.board.traces[0].attributes["segment_widths_mm"] == [0.25, 0.25]
    assert len(snapshot.board.vias) == 1
    assert {item.kind for item in snapshot.board.texts} == {"component_text", "board_text"}

    result = apply_semantic_operations(
        document,
        [
            MoveComponentsOperation(
                selector=QuerySelector(refdes=["R1"]),
                dx=1.0,
            )
        ],
    )
    reparsed = DipTraceDocument.from_bytes(Path("roundtrip.xml"), result.raw_bytes)
    extension = reparsed.container.find("./FutureExtension")
    assert extension is not None
    assert extension.get("Vendor") == "fixture"
    assert extension.find("./Data").get("Preserve") == "Y"


def test_semantic_compiler_changes_only_target_bytes() -> None:
    payload = (
        b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?>\r\n'
        b'<Source Type="DipTrace-PCB" Version="5.3.0.2" Units="mm">\r\n'
        b'<Board><Components>\r\n'
        b'<Component Id="7" X = \'1\' Y="2" Side="Top" Locked="N">'
        b'<RefDes>R1</RefDes><Value/><Future Vendor="keep"><Cache/></Future>'
        b'</Component>\r\n'
        b'</Components><UnknownSection Preserve="Y"/></Board></Source>\r\n'
    )
    document = DipTraceDocument.from_bytes(Path("raw-semantic.xml"), payload)

    result = apply_semantic_operations(
        document,
        [
            MoveComponentsOperation(
                selector=QuerySelector(refdes=["R1"]),
                dx=1.0,
            ),
            SetComponentValueOperation(
                selector=QuerySelector(refdes=["R1"]),
                value="47k & 1%",
            ),
        ],
    )

    expected = payload.replace(b"X = '1'", b"X = '2'").replace(
        b"<Value/>",
        b"<Value>47k &amp; 1%</Value>",
    )
    assert result.raw_bytes == expected
    assert result.raw_bytes.startswith(b"\xef\xbb\xbf")
    assert b'<Future Vendor="keep"><Cache/></Future>' in result.raw_bytes
    assert b'<UnknownSection Preserve="Y"/>' in result.raw_bytes


def test_semantic_coordinates_are_mm_for_inch_source(tmp_path: Path) -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes().replace(
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">',
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="inch">',
    )
    path = tmp_path / "inch-board.dip"
    path.write_bytes(raw)
    document = DipTraceDocument.load(path, 10_000_000)
    before = build_snapshot(document)
    component = next(item for item in before.objects.values() if item.refdes == "R1")
    assert component.position == {"x": 254.0, "y": 254.0}

    result = apply_semantic_operations(
        document,
        [
            MoveComponentsOperation(
                selector=QuerySelector(refdes=["R1"]),
                dx=25.4,
            )
        ],
    )
    moved = result.document.container.find("./Components/Component[@Id='0']")
    assert moved is not None
    assert moved.get("X") == "11"


def test_transaction_append_validation_and_conflict_safe_rollback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "board.dip"
    path.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = service_for(project, tmp_path / "state")

    begun = service.begin_transaction("board.dip")
    txid = begun["transaction"]["txid"]
    service.stage_operations(
        txid,
        [
            {
                "kind": "move_components",
                "selector": {"refdes": ["R1"]},
                "dx": 1.0,
            }
        ],
    )
    staged = service.stage_operations(
        txid,
        [
            {
                "kind": "set_component_value",
                "selector": {"refdes": ["R1"]},
                "value": "47k",
            }
        ],
    )
    assert staged["result"]["staged_count"] == 2

    with pytest.raises(TransactionConflictError):
        service.commit_transaction(txid, begun["transaction"]["source_sha256"])

    preview = service.preview_transaction(txid)
    committed = service.commit_transaction(
        txid,
        preview["transaction"]["source_sha256"],
    )
    commit_sha = committed["transaction"]["committed_sha256"]
    path.write_bytes(path.read_bytes().replace(b"<Value>47k</Value>", b"<Value>48k</Value>"))

    with pytest.raises(Sha256MismatchError):
        service.rollback_transaction(txid, commit_sha)
    assert sha256_bytes(path.read_bytes()) != commit_sha


def test_rolling_back_uncommitted_plan_does_not_touch_document(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    path = project / "board.dip"
    path.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    original = path.read_bytes()
    service = service_for(project, tmp_path / "state")
    begun = service.begin_transaction("board.dip")

    rolled_back = service.rollback_transaction(begun["transaction"]["txid"])

    assert rolled_back["result"]["document_restored"] is False
    assert path.read_bytes() == original
