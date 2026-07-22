from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.review import run_checks
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURE = Path(__file__).parent / "fixtures" / "diptrace_5_3" / "power_multilayer"


def _document() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURE / "source_board.xml", 10_000_000)


def test_power_multilayer_source_identity_and_structure() -> None:
    expected = json.loads((FIXTURE / "expected_summary.json").read_text())
    raw = (FIXTURE / "source_board.xml").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected["source"]["sha256"]

    snapshot = build_snapshot(_document())
    assert snapshot.board is not None
    assert snapshot.board.outline["bbox"] == {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": 70.0,
        "max_y": 50.0,
    }
    assert [layer["name"] for layer in snapshot.board.layers] == [
        "Top",
        "Inner 1",
        "Inner 2",
        "Bottom",
    ]
    assert {net.name for net in snapshot.board.nets} == {
        "VIN_RAW",
        "VIN_PROTECTED",
        "VOUT",
        "GND",
        "SENSE",
        "SIGNAL_A",
        "SIGNAL_B",
    }
    assert len(snapshot.board.traces) == 13
    assert len(snapshot.board.vias) == 2
    assert len(snapshot.board.ratlines) == 11
    assert [
        item["attributes"]["Id"] for item in snapshot.board.ratlines
    ] == [str(index) for index in range(11)]


def test_power_multilayer_signal_routes_and_via_spans() -> None:
    snapshot = build_snapshot(_document())
    assert snapshot.board is not None
    signal_a = next(net for net in snapshot.board.nets if net.name == "SIGNAL_A")
    signal_b = next(net for net in snapshot.board.nets if net.name == "SIGNAL_B")
    traces_a = [trace for trace in snapshot.board.traces if trace.net_name == "SIGNAL_A"]
    traces_b = [trace for trace in snapshot.board.traces if trace.net_name == "SIGNAL_B"]

    assert signal_a.attributes["trace_count"] == 1
    assert signal_b.attributes["trace_count"] == 1
    assert traces_a[0].attributes["length_mm"] == pytest.approx(23.27)
    assert traces_b[0].attributes["length_mm"] == pytest.approx(23.27)
    assert traces_a[0].attributes["segment_layers"] == ["0", "0", "0"]
    assert traces_b[0].attributes["segment_layers"] == ["0", "0", "3", "0", "0"]
    assert all(via.net_name == "SIGNAL_B" for via in snapshot.board.vias)
    assert all(
        via.attributes["span_layer_ids"] == ["0", "1", "2", "3"]
        for via in snapshot.board.vias
    )


def test_power_multilayer_expected_offline_drc_contract() -> None:
    findings, _metrics, skipped, _check_count = run_checks(
        build_snapshot(_document()),
        categories={"placement", "connectivity", "clearance"},
    )
    errors = [finding for finding in findings if finding.severity == "error"]
    assert skipped == []
    assert [(finding.check_id, finding.net_ids) for finding in errors] == [
        ("pcb.unrouted_net", ["net_88cfb1fd0bfebd02"])
    ]
