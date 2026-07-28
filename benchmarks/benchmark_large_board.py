from __future__ import annotations

import argparse
import gc
import json
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from benchmarks.synthetic_board import (
    MIN_COMPONENTS,
    add_component_count_argument,
    generate_synthetic_pcb,
)
from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QueryRequest, QuerySelector
from diptrace_mcp.geometry import BBox
from diptrace_mcp.model_cache import ModelCache
from diptrace_mcp.spatial import SpatialIndex
from diptrace_mcp.xml_document import DipTraceDocument

_ResultT = TypeVar("_ResultT")


def _measure(operation: Callable[[], _ResultT]) -> tuple[_ResultT, dict[str, float | int]]:
    gc.collect()
    tracing_before_measurement = tracemalloc.is_tracing()
    if tracing_before_measurement:
        tracemalloc.reset_peak()
    else:
        tracemalloc.start()
    baseline_traced_bytes, _baseline_peak_bytes = tracemalloc.get_traced_memory()
    started = time.perf_counter()
    try:
        result = operation()
        elapsed_seconds = time.perf_counter() - started
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        if not tracing_before_measurement:
            tracemalloc.stop()
    return result, {
        "elapsed_seconds": elapsed_seconds,
        "peak_traced_bytes": max(0, peak_bytes - baseline_traced_bytes),
    }


def run_large_board_benchmark(component_count: int = MIN_COMPONENTS) -> dict[str, object]:
    """Exercise public parse/model/cache/query paths on a generated synthetic PCB."""

    raw = generate_synthetic_pcb(component_count)
    source_path = Path(f"synthetic-load-{component_count}.xml")
    document, parse_sample = _measure(
        lambda: DipTraceDocument.from_bytes(source_path, raw)
    )
    snapshot, model_sample = _measure(lambda: build_snapshot(document))

    cache = ModelCache(max_entries=2, max_bytes=256 * 1024 * 1024)
    cached_snapshot, cache_miss_sample = _measure(
        lambda: cache.get(document, live_session=False)
    )
    cache_hit, cache_hit_sample = _measure(
        lambda: cache.get(document, live_session=False)
    )
    if cache_hit is not cached_snapshot:
        raise RuntimeError("ModelCache did not return the retained snapshot on a cache hit")

    query, model_query_sample = _measure(
        lambda: snapshot.query(
            QueryRequest(
                selector=QuerySelector(
                    kinds=["component"],
                    refdes_glob="C*",
                ),
                limit=500,
                sort_by="refdes",
            )
        )
    )
    spatial_index, spatial_build_sample = _measure(
        lambda: SpatialIndex.build(snapshot.objects.values())
    )
    spatial_items, spatial_query_sample = _measure(
        lambda: spatial_index.query(
            BBox(0.0, 0.0, 20.0, 20.0),
            kinds={"component"},
        )
    )
    normalized_components = (
        len(snapshot.board.components) if snapshot.board is not None else 0
    )
    if normalized_components != component_count or query.total != component_count:
        raise RuntimeError(
            "Synthetic large-board normalization/query count mismatch: "
            f"expected={component_count}, model={normalized_components}, query={query.total}"
        )
    return {
        "classification": "synthetic_parser_only",
        "component_count": component_count,
        "payload_bytes": len(raw),
        "object_count": len(snapshot.objects),
        "query_total": query.total,
        "query_returned": len(query.items),
        "spatial_query_returned": len(spatial_items),
        "cache": cache.stats(),
        "stages": {
            "parse": parse_sample,
            "build_snapshot": model_sample,
            "cache_miss": cache_miss_sample,
            "cache_hit": cache_hit_sample,
            "model_query": model_query_sample,
            "spatial_index_build": spatial_build_sample,
            "spatial_query": spatial_query_sample,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark public parser/model/cache/query paths on an in-memory synthetic PCB"
        )
    )
    add_component_count_argument(parser)
    args = parser.parse_args()
    print(json.dumps(run_large_board_benchmark(args.components), indent=2))


if __name__ == "__main__":
    main()
