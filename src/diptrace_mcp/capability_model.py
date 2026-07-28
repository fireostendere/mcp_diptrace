"""Shared capability and trust-model data.

Both the no-document and document-scoped capability reports derive from
the single source of truth in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

MAX_TRANSACTION_OPERATIONS: Final = 100
MAX_WRITE_OBJECTS: Final = 500


@dataclass(frozen=True, slots=True)
class CapabilityRule:
    """Declarative availability rule shared by every capability entry point."""

    condition: str = "always"
    advertised_without_document: bool = True


_READ_CAPABILITIES: dict[str, CapabilityRule] = {
    "document_info": CapabilityRule(),
    "board_model": CapabilityRule("board"),
    "schematic_model": CapabilityRule("schematic"),
    "library_models": CapabilityRule("library"),
    "library_validation": CapabilityRule("library"),
    "query_objects": CapabilityRule(),
    "get_object": CapabilityRule(),
    "connectivity_graph": CapabilityRule("design"),
    "bom": CapabilityRule("design"),
    "xml_fragments": CapabilityRule(),
    "structured_findings": CapabilityRule("design"),
    "offline_review": CapabilityRule("design"),
    "manufacturing_review": CapabilityRule("board"),
    "assembly_review": CapabilityRule("board"),
    "testability_review": CapabilityRule("board"),
    "return_path_heuristics": CapabilityRule("board"),
    "copper_pour_boundaries": CapabilityRule("board"),
    "silkscreen_planning": CapabilityRule("board"),
    "placement_analysis": CapabilityRule("board"),
    "placement_scoring": CapabilityRule("board"),
    "local_placement_candidates": CapabilityRule("board"),
    "unrouted_connections": CapabilityRule("board"),
    "route_details": CapabilityRule("board"),
    "physical_stackup": CapabilityRule("board"),
    "net_length_measurement": CapabilityRule("board"),
    "differential_pair_analysis": CapabilityRule("board"),
    "analytical_microstrip_impedance": CapabilityRule(),
    "analytical_differential_microstrip_impedance": CapabilityRule(),
    "analytical_symmetric_stripline_impedance": CapabilityRule(),
    "local_45_degree_routing": CapabilityRule("board"),
    "multilayer_local_routing": CapabilityRule("routable_via"),
    "coupled_diff_pair_routing": CapabilityRule("differential_pairs"),
    "autorouter_ses_inspection": CapabilityRule("board"),
    "external_jobs": CapabilityRule(),
}

_WRITE_CAPABILITIES: dict[str, CapabilityRule] = {
    "apply_xml_edits": CapabilityRule(),
    "transactions": CapabilityRule(),
    "document_creation": CapabilityRule(),
    "schematic_authoring": CapabilityRule("schematic"),
    "schematic_to_pcb_sync": CapabilityRule(),
    "panelization": CapabilityRule("board"),
    "move_components": CapabilityRule("design"),
    "rotate_components": CapabilityRule("design"),
    "set_component_side": CapabilityRule("board"),
    "lock_components": CapabilityRule("design"),
    "set_component_value": CapabilityRule("design"),
    "set_component_properties": CapabilityRule("design"),
    "set_component_pattern": CapabilityRule("board"),
    "align_distribute_components": CapabilityRule("board"),
    "component_groups": CapabilityRule("board"),
    "board_text_edits": CapabilityRule("board"),
    "set_pin_no_connect": CapabilityRule("schematic"),
    "rename_net": CapabilityRule("design"),
    "net_class_rules": CapabilityRule("board"),
    "testpoints": CapabilityRule("board"),
    "apply_silkscreen_plan": CapabilityRule("board"),
    "apply_component_placement_plan": CapabilityRule("board"),
    "trace_primitives": CapabilityRule("board"),
    "via_primitives": CapabilityRule("board"),
    "apply_route_plan": CapabilityRule("board"),
    "route_diff_pair": CapabilityRule("differential_pairs"),
    "bom_export": CapabilityRule("design"),
    "fabrication_manifest_export": CapabilityRule("board"),
    "assembly_manifest_export": CapabilityRule("board"),
    "autorouter_dsn_export": CapabilityRule(
        "unsupported",
        advertised_without_document=False,
    ),
    "autorouter_ses_import": CapabilityRule("board"),
}

_EXPERIMENTAL_CAPABILITIES: dict[str, CapabilityRule] = {
    "global_placement": CapabilityRule("unsupported", advertised_without_document=False),
    "push_and_shove_routing": CapabilityRule(
        "unsupported",
        advertised_without_document=False,
    ),
    "rip_up_retry_routing": CapabilityRule("board"),
    "automatic_via_routing": CapabilityRule("routable_via"),
    "coupled_diff_pair_routing": CapabilityRule("differential_pairs"),
    "testpoint_candidate_accessibility": CapabilityRule("board"),
    "symmetric_stripline_impedance": CapabilityRule(),
    "differential_impedance": CapabilityRule(),
    "return_path_heuristics": CapabilityRule("board"),
}

CAPABILITY_TABLES: Final[dict[str, dict[str, CapabilityRule]]] = {
    "read_capabilities": _READ_CAPABILITIES,
    "write_capabilities": _WRITE_CAPABILITIES,
    "experimental_capabilities": _EXPERIMENTAL_CAPABILITIES,
}


def _routable_via_style(snapshot: Any) -> bool:
    board = snapshot.board
    return bool(
        board is not None
        and any(
            style.diameter_mm is not None
            and style.hole_mm is not None
            and style.diameter_mm > style.hole_mm
            and (
                style.span_source == "explicit"
                or (style.span_source == "unspecified" and len(board.layers) == 2)
            )
            for style in board.via_styles
        )
    )


def _evaluate_rule(rule: CapabilityRule, snapshot: Any | None) -> bool:
    if snapshot is None:
        return rule.advertised_without_document
    document_kind = snapshot.document.kind
    conditions = {
        "always": True,
        "unsupported": False,
        "board": snapshot.board is not None,
        "schematic": snapshot.schematic is not None,
        "design": document_kind in {"pcb", "schematic"},
        "library": document_kind in {"component_library", "pattern_library"},
        "differential_pairs": bool(
            snapshot.board is not None and snapshot.board.differential_pairs
        ),
        "routable_via": _routable_via_style(snapshot),
    }
    try:
        return conditions[rule.condition]
    except KeyError as exc:
        raise ValueError(f"Unknown capability condition: {rule.condition}") from exc


def render_capability_tables(snapshot: Any | None) -> dict[str, dict[str, bool]]:
    """Render every capability group from one declarative key registry."""

    return {
        group: {name: _evaluate_rule(rule, snapshot) for name, rule in rules.items()}
        for group, rules in CAPABILITY_TABLES.items()
    }


# The trust model is a single dict that both entry points produce.
# When a document is present, additional document-specific keys are merged in.
_BASE_TRUST_MODEL: dict[str, Any] = {
    "seed_based_creation": True,
    "seed_trust_auto_upgrade": False,
    "client_can_assign_validation_level": False,
    "runtime_sidecar_can_grant_high_trust": False,
    "user_supplied_evidence_grants_high_trust": False,
    "trusted_manifest_is_revalidated_on_read": True,
    "evidence_manifest_sha_binding": True,
    "roundtrip_success_path_tested": False,
    "semantic_digest_version": "1.2",
    "semantic_comparison_fail_closed": True,
    "rollback_provenance_safe": True,
    "all_write_paths_invalidate_trust": False,
    "untested_write_paths": [
        "plan_apply",
        "ses_import",
        "schematic_to_pcb_sync",
        "live_session_apply",
    ],
    "roundtrip_authority": "user_supplied_evidence_recorded",
    "high_trust_authority": "trusted_registry_available_no_reviewed_entries",
    "trusted_registry": {
        "schema_version": "diptrace-trusted-provenance-registry-v1",
        "authority": "repository_owned_committed_sha256_allowlist",
        "source": "diptrace_mcp/data/trusted_provenance_registry.json",
        "trusted_entry_count": 0,
        "high_trust_currently_available": False,
        "entries": [],
        "every_entry_requires_human_review": True,
    },
    "roundtrip_evidence_validation": {
        "public_preview_tool": "validate_roundtrip_evidence",
        "public_record_tool": "record_roundtrip_evidence",
        "preview_writes_files": False,
        "record_writes_metadata_only": True,
        "user_supplied_recorded": True,
        "user_supplied_high_trust_denied": True,
    },
    "plane_layer_routing": False,
    "external_pattern_resolution": False,
    "provenance_sidecar": True,
    "trust_invalidated_after_mcp_write": True,
}
_DOCUMENT_TRUST_TEMPLATE: dict[str, Any] = {
    "kind": None,
    "sha256": None,
    "path": None,
    "live_session": None,
    "validation_level": None,
    "trust_authority": None,
    "requires_diptrace_verification": None,
    "evidence_manifest_path": None,
    "evidence_manifest_sha256": None,
    "warnings": [],
}


def get_trust_model(
    *,
    document_kind: str | None = None,
    document_trust: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the trust model, optionally enriched with document-specific keys.

    This is the single source of truth for the trust model. Both the no-document
    and document-scoped capability reports call this function.
    """
    import copy

    model = copy.deepcopy(_BASE_TRUST_MODEL)
    model["document_kind"] = document_kind
    model["document_loaded"] = document_kind is not None
    model["document"] = copy.deepcopy(_DOCUMENT_TRUST_TEMPLATE)
    if document_trust is not None:
        unknown = set(document_trust) - set(_DOCUMENT_TRUST_TEMPLATE)
        if unknown:
            raise ValueError(
                "Unknown document trust fields: " + ", ".join(sorted(unknown))
            )
        model["document"].update(copy.deepcopy(document_trust))
    return model
