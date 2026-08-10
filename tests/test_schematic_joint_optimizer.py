from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.schematic_joint_optimizer import (
    SchematicJointRouteConfig,
    rank_schematic_placement_candidates_with_routes,
    score_schematic_placement_candidate_routes,
)
from diptrace_mcp.schematic_optimizer import generate_schematic_placement_candidates
from diptrace_mcp.schematic_pin_geometry import resolve_document_schematic_pin_geometry
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _document_with_embedded_library() -> DipTraceDocument:
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)
    library = DipTraceDocument.load(FIXTURES / "component_library.xml", MAX_BYTES)
    root = ET.fromstring(schematic.raw_bytes)
    existing = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert existing is not None
    index = list(root).index(existing)
    root.remove(existing)
    root.insert(index, ET.fromstring(library.raw_bytes))
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return DipTraceDocument.from_bytes(schematic.path, raw)


def _document_with_ground_net() -> DipTraceDocument:
    document = _document_with_embedded_library()
    root = ET.fromstring(document.raw_bytes)
    name = root.find("./Schematic/Nets/Net[@Id='0']/Name")
    assert name is not None
    name.text = "GND"
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return DipTraceDocument.from_bytes(document.path, raw)


def _candidates(document: DipTraceDocument):
    snapshot = build_snapshot(document)
    return generate_schematic_placement_candidates(snapshot)


def test_joint_route_score_uses_exact_pins_and_explicit_anchor_fallback() -> None:
    document = _document_with_embedded_library()
    candidates = _candidates(document)
    assert candidates

    score = score_schematic_placement_candidate_routes(document, candidates[0])

    assert score.metrics.routed_edge_count == 2
    assert score.metrics.exact_pin_endpoint_count == 2
    assert score.metrics.fallback_anchor_endpoint_count == 2
    assert {edge.net_name for edge in score.edges} == {"VCC", "SIGNAL"}
    assert any(
        source == "embedded_pin"
        for edge in score.edges
        for source in (edge.start_geometry_source, edge.end_geometry_source)
    )
    assert any(
        source == "fallback_part_anchor"
        for edge in score.edges
        for source in (edge.start_geometry_source, edge.end_geometry_source)
    )


def test_ground_net_wire_mst_is_opt_in() -> None:
    document = _document_with_ground_net()
    candidate = _candidates(document)[0]

    default_score = score_schematic_placement_candidate_routes(document, candidate)

    assert default_score.metrics.routed_edge_count == 1
    assert default_score.metrics.skipped_net_group_count == 1
    assert {edge.net_name for edge in default_score.edges} == {"SIGNAL"}
    assert any("ground/power routing policy" in warning for warning in default_score.warnings)

    included_score = score_schematic_placement_candidate_routes(
        document,
        candidate,
        config=SchematicJointRouteConfig(include_ground_nets=True),
    )

    assert included_score.metrics.routed_edge_count == 2
    assert included_score.metrics.skipped_net_group_count == 0
    assert {edge.net_name for edge in included_score.edges} == {"GND", "SIGNAL"}


def test_joint_route_scoring_does_not_mutate_document_or_normalized_snapshot() -> None:
    document = _document_with_embedded_library()
    before_raw = document.raw_bytes
    before_snapshot = build_snapshot(document)
    before_positions = {
        part.stable_id: dict(part.position or {})
        for part in before_snapshot.schematic.parts
    }
    candidate = _candidates(document)[0]
    before_placements = {
        part_id: dict(position) for part_id, position in candidate.placements.items()
    }

    score_schematic_placement_candidate_routes(document, candidate)

    after_snapshot = build_snapshot(document)
    after_positions = {
        part.stable_id: dict(part.position or {})
        for part in after_snapshot.schematic.parts
    }
    assert document.raw_bytes == before_raw
    assert after_positions == before_positions
    assert candidate.placements == before_placements


def test_joint_route_score_is_deterministic_for_fixed_candidate() -> None:
    document = _document_with_embedded_library()
    candidate = _candidates(document)[0]
    geometry = resolve_document_schematic_pin_geometry(document)

    first = score_schematic_placement_candidate_routes(
        document,
        candidate,
        pin_geometry=geometry,
    )
    second = score_schematic_placement_candidate_routes(
        document,
        candidate,
        pin_geometry=geometry,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_joint_route_edge_budget_is_bounded_and_reported() -> None:
    document = _document_with_embedded_library()
    candidate = _candidates(document)[0]

    score = score_schematic_placement_candidate_routes(
        document,
        candidate,
        config=SchematicJointRouteConfig(max_edges=1),
    )

    assert score.metrics.routed_edge_count == 1
    assert any("max_edges=1" in warning for warning in score.warnings)


def test_real_route_length_responds_to_virtual_placement_distance() -> None:
    document = _document_with_embedded_library()
    snapshot = build_snapshot(document)
    base = _candidates(document)[0]
    r1 = next(part for part in snapshot.schematic.parts if part.refdes == "R1")
    u1_parts = sorted(
        (part for part in snapshot.schematic.parts if part.refdes == "U1"),
        key=lambda part: part.stable_id,
    )

    near = base.model_copy(deep=True)
    near.candidate_id = "near"
    near.placements[r1.stable_id] = {"x": 10.0, "y": 20.0}
    near.placements[u1_parts[0].stable_id] = {"x": 18.0, "y": 20.0}
    near.placements[u1_parts[1].stable_id] = {"x": 18.0, "y": 30.0}

    far = base.model_copy(deep=True)
    far.candidate_id = "far"
    far.placements[r1.stable_id] = {"x": 10.0, "y": 20.0}
    far.placements[u1_parts[0].stable_id] = {"x": 100.0, "y": 20.0}
    far.placements[u1_parts[1].stable_id] = {"x": 100.0, "y": 50.0}

    near_score = score_schematic_placement_candidate_routes(document, near)
    far_score = score_schematic_placement_candidate_routes(document, far)

    assert near_score.metrics.length_mm < far_score.metrics.length_mm


def test_candidate_ranking_is_stable_and_uses_joint_rank_key() -> None:
    document = _document_with_embedded_library()
    candidates = _candidates(document)[:3]
    assert len(candidates) >= 2

    first = rank_schematic_placement_candidates_with_routes(document, candidates)
    second = rank_schematic_placement_candidates_with_routes(document, candidates)

    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert first == sorted(
        first,
        key=lambda item: (tuple(item.joint_rank_key), item.candidate_id),
    )