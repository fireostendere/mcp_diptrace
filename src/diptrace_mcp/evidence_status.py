"""Repository-owned evidence gates exposed by public tool contracts."""

from __future__ import annotations

from typing import Any

# This is the reusable package-public evidence gate, not the historical manual
# campaign status. Private/manual PASS never promotes public provenance.
Q1_COMPONENT_ANGLE_LIVE_VALIDATED = False


def component_angle_evidence_status() -> dict[str, Any]:
    return {
        "manual_campaign_status": "PASS",
        "manual_campaign_scope": "accepted_production_checkpoint_only",
        "manual_campaign_application": "DipTrace PCB Layout 5.3.0.3",
        "manual_campaign_reference": "docs/XML_COMPATIBILITY.md#q1-component-angle",
        "package_publicly_validated": Q1_COMPONENT_ANGLE_LIVE_VALIDATED,
        "grants_high_trust": False,
    }

COMPONENT_ANGLE_VALIDATION_WARNING: dict[str, Any] = {
    "code": "component_angle_live_validation_pending",
    "message": (
        "The Q1 manual campaign passed on its accepted production checkpoint, but "
        "reusable package-public angle evidence is not yet accepted. This does not "
        "grant public provenance to current artifacts. Inspect the transaction preview and "
        "verify the result through DipTrace before relying on rotation changes."
    ),
    "affected_operation": "rotate_components",
}


def component_angle_evidence_warnings() -> list[dict[str, Any]]:
    """Return a fresh warning list while Q1 remains open."""

    if Q1_COMPONENT_ANGLE_LIVE_VALIDATED:
        return []
    return [dict(COMPONENT_ANGLE_VALIDATION_WARNING)]
