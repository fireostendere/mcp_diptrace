from __future__ import annotations

import pytest

from diptrace_mcp import geometry
from diptrace_mcp.errors import InvalidArgumentError
from diptrace_mcp.operations import (
    AddDifferentialPairRouteOperation,
    AddTestpointOperation,
    AddTraceOperation,
    DifferentialPairCenterPoint,
    MoveBoardTextsOperation,
    MoveComponentsOperation,
    MoveTestpointsOperation,
    MoveViaOperation,
    PcbSyncComponent,
    PcbSyncEndpoint,
    PcbSyncNet,
    PinEndpoint,
    PlacePartOperation,
    SetComponentPropertiesOperation,
    SetTextStyleOperation,
    SetTraceWidthOperation,
    SyncSchematicToPcbOperation,
    TracePathPoint,
    UpdateNetClassRulesOperation,
    WireEndpoint,
    parse_semantic_operations,
)


def test_operation_noop_property_and_rule_validators() -> None:
    invalid = (
        lambda: MoveComponentsOperation(),
        lambda: MoveBoardTextsOperation(),
        lambda: MoveTestpointsOperation(),
        lambda: MoveViaOperation(),
        lambda: SetComponentPropertiesOperation(),
        lambda: SetComponentPropertiesOperation(fields={" ": "x"}),
        lambda: SetTextStyleOperation(),
        lambda: UpdateNetClassRulesOperation(class_name="Default"),
        lambda: UpdateNetClassRulesOperation(class_name="Default", min_width=2, max_width=1),
        lambda: UpdateNetClassRulesOperation(class_name="Default", width=1, min_width=2),
        lambda: UpdateNetClassRulesOperation(class_name="Default", width=2, max_width=1),
        lambda: AddTestpointOperation(net="N", x=0, y=0, pad_diameter=1, hole_diameter=1),
        lambda: SetTraceWidthOperation(width=1, segment_indices=[-1]),
        lambda: PinEndpoint(pin=0),
        lambda: PinEndpoint(refdes="U1", part_id="1", pin=0),
        lambda: WireEndpoint(type="Pin", refdes="U1"),
        lambda: WireEndpoint(type="Wire"),
    )
    for build in invalid:
        with pytest.raises(ValueError):
            build()


def test_trace_and_differential_pair_validators() -> None:
    point = TracePathPoint(x=0, y=0)
    base = {
        "net": "N",
        "start_object_id": "a",
        "end_object_id": "b",
        "points": [point, point],
        "layer": "Top",
        "width": 0.2,
    }
    with pytest.raises(ValueError, match="different"):
        AddTraceOperation(**{**base, "end_object_id": "a"})
    with pytest.raises(ValueError, match="non-zero"):
        AddTraceOperation(**base)

    center = DifferentialPairCenterPoint(
        x=0,
        y=0,
        layer="Top",
        positive_dx=0,
        positive_dy=0.1,
        negative_dx=0,
        negative_dy=-0.1,
    )
    diff = {
        "pair": "USB",
        "positive_net": "DP",
        "negative_net": "DM",
        "positive_start_object_id": "a",
        "positive_end_object_id": "b",
        "negative_start_object_id": "c",
        "negative_end_object_id": "d",
        "positive_points": [point, point],
        "negative_points": [point, point],
        "center_points": [center, center],
        "start_pad_point_id": "s",
        "end_pad_point_id": "e",
        "layer": "Top",
        "width": 0.2,
    }
    with pytest.raises(ValueError, match="equal point counts"):
        AddDifferentialPairRouteOperation(**{**diff, "positive_points": [point, point, point]})
    with pytest.raises(ValueError, match="different"):
        AddDifferentialPairRouteOperation(**{**diff, "negative_net": "DP"})


def test_embedded_library_and_sync_validators() -> None:
    with pytest.raises(ValueError, match="component definition"):
        PlacePartOperation(
            component_style="X",
            refdes="U1",
            x=0,
            y=0,
            pin_count=1,
            library_pattern_xml=["<Pattern/>"],
        )
    with pytest.raises(ValueError, match="DTD"):
        PlacePartOperation(
            component_style="X",
            refdes="U1",
            x=0,
            y=0,
            pin_count=1,
            library_component_xml="<!DOCTYPE x><Component/>",
        )
    for pads, message in (([""], "empty"), (["1", "1"], "unique")):
        with pytest.raises(ValueError, match=message):
            PcbSyncComponent(refdes="U1", pattern_style="P", x=0, y=0, pad_numbers=pads)
    component = PcbSyncComponent(refdes="U1", pattern_style="P", x=0, y=0, pad_numbers=["1"])
    with pytest.raises(ValueError, match="unique RefDes"):
        SyncSchematicToPcbOperation(schematic_sha256="a" * 64, components=[component, component])
    endpoint = PcbSyncEndpoint(refdes="U1", pad_number="1")
    net = PcbSyncNet(name="N", endpoints=[endpoint])
    with pytest.raises(ValueError, match="unique names"):
        SyncSchematicToPcbOperation(
            schematic_sha256="a" * 64,
            components=[component],
            nets=[net, net],
        )
    with pytest.raises(TypeError, match="mapping"):
        parse_semantic_operations([None])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="Unsupported"):
        parse_semantic_operations([{"kind": "missing"}])


def test_geometry_units_bbox_matrix_and_degenerate_paths() -> None:
    with pytest.raises(InvalidArgumentError, match="Unsupported"):
        geometry.to_mm(1, "cm")
    with pytest.raises(InvalidArgumentError, match="Unsupported"):
        geometry.from_mm(1, "cm")
    with pytest.raises(ValueError, match="Invalid"):
        geometry.BBox(1, 0, 0, 1)
    with pytest.raises(ValueError, match="at least one"):
        geometry.BBox.from_points([])
    assert geometry.BBox.empty().min_x == 0
    assert geometry.Transform(mirror_y=True)._apply_parameter_transform(
        geometry.Point(1, 2), geometry.Point(0, 0)
    ) == geometry.Point(1, -2)
    with pytest.raises(ValueError, match="not invertible"):
        geometry.Transform(matrix=(0, 0, 0, 0, 0, 0)).inverse()
    assert geometry.Transform._multiply_matrix(
        (1, 0, 0, 1, 0, 0), (1, 0, 0, 1, 2, 3)
    ) == (1, 0, 0, 1, 2, 3)
    assert geometry.Transform().compose(geometry.Transform()).matrix is not None
    assert (
        geometry.point_to_segment_distance(
            geometry.Point(1, 0), geometry.Point(0, 0), geometry.Point(0, 0)
        )
        == 1
    )
    assert (
        geometry.segment_distance(
            geometry.Point(0, 0),
            geometry.Point(1, 1),
            geometry.Point(0, 1),
            geometry.Point(1, 0),
        )
        == 0
    )
    assert geometry.arc_through_points_length(
        geometry.Point(0, 0), geometry.Point(1, 0), geometry.Point(2, 0)
    ) == 2
    with pytest.raises(ValueError, match="flag per point"):
        geometry.trace_path_length([geometry.Point(0, 0), geometry.Point(1, 0)], [False])
    with pytest.raises(ValueError, match="at least one"):
        geometry.bbox_union([])
    assert geometry.point_in_polygon(geometry.Point(0, 0), []) is False
    assert geometry.round_mm(1.23456, digits=2) == 1.23
