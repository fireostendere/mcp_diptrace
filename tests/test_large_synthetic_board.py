from __future__ import annotations

import argparse

import pytest

from benchmarks.benchmark_large_board import run_large_board_benchmark
from benchmarks.synthetic_board import (
    MAX_COMPONENTS,
    MIN_COMPONENTS,
    add_component_count_argument,
    generate_synthetic_pcb,
    parse_component_count,
)

CI_TOTAL_TIME_BUDGET_SECONDS = 30.0
CI_STAGE_PEAK_TRACED_BYTES = 128 * 1024 * 1024


def test_synthetic_large_board_generator_is_deterministic_and_bounded() -> None:
    first = generate_synthetic_pcb(MIN_COMPONENTS)
    second = generate_synthetic_pcb(MIN_COMPONENTS)

    assert first == second
    assert first.count(b"<Component ") == MIN_COMPONENTS
    assert b"not a DipTrace export" in first
    assert generate_synthetic_pcb(MAX_COMPONENTS).count(b"<Component ") == MAX_COMPONENTS
    with pytest.raises(ValueError, match="between 500 and 3000"):
        generate_synthetic_pcb(MIN_COMPONENTS - 1)
    with pytest.raises(ValueError, match="between 500 and 3000"):
        generate_synthetic_pcb(MAX_COMPONENTS + 1)


def test_component_count_cli_argument_has_compact_bounded_help() -> None:
    parser = argparse.ArgumentParser()
    add_component_count_argument(parser)

    assert parse_component_count("500") == MIN_COMPONENTS
    assert parse_component_count("3000") == MAX_COMPONENTS
    with pytest.raises(argparse.ArgumentTypeError, match="between 500 and 3000"):
        parse_component_count("499")
    with pytest.raises(argparse.ArgumentTypeError, match="must be an integer"):
        parse_component_count("many")
    help_text = parser.format_help()
    assert "500..3000" in help_text
    assert "{500,501" not in help_text
    assert len(help_text) < 1_000


def test_500_component_public_paths_stay_within_ci_load_budgets() -> None:
    report = run_large_board_benchmark(MIN_COMPONENTS)
    stages = report["stages"]

    assert report["classification"] == "synthetic_parser_only"
    assert report["component_count"] == MIN_COMPONENTS
    assert report["object_count"] == MIN_COMPONENTS * 3
    assert report["query_total"] == MIN_COMPONENTS
    assert report["query_returned"] == MIN_COMPONENTS
    assert report["spatial_query_returned"] > 0
    assert report["cache"]["entry_count"] == 1
    assert report["cache"]["accounted_bytes"] <= report["cache"]["max_bytes"]
    assert (
        sum(sample["elapsed_seconds"] for sample in stages.values())
        <= CI_TOTAL_TIME_BUDGET_SECONDS
    )
    assert all(
        sample["peak_traced_bytes"] <= CI_STAGE_PEAK_TRACED_BYTES
        for sample in stages.values()
    )
