"""Offline review profiles, findings, silkscreen plans and the quality gate."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..server_inputs import (
    DipTraceFastMCP,
    SelectorInput,
)
from ..service import DipTraceService

ReviewProfile = Literal[
    "board_review",
    "schematic_review",
    "schematic_readability",
    "drc_basic",
    "erc_basic",
    "connectivity",
    "component_clearance",
    "silkscreen",
    "manufacturing_geometry",
    "dfm_basic",
    "dfa_basic",
    "dft_basic",
    "bom_basic",
    "thermal_basic",
]
# None runs every registered check for the document kind.
_REVIEW_PROFILE_CATEGORIES: dict[str, set[str] | None] = {
    "board_review": None,
    "schematic_review": None,
    "schematic_readability": {"readability"},
    "drc_basic": {"placement", "connectivity", "clearance"},
    "erc_basic": {"connectivity", "metadata"},
    "connectivity": {"connectivity"},
    "component_clearance": {"placement"},
    "silkscreen": {"silkscreen"},
    "manufacturing_geometry": {"manufacturing"},
    "dfm_basic": {"manufacturing"},
    "dfa_basic": {"assembly"},
    "dft_basic": {"testability"},
    "bom_basic": {"bom"},
    "thermal_basic": {"thermal"},
}

def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def run_review(
        profile: Annotated[
            ReviewProfile,
            Field(
                description=(
                    "board_review / schematic_review: every registered PCB / schematic "
                    "check. schematic_readability: all-sheet visual geometry, or explicitly "
                    "selected sheets; not native ERC. drc_basic: PCB placement, connectivity, "
                    "clearance. erc_basic: "
                    "schematic connectivity and metadata. connectivity. component_clearance: "
                    "overlap and board containment. silkscreen. manufacturing_geometry: "
                    "minimum feature, edge, drill, annular ring. dfm_basic: DFM geometry and "
                    "stackup. dfa_basic: assembly. dft_basic: testpoint coverage. bom_basic: "
                    "MPN/DNP metadata. thermal_basic: power and thermal metadata."
                )
            ),
        ],
        path: str | None = None,
        sheets: Annotated[
            list[Annotated[int, Field(strict=True, ge=0)]],
            Field(min_length=1, max_length=256, description=(
                "Explicit zero-based sheet indices, only for schematic_readability. "
                "Omit to check every sheet, including documentary overview."
            )),
        ] | None = None,
    ) -> dict[str, Any]:
        """Run one deterministic offline review profile and store its report."""
        return service.run_review(
            path, profile=profile, categories=_REVIEW_PROFILE_CATEGORIES[profile], sheets=sheets
        )

    @mcp.tool()
    def plan_silkscreen(
        path: str | None = None,
        selector: SelectorInput | None = None,
        clearance: float = 0.2,
        board_edge_clearance: float = 0.2,
        grid: float = 0.25,
        search_steps: int = 4,
        include_board_texts: bool = False,
        avoid_component_bodies: bool = True,
    ) -> dict[str, Any]:
        """Generate and persist a deterministic legal silkscreen placement plan."""
        return service.plan_silkscreen(
            path,
            selector=selector,
            clearance=clearance,
            board_edge_clearance=board_edge_clearance,
            grid=grid,
            search_steps=search_steps,
            include_board_texts=include_board_texts,
            avoid_component_bodies=avoid_component_bodies,
        )

    @mcp.tool()
    def analyze_release_readiness(path: str | None = None) -> dict[str, Any]:
        """Report bounded DFM/DFA/DFT release-readiness findings from exported XML."""
        return service.analyze_release_readiness(path)

    @mcp.tool()
    def get_findings(report_id: str) -> dict[str, Any]:
        """Read all structured findings from a stored review report."""
        return service.get_findings(report_id)

    @mcp.tool()
    def get_finding(finding_id: str) -> dict[str, Any]:
        """Read one structured finding by deterministic id."""
        return service.get_finding(finding_id)

    @mcp.tool(
        description=(
            "Check a project's PCB_BUILD.md handoff: gate-table order, recorded SHAs "
            "against the files, and the stage's offline check (board: headless QC with "
            "copper connectivity; schematic: full review with nothing skipped). status "
            "BLOCKED lists why. Native DRC/ERC and manual gates stay outside this tool."
        )
    )
    def run_quality_gate(
        project_dir: Annotated[
            str, Field(description="Project directory holding PCB_BUILD.md.")
        ],
        stage: Literal["board", "schematic"] | None = None,
        board: str | None = None,
        schematic: str | None = None,
        centerline_x: list[str] | None = None,
        centerline_y: list[str] | None = None,
    ) -> dict[str, Any]:
        """See the tool description."""
        from diptrace_mcp.quality_gate import gate_report

        resolve = service.settings.resolve_allowed_path
        return gate_report(
            resolve(project_dir),
            stage=stage,
            board=resolve(board) if board else None,
            schematic=resolve(schematic) if schematic else None,
            centerline_x=centerline_x,
            centerline_y=centerline_y,
        )
