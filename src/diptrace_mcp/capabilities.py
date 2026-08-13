from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import __version__
from .adapters import DocumentSnapshot, build_snapshot
from .capability_model import (
    MAX_TRANSACTION_OPERATIONS,
    MAX_WRITE_OBJECTS,
    get_trust_model,
    render_capability_tables,
)
from .config import (
    DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS,
    DEFAULT_LIVE_SESSION_TTL_SECONDS,
)
from .domain import CapabilityReport
from .evidence_status import component_angle_evidence_warnings
from .geometry_backend import backend_report
from .xml_document import DipTraceDocument

_SUPPORTED_SOURCE_TYPES = [
    "DipTrace-PCB",
    "DipTrace-Schematic",
    "DipTrace-ComponentLibrary",
    "DipTrace-PatternLibrary",
]
_TESTED_VERSIONS = {
    "DipTrace-PCB": ["4.3.0.3"],
    "DipTrace-Schematic": ["4.3.0.3"],
    "DipTrace-ComponentLibrary": ["4.3.0.1"],
    "DipTrace-PatternLibrary": ["4.3.0.1"],
}
_DOCUMENTED_VERSIONS = {
    "DipTrace-PCB": ["4.3.0.3"],
    "DipTrace-Schematic": ["4.3.0.3"],
    "DipTrace-ComponentLibrary": ["4.3.0.1", "5.3.0.0"],
    "DipTrace-PatternLibrary": ["4.3.0.1", "5.3.0.0"],
}


def _source_type_payload(snapshot: DocumentSnapshot | None) -> dict[str, Any]:
    return {
        "supported": list(_SUPPORTED_SOURCE_TYPES),
        "tested_versions": {key: list(value) for key, value in _TESTED_VERSIONS.items()},
        "documented_versions": {
            key: list(value) for key, value in _DOCUMENTED_VERSIONS.items()
        },
        "compatibility_policy": "feature_detected_preserve_unknown",
        "note": (
            "5.3.0.0 is the DipTrace application release and a documented library "
            "format version; PCB/Schematic 5.3 round-trip requires a real export fixture. "
            "Load a document for exact feature compatibility."
        ),
        "document": snapshot.info.source_type if snapshot is not None else None,
        "kind": snapshot.info.kind if snapshot is not None else None,
        "compatibility": snapshot.info.compatibility if snapshot is not None else None,
    }


def _external_adapters() -> dict[str, dict[str, object]]:
    return {
        "freerouting": {
            "available": False,
            "implemented": True,
            "reason": "Runtime availability requires DIPTRACE_MCP_FREEROUTING.",
        },
        "ngspice": {
            "available": False,
            "implemented": True,
            "reason": "Runtime availability requires DIPTRACE_MCP_NGSPICE or ngspice on PATH.",
        },
        "openems": {
            "available": False,
            "implemented": True,
            "reason": "Runtime availability requires DIPTRACE_MCP_OPENEMS_RUNNER.",
        },
    }


def _reasons_unavailable(
    snapshot: DocumentSnapshot | None,
    capability_tables: dict[str, dict[str, bool]],
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = [
        {
            "feature": "preview_png",
            "code": "capability_unavailable",
            "message": "PNG rendering is unavailable; use SVG or JSON geometry.",
        },
        {
            "feature": "external_autorouting",
            "code": "external_tool_unavailable",
            "message": "Freerouting adapter is implemented but no executable is configured.",
        },
        {
            "feature": "global_placement",
            "code": "capability_unavailable",
            "message": "Only deterministic bounded local placement is implemented.",
        },
        {
            "feature": "push_and_shove_routing",
            "code": "capability_unavailable",
            "message": (
                "The local router is bounded 45-degree A*; rip-up/retry is "
                "available via route_connections, push-and-shove is not implemented."
            ),
        },
        {
            "feature": "native_manufacturing_outputs",
            "code": "capability_unavailable",
            "message": "Gerber, NC drill, ODB++ and IPC-2581 generation is unavailable.",
        },
        {
            "feature": "library_mutation",
            "code": "capability_unavailable",
            "message": "Component and pattern libraries are read/validate only.",
        },
        {
            "feature": "plane_layer_routing",
            "code": "capability_unavailable",
            "message": (
                "Trace routing on Plane layers is not supported. Only Signal layers "
                "accept active trace segments. Through-via spans across Plane layers "
                "are allowed."
            ),
        },
        {
            "feature": "ratline_format_verified",
            "code": "not_diptrace_verified",
            "message": (
                "Ratline generation follows the DipTrace XML structure but has not "
                "been verified by DipTrace open/save/re-export. Synthetic scaffolding "
                "ratlines are experimental."
            ),
        },
        {
            "feature": "external_si_pi_solver",
            "code": "external_tool_unavailable",
            "message": (
                "The ngspice batch adapter is implemented for user-supplied "
                "netlists. The typed openEMS stripline adapter is implemented; "
                "configure DIPTRACE_MCP_OPENEMS_RUNNER to enable it."
            ),
        },
    ]
    if (
        snapshot is not None
        and snapshot.board is not None
        and len(snapshot.board.layers) > 1
        and not capability_tables["experimental_capabilities"]["automatic_via_routing"]
    ):
        reasons.insert(
            0,
            {
                "feature": "automatic_via_routing",
                "code": "capability_unavailable",
                "message": "No via style has valid geometry and a resolvable Lay1/Lay2 span.",
            },
        )
    return reasons


def capability_report(
    snapshot: DocumentSnapshot | None,
    *,
    workflow_prompt_names: Iterable[str] = (),
    document_trust: dict[str, Any] | None = None,
) -> CapabilityReport:
    """Render capability state from an existing snapshot or server-only context."""

    from .clearance import clearance_rule_status
    from .review import registry

    capability_tables = render_capability_tables(snapshot)
    document_kind = snapshot.document.kind if snapshot is not None else None
    trust_context: dict[str, Any] | None = None
    if snapshot is not None:
        trust_context = {
            "kind": snapshot.document.kind,
            "sha256": snapshot.info.sha256,
            "path": snapshot.info.path,
            "live_session": snapshot.info.live_session,
            "validation_level": None,
            "trust_authority": None,
            "requires_diptrace_verification": None,
            "evidence_manifest_path": None,
            "evidence_manifest_sha256": None,
            "warnings": [],
            **(document_trust or {}),
        }
    return CapabilityReport(
        server_version=__version__,
        source_types=_source_type_payload(snapshot),
        read_capabilities=capability_tables["read_capabilities"],
        write_capabilities=capability_tables["write_capabilities"],
        experimental_capabilities=capability_tables["experimental_capabilities"],
        external_adapters=_external_adapters(),
        geometry_backend=backend_report(),
        preview_formats=["svg", "json", "diff"],
        limits={
            "max_document_bytes": None,
            "max_model_cache_bytes": None,
            "max_external_log_bytes": None,
            "max_external_processes": None,
            "max_external_result_bytes": None,
            "max_query_results": 500,
            "max_transaction_operations": MAX_TRANSACTION_OPERATIONS,
            "max_write_objects": MAX_WRITE_OBJECTS,
            "default_live_session_timeout_seconds": (
                DEFAULT_LIVE_SESSION_TIMEOUT_SECONDS
            ),
            "default_live_session_ttl_seconds": DEFAULT_LIVE_SESSION_TTL_SECONDS,
            "max_write_objects_scope": (
                "semantic transactions, raw XML edits, document creation, seed-copy "
                "overwrites, and live-session apply"
            ),
            "max_write_objects_accounting": (
                "fail-closed sum of changed normalized objects, exact XML elements, and "
                "compiler-only ids; the independent views can overlap, so a write may be "
                "refused below 500 unique physical design objects"
            ),
            "max_write_objects_exemptions": [
                "exact conflict-checked transaction rollback",
                "exact validated seed copy to a new target",
            ],
            "expected_sha256_required_for": [
                "semantic design-file commit",
                "raw XML design-file write",
                "committed transaction rollback",
                "synthetic document overwrite of an existing target",
                "seed copy overwrite of an existing target",
                "live-session replacement of the external exchange file",
            ],
            "expected_sha256_not_required_for": [
                "creation of a target that does not exist",
            ],
            "expected_sha256_exemptions": [],
            "retention_max_records": None,
            "retention_max_age_days": None,
        },
        policy={
            "active_profile": None,
            "allows_preview": None,
            "allows_commit": None,
            "allows_external_execution": None,
            "default_write_mode": "dry_run",
            "rollback_supported": True,
            "conflict_safe_rollback": True,
            "explicit_sha_on_commit": True,
            "preserve_unknown_xml": True,
        },
        reasons_unavailable=_reasons_unavailable(snapshot, capability_tables),
        registered_checks=registry.ids(),
        workflow_prompts=[
            {"name": name, "status": "available"}
            for name in sorted(set(workflow_prompt_names))
        ],
        trust_model=get_trust_model(
            document_kind=document_kind,
            document_trust=trust_context,
        ),
        clearance_rule_status=clearance_rule_status(snapshot, operation="capability"),
        # Capability metadata describes the bounded surface, including the
        # trace-to-object review paths that still use DRC-only rules.
        netclass_rules_ignored=True,
        evidence_warnings=component_angle_evidence_warnings(),
    )


def get_capabilities(
    document: DipTraceDocument | None = None,
    *,
    live_session: bool = False,
    workflow_prompt_names: Iterable[str] = (),
) -> CapabilityReport:
    """Build at most one snapshot, then render the shared capability model."""

    snapshot = (
        build_snapshot(document, live_session=live_session) if document is not None else None
    )
    return capability_report(
        snapshot,
        workflow_prompt_names=workflow_prompt_names,
    )
