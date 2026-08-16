from __future__ import annotations

from types import SimpleNamespace

import pytest

from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.schematic_topology import (
    build_proven_schematic_topology,
    topology_junction_path,
)


def _pin(pin_id: str) -> SimpleNamespace:
    return SimpleNamespace(stable_id=pin_id)


def _resolved(pin_id: str, x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(pin_id=pin_id, absolute_position={"x": x, "y": y})


def test_multi_junction_tree_preserves_every_junction_in_path_order() -> None:
    wires = [
        SimpleNamespace(
            stable_id="trunk",
            attributes={
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 20.0, "y": 0.0},
                    {"x": 30.0, "y": 0.0},
                ]
            },
        ),
        SimpleNamespace(
            stable_id="branch-a",
            attributes={
                "points": [
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 10.0},
                ]
            },
        ),
        SimpleNamespace(
            stable_id="branch-b",
            attributes={
                "points": [
                    {"x": 20.0, "y": 0.0},
                    {"x": 20.0, "y": 10.0},
                ]
            },
        ),
    ]
    snapshot = SimpleNamespace(
        schematic=SimpleNamespace(
            wires=wires,
            pins=[_pin("left"), _pin("right"), _pin("a"), _pin("b")],
        )
    )
    resolution = SimpleNamespace(
        pins=[
            _resolved("left", 0.0, 0.0),
            _resolved("right", 30.0, 0.0),
            _resolved("a", 10.0, 10.0),
            _resolved("b", 20.0, 10.0),
        ]
    )

    topology = build_proven_schematic_topology(
        snapshot,
        ["trunk", "branch-a", "branch-b"],
        resolution,
    )

    assert topology is not None
    assert topology.edge_count == 5
    assert len(topology.junction_nodes) == 2
    path = topology_junction_path(topology, "left", "right")
    assert [(item.x, item.y) for item in path] == [
        (10.0, 0.0),
        (20.0, 0.0),
    ]


def test_branched_cycle_is_refused_instead_of_rewritten() -> None:
    wires = [
        SimpleNamespace(
            stable_id="box",
            attributes={
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 10.0},
                    {"x": 0.0, "y": 10.0},
                    {"x": 0.0, "y": 0.0},
                ]
            },
        ),
        SimpleNamespace(
            stable_id="branch",
            attributes={
                "points": [
                    {"x": 10.0, "y": 0.0},
                    {"x": 20.0, "y": 0.0},
                ]
            },
        ),
    ]
    snapshot = SimpleNamespace(
        schematic=SimpleNamespace(wires=wires, pins=[_pin("p")])
    )
    resolution = SimpleNamespace(pins=[_resolved("p", 20.0, 0.0)])

    with pytest.raises(CapabilityUnavailableError, match="cycle"):
        build_proven_schematic_topology(snapshot, ["box", "branch"], resolution)


def test_branched_topology_refuses_ambiguous_pin_ownership() -> None:
    wires = [
        SimpleNamespace(
            stable_id="trunk",
            attributes={
                "points": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 10.0, "y": 0.0},
                    {"x": 20.0, "y": 0.0},
                ]
            },
        ),
        SimpleNamespace(
            stable_id="branch",
            attributes={
                "points": [
                    {"x": 10.0, "y": 0.0},
                    {"x": 10.0, "y": 10.0},
                ]
            },
        ),
    ]
    snapshot = SimpleNamespace(
        schematic=SimpleNamespace(
            wires=wires,
            pins=[_pin("left-a"), _pin("left-b"), _pin("right"), _pin("branch")],
        )
    )
    resolution = SimpleNamespace(
        pins=[
            _resolved("left-a", 0.0, 0.0),
            _resolved("left-b", 0.0, 0.0),
            _resolved("right", 20.0, 0.0),
            _resolved("branch", 10.0, 10.0),
        ]
    )

    with pytest.raises(CapabilityUnavailableError, match="multiple pins"):
        build_proven_schematic_topology(
            snapshot,
            ["trunk", "branch"],
            resolution,
        )
