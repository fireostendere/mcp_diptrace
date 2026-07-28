from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import get_args, get_origin

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import (
    BOARD_MODEL_COLLECTION_SECTIONS,
    BoardModel,
    BoardModelSection,
    TransactionRecord,
)
from diptrace_mcp.errors import DocumentError, EditError
from diptrace_mcp.service import (
    BOARD_MODEL_RESPONSE_BYTE_LIMIT,
    RAW_EDIT_RESPONSE_BYTE_LIMIT,
    RAW_EDIT_XPATH_CHARACTER_LIMIT,
    DipTraceService,
)
from diptrace_mcp.xml_document import XmlEdit, unified_xml_diff_preview

FIXTURES = Path(__file__).parent / "fixtures"


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
            max_scan_files=100,
        )
    )


def _serialized_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    )


def test_board_model_section_registry_covers_every_list_field() -> None:
    BoardModel.model_rebuild()
    list_fields = {
        name
        for name, field in BoardModel.model_fields.items()
        if get_origin(field.annotation) is list
    }

    assert set(BOARD_MODEL_COLLECTION_SECTIONS) == list_fields
    assert set(get_args(BoardModelSection)) == {"summary", *list_fields}


def test_board_model_pages_nested_geometry_without_exceeding_byte_cap(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    points = root.find("./Board/Nets/Net[@Id='1']/Traces/Trace/Points")
    assert points is not None
    points.clear()
    for index in range(10_000):
        ET.SubElement(
            points,
            "Point",
            {
                "Id": str(index),
                "X": str(index / 10),
                "Y": "10",
                "Lay": "0",
                "Width": "0.25",
                "Jumper": "0",
                "Arc": "N",
                "ViaStyle": "-1",
                "Selected": "N",
            },
        )
    (workspace / "board.dip").write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    service = _service(workspace, tmp_path / "state")

    response = service.board_model("board.dip", section="traces", limit=1)

    assert _serialized_size(response) <= BOARD_MODEL_RESPONSE_BYTE_LIMIT
    page = response["result"]["page"]
    assert page["serialized_response_bytes"] == _serialized_size(response)
    assert page["returned_count"] == 1
    assert page["detail_limited"] is True
    assert page["summarized_item_count"] == 1
    item = response["result"]["items"][0]
    assert item["_payload"]["detail"] == "summary"
    assert item["_payload"]["full_item_bytes"] > page["item_detail_byte_limit"]
    assert item["_payload"]["full_model_resource"] == response["resources"][0]


def test_board_model_summary_and_cutout_page_are_explicit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "board.dip").write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")

    summary = service.board_model("board.dip")
    cutouts = service.board_model("board.dip", section="cutouts")
    limits = service.get_capabilities("board.dip")["limits"]

    assert "components" not in summary["result"]
    assert summary["result"]["section_counts"]["cutouts"] == 0
    assert "cutouts" in summary["result"]["available_sections"]
    assert cutouts["result"]["page"]["total_count"] == 0
    assert limits["max_board_model_response_bytes"] == BOARD_MODEL_RESPONSE_BYTE_LIMIT
    assert limits["max_raw_edit_response_bytes"] == RAW_EDIT_RESPONSE_BYTE_LIMIT
    assert (
        limits["max_raw_edit_xpath_characters"]
        == RAW_EDIT_XPATH_CHARACTER_LIMIT
    )
    assert limits["max_diff_lines"] == 200
    assert limits["max_diff_characters"] == 200_000


def test_board_model_byte_limited_page_advances_without_silent_omission(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    components = root.find("./Board/Components")
    assert components is not None
    for index in range(100):
        component = ET.SubElement(
            components,
            "Component",
            {
                "Id": str(100 + index),
                "PatternStyle": "Synthetic",
                "X": str(index),
                "Y": "20",
                "Blob": "Z" * 3_000,
            },
        )
        ET.SubElement(component, "RefDes").text = f"C{index + 1}"
        ET.SubElement(component, "Name").text = "SYNTHETIC"
        ET.SubElement(component, "Value").text = "Z" * 3_000
        ET.SubElement(component, "Pads")
    (workspace / "board.dip").write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    service = _service(workspace, tmp_path / "state")

    first = service.board_model("board.dip", section="components", limit=100)
    first_page = first["result"]["page"]

    assert _serialized_size(first) <= BOARD_MODEL_RESPONSE_BYTE_LIMIT
    assert first_page["byte_limited"] is True
    assert 0 < first_page["returned_count"] < first_page["total_count"]
    assert first_page["next_offset"] == first_page["returned_count"]

    second = service.board_model(
        "board.dip",
        section="components",
        offset=first_page["next_offset"],
        limit=100,
    )
    assert second["result"]["page"]["returned_count"] > 0
    assert second["result"]["page"]["offset"] == first_page["next_offset"]


def test_transaction_responses_do_not_echo_operations_or_inline_artifacts(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.dip"
    board.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")
    begun = service.begin_transaction("board.dip")
    txid = begun["transaction"]["txid"]
    legacy_payload = service.transactions.read(txid).model_dump(mode="python")
    legacy_payload.pop("preview_metadata")
    assert TransactionRecord.model_validate(legacy_payload).preview_metadata == {}
    service.stage_operations(
        txid,
        [
            {
                "kind": "set_component_value",
                "selector": {"refdes": ["R1"]},
                "value": "X" * 4_096,
            }
        ],
    )

    preview = service.preview_transaction(txid)

    assert preview["written"] is False
    assert "operations" not in preview["transaction"]
    assert preview["transaction"]["operation_count"] == 1
    assert preview["preview"]["inline"] is False
    assert set(preview["preview"]["artifacts"]) == {"svg", "json", "diff"}
    assert "X" * 4_096 not in json.dumps(preview)
    stored_transaction = service.transactions.read(txid)
    assert stored_transaction.operations[0]["value"] == "X" * 4_096
    assert stored_transaction.preview_metadata == preview["preview"]

    validated = service.validate_transaction(txid)
    assert validated["written"] is False
    assert "operations" not in validated["transaction"]

    committed = service.commit_transaction(
        txid,
        preview["transaction"]["source_sha256"],
    )
    assert committed["written"] is True
    assert "operations" not in committed["transaction"]


def test_raw_edit_diff_is_resource_only_and_bounded_by_lines_and_characters(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "board.dip").write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")
    fragment = (
        "<Bulk>\n"
        + "\n".join(f'<X Id="{index}" />' for index in range(300))
        + "\n<Blob>"
        + ("Z" * 250_000)
        + "</Blob>\n</Bulk>"
    )

    response = service.apply_edits(
        [XmlEdit(operation="append_xml", xpath=".", value=fragment)],
        "board.dip",
        dry_run=True,
    )

    metadata = response["diff"]
    assert metadata["inline"] is False
    assert metadata["truncated"] is True
    assert metadata["truncated_by_lines"] is True
    assert metadata["truncated_by_characters"] is True
    assert metadata["stored_line_count"] <= metadata["line_limit"]
    assert metadata["stored_character_count"] <= metadata["character_limit"]
    assert response["resources"] == [metadata["resource_uri"]]
    stored = service.raw_preview_diff_resource(metadata["preview_id"])
    assert len(stored) == metadata["stored_character_count"]
    assert stored.endswith("... diff truncated; see metadata for total size ...")
    assert "Z" * 250_000 not in json.dumps(response)
    with pytest.raises(DocumentError):
        service.raw_preview_diff_resource("../diff")


def test_raw_edit_many_matches_returns_only_bounded_per_edit_metadata(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    root = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    board = root.find("./Board")
    assert board is not None
    payloads = ET.SubElement(board, "SyntheticPayloads")
    for index in range(500):
        ET.SubElement(
            payloads,
            "Payload",
            {"Id": str(index), "Flag": "0"},
        )
    (workspace / "board.dip").write_bytes(
        ET.tostring(root, encoding="utf-8", xml_declaration=True)
    )
    service = _service(workspace, tmp_path / "state")
    edits = [
        XmlEdit(
            operation="set_attribute",
            xpath="./Board/SyntheticPayloads/Payload",
            attribute="Flag",
            value=str(index + 1),
            expected_matches=500,
        )
        for index in range(50)
    ]

    response = service.apply_edits(edits, "board.dip", dry_run=True)

    assert _serialized_size(response) <= RAW_EDIT_RESPONSE_BYTE_LIMIT
    assert response["serialized_response_bytes"] == _serialized_size(response)
    assert response["response_byte_limit"] == RAW_EDIT_RESPONSE_BYTE_LIMIT
    assert response["operations_metadata"] == {
        "edit_count": 50,
        "total_match_count": 25_000,
        "snippets_inline": False,
        "xpath_character_limit": RAW_EDIT_XPATH_CHARACTER_LIMIT,
    }
    assert len(response["operations"]) == 50
    for index, operation in enumerate(response["operations"]):
        assert operation["index"] == index
        assert operation["matches"] == 500
        assert operation["before_count"] == 500
        assert operation["after_count"] == 500
        assert "before" not in operation
        assert "after" not in operation
    assert response["diff"]["inline"] is False
    assert response["resources"] == [response["diff"]["resource_uri"]]


def test_raw_edit_match_guard_remains_a_typed_error_before_response(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "board.dip").write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")

    with pytest.raises(
        EditError,
        match=r"matched 2 elements, expected 3",
    ):
        service.apply_edits(
            [
                XmlEdit(
                    operation="set_text",
                    xpath="./Board/Components/Component/Value",
                    value="22k",
                    expected_matches=3,
                )
            ],
            "board.dip",
            dry_run=True,
        )


def test_raw_edit_written_response_obeys_the_same_serialized_cap(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "board.dip").write_bytes((FIXTURES / "pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")
    edits = [
        XmlEdit(
            operation="set_text",
            xpath="./Board/Components/Component[@Id='1']/Value",
            value="22k",
        )
    ]
    preview = service.apply_edits(edits, "board.dip", dry_run=True)

    response = service.apply_edits(
        edits,
        "board.dip",
        dry_run=False,
        expected_sha256=preview["before_sha256"],
    )

    assert response["written"] is True
    assert _serialized_size(response) <= RAW_EDIT_RESPONSE_BYTE_LIMIT
    assert response["serialized_response_bytes"] == _serialized_size(response)
    assert response["backup_character_count"] == len(response["backup"])
    assert response["backup_truncated"] is False


def test_diff_marker_is_inside_both_stored_caps() -> None:
    before = b"<Root>\n<A>one</A>\n<B>two</B>\n</Root>\n"
    after = (
        b"<Root>\n<A>"
        + (b"z" * 500)
        + b"</A>\n<B>changed</B>\n<C>changed</C>\n</Root>\n"
    )

    diff, metadata = unified_xml_diff_preview(
        before,
        after,
        max_lines=3,
        max_characters=80,
    )

    assert metadata["truncated"] is True
    assert metadata["stored_line_count"] <= 3
    assert metadata["stored_character_count"] <= 80
    assert metadata["stored_character_count"] == len(diff)
    assert diff.endswith("... diff truncated; see metadata for total size ...")

    full_diff, full_metadata = unified_xml_diff_preview(before, after)
    exact_diff, exact_metadata = unified_xml_diff_preview(
        before,
        after,
        max_lines=full_metadata["total_line_count"],
        max_characters=max(full_metadata["total_character_count"], 80),
    )
    assert exact_metadata["truncated"] is False
    assert exact_metadata["stored_line_count"] == exact_metadata["line_limit"]
    assert exact_diff == full_diff
