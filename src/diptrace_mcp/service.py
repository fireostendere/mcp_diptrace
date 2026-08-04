from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from . import __version__
from .adapters import DocumentSnapshot, build_snapshot
from .backups import BackupStore
from .capabilities import capability_report as build_capability_report
from .capability_model import MAX_TRANSACTION_OPERATIONS
from .clearance import resolve_clearance
from .config import Settings
from .design_compare import compare_schematic_to_pcb as compare_design_snapshots
from .domain import (
    _HIGH_TRUST_LEVELS,
    _TRUSTED_EVIDENCE_AUTHORITIES,
    _USER_SUPPLIABLE_TRUST_LEVELS,
    BoardModelSection,
    DocumentInfo,
    DocumentProvenance,
    EvidenceAuthority,
    EvidenceFileRecord,
    FieldSolverRequest,
    FixtureValidationLevel,
    JobStatus,
    ObjectRecord,
    PlanStatus,
    ProvenanceAuthority,
    QuerySelector,
    SemanticComparisonEvidence,
    SourceType,
    TransactionRecord,
    TrustedRoundtripEvidence,
    UnsupportedCategory,
    UserSuppliedRoundtripEvidence,
    ValidatedEvidence,
    requires_diptrace_verification,
)
from .errors import (
    CapabilityUnavailableError,
    ConfirmationRequiredError,
    ConnectivityRegressionError,
    DipTraceMcpError,
    DocumentError,
    DrcRegressionError,
    EditError,
    PathAccessError,
    RoundtripValidationError,
    RoutingError,
    Sha256MismatchError,
    TransactionConflictError,
)
from .evidence_status import component_angle_evidence_warnings
from .exports import (
    ExportStore,
    create_bom_export,
    create_release_manifest,
    export_resources,
)
from .external_adapters import ExternalJobManager
from .findings import FindingStore
from .geometry import Point, distance
from .jobs import JobStore, job_resources
from .model_cache import ModelCache
from .multirouter import (
    RoutingOrder,
    plan_connection_order,
    synthesize_routes_with_retry,
)
from .operations import (
    DeleteTraceOperation,
    SemanticOperation,
    SyncSchematicToPcbOperation,
    parse_semantic_operations,
)
from .placement import (
    PlacementConfig,
    PlacementProposal,
    PlacementWeights,
    analyze_placement,
    generate_placement_candidates,
    plan_component_placement,
    score_placement_proposal,
)
from .plans import PlanStore
from .policy import Policy
from .preview import (
    PREVIEW_COPPER_POINT_LIMIT,
    PREVIEW_COPPER_RECORD_LIMIT,
    render_preview_json,
    render_preview_svg,
)
from .previews import RawPreviewStore
from .provenance_registry import (
    RegistryAuthorizationError,
    TrustedProvenanceRegistry,
)
from .review import run_checks
from .routing import (
    DifferentialPairRouteConfig,
    RouteConnectionConfig,
    _find_net,
    _route_layers,
    synthesize_differential_pair_route,
    synthesize_route,
)
from .scaffolding import (
    DEFAULT_FORMAT_VERSION,
    PcbScaffold,
    SchematicScaffold,
    build_pcb_document,
    build_schematic_document,
    validate_format_version,
)
from .semantic_compiler import SemanticApplyResult, apply_semantic_operations
from .services.bom import BomService
from .services.context import (
    DocumentGateway,
    DocumentTarget,
    ServiceContext,
    read_success,
    validate_page,
)
from .services.context import (
    bounded_text as _bounded_text,
)
from .services.context import (
    json_size as _json_size,
)
from .services.documents import DocumentService
from .services.review import ReviewService
from .services.semantic_operations import SemanticOperationsService
from .sessions import LiveWorkingGuard, SessionAction, SessionStore
from .silkscreen import SilkscreenPlanConfig, plan_silkscreen
from .specctra import (
    dsn_export_limitations,
    export_dsn,
    parse_ses,
    session_to_operations,
)
from .synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan
from .transactions import (
    TransactionStore,
    default_risk,
    tx_preview_resources,
    tx_summary_resources,
)
from .write_limits import require_write_impact, write_impact
from .xml_document import (
    DEFAULT_DIFF_CHARACTER_LIMIT,
    DEFAULT_DIFF_LINE_LIMIT,
    DipTraceDocument,
    XmlEdit,
    atomic_write_bytes,
    sha256_bytes,
    unified_xml_diff_preview,
    utc_now,
    write_with_backup,
)

_CANDIDATE_SUFFIXES = {".xml", ".dip", ".dch", ".eli", ".lib"}
_SOURCE_TAG = re.compile(rb"<(?:Source|Library)\b([^>]*)>", re.IGNORECASE)
_SOURCE_ATTRIBUTE = re.compile(rb"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*['\"]([^'\"]*)['\"]")
BOARD_MODEL_RESPONSE_BYTE_LIMIT = 256 * 1024
BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT = 32 * 1024
RAW_EDIT_RESPONSE_BYTE_LIMIT = 128 * 1024
RAW_EDIT_XPATH_CHARACTER_LIMIT = 128
TRANSACTION_CHANGED_ID_PREVIEW_LIMIT = 500
TRANSACTION_MESSAGE_PREVIEW_LIMIT = 100
TRANSACTION_MESSAGE_CHARACTER_LIMIT = 1_000
EVIDENCE_RESPONSE_BYTE_LIMIT = 64 * 1024
EVIDENCE_LIST_PREVIEW_LIMIT = 25
EVIDENCE_TEXT_CHARACTER_LIMIT = 512


def _finalize_raw_edit_response(result: dict[str, Any]) -> dict[str, Any]:
    result["response_byte_limit"] = RAW_EDIT_RESPONSE_BYTE_LIMIT
    result["serialized_response_bytes"] = 0
    for _ in range(8):
        serialized_size = _json_size(result)
        if result["serialized_response_bytes"] == serialized_size:
            break
        result["serialized_response_bytes"] = serialized_size
    if (
        result["serialized_response_bytes"] != _json_size(result)
        or _json_size(result) > RAW_EDIT_RESPONSE_BYTE_LIMIT
    ):
        raise EditError("apply_xml_edits response metadata exceeds its payload cap")
    return result


def _bounded_raw_edit_previews(
    previews: list[dict[str, object]],
) -> list[dict[str, Any]]:
    bounded: list[dict[str, Any]] = []
    for preview in previews:
        xpath = str(preview["xpath"])
        xpath_preview, xpath_truncated = _bounded_text(
            xpath,
            RAW_EDIT_XPATH_CHARACTER_LIMIT,
        )
        bounded.append(
            {
                "index": preview["index"],
                "operation": preview["operation"],
                "xpath": xpath_preview,
                "xpath_character_count": len(xpath),
                "xpath_truncated": xpath_truncated,
                "matches": preview["matches"],
                "expected_matches": preview["expected_matches"],
                "before_count": preview["before_count"],
                "after_count": preview["after_count"],
            }
        )
    return bounded


def _validation_response_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("document_id", "kind", "sha256", "review_errors")
        if key in value
    }


def _bounded_messages(values: list[str]) -> tuple[list[str], dict[str, Any]]:
    rendered: list[str] = []
    truncated_characters = False
    for value in values[:TRANSACTION_MESSAGE_PREVIEW_LIMIT]:
        bounded, truncated = _bounded_text(value, TRANSACTION_MESSAGE_CHARACTER_LIMIT)
        rendered.append(bounded)
        truncated_characters = truncated_characters or truncated
    return rendered, {
        "total_count": len(values),
        "returned_count": len(rendered),
        "truncated": len(rendered) < len(values) or truncated_characters,
    }


def _bounded_changed_ids(values: list[str]) -> dict[str, Any]:
    rendered = values[:TRANSACTION_CHANGED_ID_PREVIEW_LIMIT]
    return {
        "changed_ids": rendered,
        "changed_id_count": len(values),
        "changed_ids_truncated": len(rendered) < len(values),
    }


def _bounded_evidence_comparison(
    comparison: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return a stable comparison preview without exposing unbounded parser output."""

    if comparison is None:
        return None, {"truncated": False, "fields": {}}

    result: dict[str, Any] = {
        "passed": bool(comparison.get("passed")),
        "comparison_complete": bool(comparison.get("comparison_complete")),
    }
    field_bounds: dict[str, dict[str, Any]] = {}
    truncated = False
    for field_name in (
        "compared_categories",
        "missing_required_categories",
        "differences",
        "ignored_normalizations",
        "parse_warnings",
    ):
        raw_values = comparison.get(field_name, [])
        values = raw_values if isinstance(raw_values, list) else []
        rendered: list[str] = []
        characters_truncated = False
        for value in values[:EVIDENCE_LIST_PREVIEW_LIMIT]:
            bounded, was_truncated = _bounded_text(
                str(value),
                EVIDENCE_TEXT_CHARACTER_LIMIT,
            )
            rendered.append(bounded)
            characters_truncated = characters_truncated or was_truncated
        field_truncated = len(rendered) < len(values) or characters_truncated
        result[field_name] = rendered
        field_bounds[field_name] = {
            "total_count": len(values),
            "returned_count": len(rendered),
            "truncated": field_truncated,
        }
        truncated = truncated or field_truncated

    unsupported_raw = comparison.get("unsupported_categories", [])
    unsupported = unsupported_raw if isinstance(unsupported_raw, list) else []
    rendered_unsupported: list[dict[str, str]] = []
    unsupported_characters_truncated = False
    for item in unsupported[:EVIDENCE_LIST_PREVIEW_LIMIT]:
        if not isinstance(item, dict):
            continue
        rendered_item: dict[str, str] = {}
        for key in ("category", "severity", "reason"):
            if key not in item:
                continue
            bounded, was_truncated = _bounded_text(
                str(item[key]),
                EVIDENCE_TEXT_CHARACTER_LIMIT,
            )
            rendered_item[key] = bounded
            unsupported_characters_truncated = unsupported_characters_truncated or was_truncated
        rendered_unsupported.append(rendered_item)
    unsupported_truncated = (
        len(rendered_unsupported) < len(unsupported) or unsupported_characters_truncated
    )
    result["unsupported_categories"] = rendered_unsupported
    field_bounds["unsupported_categories"] = {
        "total_count": len(unsupported),
        "returned_count": len(rendered_unsupported),
        "truncated": unsupported_truncated,
    }
    truncated = truncated or unsupported_truncated
    return result, {"truncated": truncated, "fields": field_bounds}


def _finalize_evidence_response(result: dict[str, Any]) -> dict[str, Any]:
    """Attach and enforce the public evidence response byte bound."""

    result["response_byte_limit"] = EVIDENCE_RESPONSE_BYTE_LIMIT
    result["serialized_response_bytes"] = 0
    for _ in range(8):
        serialized_size = _json_size(result)
        if result["serialized_response_bytes"] == serialized_size:
            break
        result["serialized_response_bytes"] = serialized_size
    if (
        result["serialized_response_bytes"] != _json_size(result)
        or _json_size(result) > EVIDENCE_RESPONSE_BYTE_LIMIT
    ):
        raise EditError("Evidence response metadata exceeds its payload cap")
    return result


def transaction_response_summary(record: TransactionRecord) -> dict[str, Any]:
    """Return stable transaction state without echoing staged operation payloads."""

    changed_id_summary = _bounded_changed_ids(record.changed_ids)
    target_path, target_path_truncated = _bounded_text(record.target_path, 4_096)
    error: dict[str, Any] | None = None
    if record.error:
        error = {}
        if "code" in record.error:
            error["code"] = record.error["code"]
        message = record.error.get("message")
        if isinstance(message, str):
            error["message"], error["message_truncated"] = _bounded_text(
                message,
                TRANSACTION_MESSAGE_CHARACTER_LIMIT,
            )
    return {
        "txid": record.txid,
        "document_id": record.document_id,
        "status": record.status,
        "target_path": target_path,
        "target_path_truncated": target_path_truncated,
        "source_sha256": record.source_sha256,
        "expected_sha256": record.expected_sha256,
        "committed_sha256": record.committed_sha256,
        "rolled_back_sha256": record.rolled_back_sha256,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "operation_count": len(record.operations),
        "compiled_patch_count": record.compiled_patch_count,
        **changed_id_summary,
        "risk": record.risk.model_dump(mode="json"),
        "validation_before": _validation_response_summary(record.validation_before),
        "validation_after_preview": _validation_response_summary(record.validation_after_preview),
        "preview_resources": record.preview_resources,
        "preview_metadata": record.preview_metadata,
        "backup_available": record.backup_path is not None,
        "error": error,
        "note_count": len(record.notes),
        "summary_resource": f"diptrace://transaction/{record.txid}/summary",
        "operations_resource": f"diptrace://transaction/{record.txid}/operations",
    }


@dataclass(frozen=True)
class RoundtripEvidenceEvaluation:
    """Validated, SHA-bound evidence inputs shared by preview and record paths."""

    document_path: Path
    document_sha256: str
    source: EvidenceFileRecord
    saved: EvidenceFileRecord
    reexport: EvidenceFileRecord | None
    semantic_comparison: dict[str, Any] | None

    @property
    def failed(self) -> bool:
        return self.semantic_comparison is not None and not bool(
            self.semantic_comparison.get("passed")
        )


def same_file_role(path_a: Path, path_b: Path) -> bool:
    """Return whether two evidence roles identify the same filesystem object."""
    try:
        if path_a.exists() and path_b.exists():
            return os.path.samefile(path_a, path_b)
    except OSError:
        pass
    try:
        left = os.path.normcase(os.path.abspath(path_a.resolve(strict=False)))
        right = os.path.normcase(os.path.abspath(path_b.resolve(strict=False)))
    except (OSError, ValueError):
        left = os.path.normcase(os.path.abspath(path_a))
        right = os.path.normcase(os.path.abspath(path_b))
    return left == right


def _require_transaction_capacity(operation_count: int) -> None:
    if operation_count > MAX_TRANSACTION_OPERATIONS:
        raise EditError(
            "Transaction would exceed "
            f"{MAX_TRANSACTION_OPERATIONS} operations limit ({operation_count} staged)"
        )


def _apply_bounded_semantic_operations(
    document: DipTraceDocument,
    operations: list[SemanticOperation],
    *,
    live_session: bool = False,
) -> SemanticApplyResult:
    """Compile a semantic write and enforce the independent object cap."""

    result = apply_semantic_operations(
        document,
        operations,
        live_session=live_session,
    )
    impact = write_impact(
        document,
        result.document,
        compiler_changed_ids=result.changed_ids,
    )
    require_write_impact(impact, operation="semantic write")
    result.changed_ids = list(impact.changed_ids)
    return result


# ── Effective trust resolution ───────────────────────────────────────────


@dataclass(frozen=True)
class EffectiveTrust:
    """Resolved trust state for a document, derived from sidecar + manifest."""

    validation_level: FixtureValidationLevel
    authority: str
    requires_diptrace_verification: bool
    evidence_manifest_path: str | None = None
    evidence_manifest_sha256: str | None = None
    warnings: list[dict[str, str]] = field(default_factory=list)


def _fail_closed_trust(
    *,
    reason: str = "evidence_validation_failed",
    warning_code: str = "evidence_manifest_sha_mismatch",
) -> EffectiveTrust:
    """Return a fail-closed trust result."""
    return EffectiveTrust(
        validation_level=FixtureValidationLevel.synthetic_parser_only,
        authority="invalid_or_untrusted_evidence",
        requires_diptrace_verification=True,
        warnings=[{"code": warning_code, "detail": reason}],
    )


# ── Required comparison categories ───────────────────────────────────────

REQUIRED_PCB_COMPARISON_CATEGORIES: frozenset[str] = frozenset(
    {
        "source_type",
        "board_outline",
        "copper_layers",
        "components",
        "pads",
        "nets",
        "traces",
        "vias",
        "via_styles",
    }
)

REQUIRED_SCHEMATIC_COMPARISON_CATEGORIES: frozenset[str] = frozenset(
    {
        "source_type",
        "sheets",
        "hierarchy",
        "parts",
        "patterns",
        "pins",
        "pin_net_membership",
        "wires",
        "wire_geometry",
        "labels",
    }
)


# ── Semantic comparison policy ─────────────────────────────────────────────

SEMANTIC_COMPARISON_POLICY_V1: dict[str, Any] = {
    "ignored_xml_sections": frozenset(
        {
            "FutureExtension",
        }
    ),
    "critical_xml_sections": frozenset(
        {
            # Unknown XML sections outside the allowlist are critical because they
            # may contain electrical semantics we cannot verify.
        }
    ),
    "informational_xml_sections": frozenset(
        {
            "Shapes",  # Text/shapes are cosmetic
        }
    ),
    "normalizations": frozenset(
        {
            "whitespace_in_text",
            "attribute_order",
            "xml_declaration_encoding",
        }
    ),
}


def _detected_semantic_normalizations(
    source: DipTraceDocument,
    reexport: DipTraceDocument,
) -> list[str]:
    """Report representation differences the semantic comparison actually ignores.

    These detectors are observational: they never remove a semantic difference or
    turn a failed comparison into a pass.  A name is returned only when the two
    parsed documents exhibit that specific, policy-allowlisted representation
    difference.
    """

    detected: set[str] = set()

    source_encoding = (
        source.encoding.casefold().replace("_", "-"),
        source.bom,
        (source.declared_encoding or "").casefold().replace("_", "-"),
    )
    reexport_encoding = (
        reexport.encoding.casefold().replace("_", "-"),
        reexport.bom,
        (reexport.declared_encoding or "").casefold().replace("_", "-"),
    )
    if source.raw_bytes != reexport.raw_bytes and source_encoding != reexport_encoding:
        detected.add("xml_declaration_encoding")

    source_elements = list(source.root.iter())
    reexport_elements = list(reexport.root.iter())
    source_shape = [(element.tag, len(element)) for element in source_elements]
    reexport_shape = [(element.tag, len(element)) for element in reexport_elements]

    # Attribute order and formatting whitespace are compared only when the element
    # trees have the same shape, so unrelated elements cannot be paired merely
    # because they happen to occupy the same traversal position.
    if source_shape == reexport_shape:
        for left, right in zip(source_elements, reexport_elements, strict=True):
            if left.attrib == right.attrib and tuple(left.attrib.items()) != tuple(
                right.attrib.items()
            ):
                detected.add("attribute_order")

            for left_text, right_text in (
                (left.text, right.text),
                (left.tail, right.tail),
            ):
                if left_text == right_text:
                    continue
                if (left_text or "").strip() == (right_text or "").strip():
                    detected.add("whitespace_in_text")

    configured = SEMANTIC_COMPARISON_POLICY_V1["normalizations"]
    return sorted(detected & configured)


def _semantic_roundtrip_check(
    source: DipTraceDocument, reexport: DipTraceDocument
) -> dict[str, Any]:
    """Compare electrically meaningful normalized DipTrace structures."""
    differences: list[str] = []
    compared: list[str] = ["source_type"]
    unsupported: list[dict[str, str]] = []
    warnings: list[str] = []

    if source.source_type != reexport.source_type:
        differences.append(f"source_type: {source.source_type!r} vs {reexport.source_type!r}")

    source_snapshot = build_snapshot(source)
    reexport_snapshot = build_snapshot(reexport)
    warnings.extend(source_snapshot.warnings)
    warnings.extend(reexport_snapshot.warnings)

    def rounded(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, dict):
            return tuple(sorted((str(key), rounded(item)) for key, item in value.items()))
        if isinstance(value, list):
            return tuple(rounded(item) for item in value)
        return value

    def record_key(record: ObjectRecord) -> tuple[str, str, str]:
        return (record.xml_id or "", record.refdes or "", record.label or record.stable_id)

    def compare_category(name: str, left: Any, right: Any) -> None:
        compared.append(name)
        if rounded(left) != rounded(right):
            differences.append(f"{name}: semantic content differs")

    if source_snapshot.board is not None and reexport_snapshot.board is not None:
        sb = source_snapshot.board
        rb = reexport_snapshot.board
        compare_category("board_outline", sb.outline, rb.outline)
        compare_category("copper_layers", sb.layers, rb.layers)
        compare_category(
            "via_styles",
            [item.model_dump(mode="json") for item in sb.via_styles],
            [item.model_dump(mode="json") for item in rb.via_styles],
        )

        def component_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item),
                item.name,
                item.value,
                item.side,
                item.locked,
                item.position,
                rounded(item.rotation_deg),
                item.mirrored,
                item.attributes.get("pattern_style"),
                item.attributes.get("pattern_name"),
            )

        compare_category(
            "components",
            [component_sig(item) for item in sorted(sb.components, key=record_key)],
            [component_sig(item) for item in sorted(rb.components, key=record_key)],
        )

        def endpoint_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item),
                item.parent_id,
                item.net_id,
                item.net_name,
                item.position,
                item.layer,
                item.attributes,
            )

        compare_category(
            "pads",
            [endpoint_sig(item) for item in sorted(sb.pads, key=record_key)],
            [endpoint_sig(item) for item in sorted(rb.pads, key=record_key)],
        )

        def net_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item),
                item.name,
                item.locked,
                item.attributes.get("net_class", item.attributes.get("NetClass")),
                sorted(item.relationships.get("endpoints", [])),
                sorted(item.relationships.get("traces", [])),
                sorted(item.relationships.get("vias", [])),
            )

        compare_category(
            "nets",
            [net_sig(item) for item in sorted(sb.nets, key=record_key)],
            [net_sig(item) for item in sorted(rb.nets, key=record_key)],
        )

        def trace_pair_membership(board: Any) -> dict[str, list[tuple[str, str]]]:
            membership: dict[str, list[tuple[str, str]]] = {}
            for pair in board.differential_pairs:
                for segment in pair.segments:
                    if segment.positive_trace_xml_id:
                        membership.setdefault(segment.positive_trace_xml_id, []).append(
                            (pair.name, "positive")
                        )
                    if segment.negative_trace_xml_id:
                        membership.setdefault(segment.negative_trace_xml_id, []).append(
                            (pair.name, "negative")
                        )
            return membership

        source_pairs = trace_pair_membership(sb)
        reexport_pairs = trace_pair_membership(rb)

        def trace_sig(item: ObjectRecord, pairs: dict[str, list[tuple[str, str]]]) -> Any:
            attrs = item.attributes
            return (
                record_key(item),
                item.net_id,
                item.net_name,
                item.layer,
                item.locked,
                attrs.get("Connected1"),
                attrs.get("Connected2"),
                attrs.get("points", []),
                attrs.get("segment_widths_mm", []),
                attrs.get("segment_layers", []),
                attrs.get("point_via_styles", []),
                attrs.get("point_arc_middle", []),
                sorted(pairs.get(item.xml_id or "", [])),
            )

        compare_category(
            "traces",
            [trace_sig(item, source_pairs) for item in sorted(sb.traces, key=record_key)],
            [trace_sig(item, reexport_pairs) for item in sorted(rb.traces, key=record_key)],
        )

        def via_sig(item: ObjectRecord) -> Any:
            attrs = item.attributes
            return (
                record_key(item),
                item.parent_id,
                item.net_id,
                item.net_name,
                item.position,
                item.layer,
                item.locked,
                attrs.get("via_style"),
                attrs.get("layer_start_id"),
                attrs.get("layer_end_id"),
                attrs.get("span_layer_ids", []),
                attrs.get("diameter_mm"),
                attrs.get("hole_mm"),
            )

        compare_category(
            "vias",
            [via_sig(item) for item in sorted(sb.vias, key=record_key)],
            [via_sig(item) for item in sorted(rb.vias, key=record_key)],
        )
        compare_category(
            "differential_pairs",
            [item.model_dump(mode="json", exclude={"stable_id"}) for item in sb.differential_pairs],
            [item.model_dump(mode="json", exclude={"stable_id"}) for item in rb.differential_pairs],
        )

    if source_snapshot.schematic is not None and reexport_snapshot.schematic is not None:
        ss = source_snapshot.schematic
        rs = reexport_snapshot.schematic
        compare_category("sheets", ss.sheets, rs.sheets)

        def part_sig(item: ObjectRecord) -> Any:
            attrs = item.attributes
            return (
                record_key(item),
                item.name,
                item.value,
                item.position,
                rounded(item.rotation_deg),
                item.mirrored,
                item.locked,
                attrs.get("sheet"),
                attrs.get("component_style"),
                attrs.get("component_part"),
                attrs.get("part_number"),
            )

        compare_category(
            "parts",
            [part_sig(item) for item in sorted(ss.parts, key=record_key)],
            [part_sig(item) for item in sorted(rs.parts, key=record_key)],
        )
        compare_category(
            "patterns",
            [
                (record_key(item), item.attributes.get("component_style"))
                for item in sorted(ss.parts, key=record_key)
            ],
            [
                (record_key(item), item.attributes.get("component_style"))
                for item in sorted(rs.parts, key=record_key)
            ],
        )

        def pin_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item),
                item.parent_id,
                item.net_id,
                item.net_name,
                item.attributes,
            )

        source_pins = [pin_sig(item) for item in sorted(ss.pins, key=record_key)]
        reexport_pins = [pin_sig(item) for item in sorted(rs.pins, key=record_key)]
        compare_category("pins", source_pins, reexport_pins)
        compare_category(
            "pin_net_membership",
            [(item.xml_id, item.net_id, item.net_name) for item in sorted(ss.pins, key=record_key)],
            [(item.xml_id, item.net_id, item.net_name) for item in sorted(rs.pins, key=record_key)],
        )

        def schematic_net_sig(item: ObjectRecord) -> Any:
            return (
                record_key(item),
                item.name,
                item.locked,
                sorted(item.relationships.get("endpoints", [])),
            )

        compare_category(
            "schematic_nets",
            [schematic_net_sig(item) for item in sorted(ss.nets, key=record_key)],
            [schematic_net_sig(item) for item in sorted(rs.nets, key=record_key)],
        )

        def wire_sig(item: ObjectRecord, include_geometry: bool) -> Any:
            base = (
                record_key(item),
                item.net_id,
                item.net_name,
                item.locked,
                item.attributes.get("sheet"),
            )
            return base + ((item.attributes.get("points", []),) if include_geometry else ())

        compare_category(
            "wires",
            [wire_sig(item, False) for item in sorted(ss.wires, key=record_key)],
            [wire_sig(item, False) for item in sorted(rs.wires, key=record_key)],
        )
        compare_category(
            "wire_geometry",
            [wire_sig(item, True) for item in sorted(ss.wires, key=record_key)],
            [wire_sig(item, True) for item in sorted(rs.wires, key=record_key)],
        )
        compare_category(
            "hierarchy",
            [
                (record_key(item), item.attributes.get("sheet"))
                for item in sorted(ss.parts, key=record_key)
            ],
            [
                (record_key(item), item.attributes.get("sheet"))
                for item in sorted(rs.parts, key=record_key)
            ],
        )
        compare_category(
            "buses",
            ss.buses,
            rs.buses,
        )

        def label_signatures(document: DipTraceDocument) -> list[Any]:
            labels: list[Any] = []
            for element in document.container.iter():
                if "label" not in str(element.tag).casefold():
                    continue
                labels.append(
                    (
                        element.tag,
                        tuple(sorted(element.attrib.items())),
                        (element.text or "").strip(),
                        tuple(
                            (
                                child.tag,
                                tuple(sorted(child.attrib.items())),
                                (child.text or "").strip(),
                            )
                            for child in element
                        ),
                    )
                )
            return sorted(labels, key=repr)

        compare_category("labels", label_signatures(source), label_signatures(reexport))

    known_root_children = {"Library", "Board", "Schematic"}
    has_critical_unsupported = False
    for document_label, document in (("source", source), ("reexport", reexport)):
        for child in document.root:
            if child.tag not in known_root_children:
                unsupported.append(
                    {
                        "category": f"unknown_xml_section:{child.tag}",
                        "severity": "critical",
                        "reason": f"Unknown top-level section in {document_label}",
                    }
                )
                has_critical_unsupported = True

    required: set[str] = {"source_type"}
    if source_snapshot.board is not None or reexport_snapshot.board is not None:
        required.update(REQUIRED_PCB_COMPARISON_CATEGORIES)
        required.add("differential_pairs")
    if source_snapshot.schematic is not None or reexport_snapshot.schematic is not None:
        required.update(REQUIRED_SCHEMATIC_COMPARISON_CATEGORIES)
        required.update({"schematic_nets", "buses"})

    missing_required = sorted(required - set(compared))
    comparison_complete = not missing_required
    if missing_required:
        differences.append("missing_required_categories: " + ", ".join(missing_required))

    critical_warnings = [
        warning
        for warning in warnings
        if any(token in warning.casefold() for token in ("error", "invalid", "missing"))
    ]
    passed = (
        not differences
        and comparison_complete
        and not has_critical_unsupported
        and not critical_warnings
    )
    return {
        "passed": passed,
        "comparison_complete": comparison_complete,
        "compared_categories": compared,
        "missing_required_categories": missing_required,
        "differences": differences,
        "ignored_normalizations": _detected_semantic_normalizations(source, reexport),
        "unsupported_categories": unsupported,
        "parse_warnings": warnings,
    }


class DipTraceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = Policy(settings.active_policy)
        retention = settings.retention_policy
        self.sessions = SessionStore(
            settings.state_dir,
            settings.max_document_bytes,
            allowed_roots=settings.allowed_roots,
            retention=retention,
            active_ttl_seconds=settings.live_session_ttl_seconds,
        )
        self.transactions = TransactionStore(settings.state_dir, retention=retention)
        self._raw_preview_retention = retention
        self._raw_previews: RawPreviewStore | None = None
        self.plans = PlanStore(settings.state_dir, retention=retention)
        self.findings = FindingStore(settings.state_dir, retention=retention)
        self.jobs = JobStore(settings.state_dir, retention=retention)
        self.exports = ExportStore(
            settings.state_dir,
            settings.max_document_bytes,
            retention=retention,
        )
        self.backups = BackupStore(settings.state_dir, retention=retention)
        self.external_jobs = ExternalJobManager(settings, self.jobs)
        self.models = ModelCache(max_bytes=settings.model_cache_max_bytes)
        # This package-owned file is the only production root for registry
        # authority. Workspace and state-directory data cannot replace it.
        self._trusted_provenance_registry = TrustedProvenanceRegistry.load_embedded()
        self._service_context = ServiceContext(
            settings=settings,
            policy=self.policy,
            model_cache=self.models,
            transaction_store=self.transactions,
            session_store=self.sessions,
            finding_store=self.findings,
        )
        self._document_gateway = DocumentGateway(settings, self.sessions)
        self._document_targets = self._document_gateway.targets
        self._document_service = DocumentService(
            self._service_context,
            self._document_gateway,
        )
        self._bom_service = BomService(self._service_context, self._document_gateway)
        self._review_service = ReviewService(
            self._service_context,
            self._document_gateway,
        )
        self._semantic_operations_service = SemanticOperationsService(
            self._service_context,
            self._document_gateway,
            self._run_semantic_write,
            self._run_semantic_operations,
        )
        self._workflow_prompt_names: tuple[str, ...] = ()

    @property
    def raw_previews(self) -> RawPreviewStore:
        """Create the optional raw-preview store only when a raw diff is requested."""

        if self._raw_previews is None:
            self._raw_previews = RawPreviewStore(
                self.settings.state_dir,
                retention=self._raw_preview_retention,
            )
        return self._raw_previews

    def set_workflow_prompt_names(self, names: Sequence[str]) -> None:
        """Record the prompt names registered by the concrete MCP server."""

        self._workflow_prompt_names = tuple(sorted(set(names)))

    def _load_seed_provenance(self, seed_path: Path) -> DocumentProvenance | None:
        """Load and validate the provenance sidecar for a seed file.

        Returns the validated DocumentProvenance if a valid sidecar exists,
        or None if no sidecar is present or it fails validation.
        """
        sidecar = seed_path.with_suffix(seed_path.suffix + ".provenance.json")
        if not sidecar.exists():
            return None
        try:
            raw = json.loads(sidecar.read_text())
            return DocumentProvenance.model_validate(raw)
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def _load_and_validate_evidence_manifest(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> ValidatedEvidence:
        """Load and fully validate an evidence manifest referenced by a sidecar.

        This is the single point of truth for trusting evidence-backed sidecars.
        It verifies:
          1. manifest path exists and is within allowed roots
          2. manifest file SHA matches the sidecar's evidence_manifest_sha256
          3. manifest parses as valid JSON matching the expected schema
          4. manifest contains a record for the current document
          5. document SHA in manifest matches the actual document SHA
          6. source_type matches
          7. validation_level matches the claimed level
          8. trust invariants for the level are satisfied
          9. evidence authority boundary is respected

        Raises EditError on any failure (fail-closed).
        """
        if not provenance.evidence_manifest_path:
            raise EditError(
                "Evidence manifest path is required for evidence-backed trust",
                code="evidence_manifest_missing",
            )
        if not provenance.evidence_manifest_sha256:
            raise EditError(
                "Evidence manifest SHA is required for evidence-backed trust",
                code="evidence_manifest_sha_missing",
            )

        # 1. Resolve and verify path is within allowed roots
        try:
            manifest_path = self.settings.resolve_allowed_path(
                provenance.evidence_manifest_path, must_exist=True
            )
        except (EditError, PathAccessError, OSError) as exc:
            raise EditError(
                f"Evidence manifest not found or outside allowed roots: {exc}",
                code="evidence_manifest_not_found",
            ) from exc

        # 2. SHA binding: file content must match sidecar's recorded SHA
        try:
            manifest_bytes = manifest_path.read_bytes()
        except OSError as exc:
            raise EditError(
                f"Cannot read evidence manifest: {exc}",
                code="evidence_manifest_read_error",
            ) from exc

        actual_manifest_sha = sha256_bytes(manifest_bytes)
        if actual_manifest_sha != provenance.evidence_manifest_sha256:
            raise EditError(
                f"Evidence manifest SHA mismatch: expected "
                f"{provenance.evidence_manifest_sha256}, got {actual_manifest_sha}",
                code="evidence_manifest_sha_mismatch",
            )

        # 3. Parse as JSON
        try:
            manifest_data = json.loads(manifest_bytes)
        except json.JSONDecodeError as exc:
            raise EditError(
                f"Evidence manifest is not valid JSON: {exc}",
                code="evidence_manifest_invalid_json",
            ) from exc

        # 4. Validate schema — try user-supplied first, then trusted
        record_data: dict[str, Any] = manifest_data
        evidence_authority = EvidenceAuthority.user_supplied
        try:
            user_record = UserSuppliedRoundtripEvidence.model_validate(manifest_data)
            record_data = user_record.model_dump()
            evidence_authority = EvidenceAuthority.user_supplied
        except ValueError:
            # Not a valid user-supplied record; try trusted
            try:
                trusted_record = TrustedRoundtripEvidence.model_validate(manifest_data)
                record_data = trusted_record.model_dump()
                evidence_authority = trusted_record.authority
            except ValueError as exc:
                raise EditError(
                    f"Evidence manifest schema validation failed: {exc}",
                    code="evidence_manifest_schema_error",
                ) from exc

        # 5. Bind the manifest to this exact target document, not merely bytes
        # with the same hash elsewhere in the workspace.
        doc_sha_from_manifest = record_data["document_sha256"]
        doc_path_from_manifest = record_data["document_path"]
        try:
            manifest_document_path = self.settings.resolve_allowed_path(
                doc_path_from_manifest, must_exist=True
            )
        except (EditError, PathAccessError, OSError) as exc:
            raise EditError(
                f"Evidence document path is unavailable or outside allowed roots: {exc}",
                code="evidence_document_path_invalid",
            ) from exc
        if not same_file_role(manifest_document_path, document_path):
            raise EditError(
                "Evidence manifest is bound to a different document path",
                code="evidence_document_path_mismatch",
            )

        # 6. Document SHA binding
        if doc_sha_from_manifest != provenance.current_document_sha256:
            raise EditError(
                f"Evidence manifest documents SHA {doc_sha_from_manifest} but sidecar "
                f"claims {provenance.current_document_sha256}",
                code="evidence_document_sha_mismatch",
            )

        # 7. Source type validation against the actual current document.
        saved_info = record_data.get("saved", {})
        source_type_from_manifest = ""
        if isinstance(saved_info, dict):
            source_type_from_manifest = saved_info.get("source_type", "")
        actual_document = DipTraceDocument.load(document_path, self.settings.max_document_bytes)
        if source_type_from_manifest != actual_document.source_type:
            raise EditError(
                f"Evidence source type {source_type_from_manifest!r} does not match "
                f"document source type {actual_document.source_type!r}",
                code="evidence_source_type_mismatch",
            )

        # 8. Validation level must match
        level_from_manifest = record_data.get("validation_level", "")
        level_matches = (
            isinstance(level_from_manifest, str)
            and level_from_manifest == provenance.validation_level.value
        )
        if not level_matches and isinstance(level_from_manifest, str):
            raise EditError(
                f"Evidence manifest declares validation_level={level_from_manifest} "
                f"but sidecar claims {provenance.validation_level.value}",
                code="evidence_level_mismatch",
            )

        # 9. Trust invariants: failed evidence cannot grant high trust
        status = record_data.get("status", "recorded")
        if status == "failed" and provenance.validation_level in _HIGH_TRUST_LEVELS:
            raise EditError(
                "Failed evidence record cannot grant high trust",
                code="evidence_failed_no_trust",
            )

        # 10. Authority boundary: user-supplied evidence must not grant high trust
        if (
            evidence_authority == EvidenceAuthority.user_supplied
            and provenance.validation_level in _USER_SUPPLIABLE_TRUST_LEVELS
        ):
            raise EditError(
                f"user-supplied evidence cannot grant "
                f"validation_level={provenance.validation_level.value}",
                code="user_supplied_evidence_cannot_grant_high_trust",
            )

        # 11. Sidecar authority must be compatible with evidence authority
        if (
            provenance.authority == ProvenanceAuthority.user_supplied_evidence
            and evidence_authority not in _TRUSTED_EVIDENCE_AUTHORITIES
            and provenance.validation_level in _HIGH_TRUST_LEVELS
        ):
            raise EditError(
                "user_supplied_evidence sidecar authority cannot hold "
                "high-trust validation_level from user-supplied evidence",
                code="user_supplied_evidence_cannot_grant_high_trust",
            )

        return ValidatedEvidence(
            manifest_path=manifest_path,
            manifest_sha256=actual_manifest_sha,
            document_path=doc_path_from_manifest,
            document_sha256=doc_sha_from_manifest,
            source_type=source_type_from_manifest,
            validation_level=provenance.validation_level,
            authority=evidence_authority,
            record=record_data,
        )

    def _load_and_authorize_trusted_registry_evidence(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> ValidatedEvidence:
        """Resolve high trust only through an exact embedded-registry binding."""

        evidence = self._load_and_validate_evidence_manifest(document_path, provenance)
        if evidence.authority != EvidenceAuthority.trusted_registry:
            raise EditError(
                "Trusted-registry sidecar references evidence from another authority",
                code="trusted_registry_evidence_authority_mismatch",
            )
        entry_id = provenance.trusted_registry_entry_id
        if entry_id is None:
            # DocumentProvenance normally prevents this, but keep the trust
            # boundary fail-closed if a caller bypasses model validation.
            raise EditError(
                "Trusted-registry sidecar has no registry entry id",
                code="trusted_registry_entry_missing",
            )
        try:
            self._trusted_provenance_registry.authorize(
                entry_id=entry_id,
                document_sha256=provenance.current_document_sha256,
                evidence_manifest_sha256=evidence.manifest_sha256,
                source_type=evidence.source_type,
                validation_level=provenance.validation_level,
            )
        except RegistryAuthorizationError as exc:
            raise EditError(
                "Trusted provenance registry did not authorize this exact evidence binding",
                code=exc.code,
            ) from exc
        return evidence

    def _write_provenance_sidecar(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> None:
        """Write a validated provenance sidecar next to a document."""
        sidecar = document_path.with_suffix(document_path.suffix + ".provenance.json")
        atomic_write_bytes(sidecar, provenance.model_dump_json(indent=2).encode())

    def resolve_effective_document_trust(
        self,
        document_path: Path,
        document_sha256: str,
    ) -> EffectiveTrust:
        """Central trust resolution: revalidates sidecar + evidence on every read.

        All trust consumers (document_info, create_document_from_seed, export
        workflows, capability reporting) must use this method.

        Returns an EffectiveTrust with:
          - fail-closed result on any validation failure
          - revalidated evidence manifest SHA binding
          - authority boundary enforcement
        """
        # 1. Load and parse the sidecar
        sidecar_path = document_path.with_suffix(document_path.suffix + ".provenance.json")
        if not sidecar_path.exists():
            return EffectiveTrust(
                validation_level=FixtureValidationLevel.synthetic_parser_only,
                authority="no_sidecar",
                requires_diptrace_verification=True,
            )

        try:
            sidecar_bytes = sidecar_path.read_bytes()
        except OSError:
            return _fail_closed_trust(
                reason="sidecar_read_error",
                warning_code="sidecar_read_error",
            )

        try:
            sidecar_data = json.loads(sidecar_bytes)
        except json.JSONDecodeError:
            return _fail_closed_trust(
                reason="sidecar_invalid_json",
                warning_code="sidecar_invalid_json",
            )

        # 2. Validate sidecar schema
        try:
            provenance = DocumentProvenance.model_validate(sidecar_data)
        except ValueError:
            return _fail_closed_trust(
                reason="sidecar_schema_invalid",
                warning_code="sidecar_schema_invalid",
            )

        # 3. Verify sidecar document SHA matches current document
        if provenance.current_document_sha256 != document_sha256:
            return EffectiveTrust(
                validation_level=FixtureValidationLevel.synthetic_parser_only,
                authority="stale_sidecar",
                requires_diptrace_verification=True,
                warnings=[{"code": "sidecar_sha_mismatch"}],
            )

        # 4. Runtime authority: never grants high trust
        if provenance.authority == ProvenanceAuthority.runtime:
            return EffectiveTrust(
                validation_level=provenance.validation_level,
                authority=provenance.authority.value,
                requires_diptrace_verification=requires_diptrace_verification(
                    provenance.validation_level
                ),
            )

        # 5. User-supplied evidence authority: cannot grant high trust
        if provenance.authority == ProvenanceAuthority.user_supplied_evidence:
            if provenance.validation_level in _HIGH_TRUST_LEVELS:
                return _fail_closed_trust(
                    reason="user_supplied_evidence_cannot_grant_high_trust",
                    warning_code="user_supplied_evidence_cannot_grant_high_trust",
                )
            # Revalidate evidence manifest
            try:
                evidence = self._load_and_validate_evidence_manifest(document_path, provenance)
                return EffectiveTrust(
                    validation_level=provenance.validation_level,
                    authority=provenance.authority.value,
                    requires_diptrace_verification=requires_diptrace_verification(
                        provenance.validation_level
                    ),
                    evidence_manifest_path=str(evidence.manifest_path),
                    evidence_manifest_sha256=evidence.manifest_sha256,
                )
            except EditError as exc:
                return _fail_closed_trust(
                    reason=str(exc),
                    warning_code=exc.payload.code,
                )

        # 6. Fixture-manifest is not an authenticated root of trust yet.
        # Workspace-controlled JSON + matching SHA cannot self-mint high trust.
        if provenance.authority == ProvenanceAuthority.fixture_manifest:
            if provenance.validation_level in _HIGH_TRUST_LEVELS:
                return _fail_closed_trust(
                    reason="fixture_manifest_high_trust_authority_unavailable",
                    warning_code="trusted_fixture_authority_unavailable",
                )
            return EffectiveTrust(
                validation_level=provenance.validation_level,
                authority=provenance.authority.value,
                requires_diptrace_verification=requires_diptrace_verification(
                    provenance.validation_level
                ),
            )

        # 7. Repository-owned registry authority: every document/evidence/type/
        # level field must match a reviewed embedded entry.
        if provenance.authority == ProvenanceAuthority.trusted_registry:
            try:
                evidence = self._load_and_authorize_trusted_registry_evidence(
                    document_path,
                    provenance,
                )
                return EffectiveTrust(
                    validation_level=provenance.validation_level,
                    authority=provenance.authority.value,
                    requires_diptrace_verification=requires_diptrace_verification(
                        provenance.validation_level
                    ),
                    evidence_manifest_path=str(evidence.manifest_path),
                    evidence_manifest_sha256=evidence.manifest_sha256,
                )
            except EditError as exc:
                return _fail_closed_trust(
                    reason=str(exc),
                    warning_code=exc.payload.code,
                )

    def invalidate_document_trust_after_write(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str = "mcp_write",
    ) -> None:
        """Downgrade trust after any MCP write operation.

        After an MCP-modified write, the bytes are no longer the original
        DipTrace export.  This helper updates (or creates) the sidecar to
        reflect the synthetic state while preserving parent provenance.
        """
        new_sidecar = self._invalidated_document_provenance(
            document_path,
            document_sha256,
            operation_name=operation_name,
        )
        self._write_provenance_sidecar(document_path, new_sidecar)

    def _invalidated_document_provenance(
        self,
        document_path: Path,
        document_sha256: str,
        *,
        operation_name: str,
    ) -> DocumentProvenance:
        """Build the exact trust downgrade before a guarded sidecar replace."""

        old_sidecar = self._load_seed_provenance(document_path)
        parent_level: FixtureValidationLevel | None = None
        seed_sha: str | None = None
        if old_sidecar is not None:
            # Preserve the deepest parent level from the chain
            parent_level = old_sidecar.parent_validation_level or old_sidecar.validation_level
            seed_sha = old_sidecar.seed_sha256
        return DocumentProvenance(
            provenance="mcp_modified" + (f"_from_{parent_level.value}" if parent_level else ""),
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            current_document_sha256=document_sha256,
            seed_sha256=seed_sha,
            parent_validation_level=parent_level,
            last_modified_by=operation_name,
        )

    def resolve_target(self, path: str | None) -> DocumentTarget:
        return self._document_gateway.resolve_target(path)

    def load(self, path: str | None) -> tuple[DipTraceDocument, DocumentTarget]:
        return self._document_gateway.load(path)

    def _load_overwrite_target(
        self,
        target: Path,
        *,
        overwrite: bool,
        expected_sha256: str | None,
    ) -> DipTraceDocument | None:
        """Bind an explicit overwrite to the caller's view of the existing bytes."""

        if not target.exists():
            return None
        if not overwrite:
            raise EditError(
                f"Target already exists (pass overwrite=true to replace): {target}",
                code="path_exists",
                details={"path": str(target)},
            )
        if expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required when overwrite=true replaces an existing target",
                details={"path": str(target)},
            )
        document = DipTraceDocument.load(target, self.settings.max_document_bytes)
        if document.sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {document.sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": document.sha256,
                    "path": str(target),
                },
            )
        return document

    @staticmethod
    def _require_current_target_sha256(target: Path, expected_sha256: str) -> None:
        """Repeat a caller-SHA check immediately before replacing design bytes."""

        try:
            current_sha256 = sha256_bytes(target.read_bytes())
        except OSError as exc:
            raise EditError(
                f"Cannot read target before write: {target}",
                details={"path": str(target)},
            ) from exc
        if current_sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {current_sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": current_sha256,
                    "path": str(target),
                },
            )

    @staticmethod
    def _require_target_still_absent(target: Path) -> None:
        """Refuse if a path appeared while a new document was being validated."""

        if target.exists():
            raise EditError(
                "Target appeared while document creation was being validated; "
                "reload it and retry through the overwrite SHA gate",
                code="path_exists",
                details={"path": str(target)},
            )

    @staticmethod
    def _read_optional_transaction_file(
        path: Path,
        *,
        txid: str,
        phase: str,
    ) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise TransactionConflictError(
                f"Cannot read transaction-bound file during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "current_sha256": None,
                },
                txid=txid,
            ) from exc

    @classmethod
    def _require_optional_transaction_file_unchanged(
        cls,
        path: Path,
        expected: bytes | None,
        *,
        txid: str,
        phase: str,
    ) -> None:
        current = cls._read_optional_transaction_file(path, txid=txid, phase=phase)
        if current != expected:
            raise TransactionConflictError(
                f"Transaction-bound file changed during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "expected_sha256": (sha256_bytes(expected) if expected is not None else None),
                    "current_sha256": (sha256_bytes(current) if current is not None else None),
                },
                txid=txid,
            )

    @classmethod
    def _compensate_transaction_file(
        cls,
        path: Path,
        *,
        written: bytes,
        previous: bytes | None,
        txid: str,
        phase: str,
    ) -> None:
        """Restore pre-call bytes only while this call still owns the current bytes."""

        current = cls._read_optional_transaction_file(path, txid=txid, phase=phase)
        if current == previous:
            return
        if current != written:
            raise TransactionConflictError(
                f"Refusing to overwrite unexpected bytes during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "written_sha256": sha256_bytes(written),
                    "previous_sha256": (sha256_bytes(previous) if previous is not None else None),
                    "current_sha256": (sha256_bytes(current) if current is not None else None),
                },
                txid=txid,
            )
        try:
            if previous is None:
                path.unlink()
            else:
                atomic_write_bytes(path, previous)
        except OSError as exc:
            after_error = cls._read_optional_transaction_file(
                path,
                txid=txid,
                phase=phase,
            )
            if after_error == previous:
                return
            raise TransactionConflictError(
                f"Cannot restore transaction-bound file during {phase}: {path}",
                details={
                    "phase": phase,
                    "path": str(path),
                    "written_sha256": sha256_bytes(written),
                    "previous_sha256": (sha256_bytes(previous) if previous is not None else None),
                    "current_sha256": (
                        sha256_bytes(after_error) if after_error is not None else None
                    ),
                },
                txid=txid,
            ) from exc
        cls._require_optional_transaction_file_unchanged(
            path,
            previous,
            txid=txid,
            phase=phase,
        )

    def _load_transaction_backup_bytes(
        self,
        txid: str,
        *,
        expected_sha256: str,
        phase: str,
    ) -> bytes:
        backup_path = self.transactions.require_backup(txid)
        try:
            backup_bytes = backup_path.read_bytes()
        except OSError as exc:
            raise TransactionConflictError(
                "Transaction backup cannot be read during recovery",
                details={
                    "phase": phase,
                    "path": str(backup_path),
                    "expected_sha256": expected_sha256,
                    "current_sha256": None,
                },
                txid=txid,
            ) from exc
        backup_sha256 = sha256_bytes(backup_bytes)
        if backup_sha256 != expected_sha256:
            raise TransactionConflictError(
                "Transaction backup does not match its source SHA-256",
                details={
                    "phase": phase,
                    "path": str(backup_path),
                    "expected_sha256": expected_sha256,
                    "current_sha256": backup_sha256,
                },
                txid=txid,
            )
        return backup_bytes

    def load_document_id(self, document_id: str) -> tuple[DipTraceDocument, DocumentTarget]:
        return self._document_gateway.load_document_id(document_id)

    def status(self) -> dict[str, Any]:
        active = self.sessions.active_metadata()
        if active is not None:
            session_id = str(active["session_id"])
            working = self.sessions.working_path(session_id)
            active = {
                **active,
                "working_path": str(working),
                "working_sha256": self.sessions.working_sha256(session_id),
            }
        capabilities = self.get_capabilities()
        return {
            "server": "diptrace-mcp",
            "version": __version__,
            "configuration": self.settings.as_dict(),
            "active_session": active,
            "last_session_transition": self.sessions.last_session_transition(),
            "model_cache": self.models.stats(),
            "capabilities": capabilities,
        }

    def get_capabilities(self, path: str | None = None) -> dict[str, Any]:
        if path is None:
            active = self.sessions.active_metadata()
            if active is None:
                report = build_capability_report(
                    None,
                    workflow_prompt_names=self._workflow_prompt_names,
                ).model_dump()
                return self._add_runtime_capabilities(report)
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        effective_trust = self.resolve_effective_document_trust(
            target.path,
            snapshot.info.sha256,
        )
        report = build_capability_report(
            snapshot,
            workflow_prompt_names=self._workflow_prompt_names,
            document_trust={
                "validation_level": effective_trust.validation_level.value,
                "trust_authority": effective_trust.authority,
                "requires_diptrace_verification": (effective_trust.requires_diptrace_verification),
                "evidence_manifest_path": effective_trust.evidence_manifest_path,
                "evidence_manifest_sha256": effective_trust.evidence_manifest_sha256,
                "warnings": effective_trust.warnings,
            },
        ).model_dump()
        report = self._add_runtime_capabilities(report)
        dsn_reasons = dsn_export_limitations(snapshot)
        report["write_capabilities"]["autorouter_dsn_export"] = not dsn_reasons
        if dsn_reasons:
            report["reasons_unavailable"].append(
                {
                    "feature": "autorouter_dsn_export",
                    "code": "capability_unavailable",
                    "message": (
                        "Current document cannot be represented by the bounded DSN serializer."
                    ),
                    "details": {"reasons": dsn_reasons},
                }
            )
        return report

    def trusted_provenance_registry_report(self) -> dict[str, object]:
        """Disclose the exact repository-owned high-trust registry state."""

        return self._trusted_provenance_registry.report()

    def _add_runtime_capabilities(self, report: dict[str, Any]) -> dict[str, Any]:
        """Add configured adapter, resource-limit and policy state once."""

        probe = self.external_jobs.freerouting.probe()
        report["external_adapters"]["freerouting"] = probe.as_dict()
        report["external_adapters"]["ngspice"] = self.external_jobs.ngspice.probe().as_dict()
        openems_probe = self.external_jobs.openems.probe()
        report["external_adapters"]["openems"] = openems_probe.as_dict()
        report["limits"]["max_document_bytes"] = self.settings.max_document_bytes
        report["limits"]["max_model_cache_bytes"] = self.settings.model_cache_max_bytes
        report["limits"]["max_external_log_bytes"] = self.settings.max_external_log_bytes
        report["limits"]["max_external_processes"] = self.settings.max_external_processes
        report["limits"]["max_external_result_bytes"] = self.settings.max_external_result_bytes
        report["limits"]["max_board_model_response_bytes"] = BOARD_MODEL_RESPONSE_BYTE_LIMIT
        report["limits"]["max_board_model_item_detail_bytes"] = BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT
        report["limits"]["max_raw_edit_response_bytes"] = RAW_EDIT_RESPONSE_BYTE_LIMIT
        report["limits"]["max_raw_edit_xpath_characters"] = RAW_EDIT_XPATH_CHARACTER_LIMIT
        report["limits"]["max_diff_lines"] = DEFAULT_DIFF_LINE_LIMIT
        report["limits"]["max_diff_characters"] = DEFAULT_DIFF_CHARACTER_LIMIT
        report["limits"]["max_preview_copper_records"] = PREVIEW_COPPER_RECORD_LIMIT
        report["limits"]["max_preview_copper_points"] = PREVIEW_COPPER_POINT_LIMIT
        report["limits"]["retention_max_records"] = self.settings.retention_max_records
        report["limits"]["retention_max_age_days"] = self.settings.retention_max_age_days
        report["limits"]["live_session_ttl_seconds"] = self.settings.live_session_ttl_seconds
        registry_report = self.trusted_provenance_registry_report()
        report["trust_model"]["trusted_registry"] = registry_report
        report["trust_model"]["high_trust_authority"] = (
            "trusted_registry_exact_hash_allowlist"
            if self._trusted_provenance_registry.entry_count > 0
            else "trusted_registry_available_no_reviewed_entries"
        )
        report["policy"].update(self.policy.capability_payload())
        if probe.available:
            report["reasons_unavailable"] = [
                item
                for item in report["reasons_unavailable"]
                if item.get("feature") != "external_autorouting"
            ]
        if openems_probe.available:
            report["reasons_unavailable"] = [
                item
                for item in report["reasons_unavailable"]
                if item.get("feature") != "external_si_pi_solver"
            ]
        return report

    def document_info(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        info = self.models.get(document, live_session=target.is_live).info
        result = info.model_dump()
        # Revalidate trust through the central resolver (§8)
        effective = self.resolve_effective_document_trust(target.path, info.sha256)
        result["validation_level"] = effective.validation_level.value
        result["requires_diptrace_verification"] = effective.requires_diptrace_verification
        result["trust_authority"] = effective.authority
        if effective.evidence_manifest_path:
            result["evidence_manifest_path"] = effective.evidence_manifest_path
        if effective.evidence_manifest_sha256:
            result["evidence_manifest_sha256"] = effective.evidence_manifest_sha256
        if effective.warnings:
            result["trust_warnings"] = effective.warnings
        return self._read_success(info, result)

    def board_model(
        self,
        path: str | None = None,
        *,
        section: BoardModelSection = "summary",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._document_service.board_model(path, section=section, offset=offset, limit=limit)

    def schematic_model(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.schematic_model(path)

    def library_model(self, path: str) -> dict[str, Any]:
        return self._bom_service.library_model(path)

    def scan_component_libraries(
        self, root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        return self._scan_libraries("DipTrace-ComponentLibrary", root, recursive)

    def scan_pattern_libraries(
        self, root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        return self._scan_libraries("DipTrace-PatternLibrary", root, recursive)

    def query_library_items(
        self,
        path: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._bom_service.query_library_items(path, query, offset, limit)

    def get_library_component(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.get_library_component(path, stable_id_value, name)

    def get_library_pattern(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.get_library_pattern(path, stable_id_value, name)

    def validate_library_component(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.validate_library_component(path, stable_id_value, name)

    def validate_library_pattern(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.validate_library_pattern(path, stable_id_value, name)

    def validate_pin_pad_mapping(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.validate_pin_pad_mapping(path, stable_id_value, name)

    def get_bom(
        self,
        path: str | None = None,
        *,
        grouped: bool = False,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        return self._bom_service.get_bom(path, grouped=grouped, include_dnp=include_dnp)

    def export_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        record = create_bom_export(self.exports, snapshot, include_dnp=include_dnp)
        return self._read_success(
            snapshot.info,
            {"export": record.model_dump(mode="json")},
            resources=export_resources(record),
            limitations=record.limitations,
        )

    def export_fabrication_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        if request_native_outputs:
            raise CapabilityUnavailableError(
                "Authoritative Gerber/NC drill export is unavailable from confirmed XML semantics. "
                "Call with request_native_outputs=false to create a review manifest bundle.",
                details={"not_generated": ["gerber", "nc_drill", "odb++", "ipc-2581"]},
            )
        return self._export_release_manifest(
            path,
            export_type="fabrication_manifest",
            include_dnp=include_dnp,
        )

    def export_assembly_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = False,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        if request_native_outputs:
            raise CapabilityUnavailableError(
                "Authoritative vendor-specific assembly output is unavailable. "
                "Call with request_native_outputs=false for generic placement and BOM artifacts.",
                details={"not_generated": ["vendor_cpl", "assembly_drawing"]},
            )
        return self._export_release_manifest(
            path,
            export_type="assembly_manifest",
            include_dnp=include_dnp,
        )

    def _export_release_manifest(
        self,
        path: str | None,
        *,
        export_type: Literal["fabrication_manifest", "assembly_manifest"],
        include_dnp: bool,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        record = create_release_manifest(
            self.exports,
            snapshot,
            export_type=export_type,
            include_dnp=include_dnp,
        )
        return self._read_success(
            snapshot.info,
            {"export": record.model_dump(mode="json")},
            resources=export_resources(record),
            limitations=record.limitations,
        )

    def review_bom(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.review_bom(path)

    def compare_bom_to_design(
        self,
        external_records: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.compare_bom_to_design(external_records, path=path)

    def find_missing_component_fields(
        self,
        required_fields: list[str],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._bom_service.find_missing_component_fields(required_fields, path=path)

    def group_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        return self._bom_service.group_bom(path, include_dnp=include_dnp)

    def detect_duplicate_bom_items(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.detect_duplicate_bom_items(path)

    def validate_mpn_consistency(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.validate_mpn_consistency(path)

    def validate_value_pattern_consistency(self, path: str | None = None) -> dict[str, Any]:
        return self._bom_service.validate_value_pattern_consistency(path)

    def compare_schematic_to_pcb(self, schematic_path: str, pcb_path: str) -> dict[str, Any]:
        schematic_document, schematic_target = self.load(schematic_path)
        pcb_document, pcb_target = self.load(pcb_path)
        schematic = self.models.get(schematic_document, live_session=schematic_target.is_live)
        pcb = self.models.get(pcb_document, live_session=pcb_target.is_live)
        result = compare_design_snapshots(schematic, pcb)
        return self._read_success(
            schematic.info,
            {
                **result,
                "pcb_document": pcb.info.model_dump(mode="json"),
            },
            limitations=result["limitations"],
        )

    def sync_schematic_to_pcb(
        self,
        schematic_path: str,
        pcb_path: str,
        *,
        component_mappings: list[dict[str, Any]] | None = None,
        placement: dict[str, Any] | None = None,
        pattern_library_paths: list[str] | None = None,
        update_existing_properties: bool = True,
        create_ratlines: bool = True,
        allow_reconnect: bool = False,
        reconciliation_mode: Literal["additive", "exact"] = "additive",
        allow_locked_reconciliation: bool = False,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        schematic_document, _ = self.load(schematic_path)
        pcb_document, _ = self.load(pcb_path)
        pattern_documents = [self.load(path)[0] for path in pattern_library_paths or []]
        plan = build_sync_plan(
            schematic_document,
            pcb_document,
            mappings=[
                ComponentSyncMapping.model_validate(item) for item in component_mappings or []
            ],
            placement=SyncPlacement.model_validate(placement or {}),
            pattern_documents=pattern_documents,
            update_existing_properties=update_existing_properties,
            create_ratlines=create_ratlines,
            allow_reconnect=allow_reconnect,
            reconciliation_mode=reconciliation_mode,
            allow_locked_reconciliation=allow_locked_reconciliation,
        )
        response = self._run_semantic_write(
            plan.operation,
            pcb_path,
            dry_run,
            expected_sha256,
            txid,
        )
        response["warnings"] = [*plan.warnings, *response.get("warnings", [])]
        response["limitations"] = [
            *plan.limitations,
            *response.get("limitations", []),
        ]
        response.setdefault("result", {})["schematic_source"] = {
            "path": str(schematic_document.path),
            "sha256": schematic_document.sha256,
        }
        return response

    def query_objects(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "stable_id",
    ) -> dict[str, Any]:
        return self._document_service.query_objects(path, selector, offset, limit, sort_by)

    def get_object(self, stable_id_value: str, path: str | None = None) -> dict[str, Any]:
        return self._document_service.get_object(stable_id_value, path)

    def get_connectivity_graph(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.get_connectivity_graph(path)

    def document_resource(self, document_id: str, resource: str) -> str:
        return self._document_service.document_resource(document_id, resource)

    def transaction_summary_resource(self, txid: str) -> str:
        return json.dumps(
            transaction_response_summary(self.transactions.read(txid)),
            ensure_ascii=False,
            indent=2,
        )

    def raw_preview_diff_resource(self, preview_id: str) -> str:
        return self.raw_previews.read_diff(preview_id)

    def summarize(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.summarize(path)

    def components(
        self,
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._document_service.components(path, query, offset, limit)

    def component(self, refdes: str, path: str | None = None) -> dict[str, Any]:
        return self._document_service.component(refdes, path)

    def nets(
        self,
        path: str | None = None,
        query: str | None = None,
        include_endpoints: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._document_service.nets(path, query, include_endpoints, offset, limit)

    def rules(self, path: str | None = None) -> dict[str, Any]:
        return self._document_service.rules(path)

    def read_xml(
        self,
        path: str | None = None,
        xpath: str = ".",
        max_matches: int = 25,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        return self._document_service.read_xml(path, xpath, max_matches, max_characters)

    def apply_edits(
        self,
        edits: list[XmlEdit],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=dry_run, operation="apply_xml_edits")
        if len(edits) > 50:
            raise EditError("A single call can contain at most 50 edits")
        if not dry_run and not expected_sha256:
            raise EditError("expected_sha256 from a dry-run is required when dry_run=false")
        document, target = self.load(path)
        before = document.raw_bytes
        before_document = DipTraceDocument.from_bytes(document.path, before)
        before_sha256 = sha256_bytes(before)
        if expected_sha256 and before_sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {before_sha256}",
                details={"expected_sha256": expected_sha256, "current_sha256": before_sha256},
            )
        after, previews = document.apply_edits(edits)
        impact = write_impact(before_document, document)
        require_write_impact(impact, operation="apply_xml_edits")
        after_sha256 = sha256_bytes(after)
        changed = before != after
        if not dry_run and changed:
            assert expected_sha256 is not None
            self._require_current_target_sha256(target.path, expected_sha256)
        diff, diff_metadata = unified_xml_diff_preview(before, after)
        preview_id, diff_resource = self.raw_previews.store(diff, diff_metadata)
        bounded_previews = _bounded_raw_edit_previews(previews)
        result: dict[str, Any] = {
            "path": str(target.path),
            "live_session": target.is_live,
            "session_id": target.live_session_id,
            "dry_run": dry_run,
            "changed": changed,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "operations": bounded_previews,
            "operations_metadata": {
                "edit_count": len(bounded_previews),
                "total_match_count": sum(int(preview["matches"]) for preview in bounded_previews),
                "snippets_inline": False,
                "xpath_character_limit": RAW_EDIT_XPATH_CHARACTER_LIMIT,
            },
            "changed_ids": list(impact.changed_ids),
            "write_object_count": impact.object_count,
            "diff": {
                "inline": False,
                "preview_id": preview_id,
                "resource_uri": diff_resource,
                "mime_type": "text/plain",
                **diff_metadata,
            },
            "resources": [diff_resource],
        }
        if dry_run or not changed:
            result["written"] = False
            return _finalize_raw_edit_response(result)

        # Refuse before touching the design if even worst-case bounded write
        # metadata could exceed the public response contract. JSON escaping can
        # expand one character to six bytes, hence the control-character probe.
        preflight = dict(result)
        preflight.update(
            {
                "written": True,
                "backup": "\x00" * 4_096,
                "backup_character_count": 4_096,
                "backup_truncated": True,
                "written_at": utc_now(),
            }
        )
        _finalize_raw_edit_response(preflight)

        assert expected_sha256 is not None
        if target.live_session_id:

            def finalize_live_raw_edit(_mutation: object) -> None:
                DipTraceDocument.load(target.path, self.settings.max_document_bytes)
                sidecar_path = target.path.with_suffix(target.path.suffix + ".provenance.json")
                try:
                    previous_sidecar = sidecar_path.read_bytes()
                except FileNotFoundError:
                    previous_sidecar = None
                prepared = self._invalidated_document_provenance(
                    target.path,
                    after_sha256,
                    operation_name="mcp_apply_xml_edits",
                )
                attempted_sidecar = prepared.model_dump_json(indent=2).encode()
                try:
                    self._write_provenance_sidecar(target.path, prepared)
                except Exception:
                    try:
                        current_sidecar = sidecar_path.read_bytes()
                    except FileNotFoundError:
                        current_sidecar = None
                    if current_sidecar == attempted_sidecar:
                        if previous_sidecar is None:
                            sidecar_path.unlink(missing_ok=True)
                        else:
                            atomic_write_bytes(sidecar_path, previous_sidecar)
                    raise

            mutation = self.sessions.mutate_working(
                target.live_session_id,
                expected_sha256=expected_sha256,
                replacement=after,
                after_write=finalize_live_raw_edit,
            )
            backup = mutation.backup
        else:
            self._require_current_target_sha256(target.path, expected_sha256)
            backup = write_with_backup(
                target.path,
                after,
                self.backups,
                expected_sha256=expected_sha256,
            )
            DipTraceDocument.load(target.path, self.settings.max_document_bytes)
            # Invalidate trust after MCP modification
            self.invalidate_document_trust_after_write(
                target.path,
                after_sha256,
                operation_name="mcp_apply_xml_edits",
            )
        backup_text = str(backup)
        backup_preview, backup_truncated = _bounded_text(backup_text, 4_096)
        result.update(
            {
                "written": True,
                "backup": backup_preview,
                "backup_character_count": len(backup_text),
                "backup_truncated": backup_truncated,
                "written_at": utc_now(),
            }
        )
        return _finalize_raw_edit_response(result)

    def create_document(
        self,
        kind: str,
        path: str,
        *,
        sheets: list[str] | None = None,
        pcb: dict[str, Any] | None = None,
        units: str = "mm",
        format_version: str = DEFAULT_FORMAT_VERSION,
        overwrite: bool = False,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a brand-new synthetic DipTrace-shaped XML document."""

        self.policy.require_write(dry_run=False, operation="create_document")
        if units not in {"mm", "inch", "mil"}:
            raise EditError(f"Unsupported document units: {units!r}", code="invalid_request")
        format_version = validate_format_version(format_version)
        target = self.settings.resolve_allowed_path(path, must_exist=False)
        if target.exists() and not overwrite:
            raise EditError(
                f"Target already exists (pass overwrite=true to replace): {target}",
                code="path_exists",
                details={"path": str(target)},
            )
        if kind == "schematic":
            scaffold = SchematicScaffold(sheet_names=sheets) if sheets else None
            raw = build_schematic_document(scaffold, units=units, version=format_version)
        elif kind == "pcb":
            scaffold_pcb = PcbScaffold.model_validate(pcb or {})
            raw = build_pcb_document(scaffold_pcb, units=units, version=format_version)
        else:
            raise EditError(
                f"Unsupported document kind for creation: {kind!r}",
                code="invalid_request",
            )
        # Validate the generated bytes before they ever reach the filesystem.
        candidate = DipTraceDocument.from_bytes(target, raw)
        snapshot = build_snapshot(candidate)
        previous = self._load_overwrite_target(
            target,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )
        impact = write_impact(previous, candidate)
        require_write_impact(impact, operation="create_document")
        if previous is not None:
            assert expected_sha256 is not None
            self._require_current_target_sha256(target, expected_sha256)
            written = write_with_backup(
                target,
                raw,
                self.backups,
                expected_sha256=expected_sha256,
            )
            backup: str | None = str(written)
        else:
            self._require_target_still_absent(target)
            atomic_write_bytes(target, raw)
            backup = None
        loaded = DipTraceDocument.load(target, self.settings.max_document_bytes)
        if loaded.sha256 != sha256_bytes(raw):
            raise EditError(
                "Created document failed the post-write checksum verification",
                details={"path": str(target)},
            )
        info = build_snapshot(loaded).info
        # Write provenance sidecar for synthetic documents
        sidecar = DocumentProvenance(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.synthetic_parser_only,
            current_document_sha256=loaded.sha256,
        )
        self._write_provenance_sidecar(target, sidecar)
        return self._read_success(
            info,
            {
                "created": True,
                "kind": kind,
                "path": str(target),
                "size_bytes": len(raw),
                "sha256": loaded.sha256,
                "backup": backup,
                "write_object_count": impact.object_count,
                "summary": {
                    "sheets": len(snapshot.schematic.sheets) if snapshot.schematic else None,
                    "layers": len(snapshot.board.layers) if snapshot.board else None,
                },
                "provenance": "mcp_generated",
                "validation_level": "synthetic_parser_only",
                "requires_diptrace_verification": True,
                "format_version": loaded.version,
            },
            warnings=snapshot.warnings,
        )

    def create_document_from_seed(
        self,
        seed_path: str,
        target_path: str,
        *,
        expected_seed_sha256: str | None = None,
        overwrite: bool = False,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a new document by copying an existing DipTrace-shaped XML seed.

        The seed file must be valid DipTrace XML (PCB, Schematic, ComponentLibrary,
        or PatternLibrary). The copy preserves all unknown XML, line endings, and
        unsupported sections.

        **Trust model:** The client cannot assign a validation level.  Trust is
        derived exclusively from verifiable metadata (provenance sidecar or
        fixture manifest) found alongside the seed.  If no metadata is present,
        the copy defaults to ``synthetic_parser_only``.
        """
        self.policy.require_write(dry_run=False, operation="create_document_from_seed")
        seed = self.settings.resolve_allowed_path(seed_path, must_exist=True)
        seed_bytes = seed.read_bytes()
        if len(seed_bytes) > self.settings.max_document_bytes:
            raise EditError(
                f"Seed file exceeds max document size: {len(seed_bytes)} bytes",
                code="document_too_large",
            )
        # Pre-copy SHA check
        seed_sha256 = sha256_bytes(seed_bytes)
        if expected_seed_sha256 is not None and expected_seed_sha256 != seed_sha256:
            raise EditError(
                f"Seed SHA-256 mismatch: expected {expected_seed_sha256}, got {seed_sha256}",
                code="sha256_mismatch",
            )
        # Validate seed through the parser
        seed_doc = DipTraceDocument.from_bytes(seed, seed_bytes)
        source_type = seed_doc.source_type
        if source_type not in {
            "DipTrace-PCB",
            "DipTrace-Schematic",
            "DipTrace-ComponentLibrary",
            "DipTrace-PatternLibrary",
        }:
            raise EditError(
                f"Unsupported seed source type: {source_type!r}",
                code="invalid_request",
            )
        target = self.settings.resolve_allowed_path(target_path, must_exist=False)
        previous = self._load_overwrite_target(
            target,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )
        impact = write_impact(previous, seed_doc)
        require_write_impact(impact, operation="create_document_from_seed")
        # Copy seed bytes verbatim — do not modify unknown XML
        if previous is not None:
            assert expected_sha256 is not None
            self._require_current_target_sha256(target, expected_sha256)
            written = write_with_backup(
                target,
                seed_bytes,
                self.backups,
                expected_sha256=expected_sha256,
            )
            backup: str | None = str(written)
        else:
            self._require_target_still_absent(target)
            atomic_write_bytes(target, seed_bytes)
            backup = None
        loaded = DipTraceDocument.load(target, self.settings.max_document_bytes)
        if loaded.sha256 != seed_sha256:
            raise EditError(
                "Seed copy failed the post-write checksum verification",
                details={"path": str(target)},
            )
        # Determine trust from verifiable seed metadata only
        seed_sidecar = self._load_seed_provenance(seed)
        # Default: unknown origin → synthetic
        trust_level = FixtureValidationLevel.synthetic_parser_only
        trust_provenance = "seed_copy_unknown_origin"
        parent_level: FixtureValidationLevel | None = None
        copy_authority = ProvenanceAuthority.runtime
        evidence_path: str | None = None
        evidence_sha: str | None = None
        if seed_sidecar is not None:
            # Validate the sidecar: SHA must match
            if seed_sidecar.current_document_sha256 != seed_sha256:
                # Stale sidecar — do not trust at all
                trust_provenance = "seed_copy_stale_sidecar"
            elif seed_sidecar.authority == ProvenanceAuthority.runtime:
                # Runtime sidecar: even if it claims a high level, we downgrade.
                # A runtime sidecar can never grant high trust.
                trust_level = FixtureValidationLevel.synthetic_parser_only
                trust_provenance = "seed_copy_runtime_sidecar_downgraded"
                parent_level = seed_sidecar.validation_level
            elif seed_sidecar.authority == ProvenanceAuthority.user_supplied_evidence:
                # User-supplied evidence: revalidate but cannot grant high trust
                try:
                    evidence = self._load_and_validate_evidence_manifest(seed, seed_sidecar)
                    # User-supplied evidence can never grant high trust
                    if evidence.validation_level in _HIGH_TRUST_LEVELS:
                        trust_level = FixtureValidationLevel.synthetic_parser_only
                        trust_provenance = "seed_copy_user_supplied_no_high_trust"
                        parent_level = evidence.validation_level
                    else:
                        trust_level = evidence.validation_level
                        trust_provenance = "seed_copy_user_supplied_evidence"
                        parent_level = evidence.validation_level
                    copy_authority = ProvenanceAuthority.user_supplied_evidence
                    evidence_path = str(evidence.manifest_path)
                    evidence_sha = evidence.manifest_sha256
                except EditError:
                    trust_level = FixtureValidationLevel.synthetic_parser_only
                    trust_provenance = "seed_copy_evidence_validation_failed"
                    parent_level = seed_sidecar.validation_level
            elif seed_sidecar.authority == ProvenanceAuthority.fixture_manifest:
                # Fixture manifest: MUST validate the actual manifest file
                try:
                    evidence = self._load_and_validate_evidence_manifest(seed, seed_sidecar)
                    trust_level = evidence.validation_level
                    trust_provenance = "seed_copy_of_verified_fixture"
                    parent_level = evidence.validation_level
                    copy_authority = seed_sidecar.authority
                    evidence_path = str(evidence.manifest_path)
                    evidence_sha = evidence.manifest_sha256
                except EditError:
                    trust_level = FixtureValidationLevel.synthetic_parser_only
                    trust_provenance = "seed_copy_evidence_validation_failed"
                    parent_level = seed_sidecar.validation_level
            elif seed_sidecar.authority == ProvenanceAuthority.trusted_registry:
                try:
                    evidence = self._load_and_authorize_trusted_registry_evidence(
                        seed,
                        seed_sidecar,
                    )
                    # An exact byte copy does not preserve the manifest's
                    # path-role binding. A new reviewed evidence entry for the
                    # target is required before the copy may regain authority.
                    trust_provenance = "seed_copy_trusted_registry_requires_target_evidence"
                    parent_level = evidence.validation_level
                except EditError:
                    trust_provenance = "seed_copy_trusted_registry_validation_failed"
                    parent_level = None
        # Write provenance sidecar for the new copy
        sidecar = DocumentProvenance(
            provenance=trust_provenance,
            validation_level=trust_level,
            current_document_sha256=loaded.sha256,
            seed_sha256=seed_sha256,
            parent_validation_level=parent_level,
            authority=copy_authority,
            evidence_manifest_path=evidence_path,
            evidence_manifest_sha256=evidence_sha,
            last_modified_by="mcp_create_document_from_seed",
        )
        sidecar_path = target.with_suffix(target.suffix + ".provenance.json")
        atomic_write_bytes(sidecar_path, sidecar.model_dump_json(indent=2).encode())
        snapshot = build_snapshot(loaded)
        return self._read_success(
            snapshot.info,
            {
                "created": True,
                "kind": source_type.split("-", 1)[-1].lower(),
                "path": str(target),
                "size_bytes": len(seed_bytes),
                "sha256": loaded.sha256,
                "backup": backup,
                "write_object_count": impact.object_count,
                "seed_path": str(seed),
                "seed_sha256": seed_sha256,
                "format_version": loaded.version,
                "provenance": trust_provenance,
                "validation_level": trust_level.value,
                "requires_diptrace_verification": requires_diptrace_verification(trust_level),
                "summary": {
                    "sheets": len(snapshot.schematic.sheets) if snapshot.schematic else None,
                    "layers": len(snapshot.board.layers) if snapshot.board else None,
                },
            },
            warnings=snapshot.warnings,
        )

    def begin_transaction(
        self,
        path: str | None = None,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=True, operation="begin_transaction")
        document, target = self.load(path)
        snapshot = build_snapshot(document, live_session=target.is_live)
        if expected_sha256 is not None and expected_sha256 != snapshot.info.sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {snapshot.info.sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": snapshot.info.sha256,
                },
            )
        record = self.transactions.create(
            snapshot.info,
            target.path,
            source_sha256=snapshot.info.sha256,
            expected_sha256=expected_sha256 or snapshot.info.sha256,
            notes=notes,
        )
        self.transactions.store_snapshot(record.txid, document.raw_bytes)
        # Backup existing provenance sidecar for rollback restoration
        sidecar_path = target.path.with_suffix(target.path.suffix + ".provenance.json")
        provenance_backup: str | None = None
        provenance_backup_sha: str | None = None
        if sidecar_path.exists():
            try:
                prov_bytes = sidecar_path.read_bytes()
                prov_backup = self.transactions.store_provenance_backup(
                    record.txid,
                    prov_bytes,
                )
                provenance_backup = str(prov_backup)
                provenance_backup_sha = sha256_bytes(prov_bytes)
            except OSError:
                provenance_backup = None
                provenance_backup_sha = None
        updated = self.transactions.update(
            record.txid,
            status="staged",
            snapshot_path=str(self.transactions.snapshot_path(record.txid)),
            provenance_backup_path=provenance_backup,
            provenance_backup_sha256=provenance_backup_sha,
        )
        return {
            "ok": True,
            "written": False,
            "document": snapshot.info.model_dump(),
            "transaction": transaction_response_summary(updated),
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def stage_operations(self, txid: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        self.policy.require_write(dry_run=True, operation="stage_operations")
        record = self.transactions.read(txid)
        if record.status not in {"staged", "validated"}:
            raise TransactionConflictError(
                f"Transaction cannot accept operations in state {record.status}: {txid}",
                txid=txid,
            )
        parsed = parse_semantic_operations(operations)
        if not parsed:
            raise EditError("At least one semantic operation is required")
        staged = [*record.operations, *(operation.model_dump() for operation in parsed)]
        _require_transaction_capacity(len(staged))
        source = self._load_snapshot_record(record)
        _apply_bounded_semantic_operations(
            source,
            parse_semantic_operations(staged),
            live_session=self._session_id_from_working(Path(record.target_path)) is not None,
        )
        updated = self.transactions.update(
            txid,
            status="staged",
            operations=staged,
            compiled_patch_count=len(staged),
            changed_ids=[],
            validation_before={},
            validation_after_preview={},
            preview_resources=[],
            preview_metadata={},
        )
        return {
            "ok": True,
            "written": False,
            "transaction": transaction_response_summary(updated),
            "result": {"staged_count": len(staged)},
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def preview_transaction(self, txid: str) -> dict[str, Any]:
        self.policy.require_write(dry_run=True, operation="preview_transaction")
        record = self.transactions.read(txid)
        if record.status not in {"staged", "validated"}:
            raise TransactionConflictError(
                f"Transaction cannot be previewed in state {record.status}: {txid}",
                txid=txid,
            )
        if not record.operations:
            raise TransactionConflictError("Transaction contains no operations", txid=txid)
        source = self._load_snapshot_record(record)
        operations = parse_semantic_operations(record.operations)
        preview = self._preview_semantic_operations(source, operations)
        preview_resources = tx_preview_resources(txid)
        response_resources = [
            *tx_summary_resources(txid)[:2],
            *preview_resources,
        ]
        preview_metadata = {
            "inline": False,
            "artifacts": {
                "svg": {
                    "resource_uri": preview_resources[0],
                    "mime_type": "image/svg+xml",
                },
                "json": {
                    "resource_uri": preview_resources[1],
                    "mime_type": "application/json",
                },
                "diff": {
                    "resource_uri": preview_resources[2],
                    "mime_type": "text/plain",
                    **preview["diff_metadata"],
                },
            },
        }
        self.transactions.store_preview(
            txid,
            preview["svg"],
            preview["json"],
            preview["diff"],
        )
        updated = self.transactions.update(
            txid,
            status="validated",
            changed_ids=preview["changed_ids"],
            validation_before=preview["validation_before"],
            validation_after_preview=preview["validation_after_preview"],
            preview_resources=preview_resources,
            preview_metadata=preview_metadata,
            risk=default_risk("limited_write", "semantic operation preview generated"),
            compiled_patch_count=preview["patch_count"],
        )
        warnings, warning_metadata = _bounded_messages(preview["warnings"])
        limitations, limitation_metadata = _bounded_messages(preview["limitations"])
        validation_before = _validation_response_summary(preview["validation_before"])
        validation_after = _validation_response_summary(preview["validation_after_preview"])
        angle_evidence_warnings = (
            component_angle_evidence_warnings()
            if any(operation.kind == "rotate_components" for operation in operations)
            else []
        )
        return {
            "ok": True,
            "written": False,
            "transaction": transaction_response_summary(updated),
            "result": {
                **_bounded_changed_ids(preview["changed_ids"]),
                "validation_before": validation_before,
                "validation_after_preview": validation_after,
                "warnings_metadata": warning_metadata,
                "limitations_metadata": limitation_metadata,
                **(
                    {"evidence_warnings": angle_evidence_warnings}
                    if angle_evidence_warnings
                    else {}
                ),
            },
            "warnings": warnings,
            "limitations": limitations,
            "resources": response_resources,
            "preview": preview_metadata,
            **({"evidence_warnings": angle_evidence_warnings} if angle_evidence_warnings else {}),
        }

    def validate_transaction(self, txid: str) -> dict[str, Any]:
        return self.preview_transaction(txid)

    def commit_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=False, operation="commit_transaction")
        record = self.transactions.read(txid)
        if record.status != "validated":
            raise TransactionConflictError(
                f"Transaction must be validated before commit: {txid}",
                details={"current_status": record.status},
                txid=txid,
            )
        if not record.operations:
            raise TransactionConflictError("Transaction contains no operations", txid=txid)
        if expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required when committing a transaction",
                txid=txid,
            )
        source = self._load_snapshot_record(record)
        operations = parse_semantic_operations(record.operations)
        preview = self._preview_semantic_operations(source, operations)
        target_path = self.settings.resolve_allowed_path(record.target_path)
        current = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
        current_sha256 = current.sha256
        expected = record.expected_sha256 or record.source_sha256
        if expected_sha256 != expected or current_sha256 != expected:
            raise Sha256MismatchError(
                f"Document changed: expected {expected}, current {current_sha256}",
                details={
                    "transaction_expected_sha256": expected,
                    "provided_sha256": expected_sha256,
                    "current_sha256": current_sha256,
                },
                txid=txid,
            )
        session_id = (
            _live_session_id
            if _live_session_id is not None
            else self._session_id_from_working(target_path)
        )
        if session_id is not None and _live_guard is None:
            with self.sessions.guard_working_mutation(
                session_id,
                expected_sha256=expected,
            ) as live_guard:
                return self.commit_transaction(
                    txid,
                    expected_sha256,
                    _live_session_id=session_id,
                    _live_guard=live_guard,
                )
        is_live = session_id is not None
        applied = _apply_bounded_semantic_operations(
            current,
            operations,
            live_session=is_live,
        )
        self._require_current_target_sha256(target_path, expected)
        source_bytes = current.raw_bytes
        backup = self.transactions.store_backup(txid, source_bytes)
        self._require_current_target_sha256(target_path, expected)
        try:
            atomic_write_bytes(target_path, applied.raw_bytes)
            reparsed = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
            committed_sha256 = reparsed.sha256
            if committed_sha256 != sha256_bytes(applied.raw_bytes):
                raise RoundtripValidationError(
                    "Committed XML SHA does not match compiled transaction output",
                    txid=txid,
                )
            self._require_current_target_sha256(target_path, committed_sha256)
            if _live_guard is not None:
                _live_guard.record_edit(
                    working_sha256=committed_sha256,
                    backup=backup,
                )
        except Exception as exc:
            compensation_error: TransactionConflictError | None = None
            try:
                recovery_bytes = self._load_transaction_backup_bytes(
                    txid,
                    expected_sha256=expected,
                    phase="commit_compensation",
                )
                self._compensate_transaction_file(
                    target_path,
                    written=applied.raw_bytes,
                    previous=recovery_bytes,
                    txid=txid,
                    phase="commit_compensation",
                )
            except TransactionConflictError as recovery_exc:
                compensation_error = recovery_exc
            failure_payload = {
                "code": getattr(exc, "code", "schema_write_error"),
                "message": str(exc),
                "phase": "commit_write",
                "source_restored": compensation_error is None,
            }
            try:
                failed_record = self.transactions.mark_failed(txid, failure_payload)
            except Exception as state_exc:
                try:
                    latest = self.transactions.read(txid)
                except DipTraceMcpError as read_exc:
                    current_bytes = self._read_optional_transaction_file(
                        target_path,
                        txid=txid,
                        phase="commit_failure_state_read",
                    )
                    raise TransactionConflictError(
                        "Commit failed and transaction state is unreadable",
                        details={
                            "phase": "commit_failure_state_read",
                            "source_restored": compensation_error is None,
                            "current_sha256": (
                                sha256_bytes(current_bytes) if current_bytes is not None else None
                            ),
                            "source_sha256": sha256_bytes(source_bytes),
                            "attempted_sha256": sha256_bytes(applied.raw_bytes),
                            "state_error": type(state_exc).__name__,
                            "read_error": type(read_exc).__name__,
                        },
                        txid=txid,
                    ) from state_exc
                if latest.status != "failed":
                    current_bytes = self._read_optional_transaction_file(
                        target_path,
                        txid=txid,
                        phase="commit_failure_state",
                    )
                    raise TransactionConflictError(
                        "Commit failed and its failure state could not be persisted",
                        details={
                            "phase": "commit_failure_state",
                            "transaction_status": latest.status,
                            "source_restored": compensation_error is None,
                            "current_sha256": (
                                sha256_bytes(current_bytes) if current_bytes is not None else None
                            ),
                            "source_sha256": sha256_bytes(source_bytes),
                            "attempted_sha256": sha256_bytes(applied.raw_bytes),
                            "state_error": type(state_exc).__name__,
                        },
                        txid=txid,
                    ) from state_exc
                failed_record = latest
            if compensation_error is not None:
                raise compensation_error from exc
            if isinstance(exc, DipTraceMcpError):
                raise
            raise TransactionConflictError(
                "Transaction commit write failed; authenticated source bytes were restored",
                details={
                    "phase": "commit_write",
                    "transaction_status": failed_record.status,
                    "source_restored": True,
                    "current_sha256": sha256_bytes(source_bytes),
                    "source_sha256": sha256_bytes(source_bytes),
                    "attempted_sha256": sha256_bytes(applied.raw_bytes),
                    "write_error": type(exc).__name__,
                },
                txid=txid,
            ) from exc
        try:
            updated = self.transactions.mark_committed(
                txid,
                committed_sha256=committed_sha256,
                changed_ids=applied.changed_ids,
                compiled_patch_count=applied.patch_count,
                preview_resources=tx_preview_resources(txid),
                backup_path=backup,
            )
        except Exception as state_exc:
            try:
                latest = self.transactions.read(txid)
            except DipTraceMcpError as read_exc:
                current_bytes = self._read_optional_transaction_file(
                    target_path,
                    txid=txid,
                    phase="commit_state_read",
                )
                raise TransactionConflictError(
                    "Commit state write failed and transaction state is unreadable",
                    details={
                        "phase": "commit_state_read",
                        "current_sha256": (
                            sha256_bytes(current_bytes) if current_bytes is not None else None
                        ),
                        "source_sha256": sha256_bytes(source_bytes),
                        "attempted_sha256": committed_sha256,
                        "state_error": type(state_exc).__name__,
                        "read_error": type(read_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
            if latest.status == "committed" and latest.committed_sha256 == committed_sha256:
                updated = latest
            else:
                recovery_bytes = self._load_transaction_backup_bytes(
                    txid,
                    expected_sha256=expected,
                    phase="commit_state_compensation",
                )
                self._compensate_transaction_file(
                    target_path,
                    written=applied.raw_bytes,
                    previous=recovery_bytes,
                    txid=txid,
                    phase="commit_state_compensation",
                )
                raise TransactionConflictError(
                    "Commit state was not persisted; authenticated source bytes were restored",
                    details={
                        "phase": "commit_state_write",
                        "transaction_status": latest.status,
                        "source_restored": True,
                        "current_sha256": sha256_bytes(source_bytes),
                        "source_sha256": sha256_bytes(source_bytes),
                        "attempted_sha256": committed_sha256,
                        "state_error": type(state_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
        if _live_guard is not None:
            _live_guard.commit()
        # Invalidate trust after MCP modification
        self.invalidate_document_trust_after_write(
            target_path, committed_sha256, operation_name="mcp_transaction_commit"
        )
        warnings, warning_metadata = _bounded_messages(applied.warnings)
        limitations, limitation_metadata = _bounded_messages(preview["limitations"])
        angle_evidence_warnings = (
            component_angle_evidence_warnings()
            if any(operation.kind == "rotate_components" for operation in operations)
            else []
        )
        return {
            "ok": True,
            "written": True,
            "transaction": transaction_response_summary(updated),
            "result": {
                **_bounded_changed_ids(applied.changed_ids),
                "compiled_patch_count": applied.patch_count,
                "warnings_metadata": warning_metadata,
                "limitations_metadata": limitation_metadata,
                **(
                    {"evidence_warnings": angle_evidence_warnings}
                    if angle_evidence_warnings
                    else {}
                ),
            },
            "warnings": warnings,
            "limitations": limitations,
            "resources": tx_preview_resources(txid),
            **({"evidence_warnings": angle_evidence_warnings} if angle_evidence_warnings else {}),
        }

    @staticmethod
    def _synthetic_rollback_provenance_bytes(
        restored_sha256: str,
        *,
        provenance: str,
    ) -> bytes:
        sidecar = DocumentProvenance(
            provenance=provenance,
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            current_document_sha256=restored_sha256,
            last_modified_by="mcp_rollback_transaction",
        )
        return sidecar.model_dump_json(indent=2).encode()

    def _prepare_rollback_provenance_bytes(
        self,
        record: TransactionRecord,
        target_path: Path,
        restored_sha256: str,
    ) -> bytes:
        if not record.provenance_backup_sha256:
            return self._synthetic_rollback_provenance_bytes(
                restored_sha256,
                provenance="mcp_rollback_no_backup",
            )
        try:
            provenance_backup = self.transactions.require_provenance_backup(record.txid)
        except TransactionConflictError:
            return self._synthetic_rollback_provenance_bytes(
                restored_sha256,
                provenance="mcp_rollback_no_backup",
            )
        try:
            provenance_bytes = provenance_backup.read_bytes()
            if sha256_bytes(provenance_bytes) != record.provenance_backup_sha256:
                raise ValueError("provenance backup SHA mismatch")
            restored_sidecar = DocumentProvenance.model_validate_json(provenance_bytes)
            if restored_sidecar.current_document_sha256 != restored_sha256:
                raise ValueError("restored provenance document SHA mismatch")
            if restored_sidecar.authority == ProvenanceAuthority.user_supplied_evidence:
                self._load_and_validate_evidence_manifest(target_path, restored_sidecar)
            if restored_sidecar.authority == ProvenanceAuthority.trusted_registry:
                self._load_and_authorize_trusted_registry_evidence(
                    target_path,
                    restored_sidecar,
                )
            if (
                restored_sidecar.authority == ProvenanceAuthority.fixture_manifest
                and restored_sidecar.validation_level in _HIGH_TRUST_LEVELS
            ):
                raise ValueError("unauthenticated fixture high trust cannot be restored")
            return provenance_bytes
        except (OSError, json.JSONDecodeError, ValueError, EditError):
            return self._synthetic_rollback_provenance_bytes(
                restored_sha256,
                provenance="mcp_rollback_synthetic",
            )

    @staticmethod
    def _transaction_file_sha256(path: Path) -> str | None:
        try:
            return sha256_bytes(path.read_bytes())
        except OSError:
            return None

    def _compensate_rollback_files(
        self,
        *,
        txid: str,
        target_path: Path,
        restored_document_bytes: bytes,
        committed_document_bytes: bytes,
        sidecar_path: Path,
        restored_sidecar_bytes: bytes,
        committed_sidecar_bytes: bytes | None,
        cause: Exception,
        phase: str,
    ) -> None:
        failures: list[dict[str, Any]] = []
        for path, written, previous, file_phase in (
            (
                sidecar_path,
                restored_sidecar_bytes,
                committed_sidecar_bytes,
                "rollback_sidecar_compensation",
            ),
            (
                target_path,
                restored_document_bytes,
                committed_document_bytes,
                "rollback_design_compensation",
            ),
        ):
            try:
                self._compensate_transaction_file(
                    path,
                    written=written,
                    previous=previous,
                    txid=txid,
                    phase=file_phase,
                )
            except TransactionConflictError as exc:
                failures.append(exc.payload.as_dict())
        details = {
            "phase": phase,
            "compensated": not failures,
            "cause_type": type(cause).__name__,
            "cause_code": getattr(cause, "code", None),
            "current_sha256": self._transaction_file_sha256(target_path),
            "current_sidecar_sha256": self._transaction_file_sha256(sidecar_path),
            "committed_sha256": sha256_bytes(committed_document_bytes),
            "restored_sha256": sha256_bytes(restored_document_bytes),
            "compensation_failures": failures,
        }
        if failures:
            raise TransactionConflictError(
                "Rollback failed and unexpected external bytes blocked compensation",
                details=details,
                txid=txid,
            ) from cause
        raise TransactionConflictError(
            "Rollback failed; the exact pre-call document and provenance were restored",
            details=details,
            txid=txid,
        ) from cause

    def rollback_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
        *,
        _live_session_id: str | None = None,
        _live_guard: LiveWorkingGuard | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=False, operation="rollback_transaction")
        record = self.transactions.read(txid)
        if record.status == "rolled_back":
            raise TransactionConflictError("Transaction is already rolled back", txid=txid)
        restored_sha256: str | None = None
        target_path: Path | None = None
        committed_document_bytes: bytes | None = None
        restored_document_bytes: bytes | None = None
        sidecar_path: Path | None = None
        committed_sidecar_bytes: bytes | None = None
        restored_sidecar_bytes: bytes | None = None
        if record.status == "committed":
            if expected_sha256 is None:
                raise ConfirmationRequiredError(
                    "expected_sha256 is required to roll back a committed transaction",
                    txid=txid,
                )
            target_path = self.settings.resolve_allowed_path(record.target_path)
            current = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
            if expected_sha256 != record.committed_sha256 or current.sha256 != expected_sha256:
                raise Sha256MismatchError(
                    "The committed document changed after this transaction",
                    details={
                        "transaction_commit_sha256": record.committed_sha256,
                        "provided_sha256": expected_sha256,
                        "current_sha256": current.sha256,
                    },
                    txid=txid,
                )
            session_id = (
                _live_session_id
                if _live_session_id is not None
                else self._session_id_from_working(target_path)
            )
            if session_id is not None and _live_guard is None:
                with self.sessions.guard_working_mutation(
                    session_id,
                    expected_sha256=expected_sha256,
                ) as live_guard:
                    return self.rollback_transaction(
                        txid,
                        expected_sha256,
                        _live_session_id=session_id,
                        _live_guard=live_guard,
                    )
            restored_document_bytes = self._load_transaction_backup_bytes(
                txid,
                expected_sha256=record.source_sha256,
                phase="rollback_prepare",
            )
            DipTraceDocument.from_bytes(target_path, restored_document_bytes)
            restored_sha256 = sha256_bytes(restored_document_bytes)
            committed_document_bytes = current.raw_bytes
            sidecar_path = target_path.with_suffix(target_path.suffix + ".provenance.json")
            committed_sidecar_bytes = self._read_optional_transaction_file(
                sidecar_path,
                txid=txid,
                phase="rollback_prepare",
            )
            restored_sidecar_bytes = self._prepare_rollback_provenance_bytes(
                record,
                target_path,
                restored_sha256,
            )
            try:
                self._require_current_target_sha256(target_path, expected_sha256)
                self._require_optional_transaction_file_unchanged(
                    sidecar_path,
                    committed_sidecar_bytes,
                    txid=txid,
                    phase="rollback_prewrite",
                )
                atomic_write_bytes(target_path, restored_document_bytes)
                self._require_current_target_sha256(target_path, restored_sha256)
                self._require_optional_transaction_file_unchanged(
                    sidecar_path,
                    committed_sidecar_bytes,
                    txid=txid,
                    phase="rollback_sidecar_prewrite",
                )
                atomic_write_bytes(sidecar_path, restored_sidecar_bytes)
                self._require_optional_transaction_file_unchanged(
                    sidecar_path,
                    restored_sidecar_bytes,
                    txid=txid,
                    phase="rollback_sidecar_verify",
                )
                if _live_guard is not None:
                    _live_guard.record_edit(
                        working_sha256=restored_sha256,
                    )
            except Exception as exc:
                self._compensate_rollback_files(
                    txid=txid,
                    target_path=target_path,
                    restored_document_bytes=restored_document_bytes,
                    committed_document_bytes=committed_document_bytes,
                    sidecar_path=sidecar_path,
                    restored_sidecar_bytes=restored_sidecar_bytes,
                    committed_sidecar_bytes=committed_sidecar_bytes,
                    cause=exc,
                    phase="rollback_apply",
                )
        try:
            updated = self.transactions.mark_rolled_back(
                txid,
                rolled_back_sha256=restored_sha256,
                reason="explicit rollback",
            )
        except Exception as state_exc:
            try:
                latest = self.transactions.read(txid)
            except DipTraceMcpError as read_exc:
                raise TransactionConflictError(
                    "Rollback state write failed and transaction state is unreadable",
                    details={
                        "phase": "rollback_state_read",
                        "current_sha256": (
                            self._transaction_file_sha256(target_path)
                            if target_path is not None
                            else None
                        ),
                        "current_sidecar_sha256": (
                            self._transaction_file_sha256(sidecar_path)
                            if sidecar_path is not None
                            else None
                        ),
                        "state_error": type(state_exc).__name__,
                        "read_error": type(read_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
            if latest.status == "rolled_back":
                updated = latest
            elif (
                target_path is not None
                and committed_document_bytes is not None
                and restored_document_bytes is not None
                and sidecar_path is not None
                and restored_sidecar_bytes is not None
            ):
                self._compensate_rollback_files(
                    txid=txid,
                    target_path=target_path,
                    restored_document_bytes=restored_document_bytes,
                    committed_document_bytes=committed_document_bytes,
                    sidecar_path=sidecar_path,
                    restored_sidecar_bytes=restored_sidecar_bytes,
                    committed_sidecar_bytes=committed_sidecar_bytes,
                    cause=state_exc,
                    phase="rollback_state_write",
                )
            else:
                raise TransactionConflictError(
                    "Rollback state was not persisted",
                    details={
                        "phase": "rollback_state_write",
                        "transaction_status": latest.status,
                        "current_sha256": None,
                        "current_sidecar_sha256": None,
                        "state_error": type(state_exc).__name__,
                    },
                    txid=txid,
                ) from state_exc
        if _live_guard is not None:
            _live_guard.commit()
        return {
            "ok": True,
            "written": restored_sha256 is not None,
            "transaction": transaction_response_summary(updated),
            "result": {
                "rolled_back": True,
                "document_restored": restored_sha256 is not None,
                "restored_sha256": restored_sha256,
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def list_transactions(self) -> dict[str, Any]:
        return {
            "ok": True,
            "transactions": [
                transaction_response_summary(item) for item in self.transactions.list()
            ],
        }

    def _evaluate_roundtrip_evidence(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None,
        reexport_path: str | None = None,
        reexport_sha256: str | None = None,
    ) -> RoundtripEvidenceEvaluation:
        """Validate evidence roles once for both read-only preview and recording."""

        if (reexport_path is None) != (reexport_sha256 is None):
            raise EditError(
                "reexport_path and reexport_sha256 must be supplied together",
                code="invalid_evidence_input",
            )

        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        source = self.settings.resolve_allowed_path(source_path, must_exist=True)
        saved = self.settings.resolve_allowed_path(saved_path, must_exist=True)
        reexport = (
            self.settings.resolve_allowed_path(reexport_path, must_exist=True)
            if reexport_path is not None
            else None
        )

        if same_file_role(source, saved):
            raise EditError(
                "source_path and saved_path must be different files",
                code="evidence_role_conflict",
            )
        if reexport is not None and same_file_role(source, reexport):
            raise EditError(
                "source_path and reexport_path must be different files",
                code="evidence_role_conflict",
            )
        if reexport is not None and same_file_role(saved, reexport):
            raise EditError(
                "saved_path and reexport_path must be different files",
                code="evidence_role_conflict",
            )
        if saved_sha256 is None:
            raise EditError(
                "saved_sha256 is required to bind the saved evidence role",
                code="sha256_required",
            )

        source_doc = DipTraceDocument.load(source, self.settings.max_document_bytes)
        saved_doc = DipTraceDocument.load(saved, self.settings.max_document_bytes)
        reexport_doc = (
            DipTraceDocument.load(reexport, self.settings.max_document_bytes)
            if reexport is not None
            else None
        )
        for role, evidence_document, expected_sha in (
            ("source", source_doc, source_sha256),
            ("saved", saved_doc, saved_sha256),
            ("reexport", reexport_doc, reexport_sha256),
        ):
            if evidence_document is None or expected_sha is None:
                continue
            if evidence_document.sha256 != expected_sha:
                raise Sha256MismatchError(
                    f"{role} SHA-256 mismatch: expected {expected_sha}, "
                    f"got {evidence_document.sha256}",
                    details={
                        "role": role,
                        "expected_sha256": expected_sha,
                        "current_sha256": evidence_document.sha256,
                    },
                )

        expected_source_type = snapshot.info.source_type
        for role, evidence_document in (
            ("source", source_doc),
            ("saved", saved_doc),
            ("reexport", reexport_doc),
        ):
            if evidence_document is None:
                continue
            if evidence_document.source_type != expected_source_type:
                raise EditError(
                    f"{role} source type {evidence_document.source_type!r} does not match "
                    f"document source type {expected_source_type!r}",
                    code="source_type_mismatch",
                    details={
                        "role": role,
                        "expected_source_type": expected_source_type,
                        "actual_source_type": evidence_document.source_type,
                    },
                )

        saved_snapshot = build_snapshot(saved_doc)
        critical_warnings = [
            warning
            for warning in saved_snapshot.warnings
            if any(token in warning.casefold() for token in ("error", "invalid", "missing"))
        ]
        if critical_warnings:
            bounded_warnings, _ = _bounded_messages(critical_warnings)
            raise EditError(
                f"Saved document has critical parse warnings: {bounded_warnings}",
                code="critical_parse_warnings",
            )

        semantic_comparison: dict[str, Any] | None = None
        if reexport_doc is None:
            if snapshot.info.sha256 != saved_doc.sha256:
                raise EditError(
                    f"Current document SHA {snapshot.info.sha256} does not match "
                    f"saved SHA {saved_doc.sha256}; cannot validate open/save evidence",
                    code="sha256_binding_mismatch",
                )
        else:
            if snapshot.info.sha256 != reexport_doc.sha256:
                raise EditError(
                    f"Current document SHA {snapshot.info.sha256} does not match "
                    f"reexport SHA {reexport_doc.sha256}; cannot validate roundtrip evidence",
                    code="sha256_binding_mismatch",
                )
            semantic_comparison = _semantic_roundtrip_check(source_doc, reexport_doc)

        return RoundtripEvidenceEvaluation(
            document_path=target.path,
            document_sha256=snapshot.info.sha256,
            source=EvidenceFileRecord(
                path=str(source),
                sha256=source_doc.sha256,
                source_type=cast(SourceType, source_doc.source_type),
            ),
            saved=EvidenceFileRecord(
                path=str(saved),
                sha256=saved_doc.sha256,
                source_type=cast(SourceType, saved_doc.source_type),
            ),
            reexport=(
                EvidenceFileRecord(
                    path=str(reexport),
                    sha256=reexport_doc.sha256,
                    source_type=cast(SourceType, reexport_doc.source_type),
                )
                if reexport is not None and reexport_doc is not None
                else None
            ),
            semantic_comparison=semantic_comparison,
        )

    @staticmethod
    def _semantic_evidence_record(
        comparison: dict[str, Any] | None,
    ) -> SemanticComparisonEvidence | None:
        if comparison is None:
            return None
        unsupported_raw = comparison.get("unsupported_categories", []) or []
        return SemanticComparisonEvidence(
            passed=bool(comparison["passed"]),
            comparison_complete=bool(comparison["comparison_complete"]),
            compared_categories=list(comparison.get("compared_categories", [])),
            missing_required_categories=list(comparison.get("missing_required_categories", [])),
            differences=list(comparison.get("differences", [])),
            ignored_normalizations=list(comparison.get("ignored_normalizations", [])),
            unsupported_categories=[
                UnsupportedCategory.model_validate(item)
                for item in unsupported_raw
                if isinstance(item, dict)
            ],
            parse_warnings=list(comparison.get("parse_warnings", [])),
        )

    def _require_evidence_evaluation_unchanged(
        self,
        evaluation: RoundtripEvidenceEvaluation,
    ) -> None:
        """Repeat allowed-root, bounded-parse, role, and SHA gates before writes."""

        role_records = [
            ("source", evaluation.source),
            ("saved", evaluation.saved),
        ]
        if evaluation.reexport is not None:
            role_records.append(("reexport", evaluation.reexport))
        for index, (left_role, left_record) in enumerate(role_records):
            for right_role, right_record in role_records[index + 1 :]:
                if same_file_role(Path(left_record.path), Path(right_record.path)):
                    raise EditError(
                        f"{left_role} and {right_role} evidence roles became the same file",
                        code="evidence_role_conflict",
                    )

        expected_files = [
            ("document", evaluation.document_path, evaluation.document_sha256),
            *[(role, Path(record.path), record.sha256) for role, record in role_records],
        ]
        for role, role_path, expected_sha256 in expected_files:
            try:
                resolved_path = self.settings.resolve_allowed_path(
                    role_path,
                    must_exist=True,
                )
                if resolved_path != role_path:
                    raise EditError(
                        f"{role} resolves to a different path before evidence recording",
                        code="evidence_file_changed",
                        details={"role": role},
                    )
                current_document = DipTraceDocument.load(
                    resolved_path,
                    self.settings.max_document_bytes,
                )
            except (DocumentError, PathAccessError, OSError) as exc:
                raise EditError(
                    f"Cannot safely revalidate {role} before recording evidence",
                    code="evidence_file_changed",
                    details={"role": role},
                ) from exc
            current_sha256 = current_document.sha256
            if current_sha256 != expected_sha256:
                raise Sha256MismatchError(
                    f"{role} changed before evidence metadata could be recorded",
                    details={
                        "role": role,
                        "expected_sha256": expected_sha256,
                        "current_sha256": current_sha256,
                    },
                )

    @staticmethod
    def _evidence_manifest_path(document_path: Path) -> Path:
        return Path(str(document_path) + ".roundtrip-evidence.json")

    @staticmethod
    def _evidence_sidecar_path(document_path: Path) -> Path:
        return document_path.with_suffix(document_path.suffix + ".provenance.json")

    @classmethod
    def _require_evidence_output_paths_safe(
        cls,
        evaluation: RoundtripEvidenceEvaluation,
    ) -> None:
        """Refuse metadata outputs that alias a document or evidence input."""

        outputs = (
            ("evidence_manifest", cls._evidence_manifest_path(evaluation.document_path)),
            ("provenance_sidecar", cls._evidence_sidecar_path(evaluation.document_path)),
        )
        protected = [
            ("document", evaluation.document_path),
            ("source", Path(evaluation.source.path)),
            ("saved", Path(evaluation.saved.path)),
        ]
        if evaluation.reexport is not None:
            protected.append(("reexport", Path(evaluation.reexport.path)))
        for output_role, output_path in outputs:
            for protected_role, protected_path in protected:
                if same_file_role(output_path, protected_path):
                    raise EditError(
                        f"{output_role} output aliases the {protected_role} file",
                        code="evidence_output_conflict",
                    )

    def _roundtrip_evidence_response(
        self,
        evaluation: RoundtripEvidenceEvaluation,
        *,
        written: bool,
        manifest_path: Path | None = None,
        manifest_sha256: str | None = None,
    ) -> dict[str, Any]:
        comparison, comparison_bounds = _bounded_evidence_comparison(evaluation.semantic_comparison)
        failed = evaluation.failed
        evidence_status = "failed" if failed else ("recorded" if written else "recordable")
        role_sha256: dict[str, str] = {
            "source": evaluation.source.sha256,
            "saved": evaluation.saved.sha256,
        }
        if evaluation.reexport is not None:
            role_sha256["reexport"] = evaluation.reexport.sha256
        result: dict[str, Any] = {
            "ok": not failed,
            "written": written,
            "document_written": False,
            "evidence_status": evidence_status,
            "authority": EvidenceAuthority.user_supplied.value,
            "grants_high_trust": False,
            "validation_level": FixtureValidationLevel.synthetic_operation_fixture.value,
            "requires_diptrace_verification": True,
            "source_type": evaluation.source.source_type,
            "document_sha256": evaluation.document_sha256,
            "role_sha256": role_sha256,
            "semantic_comparison": comparison,
            "semantic_comparison_bounds": comparison_bounds,
            "message": (
                "Semantic comparison failed; this observation can only be recorded "
                "as failed user-supplied evidence."
                if failed
                else (
                    "Evidence recorded with authority=user_supplied; this does not "
                    "grant authoritative DipTrace trust."
                    if written
                    else (
                        "Evidence inputs are valid and recordable as user-supplied; "
                        "validation made no filesystem changes."
                    )
                )
            ),
        }
        if written:
            result["evidence_manifest_path"] = str(manifest_path)
            result["evidence_manifest_sha256"] = manifest_sha256
            result["written_files"] = ["evidence_manifest", "provenance_sidecar"]
        else:
            result["would_write"] = {
                "evidence_manifest_path": str(
                    self._evidence_manifest_path(evaluation.document_path)
                ),
                "provenance_sidecar_path": str(
                    self._evidence_sidecar_path(evaluation.document_path)
                ),
            }
        return _finalize_evidence_response(result)

    def validate_roundtrip_evidence(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None = None,
        reexport_path: str | None = None,
        reexport_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Validate SHA-bound user evidence without writing any file."""

        evaluation = self._evaluate_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )
        return self._roundtrip_evidence_response(evaluation, written=False)

    def record_roundtrip_evidence(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None = None,
        reexport_path: str | None = None,
        reexport_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Write user-supplied evidence metadata without granting high trust."""

        self.policy.require_write(dry_run=False, operation="record_roundtrip_evidence")
        evaluation = self._evaluate_roundtrip_evidence(
            path,
            source_path=source_path,
            source_sha256=source_sha256,
            saved_path=saved_path,
            saved_sha256=saved_sha256,
            reexport_path=reexport_path,
            reexport_sha256=reexport_sha256,
        )

        evidence_level = FixtureValidationLevel.synthetic_operation_fixture

        evidence_manifest = UserSuppliedRoundtripEvidence(
            document_path=str(evaluation.document_path),
            document_sha256=evaluation.document_sha256,
            source=evaluation.source,
            saved=evaluation.saved,
            reexport=evaluation.reexport,
            semantic_comparison=self._semantic_evidence_record(evaluation.semantic_comparison),
            validation_level=evidence_level,
            status="failed" if evaluation.failed else "recorded",
            created_at=utc_now(),
        )
        manifest_path = self._evidence_manifest_path(evaluation.document_path)
        manifest_bytes = json.dumps(
            evidence_manifest.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ).encode()
        self._require_evidence_evaluation_unchanged(evaluation)
        self._require_evidence_output_paths_safe(evaluation)
        atomic_write_bytes(manifest_path, manifest_bytes)
        reloaded_manifest = manifest_path.read_bytes()
        manifest_sha = sha256_bytes(reloaded_manifest)
        UserSuppliedRoundtripEvidence.model_validate(json.loads(reloaded_manifest))

        self._require_evidence_evaluation_unchanged(evaluation)
        self._require_evidence_output_paths_safe(evaluation)
        sidecar = DocumentProvenance(
            provenance=(
                "user_supplied_evidence_failed"
                if evaluation.failed
                else "user_supplied_evidence_recorded"
            ),
            validation_level=evidence_level,
            current_document_sha256=evaluation.document_sha256,
            seed_sha256=evaluation.source.sha256,
            parent_validation_level=(None if evaluation.failed else evidence_level),
            authority=ProvenanceAuthority.user_supplied_evidence,
            evidence_manifest_path=str(manifest_path),
            evidence_manifest_sha256=manifest_sha,
            last_modified_by="mcp_record_roundtrip_evidence",
        )
        self._write_provenance_sidecar(evaluation.document_path, sidecar)

        reloaded_sidecar = self._load_seed_provenance(evaluation.document_path)
        if (
            reloaded_sidecar is None
            or reloaded_sidecar.evidence_manifest_path != str(manifest_path)
            or reloaded_sidecar.evidence_manifest_sha256 != manifest_sha
        ):
            raise EditError(
                "Evidence provenance sidecar verification failed after write",
                code="sidecar_write_error",
            )

        return self._roundtrip_evidence_response(
            evaluation,
            written=True,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha,
        )

    def move_components(
        self,
        selector: dict[str, Any] | None = None,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        grid_snap: float | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_components(
            selector,
            dx,
            dy,
            absolute_x,
            absolute_y,
            path,
            dry_run,
            expected_sha256,
            txid,
            grid_snap,
            allow_locked,
        )

    def set_component_value(
        self,
        selector: dict[str, Any] | None,
        value: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_value(
            selector, value, path, dry_run, expected_sha256, txid
        )

    def rotate_components(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allowed_angles: list[float] | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.rotate_components(
            selector,
            angle_deg,
            mode,
            path,
            dry_run,
            expected_sha256,
            txid,
            allowed_angles,
            allow_locked,
        )

    def set_component_side(
        self,
        selector: dict[str, Any] | None,
        side: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_side(
            selector, side, path, dry_run, expected_sha256, txid, allow_locked
        )

    def set_component_lock(
        self,
        selector: dict[str, Any] | None,
        locked: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_lock(
            selector, locked, path, dry_run, expected_sha256, txid
        )

    def set_component_properties(
        self,
        selector: dict[str, Any] | None,
        *,
        name: str | None = None,
        value: str | None = None,
        refdes: str | None = None,
        fields: dict[str, str] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_properties(
            selector,
            name=name,
            value=value,
            refdes=refdes,
            fields=fields,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def set_component_pattern(
        self,
        selector: dict[str, Any],
        pattern_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_component_pattern(
            selector,
            pattern_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def align_components(
        self,
        selector: dict[str, Any],
        alignment: str,
        *,
        target_value: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.align_components(
            selector,
            alignment,
            target_value=target_value,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def distribute_components(
        self,
        selector: dict[str, Any],
        axis: str,
        *,
        mode: str = "centers",
        spacing: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.distribute_components(
            selector,
            axis,
            mode=mode,
            spacing=spacing,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def group_components(
        self,
        selector: dict[str, Any],
        *,
        group_id: int | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.group_components(
            selector,
            group_id=group_id,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def ungroup_components(
        self,
        selector: dict[str, Any],
        *,
        remove_empty_groups: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.ungroup_components(
            selector,
            remove_empty_groups=remove_empty_groups,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def list_board_texts(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.list_board_texts(path, selector)

    def move_board_texts(
        self,
        selector: dict[str, Any] | None,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_board_texts(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def rotate_board_texts(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.rotate_board_texts(
            selector, angle_deg, mode, path, dry_run, expected_sha256, txid, allow_locked
        )

    def set_text_visibility(
        self,
        selector: dict[str, Any] | None,
        visibility: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_text_visibility(
            selector, visibility, path, dry_run, expected_sha256, txid, allow_locked
        )

    def set_text_style(
        self,
        selector: dict[str, Any] | None,
        *,
        font_size: int | None = None,
        font_width: float | None = None,
        horizontal_align: str | None = None,
        vertical_align: str | None = None,
        mirrored: bool | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_text_style(
            selector,
            font_size=font_size,
            font_width=font_width,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            mirrored=mirrored,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def set_pin_no_connect(
        self,
        selector: dict[str, Any] | None,
        no_connect: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_pin_no_connect(
            selector, no_connect, path, dry_run, expected_sha256, txid
        )

    def rename_net(
        self,
        selector: dict[str, Any] | None,
        new_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.rename_net(
            selector, new_name, path, dry_run, expected_sha256, txid
        )

    def add_sheet(
        self,
        name: str,
        sheet_type: str = "Normal",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_sheet(
            name, sheet_type, path, dry_run, expected_sha256, txid
        )

    def place_part(
        self,
        component_style: str,
        refdes: str,
        x: float,
        y: float,
        *,
        pin_count: int,
        name: str | None = None,
        value: str = "",
        sheet: int = 0,
        angle_deg: float = 0.0,
        component_part: int = 0,
        part_number: int = 0,
        part_refdes: str | None = None,
        part_name: str | None = None,
        allow_shared_refdes: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.place_part(
            component_style,
            refdes,
            x,
            y,
            pin_count=pin_count,
            name=name,
            value=value,
            sheet=sheet,
            angle_deg=angle_deg,
            component_part=component_part,
            part_number=part_number,
            part_refdes=part_refdes,
            part_name=part_name,
            allow_shared_refdes=allow_shared_refdes,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def connect_pins(
        self,
        net: str,
        pins: list[dict[str, Any]],
        allow_reconnect: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.connect_pins(
            net, pins, allow_reconnect, path, dry_run, expected_sha256, txid
        )

    def disconnect_pins(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.disconnect_pins(
            selector, path, dry_run, expected_sha256, txid
        )

    def add_wire(
        self,
        net: str,
        points: list[dict[str, Any]],
        start: dict[str, Any],
        end: dict[str, Any],
        sheet: int = 0,
        hidden_power: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_wire(
            net, points, start, end, sheet, hidden_power, path, dry_run, expected_sha256, txid
        )

    def delete_wire(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.delete_wire(
            selector, path, dry_run, expected_sha256, txid
        )

    def add_net_label(
        self,
        net: str,
        x: float,
        y: float,
        sheet: int = 0,
        text: str | None = None,
        font_size: int = 10,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_net_label(
            net, x, y, sheet, text, font_size, path, dry_run, expected_sha256, txid
        )

    def set_panelization(
        self,
        panel: dict[str, Any],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_panelization(
            panel, path, dry_run, expected_sha256, txid
        )

    def clear_panelization(
        self,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.clear_panelization(
            path, dry_run, expected_sha256, txid
        )

    def update_net_class_rules(
        self,
        class_name: str,
        *,
        layer: str | None = None,
        width: float | None = None,
        min_width: float | None = None,
        max_width: float | None = None,
        clearance: float | None = None,
        neck_width: float | None = None,
        differential_gap: float | None = None,
        max_uncoupled_length: float | None = None,
        tolerance: float | None = None,
        check_length: bool | None = None,
        fixed_length: float | None = None,
        length_delta: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.update_net_class_rules(
            class_name,
            layer=layer,
            width=width,
            min_width=min_width,
            max_width=max_width,
            clearance=clearance,
            neck_width=neck_width,
            differential_gap=differential_gap,
            max_uncoupled_length=max_uncoupled_length,
            tolerance=tolerance,
            check_length=check_length,
            fixed_length=fixed_length,
            length_delta=length_delta,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def assign_nets_to_class(
        self,
        selector: dict[str, Any] | None,
        class_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.assign_nets_to_class(
            selector, class_name, path, dry_run, expected_sha256, txid
        )

    def list_testpoints(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.list_testpoints(path, selector)

    def find_testpoint_candidates(
        self,
        target_nets: list[str],
        *,
        path: str | None = None,
        side: str = "Top",
        probe_diameter: float = 1.0,
        clearance: float = 0.5,
        grid: float = 2.54,
        candidates_per_net: int = 10,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.find_testpoint_candidates(
            target_nets,
            path=path,
            side=side,
            probe_diameter=probe_diameter,
            clearance=clearance,
            grid=grid,
            candidates_per_net=candidates_per_net,
        )

    def add_testpoints(
        self,
        testpoints: list[dict[str, Any]],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_testpoints(
            testpoints, path, dry_run, expected_sha256, txid
        )

    def move_testpoints(
        self,
        selector: dict[str, Any] | None,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        grid_snap: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_testpoints(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            grid_snap=grid_snap,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    def remove_testpoints(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.remove_testpoints(
            selector, path, dry_run, expected_sha256, txid, allow_locked
        )

    def review_testpoint_coverage(
        self,
        target_nets: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.review_testpoint_coverage(target_nets, path)

    def add_trace(
        self,
        *,
        net: str,
        start_object_id: str,
        end_object_id: str,
        points: list[dict[str, Any]],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_trace(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            points=points,
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def replace_trace(
        self,
        trace_id: str,
        points: list[dict[str, Any]],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.replace_trace(
            trace_id,
            points,
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def delete_trace(
        self,
        selector: dict[str, Any],
        *,
        allow_connectivity_regression: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.delete_trace(
            selector,
            allow_connectivity_regression=allow_connectivity_regression,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def set_trace_width(
        self,
        selector: dict[str, Any],
        width: float,
        *,
        segment_indices: list[int] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_trace_width(
            selector,
            width,
            segment_indices=segment_indices,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def add_via(
        self,
        trace_id: str,
        x: float,
        y: float,
        via_style: str,
        *,
        layer_before: str | None = None,
        layer_after: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.add_via(
            trace_id,
            x,
            y,
            via_style,
            layer_before=layer_before,
            layer_after=layer_after,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def move_via(
        self,
        selector: dict[str, Any],
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.move_via(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def delete_via(
        self,
        selector: dict[str, Any],
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.delete_via(
            selector, path=path, dry_run=dry_run, expected_sha256=expected_sha256, txid=txid
        )

    def set_via_style(
        self,
        selector: dict[str, Any],
        via_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._semantic_operations_service.set_via_style(
            selector,
            via_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def list_unrouted_connections(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Unrouted connections require a PCB document")
        requested = {item.casefold() for item in nets or []}
        items: list[dict[str, Any]] = []
        for index, ratline in enumerate(snapshot.board.ratlines):
            endpoints = ratline.get("endpoints", [])
            if len(endpoints) != 2:
                continue
            pad_ids = [endpoint.get("pad_id") for endpoint in endpoints]
            if any(pad_id is None for pad_id in pad_ids):
                continue
            first = snapshot.get_object(str(pad_ids[0]))
            second = snapshot.get_object(str(pad_ids[1]))
            if first.net_id is None or first.net_id != second.net_id:
                continue
            net = next(
                (item for item in snapshot.board.nets if item.xml_id == first.net_id),
                None,
            )
            if net is None or (
                requested
                and (net.name or "").casefold() not in requested
                and net.stable_id.casefold() not in requested
            ):
                continue
            positions = [endpoint.get("position") for endpoint in endpoints]
            ratline_length = (
                distance(Point(**positions[0]), Point(**positions[1]))
                if positions[0] is not None and positions[1] is not None
                else None
            )
            items.append(
                {
                    "connection_id": f"ratline:{index}",
                    "net_id": net.stable_id,
                    "net": net.name,
                    "net_class": net.attributes.get("net_class"),
                    "endpoints": endpoints,
                    "ratline_length_mm": ratline_length,
                    "priority": 0,
                    "differential_pair": None,
                }
            )
        return self._read_success(
            snapshot.info,
            {"matched_count": len(items), "items": items},
            limitations=[
                "Unrouted connections are derived from exported Ratlines.",
                "Priority and differential-pair enrichment are not implemented yet.",
            ],
        )

    def get_route_details(
        self,
        *,
        trace_id: str | None = None,
        net: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        if (trace_id is None) == (net is None):
            raise DocumentError("Specify exactly one of trace_id or net", code="scope_required")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Route details require a PCB document")
        if trace_id is not None:
            traces = [snapshot.get_object(trace_id)]
            if traces[0].kind != "trace":
                raise DocumentError(f"Object is not a trace: {trace_id}")
        else:
            assert net is not None
            net_matches = [
                item
                for item in snapshot.board.nets
                if item.stable_id == net
                or item.xml_id == net
                or (item.name or "").casefold() == net.casefold()
            ]
            if len(net_matches) != 1:
                raise DocumentError(f"Unique net was not found: {net}")
            traces = [
                item for item in snapshot.board.traces if item.parent_id == net_matches[0].stable_id
            ]
        per_layer: dict[str, float] = {}
        total_length = 0.0
        via_ids: list[str] = []
        items: list[dict[str, Any]] = []
        for trace in traces:
            points = [Point(**item) for item in trace.attributes.get("points", [])]
            layers = trace.attributes.get("segment_layers", [])
            segment_lengths: list[float] = []
            for segment_index, (start, end) in enumerate(zip(points, points[1:], strict=False)):
                length = distance(start, end)
                segment_lengths.append(length)
                layer = (
                    str(layers[segment_index]) if segment_index < len(layers) else trace.layer or ""
                )
                per_layer[layer] = per_layer.get(layer, 0.0) + length
                total_length += length
            via_ids.extend(trace.relationships.get("vias", []))
            items.append(
                {
                    **trace.model_dump(mode="json"),
                    "segment_lengths_mm": segment_lengths,
                    "bend_count": max(0, len(points) - 2),
                }
            )
        return self._read_success(
            snapshot.info,
            {
                "trace_count": len(traces),
                "traces": items,
                "total_length_mm": total_length,
                "per_layer_length_mm": per_layer,
                "via_count": len(set(via_ids)),
                "via_ids": sorted(set(via_ids)),
                "layer_transition_count": len(set(via_ids)),
            },
            limitations=[
                "Length is geometric centerline length; arc and electrical delay are not included."
            ],
        )

    def get_stackup(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.get_stackup(path)

    def measure_net_lengths(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
        effective_dielectric_constant: float | None = None,
    ) -> dict[str, Any]:
        return self._review_service.measure_net_lengths(
            path,
            nets=nets,
            effective_dielectric_constant=effective_dielectric_constant,
        )

    def analyze_length_group(
        self,
        nets: list[str],
        *,
        tolerance_mm: float | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._review_service.analyze_length_group(nets, tolerance_mm=tolerance_mm, path=path)

    def list_differential_pairs(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._review_service.list_differential_pairs(path, offset=offset, limit=limit)

    def get_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        return self._review_service.get_differential_pair(pair, path)

    def analyze_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_differential_pair(pair, path)

    def analyze_differential_pairs(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_differential_pairs(path)

    def validate_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        return self._review_service.validate_differential_pair(pair, path)

    def calculate_impedance(
        self,
        *,
        structure: str,
        width_mm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        gap_mm: float | None = None,
        frequency_hz: float | None = None,
        target_ohm: float | None = None,
        tolerance_ohm: float | None = None,
    ) -> dict[str, Any]:
        return self._review_service.calculate_impedance(
            structure=structure,
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            gap_mm=gap_mm,
            frequency_hz=frequency_hz,
            target_ohm=target_ohm,
            tolerance_ohm=tolerance_ohm,
        )

    def suggest_trace_geometry_for_impedance(
        self,
        *,
        target_ohm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        minimum_width_mm: float,
        maximum_width_mm: float,
        tolerance_ohm: float = 0.01,
    ) -> dict[str, Any]:
        return self._review_service.suggest_trace_geometry_for_impedance(
            target_ohm=target_ohm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            minimum_width_mm=minimum_width_mm,
            maximum_width_mm=maximum_width_mm,
            tolerance_ohm=tolerance_ohm,
        )

    def analyze_stackup_for_impedance(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_stackup_for_impedance(path)

    def validate_impedance_constraints(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._review_service.validate_impedance_constraints(constraints, path=path)

    def analyze_controlled_impedance_nets(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self._review_service.analyze_controlled_impedance_nets(constraints, path=path)

    def list_copper_pours(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._review_service.list_copper_pours(path, offset=offset, limit=limit)

    def analyze_plane_continuity(self, path: str | None = None) -> dict[str, Any]:
        return self._review_service.analyze_plane_continuity(path)

    def analyze_return_path(
        self,
        path: str | None = None,
        *,
        stitching_radius_mm: float,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._review_service.analyze_return_path(
            path,
            stitching_radius_mm=stitching_radius_mm,
            nets=nets,
            reference_nets=reference_nets,
        )

    def route_connection(
        self,
        *,
        net: str,
        start_object_id: str,
        end_object_id: str,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        bend_cost: float = 0.2,
        preferred_layers: list[str] | None = None,
        start_layer: str | None = None,
        end_layer: str | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        max_detour: float = 3.0,
        max_nodes: int = 100_000,
        time_budget_ms: int = 5_000,
        avoid_component_bodies: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = RouteConnectionConfig(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            bend_cost=bend_cost,
            preferred_layers=preferred_layers or [],
            start_layer=start_layer,
            end_layer=end_layer,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            max_nodes=max_nodes,
            time_budget_ms=time_budget_ms,
            avoid_component_bodies=avoid_component_bodies,
        )
        route = synthesize_route(snapshot, config)
        response = self._run_semantic_write(route.operation, path, dry_run, expected_sha256, txid)
        response["routing"] = {
            "points": [point.as_dict() for point in route.points],
            "path": [point.model_dump(mode="json") for point in route.operation.points],
            "metrics": route.metrics,
            "clearance_resolution": route.clearance_resolution,
            "assumptions": route.assumptions,
        }
        response["clearance_rule_status"] = route.clearance_resolution["clearance_rule_status"]
        response["netclass_rules_ignored"] = route.clearance_resolution["netclass_rules_ignored"]
        response["warnings"] = [*response.get("warnings", []), *route.warnings]
        response["limitations"] = [
            *response.get("limitations", []),
            *route.limitations,
        ]
        return response

    def route_net(
        self,
        net: str,
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        pairs = self._unrouted_pairs(snapshot, [net])
        if not pairs:
            raise DocumentError(f"No exported unrouted connection was found for net: {net}")
        operations: list[SemanticOperation] = []
        metrics: list[dict[str, Any]] = []
        working = document
        working_snapshot = snapshot
        for pair in pairs:
            route = synthesize_route(
                working_snapshot,
                RouteConnectionConfig(
                    net=pair["net_id"],
                    start_object_id=pair["start_object_id"],
                    end_object_id=pair["end_object_id"],
                    layer=layer,
                    width=width,
                    clearance=clearance,
                    grid=grid,
                    preferred_layers=preferred_layers or [],
                    via_style=via_style,
                    max_vias=max_vias,
                    via_cost=via_cost,
                ),
            )
            operations.append(route.operation)
            metrics.append(route.metrics)
            applied = apply_semantic_operations(
                working, [route.operation], live_session=target.is_live
            )
            working = applied.document
            working_snapshot = build_snapshot(working, live_session=target.is_live)
        response = self._run_semantic_operations(operations, path, dry_run, expected_sha256, txid)
        response["routing"] = {
            "connection_count": len(operations),
            "routes": metrics,
            "clearance_resolutions": [
                {
                    key: item[key]
                    for key in (
                        "requested_clearance_mm",
                        "required_clearance_mm",
                        "effective_clearance_mm",
                        "clearance_sources",
                        "netclass_rules_applied",
                        "netclass_rules_ignored",
                        "clearance_rule_status",
                    )
                    if key in item
                }
                for item in metrics
            ],
        }
        response["clearance_rule_status"] = {
            "per_route": [item.get("clearance_rule_status") for item in metrics],
            "netclass_rules_applied": all(
                bool(item.get("netclass_rules_applied", False)) for item in metrics
            ),
            "netclass_rules_ignored": any(
                bool(item.get("netclass_rules_ignored", False)) for item in metrics
            ),
        }
        response["netclass_rules_ignored"] = response["clearance_rule_status"][
            "netclass_rules_ignored"
        ]
        return response

    def route_diff_pair(
        self,
        pair: str,
        *,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        route = synthesize_differential_pair_route(
            snapshot,
            DifferentialPairRouteConfig(
                pair=pair,
                start_pad_point_id=start_pad_point_id,
                end_pad_point_id=end_pad_point_id,
                layer=layer,
                preferred_layers=preferred_layers or [],
                width=width,
                gap=gap,
                clearance=clearance,
                grid=grid,
                via_style=via_style,
                max_vias=max_vias,
                via_cost=via_cost,
                max_detour=max_detour,
            ),
        )
        response = self._run_semantic_write(route.operation, path, dry_run, expected_sha256, txid)
        response["routing"] = {
            "center_points": [point.as_dict() for point in route.center_points],
            "positive_points": [point.as_dict() for point in route.positive_points],
            "negative_points": [point.as_dict() for point in route.negative_points],
            "metrics": route.metrics,
            "clearance_resolution": route.clearance_resolution,
            "assumptions": route.assumptions,
        }
        response["clearance_rule_status"] = route.clearance_resolution["clearance_rule_status"]
        response["netclass_rules_ignored"] = route.clearance_resolution["netclass_rules_ignored"]
        response["warnings"] = [*response.get("warnings", []), *route.warnings]
        response["limitations"] = [
            *response.get("limitations", []),
            *route.limitations,
        ]
        return response

    def plan_diff_pair_route(
        self,
        pair: str,
        *,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = DifferentialPairRouteConfig(
            pair=pair,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            layer=layer,
            preferred_layers=preferred_layers or [],
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
        )
        route = synthesize_differential_pair_route(snapshot, config)
        resolved_config = config.model_copy(update={"clearance": route.operation.clearance})
        preview = self._preview_semantic_operations(document, [route.operation])
        record = self.plans.create(
            plan_type="diff_pair_route",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=resolved_config.model_dump(mode="json"),
            operations=[route.operation.model_dump(mode="json")],
            changed_ids=[
                route.operation.pair,
                route.operation.positive_net,
                route.operation.negative_net,
            ],
            unresolved=[],
            candidates=[{"metrics": route.metrics}],
            score={"absolute_skew_mm": float(route.metrics["absolute_skew_mm"])},
            metrics=route.metrics,
            assumptions=route.assumptions,
            warnings=route.warnings,
            limitations=route.limitations,
        )
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "center_points": [point.as_dict() for point in route.center_points],
                "positive_points": [point.as_dict() for point in route.positive_points],
                "negative_points": [point.as_dict() for point in route.negative_points],
                "metrics": route.metrics,
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        response = self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            limitations=record.limitations,
            resources=resources,
        )
        response["clearance_rule_status"] = route.clearance_resolution["clearance_rule_status"]
        response["netclass_rules_ignored"] = route.clearance_resolution["netclass_rules_ignored"]
        return response

    def plan_route_nets(
        self,
        nets: list[str],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
    ) -> dict[str, Any]:
        if not nets:
            raise DocumentError("At least one net is required", code="scope_required")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        pairs = self._unrouted_pairs(snapshot, nets)
        if not pairs:
            raise DocumentError("No matching exported unrouted connections were found")
        if len(pairs) > 20:
            raise DocumentError("A local route plan is limited to 20 connections")
        operations: list[SemanticOperation] = []
        candidates: list[dict[str, Any]] = []
        working = document
        working_snapshot = snapshot
        for pair in pairs:
            route = synthesize_route(
                working_snapshot,
                RouteConnectionConfig(
                    net=pair["net_id"],
                    start_object_id=pair["start_object_id"],
                    end_object_id=pair["end_object_id"],
                    layer=layer,
                    width=width,
                    clearance=clearance,
                    grid=grid,
                    preferred_layers=preferred_layers or [],
                    via_style=via_style,
                    max_vias=max_vias,
                    via_cost=via_cost,
                ),
            )
            operations.append(route.operation)
            candidates.append(
                {
                    "net_id": pair["net_id"],
                    "points": [point.as_dict() for point in route.points],
                    "metrics": route.metrics,
                }
            )
            applied = apply_semantic_operations(
                working, [route.operation], live_session=target.is_live
            )
            working = applied.document
            working_snapshot = build_snapshot(working, live_session=target.is_live)
        preview = self._preview_semantic_operations(document, operations)
        total_length = sum(float(item["metrics"]["length_mm"]) for item in candidates)
        resolved_clearance = float(candidates[0]["metrics"]["clearance_mm"])
        record = self.plans.create(
            plan_type="route_nets",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config={
                "nets": nets,
                "layer": layer,
                "width": width,
                "clearance": resolved_clearance,
                "grid": grid,
                "preferred_layers": preferred_layers or [],
                "via_style": via_style,
                "max_vias": max_vias,
                "via_cost": via_cost,
            },
            operations=[operation.model_dump(mode="json") for operation in operations],
            changed_ids=sorted({pair["net_id"] for pair in pairs}),
            unresolved=[],
            candidates=candidates,
            score={"total_length_mm": total_length},
            metrics={
                "connection_count": len(operations),
                "total_length_mm": total_length,
                "clearance_resolutions": [
                    {
                        key: item["metrics"][key]
                        for key in (
                            "requested_clearance_mm",
                            "required_clearance_mm",
                            "effective_clearance_mm",
                            "clearance_sources",
                            "netclass_rules_applied",
                            "netclass_rules_ignored",
                            "clearance_rule_status",
                        )
                        if key in item["metrics"]
                    }
                    for item in candidates
                ],
                "netclass_rules_ignored": any(
                    bool(item["metrics"].get("netclass_rules_ignored", False))
                    for item in candidates
                ),
            },
            assumptions=["Connections are routed sequentially with bounded 45-degree A*."],
            warnings=[],
            limitations=["No push-and-shove or rip-up/retry is implemented."],
        )
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "routes": candidates,
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        response = self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            limitations=record.limitations,
            resources=resources,
        )
        response["clearance_rule_status"] = {
            "per_route": [item["metrics"].get("clearance_rule_status") for item in candidates],
            "netclass_rules_ignored": any(
                bool(item["metrics"].get("netclass_rules_ignored", False)) for item in candidates
            ),
        }
        response["netclass_rules_ignored"] = response["clearance_rule_status"][
            "netclass_rules_ignored"
        ]
        return response

    def apply_route_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        plan = self.plans.read(plan_id)
        if plan.plan_type not in {"route_nets", "diff_pair_route"}:
            raise DocumentError(
                f"Unexpected route plan type for {plan_id}: {plan.plan_type}",
                code="transaction_conflict",
            )
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type=plan.plan_type,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def export_autorouter_dsn(
        self,
        path: str | None = None,
        *,
        design_name: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        dsn = export_dsn(snapshot, design_name=design_name)
        record = self.external_jobs.create_export_job(
            snapshot.info,
            target.path,
            dsn,
            manifest={
                "format": "Specctra DSN",
                "serializer": "diptrace-mcp-bounded-v1",
                "document_id": snapshot.info.document_id,
                "source_sha256": snapshot.info.sha256,
                "coordinate_units": "mm",
                "resolution": 1000,
                "assumptions": [
                    "DipTrace board coordinates are emitted directly in Specctra millimetres.",
                    "Only embedded pattern shapes accepted by capability validation are emitted.",
                    "Quoted tokens use only printable ASCII excluding quote and backslash; "
                    "no escape convention is assumed.",
                ],
            },
        )
        response = self._read_success(
            snapshot.info,
            {"job": record.model_dump(mode="json")},
            resources=job_resources(record.jobid),
            limitations=[
                "The bounded serializer rejects cutouts, keepouts, pours and unsupported "
                "pad shapes, plus identifiers requiring unverified escaping or encoding."
            ],
        )
        response["job"] = record.model_dump(mode="json")
        return response

    def run_external_autorouter(
        self,
        path: str | None = None,
        *,
        dsn_job_id: str | None = None,
        dsn_path: str | None = None,
        max_passes: int = 100,
        threads: int = 1,
        timeout_seconds: int | None = None,
        ignore_net_classes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.policy.require_external_execution(operation="run_external_autorouter")
        if dsn_job_id is not None and dsn_path is not None:
            raise DocumentError("Pass either dsn_job_id or dsn_path, not both")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if dsn_job_id is not None:
            export_job = self.jobs.read(dsn_job_id)
            if export_job.job_type != "dsn_export" or export_job.status != "completed":
                raise DocumentError("dsn_job_id must identify a completed DSN export job")
            if export_job.source_sha256 != snapshot.info.sha256:
                raise Sha256MismatchError(
                    "DSN export was created from a different document revision",
                    details={
                        "dsn_source_sha256": export_job.source_sha256,
                        "current_sha256": snapshot.info.sha256,
                    },
                )
            dsn = self.jobs.artifact_path(dsn_job_id, "input.dsn").read_bytes()
        elif dsn_path is not None:
            source = self.settings.resolve_allowed_path(dsn_path)
            if source.stat().st_size > self.settings.max_document_bytes:
                raise DocumentError("DSN input exceeds the document size limit")
            dsn = source.read_bytes()
        else:
            dsn = export_dsn(snapshot)
        record = self.external_jobs.start_freerouting(
            snapshot.info,
            target.path,
            dsn,
            max_passes=max_passes,
            threads=threads,
            timeout_seconds=timeout_seconds,
            ignore_net_classes=list(ignore_net_classes or []),
        )
        response = self._read_success(
            snapshot.info,
            {"job": record.model_dump(mode="json")},
            resources=job_resources(record.jobid),
        )
        response["job"] = record.model_dump(mode="json")
        return response

    def inspect_autorouter_result(
        self,
        jobid: str,
        path: str | None = None,
        *,
        via_style: str | None = None,
    ) -> dict[str, Any]:
        job = self.jobs.read(jobid)
        if job.job_type != "freerouting" or job.status != "completed":
            raise DocumentError(
                "Autorouter result inspection requires a completed Freerouting job",
                details={"jobid": jobid, "status": job.status, "job_type": job.job_type},
            )
        target_path = path or job.target_path
        if target_path is None:
            raise DocumentError("Autorouter job has no associated DipTrace target")
        document, target = self.load(target_path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.info.sha256 != job.source_sha256:
            raise Sha256MismatchError(
                "DipTrace document changed after the autorouter job was created",
                details={
                    "job_source_sha256": job.source_sha256,
                    "current_sha256": snapshot.info.sha256,
                },
            )
        ses_path = self.jobs.artifact_path(jobid, "output.ses")
        session = parse_ses(ses_path.read_bytes(), max_bytes=self.settings.max_document_bytes)
        operation_plan = session_to_operations(snapshot, session, via_style=via_style)
        plan_record = None
        resources = job_resources(jobid)
        if operation_plan.operations:
            preview = self._preview_semantic_operations(
                document, cast(list[SemanticOperation], operation_plan.operations)
            )
            plan_record = self.plans.create(
                plan_type="autorouter_ses_import",
                document_id=snapshot.info.document_id,
                source_sha256=snapshot.info.sha256,
                target_path=target.path,
                config={"jobid": jobid, "via_style": via_style},
                operations=[
                    operation.model_dump(mode="json") for operation in operation_plan.operations
                ],
                changed_ids=sorted({operation.net for operation in operation_plan.operations}),
                unresolved=operation_plan.skipped,
                candidates=[item.model_dump(mode="json") for item in session.routes],
                score={"imported_length_mm": float(operation_plan.metrics["imported_length_mm"])},
                metrics=operation_plan.metrics,
                assumptions=[
                    "SES coordinates are converted using the routes resolution scope.",
                    "Only non-branching two-endpoint nets without existing traces are importable.",
                ],
                warnings=session.warnings,
                limitations=[
                    "Branched nets and partial replacement of existing routing are "
                    "inspection-only.",
                    "Via-containing routes require an explicit DipTrace via_style mapping.",
                ],
            )
            plan_resources = self.plans.store_preview(
                plan_record.plan_id,
                svg=preview["svg"],
                geometry={
                    **preview["json"],
                    "jobid": jobid,
                    "ses_metrics": operation_plan.metrics,
                },
                diff=preview["diff"],
            )
            resources.extend(plan_resources)
            plan_record = self.plans.read(plan_record.plan_id)
        return self._read_success(
            snapshot.info,
            {
                "session": session.model_dump(mode="json"),
                "inspection": {
                    **operation_plan.metrics,
                    "imported_nets": operation_plan.imported_nets,
                    "skipped": operation_plan.skipped,
                },
                "plan": plan_record.model_dump(mode="json") if plan_record else None,
            },
            resources=resources,
            limitations=[
                "Inspection is geometric/topological and never trusts external DRC results."
            ],
        )

    def import_autorouter_ses(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type="autorouter_ses_import",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def route_connections(
        self,
        connections: list[dict[str, Any]],
        *,
        ripup_retry: bool = True,
        max_ripup_attempts: int = 4,
        ordering: RoutingOrder = "congestion_aware",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route multiple connections sequentially with bounded rip-up/retry."""

        configs = [RouteConnectionConfig.model_validate(item) for item in connections]
        document, _target = self.load(path)
        synthesis = synthesize_routes_with_retry(
            document,
            configs,
            ripup_retry=ripup_retry,
            max_ripup_attempts=max_ripup_attempts,
            ordering=ordering,
        )
        if not synthesis.operations:
            raise RoutingError(
                "No connection could be routed",
                details={"failed": synthesis.failed},
            )
        response = self._run_semantic_operations(
            synthesis.operations, path, dry_run, expected_sha256, txid
        )
        response["routing"] = synthesis.metrics
        response["clearance_rule_status"] = {
            "per_route": [
                item.get("clearance_rule_status")
                for item in synthesis.metrics.get("clearance_resolutions", [])
            ],
            "netclass_rules_ignored": bool(synthesis.metrics.get("netclass_rules_ignored", False)),
        }
        response["netclass_rules_ignored"] = response["clearance_rule_status"][
            "netclass_rules_ignored"
        ]
        if synthesis.failed:
            response.setdefault("warnings", []).append(
                f"{len(synthesis.failed)} connection(s) could not be routed; "
                "see routing metrics for details."
            )
            response["routing"]["failed"] = synthesis.failed
        if synthesis.ripups:
            response["routing"]["ripups"] = synthesis.ripups
        return response

    def analyze_routing_congestion(
        self,
        connections: list[dict[str, Any]],
        *,
        ordering: RoutingOrder = "congestion_aware",
        path: str | None = None,
    ) -> dict[str, Any]:
        """Rank routing connections deterministically without changing the document."""

        configs = [RouteConnectionConfig.model_validate(item) for item in connections]
        if not configs:
            raise RoutingError("At least one connection is required")
        document, target = self.load(path)
        ordered, priorities = plan_connection_order(
            document,
            configs,
            ordering=ordering,
        )
        snapshot = self.models.get(document, live_session=target.is_live)
        clearance_resolutions = []
        for _index, config in ordered:
            net = _find_net(snapshot, config.net)
            layer_ids, _start_layer, _end_layer = _route_layers(snapshot, config)
            # Congestion ranking uses the same clearance resolver as routing;
            # the returned resolution is part of the read-only decision record.
            clearance_resolutions.append(
                resolve_clearance(
                    snapshot,
                    layer_ids,
                    config.clearance,
                    nets=[net],
                ).as_dict()
            )
        return self._read_success(
            snapshot.info,
            {
                "ordering": ordering,
                "routing_order": [index for index, _config in ordered],
                "priorities": [item.as_dict() for item in priorities],
                "clearance_resolutions": clearance_resolutions,
                "clearance_rule_status": {
                    "per_route": [item["clearance_rule_status"] for item in clearance_resolutions],
                    "netclass_rules_ignored": any(
                        item["netclass_rules_ignored"] for item in clearance_resolutions
                    ),
                },
                "netclass_rules_ignored": any(
                    item["netclass_rules_ignored"] for item in clearance_resolutions
                ),
            },
            limitations=[
                "Congestion ranking is a deterministic corridor/bounding-box heuristic, "
                "not a global routing or push-and-shove solver."
            ],
        )

    def run_ngspice_simulation(
        self,
        *,
        netlist: str | None = None,
        netlist_path: str | None = None,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Run a user-supplied ngspice netlist as a bounded external batch job."""

        self.policy.require_external_execution(operation="run_ngspice_simulation")
        if (netlist is None) == (netlist_path is None):
            raise DocumentError("Pass exactly one of netlist or netlist_path")
        max_netlist_bytes = 256 * 1024
        if netlist_path is not None:
            source = self.settings.resolve_allowed_path(netlist_path)
            if source.stat().st_size > max_netlist_bytes:
                raise DocumentError("Netlist file exceeds the 256 KiB limit")
            netlist_bytes = source.read_bytes()
        else:
            assert netlist is not None
            netlist_bytes = netlist.encode("utf-8")
        if len(netlist_bytes) > max_netlist_bytes:
            raise DocumentError("Netlist exceeds the 256 KiB limit")
        info: DocumentInfo | None = None
        target_path: Path | None = None
        if path is not None:
            document, target = self.load(path)
            info = self.models.get(document, live_session=target.is_live).info
            target_path = target.path
        record = self.external_jobs.start_ngspice(
            info,
            target_path,
            netlist_bytes,
            timeout_seconds=timeout_seconds,
        )
        return {
            "ok": True,
            "document": info.model_dump() if info is not None else None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": [],
            "limitations": [
                "The netlist is user-supplied; the server does not verify its electrical "
                "correctness.",
                "Simulation results are ngspice output, not in-circuit measurements.",
            ],
            "resources": job_resources(record.jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def run_openems_stripline_analysis(
        self,
        *,
        width_mm: float,
        copper_thickness_mm: float,
        lower_dielectric_height_mm: float,
        upper_dielectric_height_mm: float,
        dielectric_constant: float,
        frequencies_hz: list[float],
        dielectric_loss_tangent: float = 0.0,
        conductor_conductivity_s_per_m: float = 58_000_000.0,
        trace_length_mm: float = 20.0,
        port_impedance_ohm: float = 50.0,
        mesh_cells_per_wavelength: int = 30,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Start a bounded off-center/centered stripline field-solver job."""

        self.policy.require_external_execution(operation="run_openems_stripline_analysis")
        request = FieldSolverRequest(
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            lower_dielectric_height_mm=lower_dielectric_height_mm,
            upper_dielectric_height_mm=upper_dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            dielectric_loss_tangent=dielectric_loss_tangent,
            conductor_conductivity_s_per_m=conductor_conductivity_s_per_m,
            frequencies_hz=frequencies_hz,
            trace_length_mm=trace_length_mm,
            port_impedance_ohm=port_impedance_ohm,
            mesh_cells_per_wavelength=mesh_cells_per_wavelength,
        )
        info: DocumentInfo | None = None
        target_path: Path | None = None
        if path is not None:
            document, target = self.load(path)
            info = self.models.get(document, live_session=target.is_live).info
            target_path = target.path
        record = self.external_jobs.start_openems(
            info,
            target_path,
            request,
            timeout_seconds=timeout_seconds,
        )
        return {
            "ok": True,
            "document": info.model_dump() if info is not None else None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": [],
            "limitations": [
                "The result is produced by the configured openEMS runner and is not a "
                "fabrication guarantee.",
                "Mesh, port, convergence, material, and loss assumptions remain part of the "
                "solver result and must be reviewed.",
            ],
            "resources": job_resources(record.jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def get_job_status(self, jobid: str) -> dict[str, Any]:
        record = self.jobs.read(jobid)
        return {
            "ok": True,
            "document": None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": record.warnings,
            "limitations": [],
            "resources": job_resources(jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def get_job_result(self, jobid: str) -> dict[str, Any]:
        record = self.jobs.read(jobid)
        return {
            "ok": True,
            "document": None,
            "result": {
                "status": record.status,
                "result": record.result,
                "partial_result": record.partial_result,
                "error": record.error,
                "artifacts": record.artifacts,
            },
            "warnings": record.warnings,
            "limitations": [],
            "resources": job_resources(jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def cancel_job(self, jobid: str) -> dict[str, Any]:
        record = self.external_jobs.cancel(jobid)
        return self.get_job_status(record.jobid)

    def list_jobs(self, status: str | None = None) -> dict[str, Any]:
        allowed = {None, "queued", "running", "completed", "failed", "cancelled"}
        if status not in allowed:
            raise DocumentError(f"Unknown job status: {status}")
        records = self.jobs.list(status=cast(JobStatus | None, status))
        return {
            "ok": True,
            "document": None,
            "result": {
                "matched_count": len(records),
                "jobs": [record.model_dump(mode="json") for record in records],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def list_exports(self) -> dict[str, Any]:
        records = self.exports.list()
        return {
            "ok": True,
            "document": None,
            "result": {
                "matched_count": len(records),
                "exports": [record.model_dump(mode="json") for record in records],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def export_resource(self, export_id: str, artifact: str) -> str:
        return self.exports.artifact(export_id, artifact).decode("utf-8", errors="strict")

    def job_resource(self, jobid: str, artifact: str) -> str:
        record = self.jobs.read(jobid)
        if artifact == "status":
            return json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if artifact == "result":
            return json.dumps(
                {"status": record.status, "result": record.result, "error": record.error},
                ensure_ascii=False,
                indent=2,
            )
        name = {
            "log": "log.txt",
            "input.dsn": "input.dsn",
            "output.ses": "output.ses",
            "field_solver_input.json": "field_solver_input.json",
            "field_solver_result.json": "field_solver_result.json",
            "manifest.json": "manifest.json",
        }.get(artifact)
        if name is None:
            raise CapabilityUnavailableError(f"Unknown job resource: {artifact}")
        artifact_path = self.jobs.artifact_path(jobid, name)
        if not artifact_path.exists():
            return ""
        data = artifact_path.read_bytes()
        if artifact == "log" and len(data) > self.settings.max_external_log_bytes:
            data = data[-self.settings.max_external_log_bytes :]
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _unrouted_pairs(
        snapshot: DocumentSnapshot,
        nets: list[str],
    ) -> list[dict[str, str]]:
        if snapshot.board is None:
            raise DocumentError("Routing requires a PCB document")
        requested = {item.casefold() for item in nets}
        pairs: list[dict[str, str]] = []
        for ratline in snapshot.board.ratlines:
            endpoints = ratline.get("endpoints", [])
            if len(endpoints) != 2 or any(item.get("pad_id") is None for item in endpoints):
                continue
            first = snapshot.get_object(str(endpoints[0]["pad_id"]))
            second = snapshot.get_object(str(endpoints[1]["pad_id"]))
            if first.net_id is None or first.net_id != second.net_id:
                continue
            net = next((item for item in snapshot.board.nets if item.xml_id == first.net_id), None)
            if net is None or not (
                (net.name or "").casefold() in requested
                or net.stable_id.casefold() in requested
                or (net.xml_id or "").casefold() in requested
            ):
                continue
            pairs.append(
                {
                    "net_id": net.stable_id,
                    "start_object_id": first.stable_id,
                    "end_object_id": second.stable_id,
                }
            )
        return pairs

    def plan_silkscreen(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        clearance: float = 0.2,
        board_edge_clearance: float = 0.2,
        grid: float = 0.25,
        search_steps: int = 4,
        include_board_texts: bool = False,
        avoid_component_bodies: bool = False,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = SilkscreenPlanConfig.model_validate(
            {
                "selector": selector or {},
                "clearance": clearance,
                "board_edge_clearance": board_edge_clearance,
                "grid": grid,
                "search_steps": search_steps,
                "include_board_texts": include_board_texts,
                "avoid_component_bodies": avoid_component_bodies,
            }
        )
        planned = plan_silkscreen(snapshot, config)
        record = self.plans.create(
            plan_type="silkscreen",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[operation.model_dump(mode="json") for operation in planned.operations],
            changed_ids=planned.changed_ids,
            unresolved=planned.unresolved,
            candidates=planned.candidates,
            score=planned.score,
            metrics=planned.metrics,
            assumptions=planned.assumptions,
            warnings=planned.warnings,
            limitations=planned.limitations,
        )
        if planned.operations:
            preview = self._preview_semantic_operations(document, planned.operations)
        else:
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "candidates": planned.candidates,
                "unresolved": planned.unresolved,
                "score": planned.score,
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        return self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            warnings=planned.warnings,
            limitations=planned.limitations,
            resources=resources,
        )

    def analyze_placement(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = analyze_placement(
            snapshot,
            QuerySelector.model_validate(selector or {}),
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
        )
        return self._read_success(
            snapshot.info,
            result,
            limitations=["Component bounds are estimated when body/courtyard geometry is absent."],
        )

    def generate_placement_candidates(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = self._placement_config(selector, options)
        candidates = generate_placement_candidates(snapshot, config)
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(candidates),
                "config": config.model_dump(mode="json"),
                "items": candidates,
            },
            limitations=["Candidate geometry uses normalized component bounds."],
        )

    def score_placement(
        self,
        placements: list[dict[str, Any]],
        path: str | None = None,
        *,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = PlacementConfig(
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=PlacementWeights.model_validate(weights or {}),
        )
        proposals = [PlacementProposal.model_validate(item) for item in placements]
        score, violations = score_placement_proposal(snapshot, proposals, config)
        return self._read_success(
            snapshot.info,
            {"score": score, "violations": violations},
            limitations=["Ratsnest cost uses component anchors, not exact pad anchors."],
        )

    def plan_component_placement(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = self._placement_config(selector, options)
        planned = plan_component_placement(snapshot, config)
        before_findings, _, _, _ = run_checks(snapshot, categories={"placement"})
        if planned.operations:
            applied = apply_semantic_operations(
                document, planned.operations, live_session=target.is_live
            )
            after_snapshot = build_snapshot(applied.document, live_session=target.is_live)
            after_findings, _, _, _ = run_checks(after_snapshot, categories={"placement"})
            preview = self._preview_semantic_operations(document, planned.operations)
        else:
            after_findings = before_findings
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        before_errors = sum(item.severity == "error" for item in before_findings)
        after_errors = sum(item.severity == "error" for item in after_findings)
        if after_errors > before_errors:
            raise DrcRegressionError(
                "Placement plan introduces new placement DRC errors",
                details={
                    "errors_before": before_errors,
                    "errors_after": after_errors,
                },
                object_ids=planned.changed_ids,
            )
        metrics = {
            **planned.metrics,
            "validation": {
                "placement_errors_before": before_errors,
                "placement_errors_after": after_errors,
                "no_new_placement_errors": after_errors <= before_errors,
            },
        }
        record = self.plans.create(
            plan_type="component_placement",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[operation.model_dump(mode="json") for operation in planned.operations],
            changed_ids=planned.changed_ids,
            unresolved=planned.unresolved,
            candidates=planned.candidates,
            score=planned.score,
            metrics=metrics,
            assumptions=planned.assumptions,
            warnings=planned.warnings,
            limitations=planned.limitations,
        )
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "candidates": planned.candidates,
                "unresolved": planned.unresolved,
                "score": planned.score,
                "validation": metrics["validation"],
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        return self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            warnings=planned.warnings,
            limitations=planned.limitations,
            resources=resources,
        )

    def apply_component_placement_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type="component_placement",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def apply_silkscreen_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type="silkscreen",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def _apply_stored_plan(
        self,
        plan_id: str,
        *,
        expected_plan_type: str,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        plan = self.plans.read(plan_id)
        if plan.plan_type != expected_plan_type:
            raise DocumentError(
                f"Unexpected plan type for {plan_id}: {plan.plan_type}",
                code="transaction_conflict",
                details={
                    "expected_plan_type": expected_plan_type,
                    "actual_plan_type": plan.plan_type,
                },
            )
        target_path = self.settings.resolve_allowed_path(plan.target_path)
        document = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
        if document.sha256 != plan.source_sha256:
            self.plans.update(plan_id, status="obsolete", transaction_id=plan.transaction_id)
            raise Sha256MismatchError(
                "Document changed after the silkscreen plan was generated",
                details={
                    "plan_sha256": plan.source_sha256,
                    "current_sha256": document.sha256,
                },
            )
        if expected_sha256 is not None and expected_sha256 != plan.source_sha256:
            raise Sha256MismatchError(
                "Provided SHA does not match the silkscreen plan source",
                details={
                    "plan_sha256": plan.source_sha256,
                    "provided_sha256": expected_sha256,
                },
            )
        operations = parse_semantic_operations(plan.operations)
        if not operations:
            raise EditError("Silkscreen plan contains no changes")
        response = self._run_semantic_operations(
            operations,
            str(target_path),
            dry_run,
            expected_sha256,
            txid,
        )
        transaction = response.get("transaction") or {}
        transaction_id = transaction.get("txid")
        status: PlanStatus = "committed" if transaction.get("status") == "committed" else "staged"
        updated = self.plans.update(
            plan_id,
            status=status,
            transaction_id=transaction_id,
        )
        response["plan"] = updated.model_dump(mode="json")
        return response

    @staticmethod
    def _placement_config(selector: dict[str, Any], options: dict[str, Any]) -> PlacementConfig:
        payload = {"selector": selector, **options}
        if "weights" in payload:
            payload["weights"] = PlacementWeights.model_validate(payload["weights"] or {})
        return PlacementConfig.model_validate(payload)

    def plan_resource(self, plan_id: str, resource: str) -> str:
        if resource == "summary":
            return json.dumps(
                self.plans.read(plan_id).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        paths = {
            "preview.svg": self.plans.preview_svg_path(plan_id),
            "preview.json": self.plans.preview_json_path(plan_id),
            "diff": self.plans.diff_path(plan_id),
        }
        try:
            resource_path = paths[resource]
        except KeyError as exc:
            raise DocumentError(
                f"Unknown plan resource: {resource}", code="object_not_found"
            ) from exc
        if not resource_path.is_file():
            raise DocumentError(
                f"Plan resource is unavailable: {resource}", code="object_not_found"
            )
        return resource_path.read_text(encoding="utf-8")

    def run_review(
        self,
        path: str | None = None,
        *,
        profile: str,
        categories: set[str] | None = None,
    ) -> dict[str, Any]:
        return self._review_service.run_review(path, profile=profile, categories=categories)

    def get_findings(self, report_id: str) -> dict[str, Any]:
        return self._review_service.get_findings(report_id)

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        return self._review_service.get_finding(finding_id)

    def review_resource(self, report_id: str) -> str:
        return self._review_service.review_resource(report_id)

    def findings_resource(self, document_id: str) -> str:
        return self._review_service.findings_resource(document_id)

    def finish_live_session(
        self,
        action: SessionAction,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        if action == "apply":
            self.policy.require_write(dry_run=False, operation="finish_live_session")
        request = self.sessions.request_finish(action, expected_sha256)
        return self.sessions.wait_for_finish_outcome(request)

    def abandon_live_session(self, reason: str) -> dict[str, Any]:
        """Terminate stale local session state without applying working XML."""

        metadata = self.sessions.abandon_active(reason)
        return {
            "session_id": metadata["session_id"],
            "outcome": "abandoned",
            "local_bridge_status": "abandoned",
            "written": False,
            "reason": metadata["abandon_reason"],
            "diptrace_host_acknowledged": False,
            "acknowledgement_scope": "local_session_state_only",
            "message": (
                "The local session was abandoned without applying working XML or "
                "replacing the exchange file."
            ),
        }

    def scan_documents(self, root: str | None = None, recursive: bool = True) -> dict[str, Any]:
        scan_root = self.settings.resolve_allowed_path(root or str(self.settings.workspace))
        if not scan_root.is_dir():
            raise DocumentError(f"Scan root is not a directory: {scan_root}")
        iterator = scan_root.rglob("*") if recursive else scan_root.glob("*")
        results: list[dict[str, Any]] = []
        examined = 0
        truncated = False
        for candidate in iterator:
            if not candidate.is_file() or candidate.suffix.lower() not in _CANDIDATE_SUFFIXES:
                continue
            try:
                candidate = self.settings.resolve_allowed_path(candidate)
            except PathAccessError:
                continue
            examined += 1
            if examined > self.settings.max_scan_files:
                truncated = True
                break
            header = self._read_source_header(candidate)
            if header is None:
                continue
            try:
                relative = candidate.relative_to(self.settings.workspace)
                relative_path = str(relative)
            except ValueError:
                relative_path = None
            results.append(
                {
                    "path": str(candidate),
                    "relative_path": relative_path,
                    "size_bytes": candidate.stat().st_size,
                    **header,
                }
            )
        return {
            "root": str(scan_root),
            "recursive": recursive,
            "examined_candidates": min(examined, self.settings.max_scan_files),
            "truncated": truncated,
            "documents": results,
        }

    def _scan_libraries(
        self,
        source_type: str,
        root: str | None,
        recursive: bool,
    ) -> dict[str, Any]:
        scanned = self.scan_documents(root, recursive)
        items = [item for item in scanned["documents"] if item.get("type") == source_type]
        return {
            "ok": True,
            "document": None,
            "result": {
                "source_type": source_type,
                "matched_count": len(items),
                "items": items,
                "truncated": scanned["truncated"],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def _get_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        return self._bom_service._get_library_item(path, kind, stable_id_value, name)

    def _validate_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        return self._bom_service._validate_library_item(path, kind, stable_id_value, name)

    def _run_semantic_write(
        self,
        operation: SemanticOperation,
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        return self._run_semantic_operations([operation], path, dry_run, expected_sha256, txid)

    def _run_semantic_operations(
        self,
        operations: Sequence[SemanticOperation],
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        if not operations:
            raise EditError("At least one semantic operation is required")
        self.policy.require_write(
            dry_run=dry_run,
            operation=operations[0].kind if len(operations) == 1 else "semantic_operations",
        )
        if not dry_run and expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required for semantic writes",
                txid=txid,
            )
        incoming_operations = [operation.model_dump() for operation in operations]
        _require_transaction_capacity(len(incoming_operations))
        if txid is None:
            document, target = self.load(path)
            snapshot = build_snapshot(document, live_session=target.is_live)
            if expected_sha256 is not None and expected_sha256 != snapshot.info.sha256:
                raise Sha256MismatchError(
                    "Document changed before the semantic operation was planned",
                    details={
                        "expected_sha256": expected_sha256,
                        "current_sha256": snapshot.info.sha256,
                    },
                )
            _apply_bounded_semantic_operations(
                document,
                list(operations),
                live_session=target.is_live,
            )
            tx_record = self.transactions.create(
                snapshot.info,
                target.path,
                source_sha256=snapshot.info.sha256,
                expected_sha256=expected_sha256 or snapshot.info.sha256,
                notes=[operation.kind for operation in operations],
            )
            txid = tx_record.txid
            self.transactions.store_snapshot(txid, document.raw_bytes)
            self.transactions.update(
                txid,
                status="staged",
                operations=incoming_operations,
                compiled_patch_count=len(operations),
                snapshot_path=str(self.transactions.snapshot_path(txid)),
            )
        else:
            existing = self.transactions.read(txid)
            if existing.status not in {"staged", "validated"}:
                raise TransactionConflictError(
                    f"Transaction cannot be edited in state {existing.status}: {txid}",
                    txid=txid,
                )
            if path is not None:
                supplied_target = self.resolve_target(path)
                if supplied_target.path != Path(existing.target_path):
                    raise TransactionConflictError(
                        "The supplied path does not match the transaction target",
                        details={
                            "transaction_path": existing.target_path,
                            "supplied_path": str(supplied_target.path),
                        },
                        txid=txid,
                    )
            combined_operations = (
                [*existing.operations, *incoming_operations]
                if existing.operations != incoming_operations
                else list(existing.operations)
            )
            _require_transaction_capacity(len(combined_operations))
            source = self._load_snapshot_record(existing)
            _apply_bounded_semantic_operations(
                source,
                parse_semantic_operations(combined_operations),
                live_session=(
                    self._session_id_from_working(Path(existing.target_path)) is not None
                ),
            )
            if existing.operations != incoming_operations:
                self.transactions.update(
                    txid,
                    status="staged",
                    operations=combined_operations,
                    compiled_patch_count=len(combined_operations),
                    snapshot_path=existing.snapshot_path
                    or str(self.transactions.snapshot_path(txid)),
                    changed_ids=[],
                    validation_before={},
                    validation_after_preview={},
                    preview_resources=[],
                    preview_metadata={},
                )
        preview = self.preview_transaction(txid)
        if dry_run:
            return preview
        return self.commit_transaction(
            txid,
            expected_sha256=expected_sha256,
        )

    def _preview_semantic_operations(
        self,
        document: DipTraceDocument,
        operations: list[SemanticOperation],
    ) -> dict[str, Any]:
        before = build_snapshot(document)
        result = _apply_bounded_semantic_operations(document, operations)
        after = build_snapshot(result.document)
        before_findings, _, _, _ = run_checks(before)
        after_findings, _, _, _ = run_checks(after)
        before_errors: dict[str, int] = {}
        after_errors: dict[str, int] = {}
        for finding in before_findings:
            if finding.severity == "error":
                before_errors[finding.category] = before_errors.get(finding.category, 0) + 1
        for finding in after_findings:
            if finding.severity == "error":
                after_errors[finding.category] = after_errors.get(finding.category, 0) + 1
        allow_connectivity_regression = any(
            (
                isinstance(operation, DeleteTraceOperation)
                and operation.allow_connectivity_regression
            )
            or isinstance(operation, SyncSchematicToPcbOperation)
            for operation in operations
        )
        if (
            after_errors.get("connectivity", 0) > before_errors.get("connectivity", 0)
            and not allow_connectivity_regression
        ):
            raise ConnectivityRegressionError(
                "Semantic preview introduces new connectivity errors",
                details={"before": before_errors, "after": after_errors},
                object_ids=result.changed_ids,
            )
        non_connectivity_categories = (set(before_errors) | set(after_errors)) - {"connectivity"}
        regressions = {
            category: {
                "before": before_errors.get(category, 0),
                "after": after_errors.get(category, 0),
            }
            for category in sorted(non_connectivity_categories)
            if after_errors.get(category, 0) > before_errors.get(category, 0)
        }
        if regressions:
            raise DrcRegressionError(
                "Semantic preview introduces new deterministic review errors",
                details={"regressions": regressions},
                object_ids=result.changed_ids,
            )
        svg = render_preview_svg(before, after, result.changed_ids)
        preview_json = render_preview_json(before, after, result.changed_ids)
        preview_json["review_validation"] = {
            "errors_before": before_errors,
            "errors_after": after_errors,
            "allow_connectivity_regression": allow_connectivity_regression,
        }
        diff, diff_metadata = unified_xml_diff_preview(
            before.document.raw_bytes,
            result.raw_bytes,
        )
        return {
            "svg": svg,
            "json": preview_json,
            "diff": diff,
            "diff_metadata": diff_metadata,
            "patch_count": result.patch_count,
            "changed_ids": result.changed_ids,
            "validation_before": {
                **before.info.model_dump(),
                "review_errors": before_errors,
            },
            "validation_after_preview": {
                **after.info.model_dump(),
                "review_errors": after_errors,
            },
            "warnings": result.warnings,
            "limitations": (
                ["geometry for components without footprint dimensions is estimated"]
                if before.info.kind == "pcb"
                else []
            ),
        }

    def _load_snapshot_record(self, record: TransactionRecord) -> DipTraceDocument:
        snapshot_path = self.transactions.require_snapshot(record.txid)
        snapshot = DipTraceDocument.load(snapshot_path, self.settings.max_document_bytes)
        if snapshot.sha256 != record.source_sha256:
            raise TransactionConflictError(
                "Transaction snapshot does not match its source SHA-256",
                details={
                    "expected_sha256": record.source_sha256,
                    "snapshot_sha256": snapshot.sha256,
                },
                txid=record.txid,
            )
        return snapshot

    def _session_id_from_working(self, path: Path) -> str | None:
        return self.sessions.session_id_for_working_path(path)

    def _read_source_header(self, path: Path) -> dict[str, str] | None:
        try:
            with path.open("rb") as stream:
                prefix = stream.read(16 * 1024)
        except OSError:
            return None
        match = _SOURCE_TAG.search(prefix)
        if not match:
            return None
        attributes = {
            key.decode("ascii", errors="ignore"): value.decode("utf-8", errors="replace")
            for key, value in _SOURCE_ATTRIBUTE.findall(match.group(1))
        }
        source_type = attributes.get("Type", "")
        if not source_type.startswith("DipTrace-"):
            return None
        return {
            "type": source_type,
            "source_type": source_type,
            "version": attributes.get("Version", ""),
            "units": attributes.get("Units", ""),
        }

    @staticmethod
    def _read_success(
        info: DocumentInfo,
        result: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        limitations: list[str] | None = None,
        resources: list[str] | None = None,
    ) -> dict[str, Any]:
        return read_success(
            info,
            result,
            warnings=warnings,
            limitations=limitations,
            resources=resources,
        )

    @staticmethod
    def _validate_page(offset: int, limit: int) -> None:
        validate_page(offset, limit)
