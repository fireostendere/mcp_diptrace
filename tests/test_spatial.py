from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.geometry import BBox, Point
from diptrace_mcp.spatial import SpatialIndex
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_spatial_intersection_layer_and_nearest_queries() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))
    index = SpatialIndex.build(snapshot.objects.values(), cell_size_mm=2.0)

    around_r1 = index.query(BBox(9.0, 9.0, 11.0, 11.0), kinds={"component"})
    assert [item.refdes for item in around_r1] == ["R1"]

    traces = index.query(BBox(14.0, 9.0, 16.0, 11.0), layers={"0"}, kinds={"trace"})
    assert len(traces) == 1

    nearest = index.nearest(Point(19.8, 10.0), kinds={"component"}, limit=1)
    assert nearest[0][0].refdes == "U1"


def test_spatial_index_removal_and_validation() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))
    component = next(item for item in snapshot.objects.values() if item.refdes == "R1")
    index = SpatialIndex.build([component])
    index.remove(component.stable_id)

    assert index.query(BBox(0, 0, 50, 30)) == []
