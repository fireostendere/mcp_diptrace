from __future__ import annotations

import json
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.preview import (
    PREVIEW_COPPER_POINT_LIMIT,
    PREVIEW_COPPER_RECORD_LIMIT,
    render_preview_json,
    render_preview_svg,
)
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot(name: str = "diff_pair_pcb.xml"):
    return build_snapshot(
        DipTraceDocument.load(FIXTURES / name, 10_000_000)
    )


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_preview_renders_normalized_trace_and_pour_geometry() -> None:
    snapshot = _snapshot()
    assert snapshot.board is not None

    svg = render_preview_svg(snapshot, snapshot, [])
    payload = render_preview_json(snapshot, snapshot, [])

    assert 'data-kind="trace"' in svg
    assert 'data-kind="copper_pour"' in svg
    assert 'data-geometry-scope="exported-boundary-only"' in svg
    copper = payload["copper"]["after"]
    assert copper["complete"] is True
    assert copper["truncated"] is False
    assert copper["record_limit"] == PREVIEW_COPPER_RECORD_LIMIT
    assert copper["point_limit"] == PREVIEW_COPPER_POINT_LIMIT
    assert copper["trace_count"] == {"total": 2, "rendered": 2}
    assert copper["copper_pour_count"] == {"total": 1, "rendered": 1}
    scopes = {
        primitive["geometry_scope"] for primitive in copper["primitives"]
    }
    assert scopes == {"normalized_centerline", "exported_boundary_only"}


def test_public_trace_preview_resource_shows_before_after_copper(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    board.write_bytes((FIXTURES / "diff_pair_pcb.xml").read_bytes())
    service = _service(workspace, tmp_path / "state")
    snapshot = _snapshot()
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]

    response = service.set_trace_width(
        {"ids": [trace.stable_id]},
        0.2,
        path=str(board),
    )

    assert response["written"] is False
    limits = service.get_capabilities(str(board))["limits"]
    assert limits["max_preview_copper_records"] == PREVIEW_COPPER_RECORD_LIMIT
    assert limits["max_preview_copper_points"] == PREVIEW_COPPER_POINT_LIMIT
    txid = response["transaction"]["txid"]
    svg = service.transactions.preview_svg_path(txid).read_text(encoding="utf-8")
    payload = json.loads(
        service.transactions.preview_json_path(txid).read_text(encoding="utf-8")
    )
    trace_marker = f'data-object-id="{trace.stable_id}"'
    assert f'{trace_marker} data-kind="trace" data-state="before"' in svg
    assert f'{trace_marker} data-kind="trace" data-state="after"' in svg
    assert 'data-kind="copper_pour"' in svg
    before_changed = payload["copper"]["before_changed"]
    assert before_changed["rendered_record_count"] == 1
    assert before_changed["primitives"][0]["object_id"] == trace.stable_id
    after_trace = next(
        primitive
        for primitive in payload["copper"]["after"]["primitives"]
        if primitive["object_id"] == trace.stable_id
    )
    assert after_trace["changed"] is True
    assert after_trace["segment_widths_mm"] == [0.2]


def test_preview_discloses_copper_point_budget_without_partial_primitive() -> None:
    snapshot = _snapshot()
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]
    trace.attributes["points"] = [
        {"x": float(index), "y": 0.0}
        for index in range(PREVIEW_COPPER_POINT_LIMIT + 1)
    ]

    payload = render_preview_json(snapshot, snapshot, [])
    svg = render_preview_svg(snapshot, snapshot, [])

    copper = payload["copper"]["after"]
    assert copper["complete"] is False
    assert copper["truncated"] is True
    assert copper["omitted_record_count"] == 1
    assert copper["total_record_count"] == (
        copper["rendered_record_count"]
        + copper["invalid_geometry_count"]
        + copper["omitted_record_count"]
    )
    assert trace.stable_id not in {
        primitive["object_id"] for primitive in copper["primitives"]
    }
    assert f'data-object-id="{trace.stable_id}"' not in svg
    assert "after-complete=false" in svg


@pytest.mark.parametrize(
    "malformed_points",
    [
        [{"x": 0.0, "y": 0.0}, "not-a-point", {"x": 1.0, "y": 1.0}],
        [{"x": 0.0, "y": 0.0}, {"x": float("nan"), "y": 1.0}],
    ],
    ids=("non-dict", "non-finite"),
)
def test_preview_rejects_entire_malformed_copper_primitive(
    malformed_points: list[object],
) -> None:
    snapshot = _snapshot()
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]
    trace.attributes["points"] = malformed_points

    payload = render_preview_json(snapshot, snapshot, [])
    svg = render_preview_svg(snapshot, snapshot, [])

    copper = payload["copper"]["after"]
    assert copper["complete"] is False
    assert copper["invalid_geometry_count"] == 1
    assert copper["total_record_count"] == (
        copper["rendered_record_count"]
        + copper["invalid_geometry_count"]
        + copper["omitted_record_count"]
    )
    assert trace.stable_id not in {
        primitive["object_id"] for primitive in copper["primitives"]
    }
    assert f'data-object-id="{trace.stable_id}"' not in svg


def test_preview_rejects_non_finite_trace_width_without_crashing() -> None:
    snapshot = _snapshot()
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]
    trace.attributes["segment_widths_mm"] = [float("inf")]

    copper = render_preview_json(snapshot, snapshot, [])["copper"]["after"]

    assert copper["complete"] is False
    assert copper["invalid_geometry_count"] == 1
    assert copper["total_record_count"] == (
        copper["rendered_record_count"]
        + copper["invalid_geometry_count"]
        + copper["omitted_record_count"]
    )
    assert trace.stable_id not in {
        primitive["object_id"] for primitive in copper["primitives"]
    }
