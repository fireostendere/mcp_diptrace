from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.config import Settings
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"
PointTuple = tuple[float, float]
SegmentTuple = tuple[PointTuple, PointTuple]


def _service(tmp_path: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
            max_document_bytes=10_000_000,
        )
    )


def _prepare(tmp_path: Path) -> tuple[DipTraceService, Path]:
    target = tmp_path / "main.dch"
    shutil.copy(FIXTURES / "schematic.xml", target)
    return _service(tmp_path), target


def _sha(service: DipTraceService, path: str = "main.dch") -> str:
    return str(service.document_info(path)["result"]["sha256"])


def _wire_points(target: Path, net_name: str, index: int = -1) -> list[PointTuple]:
    root = ET.fromstring(target.read_bytes())
    net = root.find(f"./Schematic/Nets/Net[Name='{net_name}']")
    assert net is not None
    wires = net.findall("./Wires/Wire")
    assert wires
    points = wires[index].findall("./Points/Point")
    return [(float(point.get("X", "0")), float(point.get("Y", "0"))) for point in points]


def _orthogonal(points: list[PointTuple]) -> bool:
    return all(
        first[0] == second[0] or first[1] == second[1]
        for first, second in zip(points, points[1:], strict=False)
    )


def _segments(points: list[PointTuple]) -> list[SegmentTuple]:
    return list(zip(points, points[1:], strict=False))


def _proper_crossing(first: SegmentTuple, second: SegmentTuple) -> bool:
    (a, b), (c, d) = first, second
    first_horizontal = a[1] == b[1]
    second_horizontal = c[1] == d[1]
    if first_horizontal == second_horizontal:
        return False
    horizontal = first if first_horizontal else second
    vertical = second if first_horizontal else first
    hx1, hx2 = sorted((horizontal[0][0], horizontal[1][0]))
    vy1, vy2 = sorted((vertical[0][1], vertical[1][1]))
    x = vertical[0][0]
    y = horizontal[0][1]
    return hx1 < x < hx2 and vy1 < y < vy2


def test_clean_wire_is_preserved(tmp_path: Path) -> None:
    service, target = _prepare(tmp_path)
    service.add_wire(
        "VCC",
        [{"x": 0.0, "y": 50.0}, {"x": 50.0, "y": 50.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    assert _wire_points(target, "VCC") == [(0.0, 50.0), (50.0, 50.0)]


def test_wire_routes_around_component_region(tmp_path: Path) -> None:
    service, target = _prepare(tmp_path)
    service.add_wire(
        "VCC",
        [{"x": 0.0, "y": 20.0}, {"x": 50.0, "y": 20.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    points = _wire_points(target, "VCC")
    assert points != [(0.0, 20.0), (50.0, 20.0)]
    assert _orthogonal(points)
    assert any(y != 20.0 for _, y in points[1:-1])


def test_wire_avoids_existing_wire_crossing(tmp_path: Path) -> None:
    service, target = _prepare(tmp_path)
    service.add_wire(
        "SIGNAL",
        [{"x": 25.0, "y": 0.0}, {"x": 25.0, "y": 40.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    existing = _wire_points(target, "SIGNAL")
    service.add_wire(
        "VCC",
        [{"x": 0.0, "y": 10.0}, {"x": 50.0, "y": 10.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    routed = _wire_points(target, "VCC")
    assert routed != [(0.0, 10.0), (50.0, 10.0)]
    assert _orthogonal(routed)
    assert not any(
        _proper_crossing(first, second)
        for first in _segments(existing)
        for second in _segments(routed)
    )


def test_wire_avoids_existing_wire_overlap(tmp_path: Path) -> None:
    service, target = _prepare(tmp_path)
    service.add_wire(
        "SIGNAL",
        [{"x": 10.0, "y": 10.0}, {"x": 40.0, "y": 10.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    service.add_wire(
        "VCC",
        [{"x": 0.0, "y": 10.0}, {"x": 50.0, "y": 10.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    routed = _wire_points(target, "VCC")
    assert routed != [(0.0, 10.0), (50.0, 10.0)]
    assert _orthogonal(routed)
    assert any(y != 10.0 for _, y in routed[1:-1])


def test_wire_routes_around_schematic_text(tmp_path: Path) -> None:
    service, target = _prepare(tmp_path)
    service.add_net_label(
        "VCC",
        25.0,
        10.0,
        text="IMPORTANT_LABEL",
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    service.add_wire(
        "VCC",
        [{"x": 0.0, "y": 10.0}, {"x": 50.0, "y": 10.0}],
        {"type": "Free"},
        {"type": "Free"},
        path="main.dch",
        dry_run=False,
        expected_sha256=_sha(service),
    )
    points = _wire_points(target, "VCC")
    assert points != [(0.0, 10.0), (50.0, 10.0)]
    assert _orthogonal(points)
    assert any(y != 10.0 for _, y in points[1:-1])
