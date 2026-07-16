from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .domain import StrictModel
from .errors import ObjectNotFoundError
from .xml_document import atomic_write_bytes, utc_now


class Finding(StrictModel):
    finding_id: str = Field(pattern=r"^finding_[0-9a-f]{16}$")
    check_id: str
    category: str
    severity: Literal["error", "warning", "info"]
    confidence: float = Field(ge=0.0, le=1.0)
    title: str
    explanation: str
    object_ids: list[str] = Field(default_factory=list)
    net_ids: list[str] = Field(default_factory=list)
    layer: str | None = None
    location: dict[str, float] | None = None
    bbox: dict[str, float] | None = None
    measured: float | None = None
    required: float | None = None
    delta: float | None = None
    units: str | None = None
    rule_source: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)
    preview_uri: str | None = None
    suppressed: bool = False


class ReviewReport(StrictModel):
    report_id: str = Field(pattern=r"^report_[0-9a-f]{16}$")
    document_id: str
    source_sha256: str
    profile: str
    created_at: str
    findings: list[Finding] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    skipped_checks: list[dict[str, str]] = Field(default_factory=list)
    completeness: float = Field(ge=0.0, le=1.0)

    def summary(self) -> dict[str, Any]:
        counts = {"error": 0, "warning": 0, "info": 0}
        for finding in self.findings:
            if not finding.suppressed:
                counts[finding.severity] += 1
        return {
            "report_id": self.report_id,
            "profile": self.profile,
            "finding_count": sum(counts.values()),
            "by_severity": counts,
            "completeness": self.completeness,
            "skipped_check_count": len(self.skipped_checks),
        }


def deterministic_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def make_finding(
    check_id: str,
    category: str,
    severity: Literal["error", "warning", "info"],
    title: str,
    explanation: str,
    *,
    object_ids: list[str] | None = None,
    net_ids: list[str] | None = None,
    layer: str | None = None,
    location: dict[str, float] | None = None,
    bbox: dict[str, float] | None = None,
    confidence: float = 1.0,
    measured: float | None = None,
    required: float | None = None,
    units: str | None = None,
    rule_source: str | None = None,
    suggested_actions: list[str] | None = None,
) -> Finding:
    objects = sorted(object_ids or [])
    nets = sorted(net_ids or [])
    location_key = json.dumps(location or bbox or {}, sort_keys=True)
    finding_id = deterministic_id(
        "finding", check_id, *objects, *nets, layer or "", location_key
    )
    delta = measured - required if measured is not None and required is not None else None
    return Finding(
        finding_id=finding_id,
        check_id=check_id,
        category=category,
        severity=severity,
        confidence=confidence,
        title=title,
        explanation=explanation,
        object_ids=objects,
        net_ids=nets,
        layer=layer,
        location=location,
        bbox=bbox,
        measured=measured,
        required=required,
        delta=delta,
        units=units,
        rule_source=rule_source,
        suggested_actions=list(suggested_actions or []),
    )


class FindingStore:
    def __init__(self, state_dir: Path):
        self.reports_dir = state_dir / "reviews"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def store(self, report: ReviewReport) -> None:
        payload = json.dumps(
            report.model_dump(mode="json"), ensure_ascii=False, indent=2
        ).encode("utf-8")
        atomic_write_bytes(self.reports_dir / f"{report.report_id}.json", payload)

    def read(self, report_id: str) -> ReviewReport:
        path = self.reports_dir / f"{report_id}.json"
        if not path.is_file():
            raise ObjectNotFoundError(f"Review report was not found: {report_id}")
        return ReviewReport.model_validate_json(path.read_bytes())

    def get_finding(self, finding_id: str) -> Finding:
        for path in sorted(self.reports_dir.glob("report_*.json"), reverse=True):
            report = ReviewReport.model_validate_json(path.read_bytes())
            for finding in report.findings:
                if finding.finding_id == finding_id:
                    return finding
        raise ObjectNotFoundError(f"Finding was not found: {finding_id}")

    def create_report(
        self,
        *,
        document_id: str,
        source_sha256: str,
        profile: str,
        findings: list[Finding],
        metrics: dict[str, Any],
        assumptions: list[str],
        skipped_checks: list[dict[str, str]],
        registered_check_count: int,
    ) -> ReviewReport:
        severity_order = {"error": 0, "warning": 1, "info": 2}
        report_id = deterministic_id("report", document_id, source_sha256, profile)
        completed = max(0, registered_check_count - len(skipped_checks))
        completeness = completed / registered_check_count if registered_check_count else 1.0
        report = ReviewReport(
            report_id=report_id,
            document_id=document_id,
            source_sha256=source_sha256,
            profile=profile,
            created_at=utc_now(),
            findings=sorted(
                findings,
                key=lambda item: (severity_order[item.severity], item.finding_id),
            ),
            metrics=metrics,
            assumptions=assumptions,
            skipped_checks=skipped_checks,
            completeness=completeness,
        )
        self.store(report)
        return report
