from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import routing
from diptrace_mcp import routing_compiler as compiler
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import (
    DifferentialPairModel,
    DifferentialPairPadPair,
    DifferentialPairSegment,
    ObjectRecord,
    QuerySelector,
    ResolvedCopperLayer,
)
from diptrace_mcp.errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    ConnectivityRegressionError,
    GeometryError,
    LockedObjectError,
    ObjectNotFoundError,
    RoutingError,
)
from diptrace_mcp.geometry import BBox, Point
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURE = Path(__file__).parent / "fixtures" / "pcb.xml"


def _record(kind: str, suffix: str = "0", **values: object) -> ObjectRecord:
    return ObjectRecord(
        stable_id=f"{kind}_{suffix * 16}",
        kind=kind,
        **values,
    )


def test_route_configuration_cross_field_guards() -> None:
    base = {"net": "N", "start_object_id": "a", "end_object_id": "b", "width": 0.2}
    for values, message in (
        (base, "layer"),
        ({**base, "layer": "Top", "max_vias": 1}, "via_style"),
        ({**base, "preferred_layers": ["Top", "Top"]}, "duplicates"),
    ):
        with pytest.raises(ValueError, match=message):
            routing.RouteConnectionConfig(**values)
    with pytest.raises(ValueError, match="via_style"):
        routing.DifferentialPairRouteConfig(pair="P", layer="Top", max_vias=1)


def test_routing_compiler_lookup_and_layer_guards() -> None:
    empty = SimpleNamespace(board=None)
    with pytest.raises(CapabilityUnavailableError):
        compiler.resolve_copper_layer(empty, "Top")
    with pytest.raises(CapabilityUnavailableError):
        compiler._via_style_id(empty, "Default")

    board = SimpleNamespace(
        layers=[
            {"id": "1", "name": "Top", "type": "Signal"},
            {"id": "2", "name": "top", "type": "Signal"},
        ]
    )
    snapshot = SimpleNamespace(board=board)
    with pytest.raises(ObjectNotFoundError):
        compiler.resolve_copper_layer(snapshot, "Bottom")
    with pytest.raises(AmbiguousSelectorError):
        compiler.resolve_copper_layer(snapshot, "Top")

    plane = ResolvedCopperLayer(
        layer_id="2", layer_name="GND", layer_type="Plane", input_value="GND"
    )
    unknown = ResolvedCopperLayer(
        layer_id="9", layer_name="Mystery", layer_type="Unknown", input_value="9"
    )
    with pytest.raises(RoutingError, match="plane"):
        compiler.require_routing_layer(plane, "test")
    with pytest.raises(RoutingError, match="unknown"):
        compiler.require_routing_layer(unknown, "test")
    with pytest.raises(RoutingError, match="plane"):
        compiler.require_via_layer(plane, "test")


def test_routing_compiler_object_and_endpoint_guards() -> None:
    net = _record("net", xml_id="1", name="VCC")
    duplicate = net.model_copy(update={"stable_id": "net_1111111111111111"})
    objects = {net.stable_id: net}
    snapshot = SimpleNamespace(
        objects=objects,
        elements={},
        select=lambda *_args, **_kwargs: [],
        get_object=lambda value: objects[value],
    )
    with pytest.raises(ObjectNotFoundError, match="explicit"):
        compiler._select(snapshot, QuerySelector(), "trace")
    with pytest.raises(ObjectNotFoundError, match="No matching"):
        compiler._select(snapshot, QuerySelector(ids=["trace_0000000000000000"]), "trace")
    with pytest.raises(ObjectNotFoundError, match="XML element"):
        compiler._element(snapshot, net)
    with pytest.raises(ObjectNotFoundError, match="Net was not found"):
        compiler._net(snapshot, "missing")
    snapshot.objects[duplicate.stable_id] = duplicate
    with pytest.raises(AmbiguousSelectorError):
        compiler._net(snapshot, "VCC")

    component = _record("component", xml_id="10")
    pad = _record("pad", parent_id=component.stable_id, xml_id="2", net_id="1", label="1")
    wrong = _record("text", "2")
    objects.update(
        {
            component.stable_id: component,
            pad.stable_id: pad,
            wrong.stable_id: wrong,
        }
    )
    with pytest.raises(ObjectNotFoundError, match="not a trace"):
        compiler._trace(snapshot, wrong.stable_id)
    locked = net.model_copy(update={"locked": True})
    with pytest.raises(LockedObjectError):
        compiler._ensure_net_unlocked(snapshot, locked)
    with pytest.raises(CapabilityUnavailableError, match="component pads"):
        compiler._endpoint(snapshot, wrong.stable_id, net)
    objects[pad.stable_id] = pad.model_copy(update={"net_id": "other"})
    with pytest.raises(ConnectivityRegressionError):
        compiler._endpoint(snapshot, pad.stable_id, net)
    objects[pad.stable_id] = pad
    objects[component.stable_id] = component.model_copy(update={"xml_id": None})
    with pytest.raises(GeometryError, match="no XML id"):
        compiler._endpoint(snapshot, pad.stable_id, net)


def test_routing_geometry_helpers_and_pair_guards() -> None:
    assert compiler._bbox_gap(BBox(0, 0, 1, 1), BBox(4, 5, 6, 7)) == 5.0
    assert routing._layer_type(SimpleNamespace(board=None), "1") == "Unknown"
    board = SimpleNamespace(
        layers=[
            {"id": "1", "name": "Top", "type": "Signal"},
            {"id": "2", "name": "GND", "type": "Plane"},
        ],
        differential_pairs=[],
    )
    snapshot = SimpleNamespace(board=board)
    with pytest.raises(ObjectNotFoundError, match="Unique differential"):
        routing._find_pair(snapshot, "missing")
    with pytest.raises(RoutingError, match="plane"):
        routing._validate_no_plane_layers(snapshot, ["2"], context="test")
    with pytest.raises(RoutingError, match="unknown"):
        routing._validate_no_plane_layers(snapshot, ["9"], context="test")
    with pytest.raises(GeometryError, match="distinct anchors"):
        routing._perpendicular_directions(Point(0, 0))
    with pytest.raises(GeometryError, match="incompatible"):
        routing._perpendicular_directions(Point(1, 2))
    with pytest.raises(RoutingError, match="zero-length"):
        routing._offset_side(Point(0, 0), Point(0, 0), Point(1, 0))
    with pytest.raises(RoutingError, match="at least two"):
        routing._offset_polyline([Point(0, 0)], 0.1, 1)
    with pytest.raises(RoutingError, match="zero-length"):
        routing._offset_polyline([Point(0, 0), Point(0, 0)], 0.1, 1)
    with pytest.raises(RoutingError, match="180-degree"):
        routing._offset_polyline([Point(0, 0), Point(1, 0), Point(0, 0)], 0.1, 1)
    assert routing._offset_polyline([Point(0, 0), Point(1, 0), Point(1, 1)], 0.1, 1) == [
        Point(0, 0.1),
        Point(0.9, 0.1),
        Point(0.9, 1),
    ]


def test_differential_pair_endpoint_and_pad_guards() -> None:
    first = DifferentialPairPadPair(xml_id="a")
    second = DifferentialPairPadPair(xml_id="b")
    pair = DifferentialPairModel(
        stable_id="pair_0000000000000000",
        name="USB",
        pad_pairs=[first, second],
    )
    config = routing.DifferentialPairRouteConfig(pair="USB", layer="Top")
    with pytest.raises(CapabilityUnavailableError, match="at least two"):
        routing._pair_endpoints(pair.model_copy(update={"pad_pairs": [first]}), config)
    with pytest.raises(ObjectNotFoundError, match="PadPoint"):
        routing._pair_endpoints(pair, config.model_copy(update={"start_pad_point_id": "x"}))
    with pytest.raises(GeometryError, match="different"):
        routing._pair_endpoints(
            pair, config.model_copy(update={"start_pad_point_id": "a", "end_pad_point_id": "a"})
        )
    routed = pair.model_copy(
        update={
            "segments": [
                DifferentialPairSegment(index=0, attributes={"StartPoint": "a", "EndPoint": "b"})
            ]
        }
    )
    with pytest.raises(ConnectivityRegressionError, match="already routed"):
        routing._pair_endpoints(routed, config)

    with pytest.raises(ObjectNotFoundError, match="does not resolve"):
        routing._pair_pad(SimpleNamespace(), None, None)
    component = _record("component")
    bad_pad = _record("text", "1")
    records = {component.stable_id: component, bad_pad.stable_id: bad_pad}
    snapshot = SimpleNamespace(get_object=lambda value: records[value])
    with pytest.raises(ObjectNotFoundError, match="relationship"):
        routing._pair_pad(snapshot, component.stable_id, bad_pad.stable_id)


def test_via_pad_detection_covers_shape_bbox_and_thermal_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert compiler.via_pad_violation_pairs(SimpleNamespace(board=None), 0.2) == set()
    via = SimpleNamespace(
        stable_id="via",
        attributes={"span_layer_ids": ["1"]},
        geometry=object(),
        bbox={"min_x": 0.2, "min_y": 0.2, "max_x": 0.8, "max_y": 0.8},
        net_id="N",
    )
    pad = SimpleNamespace(
        stable_id="pad",
        geometry=object(),
        bbox={"min_x": 0.0, "min_y": 0.0, "max_x": 1.0, "max_y": 1.0},
        net_id="N",
    )
    snapshot = SimpleNamespace(board=SimpleNamespace(vias=[via], pads=[pad]))
    monkeypatch.setattr(compiler, "pad_on_layer", lambda *_args: False)
    assert compiler.via_pad_violation_pairs(snapshot, 0.2) == set()
    monkeypatch.setattr(compiler, "pad_on_layer", lambda *_args: True)
    monkeypatch.setattr(compiler, "shape_distance", lambda *_args: 0.0)
    assert compiler.via_pad_violation_pairs(snapshot, 0.2) == {("via", "pad")}
    assert compiler.via_pad_violation_pairs(snapshot, 0.2, True) == set()


def test_fixture_route_lookup_and_clearance_fallbacks() -> None:
    document = DipTraceDocument.load(FIXTURE, 10_000_000)
    snapshot = build_snapshot(document)
    assert compiler._clearance(document, "missing", None) >= 0
    assert compiler._clearance(document, "missing", 0.42) == 0.42
    assert routing._layer_type(snapshot, "0") in {"Signal", "Unknown"}
