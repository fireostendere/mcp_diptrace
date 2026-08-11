from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.specctra_analysis import (
    analyze_ses_compatibility,
    analyze_specctra_structure,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot():
    return build_snapshot(DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000))


def _ses(*, net: str = "VCC", layer: str = "Top") -> bytes:
    return f"""(session "result.ses"
  (base_design "board.dsn")
  (routes
    (resolution mm 1000)
    (library_out)
    (network_out
      (net "{net}"
        (wire (path "{layer}" 250 10000 9000 20000 9000)))
    )
  )
)""".encode()


def test_specctra_structure_inventory_is_bounded_and_deterministic() -> None:
    first = analyze_specctra_structure(_ses(), expected_root="session")
    second = analyze_specctra_structure(_ses(), expected_root="session")

    assert first == second
    assert first.root_scope == "session"
    assert first.token_count > 0
    assert first.scope_histogram["net"] == 1
    assert first.max_depth > 1


def test_ses_compatibility_reports_route_statistics_and_importability() -> None:
    result = analyze_ses_compatibility(_snapshot(), _ses())

    assert result.routes.net_count == 1
    assert result.routes.wire_count == 1
    assert result.routes.segment_count == 1
    assert result.routes.total_length_mm == pytest.approx(10.0)
    assert result.routes.min_width_mm == pytest.approx(0.25)
    assert result.importable_nets == ["VCC"]
    assert result.skipped_nets == []
    assert result.unknown_board_nets == []
    assert result.unknown_board_layers == []


def test_ses_compatibility_surfaces_unknown_net_and_layer_without_mutation() -> None:
    result = analyze_ses_compatibility(
        _snapshot(),
        _ses(net="DOES_NOT_EXIST", layer="UnknownLayer"),
    )

    assert result.importable_nets == []
    assert result.unknown_board_nets == ["DOES_NOT_EXIST"]
    assert result.unknown_board_layers == ["UnknownLayer"]
    assert result.skipped_nets == [{"net": "DOES_NOT_EXIST", "reason": "net_not_found"}]
    assert result.warnings


def test_specctra_structure_refuses_wrong_root_and_unclosed_input() -> None:
    with pytest.raises(DocumentError, match="Expected Specctra root"):
        analyze_specctra_structure(b"(pcb board)", expected_root="session")
    with pytest.raises(DocumentError, match="Unclosed"):
        analyze_specctra_structure(b"(session bad")
