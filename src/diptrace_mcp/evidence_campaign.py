from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .domain import StrictModel
from .evidence_report import EvidenceReport


class EvidenceMediaBinding(StrictModel):
    artifact_path: str = Field(min_length=1, max_length=4_096)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_kind: Literal["screenshot", "frame", "video", "gif"]
    frame_metrics: dict[str, float | int | str | bool] = Field(default_factory=dict)


class ExportedEvidenceDelta(StrictModel):
    delta_kind: Literal["exported_geometry", "exported_manufacturing"]
    before_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: dict[str, Any] = Field(default_factory=dict)
    authoritative_native_refill: Literal[False] = False


class UntrustedVisualFinding(StrictModel):
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_id: str = Field(min_length=1, max_length=256)
    finding: str = Field(min_length=1, max_length=8_192)
    severity: Literal["info", "warning", "error"] = "warning"
    trusted: Literal[False] = False


class EvidencePromotionRecord(StrictModel):
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["pending", "promotion_requested", "rejected"] = "pending"
    reason: str = Field(default="", max_length=8_192)
    reviewer_identity: str | None = Field(default=None, max_length=512)
    trust_grant: Literal["none"] = "none"
    required_manual_gate: Literal["M11"] = "M11"


class EvidenceCampaignReport(StrictModel):
    schema_version: Literal["diptrace-evidence-campaign-v1"] = "diptrace-evidence-campaign-v1"
    campaign_id: str = Field(min_length=1, max_length=256)
    campaign_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reports: list[EvidenceReport] = Field(default_factory=list)
    media: list[EvidenceMediaBinding] = Field(default_factory=list)
    exported_deltas: list[ExportedEvidenceDelta] = Field(default_factory=list)
    visual_findings: list[UntrustedVisualFinding] = Field(default_factory=list)
    promotion_records: list[EvidencePromotionRecord] = Field(default_factory=list)
    trust_grant: Literal["none"] = "none"
    required_manual_gate: Literal["M11"] = "M11"
    limitations: list[str] = Field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_media_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise ValueError(f"Unsafe evidence media path: {relative!r}")
    resolved_root = root.resolve(strict=True)
    resolved = (root / candidate).resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Evidence media escapes campaign root: {relative!r}") from exc
    if not resolved.is_file():
        raise ValueError(f"Evidence media is not a regular file: {relative!r}")
    return resolved


def _campaign_payload(
    campaign_id: str,
    reports: list[EvidenceReport],
    media: list[EvidenceMediaBinding],
    exported_deltas: list[ExportedEvidenceDelta],
    visual_findings: list[UntrustedVisualFinding],
    promotion_records: list[EvidencePromotionRecord],
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "reports": [record.model_dump(mode="json") for record in reports],
        "media": [binding.model_dump(mode="json") for binding in media],
        "exported_deltas": [delta.model_dump(mode="json") for delta in exported_deltas],
        "visual_findings": [
            finding.model_dump(mode="json") for finding in visual_findings
        ],
        "promotion_records": [
            promotion.model_dump(mode="json") for promotion in promotion_records
        ],
    }


def build_evidence_campaign_report(
    campaign_id: str,
    reports: list[EvidenceReport],
    *,
    media_root: Path | None = None,
    media: list[EvidenceMediaBinding] | None = None,
    exported_deltas: list[ExportedEvidenceDelta] | None = None,
    visual_findings: list[UntrustedVisualFinding] | None = None,
    promotion_records: list[EvidencePromotionRecord] | None = None,
) -> EvidenceCampaignReport:
    """Aggregate candidate evidence without granting provenance or PASS.

    Media bindings are verified when ``media_root`` is supplied. AI visual
    findings remain explicitly untrusted and exported geometry/manufacturing
    deltas can never masquerade as authoritative DipTrace native refill.
    """

    media = list(media or [])
    exported_deltas = list(exported_deltas or [])
    visual_findings = list(visual_findings or [])
    promotion_records = list(promotion_records or [])
    candidate_hashes = {report.candidate_sha256 for report in reports}
    for promotion in promotion_records:
        if promotion.candidate_sha256 not in candidate_hashes:
            raise ValueError(
                "Promotion/rejection record references a candidate absent from the "
                "campaign"
            )
    media_hashes = {binding.sha256 for binding in media}
    if media_root is not None:
        for binding in media:
            path = _safe_media_path(media_root, binding.artifact_path)
            actual = _sha256(path.read_bytes())
            if actual != binding.sha256:
                raise ValueError(
                    f"Evidence media SHA-256 mismatch for {binding.artifact_path}: "
                    f"expected {binding.sha256}, got {actual}"
                )
    for finding in visual_findings:
        if finding.image_sha256 not in media_hashes:
            raise ValueError(
                "Visual finding must reference an exact hash-bound campaign image/frame"
            )
    payload = _campaign_payload(
        campaign_id,
        reports,
        media,
        exported_deltas,
        visual_findings,
        promotion_records,
    )
    digest = _sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return EvidenceCampaignReport(
        campaign_id=campaign_id,
        campaign_sha256=digest,
        reports=reports,
        media=media,
        exported_deltas=exported_deltas,
        visual_findings=visual_findings,
        promotion_records=promotion_records,
        limitations=[
            "Campaign aggregation is deterministic review evidence, not an automatic PASS.",
            (
                "Exported geometry/manufacturing deltas are not authoritative native "
                "copper refill."
            ),
            "AI visual findings are untrusted observations until independently reviewed.",
            "Trust promotion remains a separate human M11 registry/fixture decision.",
        ],
    )


def render_evidence_campaign_markdown(report: EvidenceCampaignReport) -> str:
    lines = [
        f"# Evidence campaign: {report.campaign_id}",
        "",
        f"- Campaign SHA-256: `{report.campaign_sha256}`",
        f"- Candidate reports: {len(report.reports)}",
        f"- Media bindings: {len(report.media)}",
        f"- Exported deltas: {len(report.exported_deltas)}",
        f"- Untrusted visual findings: {len(report.visual_findings)}",
        "- Trust grant: `none`",
        "- Required manual gate for promotion: `M11`",
        "",
        "## Candidate records",
        "",
    ]
    for candidate_report in report.reports:
        lines.append(
            f"- `{candidate_report.candidate_sha256}` — "
            f"{candidate_report.report_status}; registry review eligible: "
            f"{str(candidate_report.eligible_for_registry_review).lower()}"
        )
    if report.promotion_records:
        lines.extend(["", "## Promotion/rejection requests", ""])
        for promotion in report.promotion_records:
            lines.append(
                f"- `{promotion.candidate_sha256}` — {promotion.decision}; "
                "trust remains `none`."
            )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    return "\n".join(lines) + "\n"
