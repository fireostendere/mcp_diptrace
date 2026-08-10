from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

import diptrace_mcp.geometry_backend as geometry_backend
import diptrace_mcp.review as review_module
import diptrace_mcp.routing as routing_module
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import RoutingError
from diptrace_mcp.findings import Finding
from diptrace_mcp.geometry_backend import shapely_available
from diptrace_mcp.review import run_checks
from diptrace_mcp.routing import RouteConnectionConfig, synthesize_route
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _document_with_pour(
    points: tuple[tuple[float, float], ...],
    *,
    net_id: str = "1",
    layer: str = "0",
    pour_clearance: float = 0.2,
    use_net_clearance: str = "N",
    trace_to_copper: float | None = 0.2,
    trace: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> DipTraceDocument:
    original = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    root = ET.fromstring(original.raw_bytes)
    board = root.find("./Board")
    assert board is not None
    layer_rule = root.find("./Board/DRC/LayClearances/LayClearance[@Lay='0']")
    assert layer_rule is not None
    if trace_to_copper is None:
        layer_rule.attrib.pop("TraceToCopper", None)
    else:
        layer_rule.set("TraceToCopper", str(trace_to_copper))
    existing_traces = root.find("./Board/Nets/Net[@Id='1']/Traces")
    assert existing_traces is not None
    existing_traces.clear()
    pours = ET.SubElement(board, "CopperPours")
    pour = ET.SubElement(
        pours,
        "CopperPour",
        {
            "Id": "0",
            "NetId": net_id,
            "Lay": layer,
            "Poured": "Y",
            "Clearance": str(pour_clearance),
            "UseNetClearance": use_net_clearance,
            "RegionsDone": "Y",
            "Locked": "N",
            "Selected": "N",
        },
    )
    boundary = ET.SubElement(pour, "Points")
    for x, y in points:
        ET.SubElement(boundary, "Point", {"X": str(x), "Y": str(y)})
    if trace is not None:
        traces = root.find("./Board/Nets/Net[@Id='0']/Traces")
        assert traces is not None
        trace_element = ET.SubElement(
            traces,
            "Trace",
            {"Id": "99", "Selected": "N"},
        )
        trace_points = ET.SubElement(trace_element, "Points")
        (start_x, start_y), (end_x, end_y) = trace
        ET.SubElement(
            trace_points,
            "Point",
            {"Id": "0", "X": str(start_x), "Y": str(start_y)},
        )
        ET.SubElement(
            trace_points,
            "Point",
            {
                "Id": "1",
                "X": str(end_x),
                "Y": str(end_y),
                "Lay": "0",
                "Width": "0.25",
                "Arc": "N",
                "Jumper": "0",
                "ViaStyle": "-1",
                "Selected": "N",
            },
        )
    return DipTraceDocument.from_bytes(
        original.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def _route_config(document: DipTraceDocument) -> RouteConnectionConfig:
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    net = next(item for item in snapshot.board.nets if item.name == "VCC")
    start, end = net.relationships["endpoints"]
    return RouteConnectionConfig(
        net=net.stable_id,
        start_object_id=start,
        end_object_id=end,
        layer="Top",
        width=0.25,
        clearance=0.2,
        grid=0.5,
    )


def _pour_findings(document: DipTraceDocument) -> tuple[list[Finding], dict[str, Any]]:
    findings, metrics, _, _ = run_checks(
        build_snapshot(document),
        categories={"clearance"},
    )
    pours = [item for item in findings if item.pour_geometry == "boundary_only"]
    return pours, metrics["pcb.trace_object_clearance"]


def test_trace_to_pour_clearance_uses_boundary_and_discloses_scope() -> None:
    document = _document_with_pour(
        ((14, 8), (16, 8), (16, 10), (14, 10)),
        trace=((10, 9), (20, 9)),
    )

    findings, metrics = _pour_findings(document)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.title == "Trace-to-copper-pour clearance violation"
    assert finding.rule_source == "DRC/LayClearances/LayClearance.TraceToCopper"
    assert finding.pour_geometry == "boundary_only"
    assert finding.geometry_accuracy == ("exact" if shapely_available() else "approximate")
    assert metrics["pour_candidate_pairs_checked"] == 1
    assert metrics["pour_geometry"] == "boundary_only"


def test_trace_to_pour_discloses_missing_trace_to_copper_rule() -> None:
    document = _document_with_pour(
        ((14, 8), (16, 8), (16, 10), (14, 10)),
        trace_to_copper=None,
        trace=((10, 9), (20, 9)),
    )

    findings, metrics = _pour_findings(document)

    assert findings == []
    assert metrics["pour_candidate_pairs_checked"] == 0
    assert metrics["pour_boundaries_without_trace_to_copper_rule"] == 1


@pytest.mark.parametrize(
    ("net_id", "layer"),
    (("0", "0"), ("1", "1")),
    ids=("same-net", "different-layer"),
)
def test_trace_to_pour_clearance_exempts_same_net_and_other_layers(
    net_id: str,
    layer: str,
) -> None:
    document = _document_with_pour(
        ((14, 8), (16, 8), (16, 10), (14, 10)),
        net_id=net_id,
        layer=layer,
        trace=((10, 9), (20, 9)),
    )

    findings, metrics = _pour_findings(document)

    assert findings == []
    assert metrics["pour_candidate_pairs_checked"] == 0


@pytest.mark.skipif(not shapely_available(), reason="geometry extra is not installed")
def test_trace_to_pour_exact_polygon_avoids_bbox_false_positive() -> None:
    document = _document_with_pour(
        ((11, 8), (15, 8), (15, 10)),
        trace=((10, 9), (12, 9)),
    )

    findings, metrics = _pour_findings(document)

    assert findings == []
    assert metrics["pour_candidate_pairs_checked"] == 1
    assert metrics["pour_geometry_accuracy"] == "exact"


def test_trace_to_pour_fallback_is_conservative_and_marked_approximate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document_with_pour(
        ((11, 8), (15, 8), (15, 10)),
        trace=((10, 9), (12, 9)),
    )
    monkeypatch.setattr(geometry_backend, "shapely_available", lambda: False)
    monkeypatch.setattr(review_module, "shapely_available", lambda: False)

    findings, metrics = _pour_findings(document)

    assert len(findings) == 1
    assert findings[0].geometry_accuracy == "approximate"
    assert findings[0].confidence == 0.5
    assert metrics["pour_geometry_accuracy"] == "aabb_approximate"


def test_router_avoids_different_net_pour_boundary() -> None:
    document = _document_with_pour(
        ((14, 8), (16, 8), (16, 10), (14, 10)),
    )

    result = synthesize_route(build_snapshot(document), _route_config(document))

    assert len(result.points) > 2
    assert result.metrics["pour_obstacle_count"] == 1
    assert result.metrics["pour_geometry"] == "boundary_only"
    assert result.metrics["pour_geometry_backend"] == (
        "shapely_geos" if shapely_available() else "aabb_approximate"
    )
    assert any("final refill geometry is unavailable" in item for item in result.limitations)


@pytest.mark.parametrize(
    ("net_id", "layer"),
    (("0", "0"), ("1", "1")),
    ids=("same-net", "different-layer"),
)
def test_router_ignores_same_net_and_other_layer_pours(
    net_id: str,
    layer: str,
) -> None:
    document = _document_with_pour(
        ((14, 8), (16, 8), (16, 10), (14, 10)),
        net_id=net_id,
        layer=layer,
    )

    result = synthesize_route(build_snapshot(document), _route_config(document))

    assert [point.as_dict() for point in result.points] == [
        {"x": 10.0, "y": 9.0},
        {"x": 20.0, "y": 9.0},
    ]
    assert result.metrics["pour_obstacle_count"] == 0


def test_router_honors_use_net_clearance_instead_of_stale_custom_value() -> None:
    points = ((14, 10.0), (16, 10.0), (16, 12.0), (14, 12.0))
    custom = _document_with_pour(
        points,
        pour_clearance=5.0,
        use_net_clearance="N",
    )
    inherited = _document_with_pour(
        points,
        pour_clearance=5.0,
        use_net_clearance="Y",
    )

    with pytest.raises(RoutingError, match="No legal multi-layer"):
        synthesize_route(build_snapshot(custom), _route_config(custom))
    inherited_route = synthesize_route(build_snapshot(inherited), _route_config(inherited))

    assert [point.as_dict() for point in inherited_route.points] == [
        {"x": 10.0, "y": 9.0},
        {"x": 20.0, "y": 9.0},
    ]


def test_router_refuses_full_layer_pour_barrier() -> None:
    document = _document_with_pour(
        ((14, 0), (16, 0), (16, 30), (14, 30)),
    )

    # The correctness invariant is fail-closed: no route may cross the barrier.
    # Slow CI runners can exhaust the bounded search timer before the node search
    # proves that no legal route exists, and both outcomes are safe RoutingError.
    with pytest.raises(RoutingError):
        synthesize_route(build_snapshot(document), _route_config(document))


def test_router_fallback_discloses_conservative_aabb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document_with_pour(
        ((14, 8), (16, 8), (16, 10), (14, 10)),
    )
    monkeypatch.setattr(geometry_backend, "shapely_available", lambda: False)
    monkeypatch.setattr(routing_module, "shapely_available", lambda: False)

    result = synthesize_route(build_snapshot(document), _route_config(document))

    assert result.metrics["pour_geometry_backend"] == "aabb_approximate"
    assert any("conservative AABB" in item for item in result.warnings)
