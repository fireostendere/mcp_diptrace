from __future__ import annotations

from .adapter_common import (
    _bool_attr,
    _float_attr,
    _float_attr_mm,
    _text,
    _xml_identity,
    stable_id,
)
from .domain import (
    GeometryShape,
    ObjectRecord,
)
from .geometry import BBox, Point, to_mm
from .xml_document import DipTraceDocument


def _board_copper_pour_records(document: DipTraceDocument) -> list[ObjectRecord]:
    if document.kind != "pcb":
        return []
    net_lookup: dict[str, tuple[str, str]] = {}
    for net in document.container.findall("./Nets/Net"):
        xml_id = net.get("Id", "")
        name = _text(net, "Name")
        net_lookup[xml_id] = (
            stable_id("net", document.source_type, *_xml_identity(xml_id, name)),
            name,
        )
    records: list[ObjectRecord] = []
    for index, pour in enumerate(document.container.findall("./CopperPours/CopperPour")):
        xml_id = pour.get("Id", "")
        net_xml_id = pour.get("NetId", "")
        connected_net = net_lookup.get(net_xml_id)
        points = [
            Point(
                _float_attr_mm(document, point, "X") or 0.0,
                _float_attr_mm(document, point, "Y") or 0.0,
            )
            for point in pour.findall("./Points/Point")
        ]
        records.append(
            ObjectRecord(
                stable_id=stable_id(
                    "copper-pour",
                    document.source_type,
                    *_xml_identity(xml_id, str(index)),
                ),
                kind="copper_pour",
                label=(
                    f"{connected_net[1] if connected_net else 'unassigned'}:pour-{xml_id or index}"
                ),
                xml_id=xml_id or None,
                net_id=net_xml_id if connected_net is not None else None,
                net_name=connected_net[1] if connected_net is not None else None,
                layer=pour.get("Lay"),
                locked=_bool_attr(pour, "Locked"),
                selected=_bool_attr(pour, "Selected"),
                bbox=BBox.from_points(points).as_dict() if points else None,
                geometry=(
                    GeometryShape(
                        kind="polygon",
                        points=[point.as_dict() for point in points],
                        approximation=(
                            "Exported CopperPour boundary; not authoritative refilled copper"
                        ),
                    )
                    if len(points) >= 3
                    else None
                ),
                geometry_source="xml-copper-pour-boundary",
                confidence=0.8 if points else 0.3,
                attributes={
                    **dict(pour.attrib),
                    "points": [point.as_dict() for point in points],
                    "poured": _bool_attr(pour, "Poured"),
                    "regions_done": _bool_attr(pour, "RegionsDone"),
                    "clearance_mm": _float_attr_mm(document, pour, "Clearance"),
                    "use_net_clearance": _bool_attr(pour, "UseNetClearance"),
                    "board_clearance_mm": _float_attr_mm(document, pour, "BoardClearance"),
                    "minimum_area_mm2": (
                        to_mm(1.0, document.units) ** 2
                        * (_float_attr(document, pour, "MinimumArea") or 0.0)
                    ),
                },
                relationships={"net": [connected_net[0]] if connected_net is not None else []},
                warnings=["Boundary geometry is not the final refilled copper region."],
            )
        )
    return records
