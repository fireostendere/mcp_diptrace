from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.geometry import BBox
from diptrace_mcp.operations import SetComponentValueOperation
from diptrace_mcp.placement import PlacementConfig, generate_placement_candidates
from diptrace_mcp.preview import render_preview_svg
from diptrace_mcp.review import run_checks
from diptrace_mcp.routing import RouteConnectionConfig, synthesize_route
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.spatial import SpatialIndex
from diptrace_mcp.xml_document import DipTraceDocument


def _measure(function: Callable[[], Any], repeat: int) -> dict[str, float]:
    samples: list[float] = []
    for _ in range(repeat):
        started = time.perf_counter()
        function()
        samples.append((time.perf_counter() - started) * 1_000.0)
    return {
        "minimum_ms": min(samples),
        "median_ms": statistics.median(samples),
        "maximum_ms": max(samples),
    }


def run(fixture: Path, repeat: int, patch_count: int) -> dict[str, object]:
    max_bytes = max(fixture.stat().st_size + 1, 10_000_000)
    document = DipTraceDocument.load(fixture, max_bytes)
    snapshot = build_snapshot(document)
    records = list(snapshot.objects.values())
    region = BBox(0.0, 0.0, 25.0, 25.0)
    selector = QuerySelector(refdes=["R1"])
    placement = PlacementConfig(
        selector=selector,
        search_steps=4,
        max_candidates_per_component=64,
        time_budget_ms=1_000,
    )
    if snapshot.board is None or not snapshot.board.ratlines:
        raise ValueError("The route benchmark requires a PCB fixture with one ratline")
    ratline = snapshot.board.ratlines[0]
    endpoints = ratline["endpoints"]
    start_id = endpoints[0]["pad_id"]
    end_id = endpoints[1]["pad_id"]
    if not isinstance(start_id, str) or not isinstance(end_id, str):
        raise ValueError("Ratline endpoint stable ids are unavailable")
    net_id = snapshot.get_object(start_id).relationships["net"][0]
    route = RouteConnectionConfig(
        net=net_id,
        start_object_id=start_id,
        end_object_id=end_id,
        layer="Top",
        width=0.25,
        clearance=0.2,
        grid=0.5,
    )
    operations = [
        SetComponentValueOperation(
            selector=selector,
            value="10k" if index % 2 == 0 else "10k ",
        )
        for index in range(patch_count)
    ]
    benchmarks = {
        "parse_and_normalize": _measure(
            lambda: build_snapshot(DipTraceDocument.load(fixture, max_bytes)), repeat
        ),
        "build_spatial_index": _measure(lambda: SpatialIndex.build(records), repeat),
        "bbox_query": _measure(
            lambda: SpatialIndex.build(records).query(region), repeat
        ),
        "clearance_review": _measure(
            lambda: run_checks(snapshot, categories={"clearance"}), repeat
        ),
        "placement_candidates": _measure(
            lambda: generate_placement_candidates(snapshot, placement), repeat
        ),
        "route_one_net": _measure(lambda: synthesize_route(snapshot, route), repeat),
        "render_svg": _measure(
            lambda: render_preview_svg(snapshot, snapshot, []), repeat
        ),
        "semantic_patches": _measure(
            lambda: apply_semantic_operations(document, operations), 1
        ),
    }
    return {
        "fixture": str(fixture),
        "fixture_bytes": fixture.stat().st_size,
        "object_count": len(records),
        "repeat": repeat,
        "semantic_patch_count": patch_count,
        "benchmarks": benchmarks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic DipTrace MCP core benchmarks")
    parser.add_argument(
        "fixture",
        nargs="?",
        type=Path,
        default=Path("tests/fixtures/pcb.xml"),
    )
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--patch-count", type=int, default=1_000)
    args = parser.parse_args()
    if args.repeat < 1 or not 1 <= args.patch_count <= 10_000:
        parser.error("repeat must be positive and patch-count must be between 1 and 10000")
    print(json.dumps(run(args.fixture, args.repeat, args.patch_count), indent=2))


if __name__ == "__main__":
    main()
