from __future__ import annotations

from collections import Counter
from typing import Any, Protocol

from .adapters import DocumentSnapshot
from .findings import Finding, make_finding
from .geometry import Point, segment_distance, to_mm
from .lengths import analyze_differential_pair


class _Registry(Protocol):
    def register(self, check_id: str, category: str, source_kind: str) -> Any: ...


def _layer_sizes(snapshot: DocumentSnapshot) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for item in snapshot.document.container.findall("./DRC/LaySizes/LaySize"):
        values: dict[str, float] = {}
        for attribute in ("MinTrace", "MinDrill", "MinRing"):
            raw = item.get(attribute)
            if raw is not None:
                values[attribute] = to_mm(float(raw), snapshot.document.units)
        result[item.get("Lay", "")] = values
    return result


def _trace_board_clearance(snapshot: DocumentSnapshot) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in snapshot.document.container.findall("./DRC/LayClearances/LayClearance"):
        details = item.find("./ClearanceDetails")
        raw = item.get("TraceToBoard")
        if raw is None and details is not None:
            raw = details.get("TraceToBoard")
        if raw is not None:
            result[item.get("Lay", "")] = to_mm(float(raw), snapshot.document.units)
    return result


def check_min_trace_width(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    sizes = _layer_sizes(snapshot)
    if not sizes:
        return [], {"skipped": "minimum_trace_rules_unavailable"}
    findings: list[Finding] = []
    segments_checked = 0
    for trace in snapshot.board.traces:
        widths = trace.attributes.get("segment_widths_mm", [])
        layers = trace.attributes.get("segment_layers", [])
        for index, raw_width in enumerate(widths):
            if raw_width is None:
                continue
            layer = str(layers[index]) if index < len(layers) else trace.layer or ""
            required = sizes.get(layer, {}).get("MinTrace")
            if required is None:
                continue
            segments_checked += 1
            width = float(raw_width)
            if width + 1e-9 < required:
                findings.append(
                    make_finding(
                        "pcb.min_trace_width",
                        "manufacturing",
                        "error",
                        "Trace is narrower than the DRC minimum",
                        f"Segment {index} of {trace.label} is {width:g} mm wide; "
                        f"{required:g} mm is required.",
                        object_ids=[trace.stable_id],
                        net_ids=[trace.parent_id] if trace.parent_id else [],
                        layer=layer,
                        measured=width,
                        required=required,
                        units="mm",
                        rule_source="DRC/LaySizes/LaySize.MinTrace",
                    )
                )
    return findings, {"segments_checked": segments_checked}


def check_via_drill_and_ring(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    sizes = _layer_sizes(snapshot)
    if not sizes:
        return [], {"skipped": "via_size_rules_unavailable"}
    min_drill = max(
        (item["MinDrill"] for item in sizes.values() if "MinDrill" in item),
        default=None,
    )
    min_ring = max(
        (item["MinRing"] for item in sizes.values() if "MinRing" in item),
        default=None,
    )
    if min_drill is None and min_ring is None:
        return [], {"skipped": "via_drill_and_ring_rules_unavailable"}
    findings: list[Finding] = []
    checked = 0
    for via in snapshot.board.vias:
        diameter = via.attributes.get("diameter_mm")
        hole = via.attributes.get("hole_mm")
        if diameter is None or hole is None:
            continue
        checked += 1
        diameter_value = float(diameter)
        hole_value = float(hole)
        if min_drill is not None and hole_value + 1e-9 < min_drill:
            findings.append(
                make_finding(
                    "pcb.via_drill_annular_ring",
                    "manufacturing",
                    "error",
                    "Via drill is below the DRC minimum",
                    f"Via drill is {hole_value:g} mm; {min_drill:g} mm is required.",
                    object_ids=[via.stable_id],
                    net_ids=[value for value in [via.net_id] if value],
                    location=via.position,
                    measured=hole_value,
                    required=min_drill,
                    units="mm",
                    rule_source="DRC/LaySizes/LaySize.MinDrill",
                )
            )
        ring = (diameter_value - hole_value) / 2.0
        if min_ring is not None and ring + 1e-9 < min_ring:
            findings.append(
                make_finding(
                    "pcb.via_drill_annular_ring",
                    "manufacturing",
                    "error",
                    "Via annular ring is below the DRC minimum",
                    f"Via ring is {ring:g} mm; {min_ring:g} mm is required.",
                    object_ids=[via.stable_id],
                    net_ids=[value for value in [via.net_id] if value],
                    location=via.position,
                    measured=ring,
                    required=min_ring,
                    units="mm",
                    rule_source="DRC/LaySizes/LaySize.MinRing",
                )
            )
    return findings, {"vias_checked": checked}


def check_trace_board_edge(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    outline = snapshot.board.outline
    if outline is None:
        return [], {"skipped": "board_outline_missing"}
    rules = _trace_board_clearance(snapshot)
    if not rules:
        return [], {"skipped": "trace_to_board_rules_unavailable"}
    polygon = [Point(**point) for point in outline.get("points", [])]
    if len(polygon) < 3:
        return [], {"skipped": "board_outline_invalid"}
    edges = list(zip(polygon, [*polygon[1:], polygon[0]], strict=True))
    findings: list[Finding] = []
    checked = 0
    for trace in snapshot.board.traces:
        points = [Point(**point) for point in trace.attributes.get("points", [])]
        widths = trace.attributes.get("segment_widths_mm", [])
        layers = trace.attributes.get("segment_layers", [])
        for index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
            layer = str(layers[index]) if index < len(layers) else trace.layer or ""
            required = rules.get(layer)
            raw_width = widths[index] if index < len(widths) else None
            if required is None or raw_width is None:
                continue
            checked += 1
            measured = max(
                0.0,
                min(segment_distance(start, end, left, right) for left, right in edges)
                - float(raw_width) / 2.0,
            )
            if measured + 1e-9 < required:
                findings.append(
                    make_finding(
                        "pcb.trace_board_edge",
                        "manufacturing",
                        "error",
                        "Trace is too close to the board outline",
                        f"Copper-to-edge distance is {measured:g} mm; "
                        f"{required:g} mm is required.",
                        object_ids=[trace.stable_id],
                        net_ids=[trace.parent_id] if trace.parent_id else [],
                        layer=layer,
                        measured=measured,
                        required=required,
                        units="mm",
                        rule_source=(
                            "DRC/LayClearances/LayClearance/"
                            "ClearanceDetails.TraceToBoard"
                        ),
                    )
                )
    return findings, {"segments_checked": checked}


def check_stackup_completeness(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    stackup = snapshot.board.stackup
    if stackup.completeness == "complete":
        return [], {"layer_count": len(stackup.layers), "completeness": "complete"}
    finding = make_finding(
        "pcb.stackup_completeness",
        "manufacturing",
        "warning",
        "Physical stackup data is incomplete",
        "Manufacturing and controlled-impedance release checks cannot be completed from "
        "this XML without the missing physical stack fields.",
        confidence=1.0,
        suggested_actions=["Export LayerStackItems with thickness and dielectric constants."],
    )
    return [finding], {
        "layer_count": len(stackup.layers),
        "completeness": stackup.completeness,
        "missing_fields": stackup.missing_fields,
    }


def check_differential_pairs(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    findings: list[Finding] = []
    evaluated = 0
    for pair in snapshot.board.differential_pairs:
        analysis = analyze_differential_pair(snapshot, pair.stable_id)
        evaluated += 1
        for check in analysis.checks:
            if bool(check["passed"]):
                continue
            findings.append(
                make_finding(
                    str(check["check_id"]),
                    "signal_integrity",
                    "error",
                    "Differential-pair rule violation",
                    f"{pair.name}: measured {check['measured']:g} {check['unit']}; "
                    f"required {check['required']:g}.",
                    net_ids=[
                        value
                        for value in [pair.positive_net_id, pair.negative_net_id]
                        if value
                    ],
                    measured=float(check["measured"]),
                    required=float(check["required"]),
                    units=str(check["unit"]),
                    rule_source=f"NetClasses/NetClass[{pair.net_class_id}]",
                )
            )
    return findings, {"pairs_checked": evaluated}


def check_testpoint_coverage(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    covered_xml_ids = {
        item.net_id for item in snapshot.board.testpoints if item.net_id is not None
    }
    findings: list[Finding] = []
    eligible = 0
    for net in snapshot.board.nets:
        if int(net.attributes.get("endpoint_count", 0)) < 2:
            continue
        eligible += 1
        if net.xml_id in covered_xml_ids:
            continue
        findings.append(
            make_finding(
                "pcb.testpoint_coverage",
                "testability",
                "warning",
                "Net has no explicit testpoint",
                f"Net {net.name!r} has no standalone MCP/DipTrace testpoint component.",
                object_ids=[net.stable_id],
                net_ids=[net.stable_id],
                confidence=0.85,
                suggested_actions=[
                    "Decide whether this net needs fixture access before adding a testpoint."
                ],
            )
        )
    return findings, {
        "eligible_nets": eligible,
        "covered_nets": len(covered_xml_ids),
        "coverage": len(covered_xml_ids) / eligible if eligible else 1.0,
    }


def _metadata_fields(item: Any) -> dict[str, str]:
    raw = item.attributes.get("additional_fields", {})
    return {str(key).casefold(): str(value).strip() for key, value in raw.items()}


def check_bom_identity(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    if snapshot.board is not None:
        items = snapshot.board.components
    else:
        assert snapshot.schematic is not None
        items = snapshot.schematic.parts
    unique_by_refdes: dict[str, Any] = {}
    for item in items:
        unique_by_refdes.setdefault((item.refdes or item.stable_id).casefold(), item)
    findings: list[Finding] = []
    for item in unique_by_refdes.values():
        fields = _metadata_fields(item)
        dnp = fields.get("dnp", "").casefold() in {"y", "yes", "true", "1"}
        if dnp:
            continue
        mpn = next(
            (
                fields[key]
                for key in (
                    "mpn",
                    "manufacturer part number",
                    "manufacturer_part_number",
                )
                if fields.get(key)
            ),
            "",
        )
        manufacturer = fields.get("manufacturer") or str(
            item.attributes.get("manufacturer", "")
        ).strip()
        missing = [
            label
            for label, value in (("manufacturer", manufacturer), ("MPN", mpn))
            if not value
        ]
        if missing:
            findings.append(
                make_finding(
                    f"{snapshot.document.kind}.bom_identity",
                    "bom",
                    "warning",
                    "BOM identity is incomplete",
                    f"{item.refdes or item.label} is missing {', '.join(missing)}.",
                    object_ids=[item.stable_id],
                    confidence=1.0,
                    suggested_actions=["Add explicit manufacturer and MPN fields or mark DNP."],
                )
            )
    return findings, {"unique_refdes_checked": len(unique_by_refdes)}


def check_assembly_geometry(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    patterns = {pattern.style for pattern in snapshot.board.patterns if pattern.style}
    missing = [
        item
        for item in snapshot.board.components
        if str(item.attributes.get("pattern_style", "")) not in patterns
    ]
    findings = [
        make_finding(
            "pcb.assembly_geometry",
            "assembly",
            "warning",
            "Footprint geometry is unavailable in the design cache",
            f"{item.refdes or item.label} references pattern "
            f"{item.attributes.get('pattern_style', '')!r}, which is not embedded.",
            object_ids=[item.stable_id],
            confidence=1.0,
            suggested_actions=["Export the PCB with its embedded Pattern Library design cache."],
        )
        for item in missing
    ]
    return findings, {
        "components_checked": len(snapshot.board.components),
        "missing_pattern_geometry": len(missing),
    }


def check_thermal_metadata(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.board is not None
    power_keys = {"power_w", "power (w)", "mcp.powerw", "dissipation_w"}
    annotated = [
        item
        for item in snapshot.board.components
        if power_keys.intersection(_metadata_fields(item))
    ]
    if not annotated:
        return [], {"skipped": "explicit_component_power_metadata_unavailable"}
    findings: list[Finding] = []
    for item in annotated:
        fields = _metadata_fields(item)
        if not fields.get("thermal strategy") and not fields.get("mcp.thermalstrategy"):
            findings.append(
                make_finding(
                    "pcb.thermal_metadata",
                    "thermal",
                    "info",
                    "Power metadata has no thermal implementation note",
                    f"{item.refdes or item.label} has explicit dissipation metadata but no "
                    "thermal-strategy field.",
                    object_ids=[item.stable_id],
                    confidence=0.7,
                    suggested_actions=[
                        "Document copper area, thermal vias, airflow or heatsink assumptions."
                    ],
                )
            )
    return findings, {"annotated_components": len(annotated)}


def check_schematic_duplicate_units(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.schematic is not None
    keys = [
        (
            (part.refdes or "").casefold(),
            str(part.attributes.get("part_number") or part.attributes.get("component_part")),
        )
        for part in snapshot.schematic.parts
        if part.refdes
    ]
    duplicates = {key for key, count in Counter(keys).items() if count > 1}
    findings: list[Finding] = []
    for refdes, unit in sorted(duplicates):
        objects = [
            part.stable_id
            for part in snapshot.schematic.parts
            if (part.refdes or "").casefold() == refdes
            and str(
                part.attributes.get("part_number")
                or part.attributes.get("component_part")
            )
            == unit
        ]
        findings.append(
            make_finding(
                "schematic.duplicate_unit",
                "metadata",
                "error",
                "Duplicate RefDes unit",
                f"{refdes.upper()} unit {unit} appears more than once.",
                object_ids=objects,
            )
        )
    return findings, {"units_checked": len(keys)}


def check_schematic_electrical_conflicts(
    snapshot: DocumentSnapshot,
) -> tuple[list[Finding], dict[str, Any]]:
    assert snapshot.schematic is not None
    typed_pins = [
        pin
        for pin in snapshot.schematic.pins
        if pin.attributes.get("ElectricType") or pin.attributes.get("ElectricalType")
    ]
    if not typed_pins:
        return [], {"skipped": "electrical_pin_types_unavailable"}
    by_id = {pin.stable_id: pin for pin in typed_pins}
    findings: list[Finding] = []
    for net in snapshot.schematic.nets:
        pins = [
            by_id[endpoint]
            for endpoint in net.relationships.get("endpoints", [])
            if endpoint in by_id
        ]
        outputs = [
            pin
            for pin in pins
            if str(
                pin.attributes.get("ElectricType")
                or pin.attributes.get("ElectricalType")
            ).casefold()
            in {"output", "power output"}
        ]
        if len(outputs) > 1:
            findings.append(
                make_finding(
                    "schematic.electrical_conflict",
                    "connectivity",
                    "error",
                    "Multiple electrical outputs share a net",
                    f"Net {net.name!r} contains {len(outputs)} output-type pins.",
                    object_ids=[pin.stable_id for pin in outputs],
                    net_ids=[net.stable_id],
                    confidence=1.0,
                )
            )
    return findings, {"typed_pins_checked": len(typed_pins)}


def register_advanced_checks(registry: _Registry) -> None:
    registrations = (
        ("pcb.min_trace_width", "manufacturing", "pcb", check_min_trace_width),
        (
            "pcb.via_drill_annular_ring",
            "manufacturing",
            "pcb",
            check_via_drill_and_ring,
        ),
        ("pcb.trace_board_edge", "manufacturing", "pcb", check_trace_board_edge),
        (
            "pcb.stackup_completeness",
            "manufacturing",
            "pcb",
            check_stackup_completeness,
        ),
        (
            "pcb.differential_pair_rules",
            "signal_integrity",
            "pcb",
            check_differential_pairs,
        ),
        ("pcb.testpoint_coverage", "testability", "pcb", check_testpoint_coverage),
        ("pcb.bom_identity", "bom", "pcb", check_bom_identity),
        ("pcb.assembly_geometry", "assembly", "pcb", check_assembly_geometry),
        ("pcb.thermal_metadata", "thermal", "pcb", check_thermal_metadata),
        (
            "schematic.duplicate_unit",
            "metadata",
            "schematic",
            check_schematic_duplicate_units,
        ),
        ("schematic.bom_identity", "bom", "schematic", check_bom_identity),
        (
            "schematic.electrical_conflict",
            "connectivity",
            "schematic",
            check_schematic_electrical_conflicts,
        ),
    )
    for check_id, category, source_kind, function in registrations:
        registry.register(check_id, category, source_kind)(function)
