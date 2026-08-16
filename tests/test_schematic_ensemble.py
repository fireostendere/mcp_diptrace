from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.schematic_ensemble import (
    SchematicCongestionConfig,
    analyze_schematic_candidate_congestion,
    infer_builtin_schematic_motifs,
    rank_schematic_ensemble,
)
from diptrace_mcp.schematic_layout import infer_schematic_design_intent
from diptrace_mcp.schematic_optimizer import generate_schematic_placement_candidates
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 10_000_000


def _document() -> DipTraceDocument:
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", MAX_BYTES)
    library = DipTraceDocument.load(FIXTURES / "component_library.xml", MAX_BYTES)
    root = ET.fromstring(schematic.raw_bytes)
    existing = root.find("./Library[@Type='DipTrace-ComponentLibrary']")
    assert existing is not None
    index = list(root).index(existing)
    root.remove(existing)
    root.insert(index, ET.fromstring(library.raw_bytes))
    return DipTraceDocument.from_bytes(
        schematic.path,
        ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


def test_builtin_motifs_are_deterministic_and_explicitly_builtin() -> None:
    snapshot = build_snapshot(_document())
    intent = infer_schematic_design_intent(snapshot)

    first = infer_builtin_schematic_motifs(snapshot, intent)
    second = infer_builtin_schematic_motifs(snapshot, intent)

    assert first == second
    assert all(item.motif.source_kind == "builtin" for item in first)
    assert all("heuristic" in item.motif.source.lower() for item in first)


def test_congestion_penalizes_collapsed_candidate() -> None:
    document = _document()
    snapshot = build_snapshot(document)
    candidate = generate_schematic_placement_candidates(snapshot)[0]
    spread = analyze_schematic_candidate_congestion(
        candidate,
        SchematicCongestionConfig(cell_size_mm=10.0, hotspot_occupancy=2),
    )

    collapsed = candidate.model_copy(deep=True)
    for part_id in collapsed.placements:
        collapsed.placements[part_id] = {"x": 20.0, "y": 20.0}
    crowded = analyze_schematic_candidate_congestion(
        collapsed,
        SchematicCongestionConfig(cell_size_mm=10.0, hotspot_occupancy=2),
    )

    assert crowded.hotspot_cell_count >= 1
    assert crowded.max_cell_occupancy > spread.max_cell_occupancy
    assert crowded.penalty > spread.penalty


def test_schematic_ensemble_is_bounded_deterministic_and_route_first() -> None:
    document = _document()

    first = rank_schematic_ensemble(document)
    second = rank_schematic_ensemble(document)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.candidates
    assert first.selected == first.candidates[0]
    assert len(first.selected.rank_key) == 12
    assert first.candidates == sorted(
        first.candidates,
        key=lambda item: (tuple(item.rank_key), item.candidate.candidate_id),
    )
    assert first.interconnect_plan.scheduled_nets
    assert all(item.objective_history for item in first.candidates)
    assert all(item.objective_history[-1] == item.rank_key for item in first.candidates)
