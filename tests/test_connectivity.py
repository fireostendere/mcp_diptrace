from pathlib import Path

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.connectivity import build_connectivity_graph
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_pcb_graph_separates_logical_connectivity_from_ratlines() -> None:
    snapshot = build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))

    graph = build_connectivity_graph(snapshot)

    assert graph.source_kind == "pcb"
    assert len(graph.nets) == 2
    assert len(graph.connected_components) == 1
    assert len(graph.unrouted_connections) == 1
    assert graph.unrouted_connections[0]["ambiguous_net"] is False
    assert len(graph.endpoint_mapping) == 4


def test_schematic_graph_has_no_synthetic_physical_unrouted_edges() -> None:
    snapshot = build_snapshot(
        DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    )

    graph = build_connectivity_graph(snapshot)

    assert graph.source_kind == "schematic"
    assert graph.unrouted_connections == []
    assert len(graph.connected_components) == 1
