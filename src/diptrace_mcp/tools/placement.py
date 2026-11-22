"""PCB placement analysis, candidates and plans."""
from __future__ import annotations

from typing import Any, Literal

from ..placement import PlacementProposal
from ..reference_rules import EngineeringRulePack
from ..server_inputs import (
    DipTraceFastMCP,
    SelectorInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def analyze_placement(
        path: str | None = None,
        selector: SelectorInput | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
    ) -> dict[str, Any]:
        """Measure current component overlap, containment and placement score."""
        return service.analyze_placement(
            path,
            selector=selector,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
        )

    @mcp.tool()
    def generate_placement_candidates(
        selector: SelectorInput,
        path: str | None = None,
        region: dict[str, float] | None = None,
        allowed_sides: list[Literal["Top", "Bottom"]] | None = None,
        allowed_rotations: list[float] | None = None,
        grid: float = 0.5,
        search_steps: int = 8,
        max_candidates_per_component: int = 256,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        deterministic_seed: int = 0,
        time_budget_ms: int = 5_000,
        respect_keepouts: bool = True,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Generate bounded deterministic local placement candidates."""
        return service.generate_placement_candidates(
            selector,
            path,
            region=region,
            allowed_sides=allowed_sides or [],
            allowed_rotations=allowed_rotations or [],
            grid=grid,
            search_steps=search_steps,
            max_candidates_per_component=max_candidates_per_component,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            deterministic_seed=deterministic_seed,
            time_budget_ms=time_budget_ms,
            respect_keepouts=respect_keepouts,
            weights=weights or {},
        )

    @mcp.tool()
    def score_placement(
        placements: list[PlacementProposal],
        path: str | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Score an explicit component placement proposal without editing XML."""
        return service.score_placement(
            [placement.model_dump() for placement in placements],
            path,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=weights,
        )

    @mcp.tool()
    def plan_component_placement(
        selector: SelectorInput,
        path: str | None = None,
        region: dict[str, float] | None = None,
        allowed_sides: list[Literal["Top", "Bottom"]] | None = None,
        allowed_rotations: list[float] | None = None,
        grid: float = 0.5,
        search_steps: int = 8,
        max_candidates_per_component: int = 256,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        deterministic_seed: int = 0,
        time_budget_ms: int = 5_000,
        respect_keepouts: bool = True,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Create a validated deterministic local component-placement plan."""
        return service.plan_component_placement(
            selector,
            path,
            region=region,
            allowed_sides=allowed_sides or [],
            allowed_rotations=allowed_rotations or [],
            grid=grid,
            search_steps=search_steps,
            max_candidates_per_component=max_candidates_per_component,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            deterministic_seed=deterministic_seed,
            time_budget_ms=time_budget_ms,
            respect_keepouts=respect_keepouts,
            weights=weights or {},
        )

    @mcp.tool()
    def compare_pcb_placement_candidates(
        path: str | None = None,
        profiles: list[
            Literal["balanced", "critical_nets", "noise_aware", "support_compact"]
        ]
        | None = None,
        include_existing_board: bool = True,
        engineering_rules: EngineeringRulePack | None = None,
    ) -> dict[str, Any]:
        """Rank PCB A-D candidates with physics and optional sourced rules."""
        return service.compare_pcb_placement_candidates(
            path,
            profiles=profiles,
            include_existing_board=include_existing_board,
            engineering_rules=engineering_rules,
        )
