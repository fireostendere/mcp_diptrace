"""MCP workflow prompts."""
from __future__ import annotations

from ..server_inputs import (
    DipTraceFastMCP,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.prompt()
    def review_diptrace_design(scope: str = "full") -> str:
        """Create a safe workflow prompt for reviewing the active DipTrace design."""
        return (
            "Review the active DipTrace design. First call diptrace_status and summarize_design. "
            f"Review scope: {scope}. Inspect components, nets and design rules as needed. Report "
            "findings with exact RefDes/net names. Do not edit unless explicitly requested. "
            "If edits are requested, preview with dry_run=true, explain the diff, then commit "
            "with the returned before_sha256 and finish the live session only after confirmation."
        )

    @mcp.prompt()
    def review_board_before_release(scope: str = "full") -> str:
        """Review a requested PCB scope before release using available checks."""
        return (
            f"Review the board before release. Review scope: {scope}. "
            "Start with get_capabilities, summarize_design, "
            "get_board_model, get_design_rules and a focused query_objects pass. Stop if any "
            "capability is unavailable."
        )

    @mcp.prompt()
    def place_selected_components_safely(scope: str = "selected") -> str:
        """Plan and preview bounded component placement for a requested scope."""
        return (
            f"Place components safely. Placement scope: {scope}. "
            "Inspect the current model, build a transaction, "
            "preview it, review the diff and commit only after confirming no locked parts move."
        )

    @mcp.prompt()
    def review_schematic_before_layout(scope: str = "full") -> str:
        """Review a requested schematic scope before PCB layout begins."""
        return (
            f"Review the schematic before layout. Review scope: {scope}. "
            "Inspect components, nets, ERC settings and "
            "the connection graph, then summarize blocking issues and missing metadata."
        )

    @mcp.prompt()
    def place_decoupling_network(component_selector: str, region: str = "local") -> str:
        """Plan a bounded decoupling-network placement around selected components."""
        return (
            f"Required inputs: target selector={component_selector}; allowed region={region}. "
            "Call get_capabilities, query_objects, get_connectivity_graph, analyze_placement, "
            "generate_placement_candidates and plan_component_placement. The model decides which "
            "parts form the decoupling network. Inspect SVG/JSON preview before any write; apply "
            "the selected plan as a dry-run transaction, then run localized DRC. Stop on ambiguous "
            "nets, locked objects, unknown body geometry, SHA conflict or any DRC regression."
        )

    @mcp.prompt()
    def route_critical_net(net: str, constraints: str = "use exported rules") -> str:
        """Plan a bounded route for one explicitly named critical net."""
        return (
            f"Required net={net}; constraints={constraints}. Call get_capabilities, get_stackup, "
            "list_unrouted_connections and get_route_details. Use route_connection or "
            "plan_route_nets only when bounded 45-degree routing satisfies the "
            "constraints. Inspect route preview and dry-run transaction before commit; rerun "
            "connectivity and DRC after write. "
            "The model chooses routing priority. Vias require explicit layers/style/budget. Stop "
            "if push-and-shove or unknown rules are required, or if connectivity/DRC regresses."
        )

    @mcp.prompt()
    def route_diff_pair_with_constraints(pair: str) -> str:
        """Plan a differential-pair route using explicit stackup and pair constraints."""
        return (
            f"Required differential pair={pair}. Call get_capabilities, get_stackup, "
            "get_differential_pair, analyze_differential_pair and analyze_stackup_for_impedance. "
            "Use calculate_impedance with differential_microstrip, then plan_diff_pair_route. "
            "Inspect SVG/JSON and skew/via metrics before apply_plan; rerun pair validation "
            "and DRC after commit. The model decides whether analytical assumptions are "
            "acceptable. "
            "Stop on incomplete stackup, incompatible pad spacing, unresolved DRC or SHA conflict."
        )

    @mcp.prompt()
    def clean_silkscreen_for_manufacturing(scope: str = "whole board") -> str:
        """Plan and validate silkscreen cleanup for the requested board scope."""
        return (
            f"Required scope={scope}. Call run_review(profile=silkscreen), plan_silkscreen, "
            "inspect the plan score, "
            "unresolved labels and SVG preview, then apply_plan with dry_run=true. The "
            "model decides how to handle unresolved labels. Commit only after preview; rerun "
            "run_review with profiles silkscreen and dfm_basic. Stop on locked labels, "
            "incomplete mask geometry, unexpected scope or a new finding."
        )

    @mcp.prompt()
    def add_testpoints_for_fixture(target_nets: str, side: str = "Top") -> str:
        """Plan guarded testpoint coverage for explicitly selected nets."""
        return (
            f"Required target nets={target_nets}; probe side={side}. Call get_connectivity_graph, "
            "list_testpoints, review_testpoint_coverage and find_testpoint_candidates. The model "
            "chooses coverage priority. Stage add_testpoints as a dry-run transaction and inspect "
            "preview before commit; rerun testability and DRC checks. Stop if accessibility "
            "is only "
            "estimated, keepout data is incomplete or coverage would duplicate an existing point."
        )

    @mcp.prompt()
    def review_return_paths(nets: str) -> str:
        """Review geometry-based return-path heuristics for selected nets."""
        return (
            f"Required nets={nets}. Call get_stackup, list_copper_pours, analyze_plane_continuity "
            "and analyze_return_path. Treat results as geometry-based heuristics, not "
            "full-wave SI. "
            "The model decides criticality and remediation. Stop if reference layers, plane net or "
            "refilled copper geometry are unknown; report skipped checks and confidence."
        )

    @mcp.prompt()
    def prepare_fabrication_export(scope: str = "whole board") -> str:
        """Review release readiness before creating a generic fabrication manifest."""
        return (
            f"Required release scope={scope}. Run board, manufacturing, connectivity and stackup "
            "reviews first. Stop on blocking findings or incomplete stackup. Call "
            "export_fabrication_outputs only for the generic review manifest; it does not generate "
            "Gerber or NC drill. The model decides release readiness and must not label "
            "this bundle "
            "fabrication-ready."
        )

    @mcp.prompt()
    def prepare_assembly_export(variant: str = "default") -> str:
        """Review one assembly variant before creating generic assembly artifacts."""
        return (
            f"Required variant={variant}. Run assembly, BOM and silkscreen reviews, then call "
            "export_assembly_outputs for generic placement/BOM artifacts. Stop on DNP ambiguity, "
            "missing pattern/MPN or unknown coordinate convention. The model selects variant "
            "policy "
            "and must map the generic CSV to the assembler outside MCP."
        )

    @mcp.prompt(name="review_bom")
    def review_bom_workflow(variant: str = "all") -> str:
        """Review BOM metadata and consistency for the requested variant."""
        return (
            f"Required variant={variant}. Call get_bom, review_bom and "
            "find_missing_component_fields. The model decides "
            "substitution policy. Stop on DNP/variant ambiguity; no internet sourcing is performed."
        )

    @mcp.prompt()
    def compare_schematic_and_pcb(schematic_path: str, pcb_path: str) -> str:
        """Compare an explicit schematic and PCB without applying changes."""
        return (
            f"Required schematic={schematic_path}; PCB={pcb_path}. Read both document infos, call "
            "compare_schematic_to_pcb and inspect RefDes, value, net and endpoint deltas. The "
            "model decides whether differences are intentional. Stop before edits on ambiguous "
            "pin-to-pad "
            "mapping or source SHA changes."
        )

    @mcp.prompt()
    def synchronize_schematic_to_pcb(schematic_path: str, pcb_path: str) -> str:
        """Plan a guarded schematic-to-PCB synchronization workflow."""
        return (
            f"Synchronize schematic={schematic_path} into PCB={pcb_path}. First call "
            "compare_schematic_to_pcb and inspect component libraries. Supply explicit "
            "pattern_style and multi-part pin_map entries wherever XML evidence is missing. "
            "Call sync_schematic_to_pcb with dry_run=true, inspect the XML/SVG preview and "
            "commit with the returned source SHA only after pin-to-pad mapping is complete. "
            "Then legalize placement and rerun connectivity and DRC."
        )
