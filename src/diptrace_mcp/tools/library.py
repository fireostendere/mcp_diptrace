"""Standalone and installed component/pattern libraries."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..pattern_recommendation import PatternRequirement
from ..server_inputs import (
    DipTraceFastMCP,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def scan_component_libraries(
        root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        """Find standalone DipTrace Component Library XML files inside allowed roots."""
        return service.scan_component_libraries(root, recursive)

    @mcp.tool()
    def scan_pattern_libraries(
        root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        """Find standalone DipTrace Pattern Library XML files inside allowed roots."""
        return service.scan_pattern_libraries(root, recursive)

    @mcp.tool()
    def query_builtin_library_catalog(
        diptrace_root: str | None = None,
        kind: Literal["component", "pattern", "library"] = "component",
        query: str | None = None,
        offset: int = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        """Browse or search the installed DipTrace catalog without modifying native libraries."""
        return service.query_builtin_library_catalog(
            diptrace_root, kind, query, offset, limit
        )

    @mcp.tool()
    def query_library_items(
        path: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Query normalized components or patterns in a standalone library."""
        return service.query_library_items(path, query, offset, limit)

    @mcp.tool()
    def get_library_component(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Get one normalized component-library item by stable id or exact name."""
        return service.get_library_component(path, stable_id, name)

    @mcp.tool()
    def get_library_pattern(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Get one normalized pattern-library item by stable id or exact name."""
        return service.get_library_pattern(path, stable_id, name)

    @mcp.tool()
    def validate_library_component(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Validate component pins, attached pattern and pin-to-pad mapping."""
        return service.validate_library_component(path, stable_id, name)

    @mcp.tool()
    def validate_library_pattern(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Validate pattern pad numbering, styles, geometry, holes and annular rings."""
        return service.validate_library_pattern(path, stable_id, name)

    @mcp.tool()
    def recommend_patterns(
        requirement: PatternRequirement,
        path: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Rank compatible footprint patterns from a pattern library deterministically."""
        return service.recommend_patterns(requirement, path, limit=limit)
