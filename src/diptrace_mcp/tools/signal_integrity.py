"""Stackup, lengths, differential pairs, impedance and return-path analysis."""
from __future__ import annotations

from typing import Any, Literal

from ..server_inputs import (
    DipTraceFastMCP,
    ImpedanceConstraintInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def get_stackup(path: str | None = None) -> dict[str, Any]:
        """Return the normalized physical layer stack without inventing missing Dk values."""
        return service.get_stackup(path)

    @mcp.tool()
    def measure_net_lengths(
        path: str | None = None,
        nets: list[str] | None = None,
        effective_dielectric_constant: float | None = None,
    ) -> dict[str, Any]:
        """Measure geometric centerline lengths and optional preliminary delay."""
        return service.measure_net_lengths(
            path,
            nets=nets,
            effective_dielectric_constant=effective_dielectric_constant,
        )

    @mcp.tool()
    def analyze_length_group(
        nets: list[str],
        tolerance_mm: float | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Compare routed geometric lengths for an explicit group of nets."""
        return service.analyze_length_group(nets, tolerance_mm=tolerance_mm, path=path)

    @mcp.tool()
    def list_differential_pairs(
        path: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List normalized DipTrace project differential pairs and their rules."""
        return service.list_differential_pairs(path, offset=offset, limit=limit)

    @mcp.tool()
    def get_differential_pair(pair: str, path: str | None = None) -> dict[str, Any]:
        """Get one differential pair by stable id, XML id or exact name."""
        return service.get_differential_pair(pair, path)

    @mcp.tool()
    def analyze_differential_pair(
        pair: str, path: str | None = None
    ) -> dict[str, Any]:
        """Measure pair lengths, skew, via balance, coupled length and edge gap."""
        return service.analyze_differential_pair(pair, path)

    @mcp.tool()
    def analyze_differential_pairs(path: str | None = None) -> dict[str, Any]:
        """Analyze all normalized project differential pairs."""
        return service.analyze_differential_pairs(path)

    @mcp.tool()
    def validate_differential_pair(
        pair: str, path: str | None = None
    ) -> dict[str, Any]:
        """Evaluate available exported rules for one differential pair."""
        return service.validate_differential_pair(pair, path)

    @mcp.tool()
    def calculate_impedance(
        structure: Literal[
            "microstrip", "differential_microstrip", "symmetric_stripline"
        ],
        width_mm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        gap_mm: float | None = None,
        frequency_hz: float | None = None,
        target_ohm: float | None = None,
        tolerance_ohm: float | None = None,
    ) -> dict[str, Any]:
        """Calculate a preliminary analytical impedance with explicit assumptions."""
        return service.calculate_impedance(
            structure=structure,
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            gap_mm=gap_mm,
            frequency_hz=frequency_hz,
            target_ohm=target_ohm,
            tolerance_ohm=tolerance_ohm,
        )

    @mcp.tool()
    def suggest_trace_geometry_for_impedance(
        target_ohm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        minimum_width_mm: float,
        maximum_width_mm: float,
        tolerance_ohm: float = 0.01,
    ) -> dict[str, Any]:
        """Synthesize a bounded microstrip width using the analytical model."""
        return service.suggest_trace_geometry_for_impedance(
            target_ohm=target_ohm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            minimum_width_mm=minimum_width_mm,
            maximum_width_mm=maximum_width_mm,
            tolerance_ohm=tolerance_ohm,
        )

    @mcp.tool()
    def analyze_stackup_for_impedance(path: str | None = None) -> dict[str, Any]:
        """Find only complete outer-layer microstrip geometries in the physical stackup."""
        return service.analyze_stackup_for_impedance(path)

    @mcp.tool()
    def validate_impedance_constraints(
        constraints: list[ImpedanceConstraintInput],
        path: str | None = None,
    ) -> dict[str, Any]:
        """Validate explicit net/layer/target constraints against routed widths and stackup."""
        return service.validate_impedance_constraints(
            [constraint.model_dump() for constraint in constraints],
            path=path,
        )

    @mcp.tool()
    def analyze_plane_continuity(path: str | None = None) -> dict[str, Any]:
        """Inspect exported pour boundaries without claiming final-refill continuity."""
        return service.analyze_plane_continuity(path)

    @mcp.tool()
    def analyze_return_path(
        stitching_radius_mm: float,
        path: str | None = None,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run low-confidence geometry heuristics with a caller-supplied radius."""
        return service.analyze_return_path(
            path,
            stitching_radius_mm=stitching_radius_mm,
            nets=nets,
            reference_nets=reference_nets,
        )
