from __future__ import annotations

import hashlib

import pytest

from diptrace_mcp.evidence_campaign import (
    EvidenceMediaBinding,
    EvidencePromotionRecord,
    ExportedEvidenceDelta,
    UntrustedVisualFinding,
    build_evidence_campaign_report,
    render_evidence_campaign_markdown,
)
from diptrace_mcp.evidence_report import EvidenceReport


def _report(candidate: str) -> EvidenceReport:
    return EvidenceReport(
        session_id="s1",
        recipe_id="r1",
        authority="operator",
        review_status="pending",
        report_status="complete_review_only",
        candidate_sha256=candidate,
        eligible_for_registry_review=True,
    )


def test_campaign_binds_media_and_never_grants_trust(tmp_path) -> None:
    image = tmp_path / "board.png"
    image.write_bytes(b"not-an-image-but-hash-bound-evidence")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    candidate = "b" * 64

    campaign = build_evidence_campaign_report(
        "campaign-1",
        [_report(candidate)],
        media_root=tmp_path,
        media=[
            EvidenceMediaBinding(
                artifact_path="board.png",
                sha256=digest,
                media_kind="screenshot",
                frame_metrics={"width": 1920, "height": 1080},
            )
        ],
        exported_deltas=[
            ExportedEvidenceDelta(
                delta_kind="exported_geometry",
                before_sha256="c" * 64,
                after_sha256="d" * 64,
                summary={"changed": 2},
            )
        ],
        visual_findings=[
            UntrustedVisualFinding(
                image_sha256=digest,
                rule_id="silk-over-pad",
                finding="Possible overlap; independent review required.",
            )
        ],
        promotion_records=[
            EvidencePromotionRecord(
                candidate_sha256=candidate,
                decision="promotion_requested",
            )
        ],
    )

    assert campaign.trust_grant == "none"
    assert campaign.required_manual_gate == "M11"
    assert campaign.exported_deltas[0].authoritative_native_refill is False
    assert campaign.visual_findings[0].trusted is False
    assert campaign.media[0].frame_metrics["width"] == 1920
    assert "Trust grant: `none`" in render_evidence_campaign_markdown(campaign)


def test_campaign_rejects_tampered_media(tmp_path) -> None:
    path = tmp_path / "frame.png"
    path.write_bytes(b"current")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_evidence_campaign_report(
            "campaign-2",
            [],
            media_root=tmp_path,
            media=[
                EvidenceMediaBinding(
                    artifact_path="frame.png",
                    sha256=hashlib.sha256(b"other").hexdigest(),
                    media_kind="frame",
                )
            ],
        )


def test_campaign_rejects_unbound_visual_and_promotion_records(tmp_path) -> None:
    image = tmp_path / "frame.png"
    image.write_bytes(b"frame")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="exact hash-bound"):
        build_evidence_campaign_report(
            "campaign-3",
            [],
            visual_findings=[
                UntrustedVisualFinding(
                    image_sha256=digest,
                    rule_id="visual",
                    finding="unbound",
                )
            ],
        )

    with pytest.raises(ValueError, match="candidate absent"):
        build_evidence_campaign_report(
            "campaign-4",
            [_report("e" * 64)],
            promotion_records=[
                EvidencePromotionRecord(
                    candidate_sha256="f" * 64,
                    decision="rejected",
                )
            ],
        )
