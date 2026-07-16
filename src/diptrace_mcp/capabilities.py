from __future__ import annotations

from . import __version__
from .adapters import capability_report
from .domain import CapabilityReport
from .geometry_backend import backend_report
from .xml_document import DipTraceDocument


def get_capabilities(
    document: DipTraceDocument | None = None,
    *,
    live_session: bool = False,
) -> CapabilityReport:
    from .review import registry

    if document is None:
        return CapabilityReport(
            server_version=__version__,
            source_types={
                "supported": [
                    "DipTrace-PCB",
                    "DipTrace-Schematic",
                    "DipTrace-ComponentLibrary",
                    "DipTrace-PatternLibrary",
                ],
                "tested_versions": {
                    "DipTrace-PCB": ["4.3.0.3"],
                    "DipTrace-Schematic": ["4.3.0.3"],
                    "DipTrace-ComponentLibrary": ["4.3.0.1"],
                    "DipTrace-PatternLibrary": ["4.3.0.1"],
                },
                "documented_versions": {
                    "DipTrace-PCB": ["4.3.0.3"],
                    "DipTrace-Schematic": ["4.3.0.3"],
                    "DipTrace-ComponentLibrary": ["4.3.0.1", "5.3.0.0"],
                    "DipTrace-PatternLibrary": ["4.3.0.1", "5.3.0.0"],
                },
                "compatibility_policy": "feature_detected_preserve_unknown",
                "note": (
                    "5.3.0.0 is the DipTrace application release and a documented library "
                    "format version; PCB/Schematic 5.3 round-trip requires a real export fixture. "
                    "Load a document for exact feature compatibility."
                ),
            },
            read_capabilities={
                "document_info": True,
                "board_model": True,
                "schematic_model": True,
                "library_models": True,
                "library_validation": True,
                "query_objects": True,
                "connectivity_graph": True,
                "bom": True,
                "structured_findings": True,
                "offline_review": True,
                "manufacturing_review": True,
                "assembly_review": True,
                "testability_review": True,
                "return_path_heuristics": True,
                "copper_pour_boundaries": True,
                "silkscreen_planning": True,
                "placement_analysis": True,
                "placement_scoring": True,
                "local_placement_candidates": True,
                "unrouted_connections": True,
                "route_details": True,
                "physical_stackup": True,
                "net_length_measurement": True,
                "differential_pair_analysis": True,
                "analytical_microstrip_impedance": True,
                "analytical_differential_microstrip_impedance": True,
                "local_45_degree_routing": True,
                "multilayer_local_routing": True,
                "coupled_diff_pair_routing": True,
                "autorouter_ses_inspection": True,
                "external_jobs": True,
            },
            write_capabilities={
                "apply_xml_edits": True,
                "transactions": True,
                "move_components": True,
                "rotate_components": True,
                "set_component_side": True,
                "lock_components": True,
                "set_component_value": True,
                "set_component_properties": True,
                "set_component_pattern": True,
                "align_distribute_components": True,
                "component_groups": True,
                "board_text_edits": True,
                "set_pin_no_connect": True,
                "rename_net": True,
                "net_class_rules": True,
                "testpoints": True,
                "apply_silkscreen_plan": True,
                "apply_component_placement_plan": True,
                "trace_primitives": True,
                "via_primitives": True,
                "apply_route_plan": True,
                "route_diff_pair": True,
                "bom_export": True,
                "fabrication_manifest_export": True,
                "assembly_manifest_export": True,
                "autorouter_dsn_export": False,
                "autorouter_ses_import": True,
            },
            experimental_capabilities={
                "global_placement": False,
                "push_and_shove_routing": False,
                "automatic_via_routing": True,
                "coupled_diff_pair_routing": True,
                "testpoint_candidate_accessibility": True,
                "symmetric_stripline_impedance": False,
                "differential_impedance": True,
                "return_path_heuristics": True,
            },
            external_adapters={
                "freerouting": {
                    "available": False,
                    "implemented": True,
                    "reason": "Runtime availability requires DIPTRACE_MCP_FREEROUTING.",
                }
            },
            geometry_backend=backend_report(),
            preview_formats=["svg", "json", "diff"],
            limits={"max_transaction_operations": 100, "max_query_results": 500},
            policy={
                "active_profile": "interactive_edit",
                "default_write_mode": "dry_run",
                "explicit_sha_on_commit": True,
                "conflict_safe_rollback": True,
            },
            reasons_unavailable=[
                {
                    "feature": "preview_png",
                    "code": "capability_unavailable",
                    "message": "PNG rendering is unavailable; use SVG or JSON geometry.",
                },
                {
                    "feature": "global_placement",
                    "code": "capability_unavailable",
                    "message": "Only deterministic bounded local placement is implemented.",
                },
                {
                    "feature": "push_and_shove_routing",
                    "code": "capability_unavailable",
                    "message": "The local router is bounded 45-degree A* without push-and-shove.",
                },
                {
                    "feature": "symmetric_stripline_impedance",
                    "code": "solver_required",
                    "message": "Only verified analytical microstrip impedance is enabled.",
                },
                {
                    "feature": "native_manufacturing_outputs",
                    "code": "capability_unavailable",
                    "message": "Gerber, NC drill, ODB++ and IPC-2581 generation is unavailable.",
                },
                {
                    "feature": "schematic_wire_edits",
                    "code": "capability_unavailable",
                    "message": "Wire and label mutation lacks a verified round-trip fixture.",
                },
                {
                    "feature": "library_mutation",
                    "code": "capability_unavailable",
                    "message": "Component and pattern libraries are read/validate only.",
                },
                {
                    "feature": "panelization",
                    "code": "capability_unavailable",
                    "message": "No confirmed panel-object XML semantics are available.",
                },
                {
                    "feature": "external_si_pi_solver",
                    "code": "external_tool_unavailable",
                    "message": "No verified solver adapter is configured or implemented.",
                },
            ],
            registered_checks=registry.ids(),
            workflow_prompts=[
                {"name": name, "status": "available"}
                for name in (
                    "review_board_before_release",
                    "review_schematic_before_layout",
                    "place_selected_components_safely",
                    "place_decoupling_network",
                    "route_critical_net",
                    "route_diff_pair_with_constraints",
                    "clean_silkscreen_for_manufacturing",
                    "add_testpoints_for_fixture",
                    "review_return_paths",
                    "prepare_fabrication_export",
                    "prepare_assembly_export",
                    "review_bom",
                    "compare_schematic_and_pcb",
                )
            ],
        )
    return capability_report(document, live_session=live_session)
