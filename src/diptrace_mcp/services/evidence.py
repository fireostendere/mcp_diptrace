"""Evidence, provenance, and fail-closed trust orchestration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from ..adapters import build_snapshot
from ..domain import (
    _HIGH_TRUST_LEVELS,
    _TRUSTED_EVIDENCE_AUTHORITIES,
    _USER_SUPPLIABLE_TRUST_LEVELS,
    DocumentProvenance,
    EvidenceAuthority,
    EvidenceFileRecord,
    FixtureValidationLevel,
    ObjectRecord,
    ProvenanceAuthority,
    SemanticComparisonEvidence,
    SourceType,
    TrustedRoundtripEvidence,
    UnsupportedCategory,
    UserSuppliedRoundtripEvidence,
    ValidatedEvidence,
    requires_diptrace_verification,
)
from ..errors import (
    DocumentError,
    EditError,
    PathAccessError,
    Sha256MismatchError,
)
from ..provenance_registry import (
    RegistryAuthorizationError,
    TrustedProvenanceRegistry,
)
from ..services.context import (
    DocumentGateway,
    ServiceContext,
)
from ..services.context import (
    bounded_text as _bounded_text,
)
from ..services.context import (
    json_size as _json_size,
)
from ..xml_document import DipTraceDocument, sha256_bytes, utc_now
from .transactions import _bounded_messages

EVIDENCE_RESPONSE_BYTE_LIMIT = 64 * 1024
EVIDENCE_LIST_PREVIEW_LIMIT = 25
EVIDENCE_TEXT_CHARACTER_LIMIT = 512


class AtomicWriteBytes(Protocol):
    def __call__(self, path: Path, data: bytes) -> None: ...


class TrustedRegistryProvider(Protocol):
    def __call__(self) -> TrustedProvenanceRegistry: ...


class WriteProvenanceSidecar(Protocol):
    def __call__(self, document_path: Path, provenance: DocumentProvenance) -> None: ...


class EvaluateRoundtripEvidence(Protocol):
    def __call__(
        self,
        path: str,
        *,
        source_path: str,
        source_sha256: str,
        saved_path: str,
        saved_sha256: str | None,
        reexport_path: str | None,
        reexport_sha256: str | None,
    ) -> RoundtripEvidenceEvaluation: ...


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
            "coordinate_precision",
            "default_attribute_omission",
            "equivalent_component_style_alias",
        }
    ),
}


def _rounded_semantic(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _rounded_semantic(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_rounded_semantic(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_rounded_semantic(item) for item in value)
    return value


def _schematic_style_signatures(
    document: DipTraceDocument, *, round_numeric: bool = True
) -> dict[str, Any]:
    def attribute_value(value: str) -> Any:
        if not round_numeric:
            return value
        try:
            return _rounded_semantic(float(value))
        except ValueError:
            return value

    def signature(element: Any) -> Any:
        return (
            element.tag,
            tuple(
                sorted(
                    (key, attribute_value(value))
                    for key, value in element.attrib.items()
                    if key not in {"Id", "RefDes", "Locked"}
                )
            ),
            (element.text or "").strip(),
            tuple(signature(child) for child in element if child.tag != "LibPath"),
        )

    return {
        component.get("ComponentStyle", ""): tuple(
            signature(part) for part in component.findall("./Part")
        )
        for component in document.root.findall("./Library/Components/Component")
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

    source_snapshot = build_snapshot(source)
    reexport_snapshot = build_snapshot(reexport)
    if source_snapshot.schematic is not None and reexport_snapshot.schematic is not None:
        source_parts = {item.xml_id: item for item in source_snapshot.schematic.parts}
        reexport_parts = {item.xml_id: item for item in reexport_snapshot.schematic.parts}
        source_styles = _schematic_style_signatures(source)
        reexport_styles = _schematic_style_signatures(reexport)
        source_raw_styles = _schematic_style_signatures(source, round_numeric=False)
        reexport_raw_styles = _schematic_style_signatures(reexport, round_numeric=False)
        if any(
            source_raw_styles[style] != reexport_raw_styles[style]
            and source_styles[style] == reexport_styles[style]
            for style in source_styles.keys() & reexport_styles.keys()
        ):
            detected.add("coordinate_precision")
        for part_id in source_parts.keys() & reexport_parts.keys():
            left = source_parts[part_id]
            right = reexport_parts[part_id]
            left_style = str(left.attributes.get("component_style", ""))
            right_style = str(right.attributes.get("component_style", ""))
            if left_style != right_style and source_styles.get(left_style) == reexport_styles.get(
                right_style
            ):
                detected.add("equivalent_component_style_alias")
            if left.position != right.position and _rounded_semantic(
                left.position
            ) == _rounded_semantic(right.position):
                detected.add("coordinate_precision")

        source_pins = {item.xml_id: item for item in source_snapshot.schematic.pins}
        reexport_pins = {item.xml_id: item for item in reexport_snapshot.schematic.pins}
        for pin_id in source_pins.keys() & reexport_pins.keys():
            source_attributes = dict(source_pins[pin_id].attributes)
            reexport_attributes = dict(reexport_pins[pin_id].attributes)
            source_attributes.setdefault("NotConnected", "N")
            reexport_attributes.setdefault("NotConnected", "N")
            if (
                source_pins[pin_id].attributes != reexport_pins[pin_id].attributes
                and source_attributes == reexport_attributes
            ):
                detected.add("default_attribute_omission")

        source_wires = {
            (item.net_id, item.xml_id): item for item in source_snapshot.schematic.wires
        }
        reexport_wires = {
            (item.net_id, item.xml_id): item for item in reexport_snapshot.schematic.wires
        }
        for wire_id in source_wires.keys() & reexport_wires.keys():
            left = source_wires[wire_id].attributes.get("points", [])
            right = reexport_wires[wire_id].attributes.get("points", [])
            if left != right and _rounded_semantic(left) == _rounded_semantic(right):
                detected.add("coordinate_precision")

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

    def record_key(record: ObjectRecord) -> tuple[str, str, str]:
        return (record.xml_id or "", record.refdes or "", record.label or record.stable_id)

    def compare_category(name: str, left: Any, right: Any) -> None:
        compared.append(name)
        if _rounded_semantic(left) != _rounded_semantic(right):
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
                _rounded_semantic(item.rotation_deg),
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
        source_styles = _schematic_style_signatures(source)
        reexport_styles = _schematic_style_signatures(reexport)
        compare_category("sheets", ss.sheets, rs.sheets)

        def part_identity(item: ObjectRecord) -> tuple[Any, ...]:
            attrs = item.attributes
            return (
                item.refdes,
                item.name,
                attrs.get("part_name"),
                attrs.get("component_part"),
                attrs.get("part_number"),
            )

        def pin_index(item: ObjectRecord) -> str:
            raw = item.xml_id or ""
            _, separator, suffix = raw.rpartition(":")
            return suffix if separator else raw

        def pin_identities(schematic: Any) -> dict[str, tuple[Any, ...]]:
            parts = {item.stable_id: part_identity(item) for item in schematic.parts}
            return {
                item.stable_id: (parts.get(item.parent_id or ""), pin_index(item))
                for item in schematic.pins
            }

        source_pin_identities = pin_identities(ss)
        reexport_pin_identities = pin_identities(rs)

        def part_sig(item: ObjectRecord, styles: dict[str, Any]) -> Any:
            attrs = item.attributes
            style = str(attrs.get("component_style", ""))
            return (
                part_identity(item),
                item.name,
                item.value,
                item.position,
                _rounded_semantic(item.rotation_deg),
                item.mirrored,
                item.locked,
                attrs.get("sheet"),
                styles.get(style, ("unresolved", style)),
                attrs.get("component_part"),
                attrs.get("part_number"),
            )

        compare_category(
            "parts",
            sorted((part_sig(item, source_styles) for item in ss.parts), key=repr),
            sorted((part_sig(item, reexport_styles) for item in rs.parts), key=repr),
        )
        compare_category(
            "patterns",
            [
                (
                    part_identity(item),
                    source_styles.get(
                        str(item.attributes.get("component_style", "")),
                        ("unresolved", item.attributes.get("component_style")),
                    ),
                )
                for item in sorted(ss.parts, key=lambda part: repr(part_identity(part)))
            ],
            [
                (
                    part_identity(item),
                    reexport_styles.get(
                        str(item.attributes.get("component_style", "")),
                        ("unresolved", item.attributes.get("component_style")),
                    ),
                )
                for item in sorted(rs.parts, key=lambda part: repr(part_identity(part)))
            ],
        )

        def pin_sig(item: ObjectRecord, identities: dict[str, tuple[Any, ...]]) -> Any:
            attributes = dict(item.attributes)
            attributes.pop("NetId", None)
            attributes.setdefault("NotConnected", "N")
            return (
                identities[item.stable_id],
                item.net_name,
                attributes,
            )

        source_pins = sorted((pin_sig(item, source_pin_identities) for item in ss.pins), key=repr)
        reexport_pins = sorted(
            (pin_sig(item, reexport_pin_identities) for item in rs.pins), key=repr
        )
        compare_category("pins", source_pins, reexport_pins)
        compare_category(
            "pin_net_membership",
            sorted(
                [(source_pin_identities[item.stable_id], item.net_name) for item in ss.pins],
                key=repr,
            ),
            sorted(
                [(reexport_pin_identities[item.stable_id], item.net_name) for item in rs.pins],
                key=repr,
            ),
        )

        def schematic_net_sig(item: ObjectRecord, identities: dict[str, tuple[Any, ...]]) -> Any:
            return (
                item.name,
                item.locked,
                sorted(
                    (identities[endpoint] for endpoint in item.relationships.get("endpoints", [])),
                    key=repr,
                ),
            )

        compare_category(
            "schematic_nets",
            sorted(
                (schematic_net_sig(item, source_pin_identities) for item in ss.nets),
                key=repr,
            ),
            sorted(
                (schematic_net_sig(item, reexport_pin_identities) for item in rs.nets),
                key=repr,
            ),
        )

        def wire_sig(item: ObjectRecord, include_geometry: bool) -> Any:
            base = (
                item.net_name,
                item.locked,
                item.attributes.get("sheet"),
            )
            return base + ((item.attributes.get("points", []),) if include_geometry else ())

        compare_category(
            "wires",
            sorted((wire_sig(item, False) for item in ss.wires), key=repr),
            sorted((wire_sig(item, False) for item in rs.wires), key=repr),
        )
        compare_category(
            "wire_geometry",
            sorted((wire_sig(item, True) for item in ss.wires), key=repr),
            sorted((wire_sig(item, True) for item in rs.wires), key=repr),
        )
        compare_category(
            "hierarchy",
            [
                (part_identity(item), item.attributes.get("sheet"))
                for item in sorted(ss.parts, key=lambda part: repr(part_identity(part)))
            ],
            [
                (part_identity(item), item.attributes.get("sheet"))
                for item in sorted(rs.parts, key=lambda part: repr(part_identity(part)))
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


class EvidenceService:
    """Implementation for fail-closed provenance and roundtrip evidence."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        trusted_registry: TrustedRegistryProvider,
        atomic_write_bytes: AtomicWriteBytes,
        write_provenance_sidecar: WriteProvenanceSidecar,
        evaluate_roundtrip_evidence: EvaluateRoundtripEvidence,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.trusted_registry_provider = trusted_registry
        self.atomic_write_bytes = atomic_write_bytes
        self.write_provenance_sidecar = write_provenance_sidecar
        self.evaluate_roundtrip_evidence = evaluate_roundtrip_evidence

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
            manifest_path = self.context.settings.resolve_allowed_path(
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
            manifest_document_path = self.context.settings.resolve_allowed_path(
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
        actual_document = DipTraceDocument.load(
            document_path, self.context.settings.max_document_bytes
        )
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
            self.trusted_registry_provider().authorize(
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
        self.write_provenance_sidecar(document_path, new_sidecar)

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

        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        source = self.context.settings.resolve_allowed_path(source_path, must_exist=True)
        saved = self.context.settings.resolve_allowed_path(saved_path, must_exist=True)
        reexport = (
            self.context.settings.resolve_allowed_path(reexport_path, must_exist=True)
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

        source_doc = DipTraceDocument.load(source, self.context.settings.max_document_bytes)
        saved_doc = DipTraceDocument.load(saved, self.context.settings.max_document_bytes)
        reexport_doc = (
            DipTraceDocument.load(reexport, self.context.settings.max_document_bytes)
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
                resolved_path = self.context.settings.resolve_allowed_path(
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
                    self.context.settings.max_document_bytes,
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

        evaluation = self.evaluate_roundtrip_evidence(
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

        self.context.policy.require_write(dry_run=False, operation="record_roundtrip_evidence")
        evaluation = self.evaluate_roundtrip_evidence(
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
        self.atomic_write_bytes(manifest_path, manifest_bytes)
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
        self.write_provenance_sidecar(evaluation.document_path, sidecar)

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
