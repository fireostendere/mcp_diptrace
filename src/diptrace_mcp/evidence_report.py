from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .adapters import build_snapshot
from .domain import StrictModel
from .xml_analysis import (
    XMLSemanticDelta,
    XMLSemanticInventory,
    analyze_xml_semantics,
    compare_xml_semantics,
)
from .xml_document import DipTraceDocument

_CANDIDATE_SCHEMA = "diptrace-capture-candidate-v1"
_REQUIRED_STAGES = ("source", "open_save", "reexport")


class EvidenceStageReport(StrictModel):
    stage: str
    recorded_sha256: str
    actual_sha256: str | None = None
    integrity: Literal["verified", "missing", "mismatch"]
    artifact_path: str
    inventory: XMLSemanticInventory | None = None
    domain_summary: dict[str, Any] = Field(default_factory=dict)
    operator_attestations: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EvidenceComparisonReport(StrictModel):
    first_stage: str
    second_stage: str
    delta: XMLSemanticDelta | None = None
    connectivity_equal: bool | None = None
    domain_count_delta: dict[str, int] = Field(default_factory=dict)
    status: Literal["available", "unavailable"]


class EvidenceReport(StrictModel):
    schema_version: Literal["diptrace-evidence-report-v1"] = "diptrace-evidence-report-v1"
    session_id: str
    recipe_id: str
    authority: str
    review_status: str
    report_status: Literal["complete_review_only", "incomplete", "integrity_failure"]
    trust_grant: Literal["none"] = "none"
    candidate_sha256: str
    eligible_for_registry_review: bool
    review_blockers: list[str] = Field(default_factory=list)
    operator_claims: dict[str, Any] = Field(default_factory=dict)
    checklist: dict[str, Any] = Field(default_factory=dict)
    stages: list[EvidenceStageReport] = Field(default_factory=list)
    comparisons: list[EvidenceComparisonReport] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _load_candidate(candidate_path: Path) -> tuple[dict[str, Any], bytes]:
    raw = candidate_path.read_bytes()
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid evidence candidate JSON: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != _CANDIDATE_SCHEMA:
        raise ValueError(f"Evidence candidate must use schema {_CANDIDATE_SCHEMA!r}")
    if value.get("trust_grant") != "none" or value.get("candidate_only") is not True:
        raise ValueError("Evidence report accepts review-only capture candidates only")
    return {str(key): item for key, item in value.items()}, raw


def _safe_relative(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ValueError(f"Unsafe evidence artifact path: {relative!r}")
    path = root / candidate
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"Evidence artifact escapes capture root: {relative!r}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(f"Evidence artifact is not a regular file: {relative!r}")
    return resolved


def _domain_summary(document: DipTraceDocument) -> dict[str, Any]:
    snapshot = build_snapshot(document)
    if snapshot.board is not None:
        connectivity = sorted(
            (
                net.name or net.net_name or net.stable_id,
                tuple(sorted(net.relationships.get("endpoints", []))),
            )
            for net in snapshot.board.nets
        )
        counts = {
            "components": len(snapshot.board.components),
            "pads": len(snapshot.board.pads),
            "nets": len(snapshot.board.nets),
            "traces": len(snapshot.board.traces),
            "vias": len(snapshot.board.vias),
            "copper_pours": len(snapshot.board.copper_pours),
            "silkscreen_texts": sum(
                "Silk" in (item.layer or "") and item.attributes.get("Show", "Show") != "Hide"
                for item in snapshot.board.texts
            ),
        }
        kind = "pcb"
    elif snapshot.schematic is not None:
        connectivity = sorted(
            (
                net.name or net.net_name or net.stable_id,
                tuple(sorted(net.relationships.get("endpoints", []))),
            )
            for net in snapshot.schematic.nets
        )
        counts = {
            "parts": len(snapshot.schematic.parts),
            "pins": len(snapshot.schematic.pins),
            "nets": len(snapshot.schematic.nets),
            "wires": len(snapshot.schematic.wires),
            "buses": len(snapshot.schematic.buses),
        }
        kind = "schematic"
    else:
        return {"kind": document.kind, "counts": {}, "connectivity_sha256": None}
    payload = json.dumps(connectivity, ensure_ascii=False, separators=(",", ":"))
    return {
        "kind": kind,
        "counts": counts,
        "connectivity_sha256": _sha256(payload.encode("utf-8")),
    }


def _stage_report(
    root: Path,
    stage: str,
    record: dict[str, Any],
) -> EvidenceStageReport:
    relative = str(record.get("quarantine_path") or "")
    recorded_sha = str(record.get("sha256") or "")
    attestations = _mapping(record.get("operator_attestations"))
    normalized_attestations = {
        str(key): bool(value) for key, value in attestations.items()
    }
    warnings_value = record.get("warnings")
    warnings = (
        [str(item) for item in warnings_value]
        if isinstance(warnings_value, list)
        else []
    )
    try:
        path = _safe_relative(root, relative)
        raw = path.read_bytes()
    except (OSError, ValueError):
        return EvidenceStageReport(
            stage=stage,
            recorded_sha256=recorded_sha,
            actual_sha256=None,
            integrity="missing",
            artifact_path=relative,
            operator_attestations=normalized_attestations,
            warnings=warnings,
        )
    actual_sha = _sha256(raw)
    integrity: Literal["verified", "missing", "mismatch"] = (
        "verified" if actual_sha == recorded_sha else "mismatch"
    )
    inventory = None
    domain_summary: dict[str, Any] = {}
    if integrity == "verified":
        try:
            document = DipTraceDocument.from_bytes(path, raw)
            inventory = analyze_xml_semantics(document)
            domain_summary = _domain_summary(document)
        except Exception:
            warnings.append(
                "Artifact bytes passed SHA binding but could not be analyzed "
                "as DipTrace XML."
            )
    return EvidenceStageReport(
        stage=stage,
        recorded_sha256=recorded_sha,
        actual_sha256=actual_sha,
        integrity=integrity,
        artifact_path=relative,
        inventory=inventory,
        domain_summary=domain_summary,
        operator_attestations=normalized_attestations,
        warnings=warnings,
    )


def _comparison(
    first: EvidenceStageReport,
    second: EvidenceStageReport,
    *,
    root: Path,
) -> EvidenceComparisonReport:
    if first.integrity != "verified" or second.integrity != "verified":
        return EvidenceComparisonReport(
            first_stage=first.stage,
            second_stage=second.stage,
            status="unavailable",
        )
    try:
        first_path = _safe_relative(root, first.artifact_path)
        second_path = _safe_relative(root, second.artifact_path)
        before = DipTraceDocument.from_bytes(first_path, first_path.read_bytes())
        after = DipTraceDocument.from_bytes(second_path, second_path.read_bytes())
        delta = compare_xml_semantics(before, after)
    except Exception:
        return EvidenceComparisonReport(
            first_stage=first.stage,
            second_stage=second.stage,
            status="unavailable",
        )
    first_counts = _mapping(first.domain_summary.get("counts"))
    second_counts = _mapping(second.domain_summary.get("counts"))
    count_delta = {
        key: int(second_counts.get(key, 0)) - int(first_counts.get(key, 0))
        for key in sorted(set(first_counts) | set(second_counts))
        if int(second_counts.get(key, 0)) != int(first_counts.get(key, 0))
    }
    first_connectivity = first.domain_summary.get("connectivity_sha256")
    second_connectivity = second.domain_summary.get("connectivity_sha256")
    connectivity_equal = (
        first_connectivity == second_connectivity
        if first_connectivity is not None and second_connectivity is not None
        else None
    )
    return EvidenceComparisonReport(
        first_stage=first.stage,
        second_stage=second.stage,
        delta=delta,
        connectivity_equal=connectivity_equal,
        domain_count_delta=count_delta,
        status="available",
    )


def build_evidence_report(
    candidate_path: str | Path,
    capture_root: str | Path,
) -> EvidenceReport:
    candidate_path = Path(candidate_path)
    root = Path(capture_root)
    candidate, raw = _load_candidate(candidate_path)
    stages_by_name = _mapping(candidate.get("stages"))
    stage_reports = [
        _stage_report(root, stage, _mapping(stages_by_name[stage]))
        for stage in _REQUIRED_STAGES
        if isinstance(stages_by_name.get(stage), dict)
    ]
    missing_stage_names = [
        stage for stage in _REQUIRED_STAGES if stage not in stages_by_name
    ]
    integrity_failures = [
        item.stage for item in stage_reports if item.integrity != "verified"
    ]
    if integrity_failures:
        report_status: Literal[
            "complete_review_only", "incomplete", "integrity_failure"
        ] = "integrity_failure"
    elif missing_stage_names:
        report_status = "incomplete"
    else:
        report_status = "complete_review_only"

    by_stage = {item.stage: item for item in stage_reports}
    comparisons: list[EvidenceComparisonReport] = []
    pairs = (
        ("source", "open_save"),
        ("open_save", "reexport"),
        ("source", "reexport"),
    )
    for first_name, second_name in pairs:
        if first_name in by_stage and second_name in by_stage:
            comparisons.append(
                _comparison(by_stage[first_name], by_stage[second_name], root=root)
            )

    recipe = _mapping(candidate.get("recipe"))
    recipe_snapshot = _mapping(recipe.get("snapshot"))
    checklist = _mapping(candidate.get("checklist"))
    operator_claims = _mapping(candidate.get("operator_claims"))
    semantic_equal_pairs = [
        f"{item.first_stage}->{item.second_stage}"
        for item in comparisons
        if item.status == "available"
        and item.delta is not None
        and item.delta.semantic_equal
    ]
    changed_pairs = [
        f"{item.first_stage}->{item.second_stage}"
        for item in comparisons
        if item.status == "available"
        and item.delta is not None
        and not item.delta.semantic_equal
    ]
    connectivity_changed_pairs = [
        f"{item.first_stage}->{item.second_stage}"
        for item in comparisons
        if item.connectivity_equal is False
    ]
    blockers_value = candidate.get("review_blockers")
    review_blockers = (
        [str(item) for item in blockers_value]
        if isinstance(blockers_value, list)
        else []
    )
    return EvidenceReport(
        session_id=str(candidate.get("session_id") or ""),
        recipe_id=str(recipe_snapshot.get("recipe_id") or ""),
        authority=str(candidate.get("authority") or "operator_supplied_unverified"),
        review_status=str(
            candidate.get("review_status") or "pending_independent_review"
        ),
        report_status=report_status,
        candidate_sha256=_sha256(raw),
        eligible_for_registry_review=bool(candidate.get("eligible_for_registry_review")),
        review_blockers=review_blockers,
        operator_claims=operator_claims,
        checklist=checklist,
        stages=stage_reports,
        comparisons=comparisons,
        summary={
            "stage_count": len(stage_reports),
            "missing_stages": missing_stage_names,
            "integrity_failures": integrity_failures,
            "semantic_equal_pairs": semantic_equal_pairs,
            "semantic_changed_pairs": changed_pairs,
            "connectivity_changed_pairs": connectivity_changed_pairs,
            "all_required_checklist_yes": all(
                isinstance(item, dict)
                and (not item.get("required") or item.get("answer") == "yes")
                for item in checklist.values()
            ),
        },
        limitations=[
            (
                "This report verifies candidate/artifact binding and summarizes XML "
                "semantics; it does not grant provenance trust, fixture trust, release "
                "acceptance, or a PASS result."
            ),
            (
                "Operator claims and checklist answers are reproduced as "
                "operator-supplied facts and are not independently authenticated by "
                "the report builder."
            ),
            (
                "XML semantic fingerprints complement but do not replace "
                "claim-specific PCB/schematic connectivity, visual, manufacturing, "
                "or real-host review."
            ),
        ],
    )


def render_evidence_report_markdown(report: EvidenceReport) -> str:
    lines = [
        f"# DipTrace Evidence Report — {report.session_id}",
        "",
        f"- Recipe: `{report.recipe_id}`",
        f"- Status: **{report.report_status}**",
        f"- Authority: `{report.authority}`",
        f"- Trust grant: `{report.trust_grant}`",
        f"- Candidate SHA-256: `{report.candidate_sha256}`",
        (
            "- Registry-review eligible: "
            f"`{str(report.eligible_for_registry_review).lower()}`"
        ),
        "",
        "## Captured stages",
        "",
        "| Stage | Integrity | Recorded SHA-256 | Semantic SHA-256 |",
        "| --- | --- | --- | --- |",
    ]
    for stage in report.stages:
        semantic_sha = (
            stage.inventory.semantic_sha256 if stage.inventory else "unavailable"
        )
        lines.append(
            f"| `{stage.stage}` | **{stage.integrity}** | "
            f"`{stage.recorded_sha256}` | `{semantic_sha}` |"
        )
    lines.extend(["", "## Semantic comparisons", ""])
    for comparison in report.comparisons:
        if comparison.status == "unavailable" or comparison.delta is None:
            lines.append(
                f"- `{comparison.first_stage} -> {comparison.second_stage}`: unavailable"
            )
            continue
        delta = comparison.delta
        lines.append(
            f"- `{comparison.first_stage} -> {comparison.second_stage}`: "
            f"semantic_equal=`{str(delta.semantic_equal).lower()}`, "
            f"connectivity_equal=`{str(comparison.connectivity_equal).lower()}`, "
            f"added_local_records={delta.added_local_records}, "
            f"removed_local_records={delta.removed_local_records}, "
            f"domain_count_delta={comparison.domain_count_delta}"
        )
    if report.review_blockers:
        lines.extend(["", "## Review blockers", ""])
        lines.extend(f"- `{item}`" for item in report.review_blockers)
    lines.extend(["", "## Evidence boundary", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    return "\n".join(lines) + "\n"
