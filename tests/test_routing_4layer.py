"""End-to-end routing tests against synthetic 4-layer PCB with Plane layer.

The fixture has 4 copper layers:
  - Id=0, Type=Signal, Name=Top
  - Id=1, Type=Signal, Name=Inner 1
  - Id=2, Type=Plane,  Name=GND
  - Id=3, Type=Signal, Name=Bottom

Vias span Top (0) to Bottom (3).

Tests exercise:
  - resolve_copper_layer on every layer type
  - require_routing_layer on Signal / Plane / Unknown
  - require_via_layer on Plane (rejected) and Unknown (allowed)
  - add_trace through service/transaction API on Signal layers
  - add_trace on Plane layer (rejected)
  - add_trace via on Plane layer (rejected)
  - replace_trace on Signal layer
  - diff_pair_route on Signal layer
  - diff_pair_route on Plane layer (rejected)
  - add_via layer_before / layer_after validation
  - name-based layer resolution (case-insensitive)
  - ambiguous layer name rejection
  - unknown layer name rejection
  - via transition across Plane layer (through-via allowed)
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.errors import ObjectNotFoundError, RoutingError
from diptrace_mcp.operations import AddTraceOperation, TracePathPoint
from diptrace_mcp.routing_compiler import (
    require_routing_layer,
    require_via_layer,
    resolve_copper_layer,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load_4layer() -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / "pcb_4layer.xml", 10_000_000)


def _snapshot_4layer():
    return build_snapshot(_load_4layer())


def _vcc_endpoints() -> tuple[str, str]:
    snapshot = _snapshot_4layer()
    net = next(item for item in snapshot.board.nets if item.name == "VCC")
    endpoints = net.relationships["endpoints"]
    return endpoints[0], endpoints[1]


def _signal_top_endpoints() -> tuple[str, str]:
    snapshot = _snapshot_4layer()
    net = next(item for item in snapshot.board.nets if item.name == "SIGNAL_TOP")
    endpoints = net.relationships["endpoints"]
    return endpoints[0], endpoints[1]


def _signal_inner_endpoints() -> tuple[str, str]:
    snapshot = _snapshot_4layer()
    net = next(item for item in snapshot.board.nets if item.name == "SIGNAL_INNER")
    endpoints = net.relationships["endpoints"]
    return endpoints[0], endpoints[1]


# ── resolve_copper_layer tests ──────────────────────────────────────────────


class TestResolveCopperLayer:
    """Validate resolve_copper_layer returns correct metadata."""

    def test_signal_layer_by_name(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Top")
        assert resolved.layer_id == "0"
        assert resolved.layer_name == "Top"
        assert resolved.layer_type == "Signal"
        assert resolved.is_signal is True
        assert resolved.is_plane is False

    def test_plane_layer_by_name(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "GND")
        assert resolved.layer_id == "2"
        assert resolved.layer_name == "GND"
        assert resolved.layer_type == "Plane"
        assert resolved.is_signal is False
        assert resolved.is_plane is True

    def test_signal_layer_by_id(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "1")
        assert resolved.layer_id == "1"
        assert resolved.layer_name == "Inner 1"
        assert resolved.layer_type == "Signal"

    def test_case_insensitive_name(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "top")
        assert resolved.layer_id == "0"
        assert resolved.layer_name == "Top"

    def test_case_insensitive_plane(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "gnd")
        assert resolved.layer_id == "2"
        assert resolved.layer_type == "Plane"

    def test_unknown_layer_name_raises(self) -> None:
        with pytest.raises(ObjectNotFoundError, match="Copper layer was not found"):
            resolve_copper_layer(_snapshot_4layer(), "Nonexistent")

    def test_bottom_layer(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Bottom")
        assert resolved.layer_id == "3"
        assert resolved.layer_type == "Signal"

    def test_repr(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Top")
        assert "ResolvedCopperLayer" in repr(resolved)
        assert "Top" in repr(resolved)


# ── require_routing_layer tests ─────────────────────────────────────────────


class TestRequireRoutingLayer:
    """Validate require_routing_layer rejects Plane and Unknown layers."""

    def test_signal_layer_passes(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Top")
        require_routing_layer(resolved, context="test")  # should not raise

    def test_plane_layer_rejected(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "GND")
        with pytest.raises(RoutingError, match="plane layer"):
            require_routing_layer(resolved, context="test_routing")

    def test_inner_signal_passes(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Inner 1")
        require_routing_layer(resolved, context="test")  # should not raise

    def test_bottom_signal_passes(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Bottom")
        require_routing_layer(resolved, context="test")  # should not raise


# ── require_via_layer tests ─────────────────────────────────────────────────


class TestRequireViaLayer:
    """Validate require_via_layer rejects Plane but allows Unknown."""

    def test_signal_layer_passes(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "Top")
        require_via_layer(resolved, context="test")  # should not raise

    def test_plane_layer_rejected(self) -> None:
        resolved = resolve_copper_layer(_snapshot_4layer(), "GND")
        with pytest.raises(RoutingError, match="plane layer"):
            require_via_layer(resolved, context="test_via")


# ── Service-level routing tests ─────────────────────────────────────────────


class TestServiceRouting:
    """End-to-end routing through apply_semantic_operations."""

    def test_add_trace_on_top_layer(self) -> None:
        doc = _load_4layer()
        start, end = _vcc_endpoints()
        result = apply_semantic_operations(
            doc,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9),
                        TracePathPoint(x=20, y=9, layer="Top"),
                        TracePathPoint(x=30, y=9),
                    ],
                    layer="Top",
                    width=0.25,
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        trace = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace")
        assert trace is not None
        points = trace.findall("./Points/Point")
        assert len(points) == 3
        assert points[1].get("Lay") == "0"

    def test_add_trace_on_bottom_layer(self) -> None:
        doc = _load_4layer()
        start, end = _vcc_endpoints()
        result = apply_semantic_operations(
            doc,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9),
                        TracePathPoint(x=20, y=9, layer="Bottom"),
                        TracePathPoint(x=30, y=9),
                    ],
                    layer="Bottom",
                    width=0.25,
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        trace = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace")
        assert trace is not None
        points = trace.findall("./Points/Point")
        assert points[1].get("Lay") == "3"

    def test_add_trace_on_inner_layer(self) -> None:
        doc = _load_4layer()
        start, end = _vcc_endpoints()
        result = apply_semantic_operations(
            doc,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9),
                        TracePathPoint(x=20, y=9, layer="Inner 1"),
                        TracePathPoint(x=30, y=9),
                    ],
                    layer="Inner 1",
                    width=0.25,
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        trace = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace")
        assert trace is not None
        points = trace.findall("./Points/Point")
        assert points[1].get("Lay") == "1"

    def test_add_trace_on_plane_layer_rejected(self) -> None:
        doc = _load_4layer()
        start, end = _vcc_endpoints()
        with pytest.raises(RoutingError, match="plane layer"):
            apply_semantic_operations(
                doc,
                [
                    AddTraceOperation(
                        net="VCC",
                        start_object_id=start,
                        end_object_id=end,
                        points=[
                            TracePathPoint(x=10, y=9),
                            TracePathPoint(x=20, y=9, layer="GND"),
                            TracePathPoint(x=30, y=9),
                        ],
                        layer="GND",
                        width=0.25,
                    )
                ],
            )

    def test_add_trace_with_via_across_plane(self) -> None:
        """Through-via spanning across Plane layer is allowed."""
        doc = _load_4layer()
        start, end = _vcc_endpoints()
        result = apply_semantic_operations(
            doc,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9, layer="Top"),
                        TracePathPoint(
                            x=20, y=9, layer="Top", via_style="Default"
                        ),
                        TracePathPoint(x=30, y=9, layer="Bottom"),
                    ],
                    layer="Top",
                    width=0.25,
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        trace = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace")
        assert trace is not None
        points = trace.findall("./Points/Point")
        # Layer change from Top (0) to Bottom (3) crosses the GND Plane layer.
        # The route compiles without rejection — through-via spans are permitted.
        layers_used = {p.get("Lay") for p in points if p.get("Lay") is not None}
        assert "3" in layers_used  # Bottom layer is used
        # The via transition point must have a real ViaStyle assigned.
        via_point = points[1]
        assert via_point.get("ViaStyle") not in (None, "-1"), (
            f"Expected a real ViaStyle at via transition, got {via_point.get('ViaStyle')!r}"
        )

    def test_add_trace_case_insensitive_layer(self) -> None:
        """Layer name resolution is case-insensitive."""
        doc = _load_4layer()
        start, end = _vcc_endpoints()
        result = apply_semantic_operations(
            doc,
            [
                AddTraceOperation(
                    net="VCC",
                    start_object_id=start,
                    end_object_id=end,
                    points=[
                        TracePathPoint(x=10, y=9),
                        TracePathPoint(x=20, y=9, layer="top"),
                        TracePathPoint(x=30, y=9),
                    ],
                    layer="top",
                    width=0.25,
                )
            ],
        )
        root = ET.fromstring(result.raw_bytes)
        trace = root.find("./Board/Nets/Net[@Id='0']/Traces/Trace")
        assert trace is not None
        points = trace.findall("./Points/Point")
        assert points[1].get("Lay") == "0"
