"""Repository-owned evidence gates exposed by public tool contracts."""

from __future__ import annotations

from typing import Any

# Q1 is deliberately a source-controlled gate. It must only be changed after
# an independent DipTrace GUI edit and re-export has been accepted into the
# evidence directory; a writer round-trip is not sufficient.
Q1_COMPONENT_ANGLE_LIVE_VALIDATED = False

COMPONENT_ANGLE_VALIDATION_WARNING: dict[str, Any] = {
    "code": "component_angle_live_validation_pending",
    "message": (
        "Component angle semantics have not yet been independently validated against "
        "a live DipTrace GUI edit and re-export. Inspect the transaction preview and "
        "verify the result through DipTrace before relying on rotation changes."
    ),
    "affected_operation": "rotate_components",
}


def component_angle_evidence_warnings() -> list[dict[str, Any]]:
    """Return a fresh warning list while Q1 remains open."""

    if Q1_COMPONENT_ANGLE_LIVE_VALIDATED:
        return []
    return [dict(COMPONENT_ANGLE_VALIDATION_WARNING)]
