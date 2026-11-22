"""Public tool → qualified capability keys (implementation, not policy permission).

New tools can supply capability_keys to DipTraceFastMCP.tool; identical tool and
capability names are resolved automatically. Server startup checks coverage.
"""

from collections.abc import Iterable

from .capability_model import CAPABILITY_TABLES

_GROUPS = {
    "read_capabilities": {
        "server_status": "diptrace_status",
        "capability_discovery": "get_capabilities",
        "document_info": "get_document_info summarize_design",
        "document_catalog": "scan_diptrace_documents",
        "roundtrip_evidence_validation": "validate_roundtrip_evidence",
        "quality_gate": "run_quality_gate",
        "board_model": "get_board_model",
        "schematic_model": "get_schematic_model",
        "library_models": (
            "scan_component_libraries scan_pattern_libraries query_library_items "
            "get_library_component get_library_pattern"
        ),
        "library_validation": (
            "validate_library_component validate_library_pattern"
        ),
        "builtin_library_catalog": "query_builtin_library_catalog",
        "bom": (
            "get_bom review_bom compare_bom_to_design find_missing_component_fields"
        ),
        "query_objects": "query_objects list_components get_component list_nets get_design_rules",
        "get_object": "get_object",
        "connectivity_graph": "get_connectivity_graph compare_schematic_to_pcb",
        "xml_fragments": "read_xml_fragment",
        "structured_findings": "get_findings get_finding",
        "offline_review": "run_review",
        "testability_review": "list_testpoints find_testpoint_candidates review_testpoint_coverage",
        "silkscreen_planning": "plan_silkscreen",
        "placement_analysis": "analyze_placement",
        "placement_scoring": "score_placement",
        "local_placement_candidates": "generate_placement_candidates plan_component_placement",
        "schematic_placement_candidate_ranking": (
            "rank_schematic_placement_candidates plan_schematic_placement_repair"
        ),
        "pcb_placement_candidate_ensemble": "compare_pcb_placement_candidates",
        "pattern_recommendation": "recommend_patterns",
        "release_readiness": "analyze_release_readiness",
        "unrouted_connections": "list_unrouted_connections",
        "route_details": "get_route_details analyze_routing_congestion",
        "physical_stackup": (
            "get_stackup analyze_stackup_for_impedance validate_impedance_constraints"
        ),
        "net_length_measurement": "measure_net_lengths analyze_length_group",
        "differential_pair_analysis": (
            "list_differential_pairs get_differential_pair analyze_differential_pair "
            "analyze_differential_pairs validate_differential_pair"
        ),
        "analytical_microstrip_impedance": (
            "calculate_impedance suggest_trace_geometry_for_impedance"
        ),
        "copper_pour_boundaries": "list_copper_pours analyze_plane_continuity",
        "return_path_heuristics": "analyze_return_path",
        "local_45_degree_routing": "route_connection route_net route_connections plan_route_nets",
        "coupled_diff_pair_routing": "plan_diff_pair_route",
        "autorouter_ses_inspection": "inspect_autorouter_result",
        "external_jobs": (
            "run_external_autorouter run_native_check run_ngspice_simulation "
            "run_openems_stripline_analysis get_job_status get_job_result cancel_job list_jobs"
        ),
    },
    "write_capabilities": {
        "roundtrip_evidence_recording": "record_roundtrip_evidence",
        "live_session_lifecycle": "finish_live_session abandon_live_session",
        "apply_xml_edits": "apply_xml_edits apply_xml_edits_from_file",
        "document_creation": (
            "create_schematic_document create_pcb_document create_document_from_seed"
        ),
        "transactions": (
            "begin_transaction stage_operations preview_transaction "
            "commit_transaction rollback_transaction list_transactions"
        ),
        "schematic_authoring": (
            "add_sheet place_part connect_pins disconnect_pins add_wire delete_wire add_net_label"
        ),
        "place_builtin_library_component": "place_builtin_component",
        "schematic_to_pcb_sync": "sync_schematic_to_pcb",
        "panelization": "set_panelization clear_panelization",
        "align_distribute_components": "align_components distribute_components",
        "component_groups": "group_components ungroup_components",
        "board_text_edits": (
            "list_board_texts move_board_texts rotate_board_texts "
            "set_text_visibility set_text_style"
        ),
        "net_class_rules": "update_net_class_rules",
        "net_class_assignment": "assign_nets_to_class",
        "copper_pour_edits": "add_copper_pours delete_copper_pours",
        "board_outline": "set_board_outline",
        "testpoints": "add_testpoints move_testpoints remove_testpoints",
        "trace_primitives": "add_trace replace_trace delete_trace set_trace_width",
        "via_primitives": "add_via move_via delete_via set_via_style",
        "bom_export": "export_bom",
        "fabrication_manifest_export": "export_fabrication_outputs",
        "assembly_manifest_export": "export_assembly_outputs",
        "autorouter_dsn_export": "export_autorouter_dsn",
    },
}

TOOL_CAPABILITIES: dict[str, list[str]] = {
    tool: [f"{group}.{key}"]
    for group, entries in _GROUPS.items()
    for key, tools in entries.items()
    for tool in tools.split()
}
# Listing exports is independent of which export format created them.
TOOL_CAPABILITIES["list_exports"] = ["read_capabilities.export_catalog"]
TOOL_CAPABILITIES["calculate_impedance"] = [
    "read_capabilities.analytical_microstrip_impedance",
    "read_capabilities.analytical_differential_microstrip_impedance",
    "read_capabilities.analytical_symmetric_stripline_impedance",
]
for _name in [
    "move_components",
    "rotate_components",
    "set_component_side",
    "lock_components",
    "set_component_value",
    "set_component_properties",
    "set_component_pattern",
    "set_pin_no_connect",
    "rename_net",
    "delete_parts",
    "delete_net_labels",
    "route_diff_pair",
    "pipeline_source_component",
    "pipeline_nativeize_document",
    "pipeline_render_board_preview",
]:
    TOOL_CAPABILITIES[_name] = [f"write_capabilities.{_name}"]


def register_tool_capabilities(name: str, keys: list[str] | None = None) -> None:
    if keys is None:
        keys = TOOL_CAPABILITIES.get(name) or [
            f"{group}.{name}" for group, rules in CAPABILITY_TABLES.items() if name in rules
        ]
    if not keys:
        # Standalone FastMCP instances may register non-product test/client tools.
        # The product server requires complete coverage after registration.
        return
    for key in keys:
        group, _, capability = key.partition(".")
        if capability not in CAPABILITY_TABLES.get(group, {}):
            raise ValueError(f"Unknown capability key for {name}: {key}")
    TOOL_CAPABILITIES[name] = list(keys)


def tool_capability_mapping(tool_names: Iterable[str] | None = None) -> dict[str, list[str]]:
    if tool_names is not None:
        missing = set(tool_names) - TOOL_CAPABILITIES.keys()
        if missing:
            raise ValueError(f"No capability mapping for public tools: {sorted(missing)}")
    return {name: list(keys) for name, keys in sorted(TOOL_CAPABILITIES.items())}
