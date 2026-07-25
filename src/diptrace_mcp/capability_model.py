"""Shared capability and trust-model data.

Both the no-document and document-scoped capability reports derive from
the single source of truth in this module.
"""

from __future__ import annotations

from typing import Any

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
    "high_trust_authority": "unavailable_no_trusted_bridge",
    "roundtrip_evidence_validation": {
        "user_supplied_recorded": True,
        "user_supplied_high_trust_denied": True,
    },
    "plane_layer_routing": False,
    "external_pattern_resolution": False,
    "provenance_sidecar": True,
    "trust_invalidated_after_mcp_write": True,
}


def get_trust_model(*, document_kind: str | None = None) -> dict[str, Any]:
    """Return the trust model, optionally enriched with document-specific keys.

    This is the single source of truth for the trust model. Both the no-document
    and document-scoped capability reports call this function.
    """
    import copy

    model = copy.deepcopy(_BASE_TRUST_MODEL)
    if document_kind is not None:
        model["document_kind"] = document_kind
        model["document_loaded"] = True
    else:
        model["document_loaded"] = False
    return model
