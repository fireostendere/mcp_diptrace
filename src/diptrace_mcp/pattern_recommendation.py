"""Deterministic human-guided pattern recommendation baseline.

The recommender deliberately does not train or call a model. It ranks existing
parsed ``LibraryPattern`` records using hard compatibility filters followed by a
bounded geometry-distance score. Feedback storage is append-only and stores only
compact derived features/identifiers; project XML, datasheets and screenshots are
not accepted by its schema.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import LibraryPattern
from .errors import DocumentError


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PatternRequirement(_StrictModel):
    pad_count: int | None = Field(default=None, ge=1, le=4096)
    mounting: str | None = Field(default=None, min_length=1, max_length=64)
    width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    height_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    pitch_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    hole_count: int | None = Field(default=None, ge=0, le=4096)
    required_pad_numbers: list[str] = Field(default_factory=list, max_length=4096)
    max_width_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    max_height_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)

    @field_validator("required_pad_numbers")
    @classmethod
    def _unique_numbers(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("required_pad_numbers cannot contain empty values")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("required_pad_numbers must be unique")
        return cleaned

    @model_validator(mode="after")
    def _dimension_bounds(self) -> PatternRequirement:
        if (
            self.width_mm is not None
            and self.max_width_mm is not None
            and self.width_mm > self.max_width_mm
        ):
            raise ValueError("width_mm cannot exceed max_width_mm")
        if (
            self.height_mm is not None
            and self.max_height_mm is not None
            and self.height_mm > self.max_height_mm
        ):
            raise ValueError("height_mm cannot exceed max_height_mm")
        return self


class PatternFeatures(_StrictModel):
    stable_id: str
    name: str
    style: str | None = None
    mounting: str
    pad_count: int = Field(ge=0)
    pad_numbers: list[str] = Field(default_factory=list)
    hole_count: int = Field(ge=0)
    width_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    height_mm: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    pitch_mm: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)


class PatternCandidate(_StrictModel):
    pattern_id: str
    name: str
    style: str | None = None
    score: float = Field(ge=0.0, allow_inf_nan=False)
    score_terms: dict[str, float] = Field(default_factory=dict)
    features: PatternFeatures


class RejectedPattern(_StrictModel):
    pattern_id: str
    name: str
    reasons: list[str] = Field(min_length=1)


class RecommendationResult(_StrictModel):
    requirement: PatternRequirement
    candidates: list[PatternCandidate]
    rejected: list[RejectedPattern]
    total_patterns: int = Field(ge=0)
    compatible_patterns: int = Field(ge=0)


class PatternFeedbackRecord(_StrictModel):
    schema_version: Literal["pattern-feedback-v1"] = "pattern-feedback-v1"
    requirement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pattern_id: str = Field(min_length=1, max_length=256)
    decision: Literal["accepted", "rejected", "corrected"]
    corrected_pattern_id: str | None = Field(default=None, min_length=1, max_length=256)
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _correction_requires_target(self) -> PatternFeedbackRecord:
        if self.decision == "corrected" and self.corrected_pattern_id is None:
            raise ValueError("corrected feedback requires corrected_pattern_id")
        if self.decision != "corrected" and self.corrected_pattern_id is not None:
            raise ValueError("corrected_pattern_id is only valid for corrected feedback")
        return self


class EvaluationCase(_StrictModel):
    requirement: PatternRequirement
    expected_pattern_ids: list[str] = Field(min_length=1, max_length=128)
    forbidden_pattern_ids: list[str] = Field(default_factory=list, max_length=128)


class EvaluationMetrics(_StrictModel):
    case_count: int = Field(ge=0)
    top1_accuracy: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    top3_accuracy: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    forbidden_rejection_rate: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    compatible_candidate_rate: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


def _normalized_mounting(value: str) -> str:
    folded = value.casefold().replace("-", " ").replace("_", " ").strip()
    if folded in {"smd", "surface", "surface mount", "surface mounted"}:
        return "smd"
    if folded in {"through", "through hole", "tht", "throughhole"}:
        return "through"
    return folded


def _bbox_dimensions(pattern: LibraryPattern) -> tuple[float | None, float | None]:
    if pattern.bbox is None:
        return None, None
    width = max(0.0, pattern.bbox["max_x"] - pattern.bbox["min_x"])
    height = max(0.0, pattern.bbox["max_y"] - pattern.bbox["min_y"])
    return width, height


def _pitch(pattern: LibraryPattern) -> float | None:
    points = [
        (float(item.position["x"]), float(item.position["y"]))
        for item in pattern.pads
        if item.position is not None
    ]
    distances: list[float] = []
    for index, first in enumerate(points):
        for second in points[index + 1 :]:
            value = math.hypot(first[0] - second[0], first[1] - second[1])
            if value > 1e-9:
                distances.append(value)
    return min(distances) if distances else None


def extract_pattern_features(pattern: LibraryPattern) -> PatternFeatures:
    width, height = _bbox_dimensions(pattern)
    return PatternFeatures(
        stable_id=pattern.stable_id,
        name=pattern.name,
        style=pattern.style,
        mounting=pattern.mounting,
        pad_count=len(pattern.pads),
        pad_numbers=sorted({item.number for item in pattern.pads if item.number}),
        hole_count=len(pattern.holes),
        width_mm=width,
        height_mm=height,
        pitch_mm=_pitch(pattern),
    )


def _hard_filter(requirement: PatternRequirement, features: PatternFeatures) -> list[str]:
    reasons: list[str] = []
    if requirement.pad_count is not None and features.pad_count != requirement.pad_count:
        reasons.append(f"pad_count:{features.pad_count}!={requirement.pad_count}")
    if requirement.mounting is not None:
        expected = _normalized_mounting(requirement.mounting)
        actual = _normalized_mounting(features.mounting)
        if expected != actual:
            reasons.append(f"mounting:{actual or '<empty>'}!={expected}")
    if requirement.hole_count is not None and features.hole_count != requirement.hole_count:
        reasons.append(f"hole_count:{features.hole_count}!={requirement.hole_count}")
    if requirement.required_pad_numbers:
        missing = sorted(set(requirement.required_pad_numbers) - set(features.pad_numbers))
        if missing:
            reasons.append("missing_pad_numbers:" + ",".join(missing))
    if requirement.max_width_mm is not None:
        if features.width_mm is None:
            reasons.append("width_unavailable")
        elif features.width_mm > requirement.max_width_mm + 1e-9:
            reasons.append(f"width:{features.width_mm:g}>{requirement.max_width_mm:g}")
    if requirement.max_height_mm is not None:
        if features.height_mm is None:
            reasons.append("height_unavailable")
        elif features.height_mm > requirement.max_height_mm + 1e-9:
            reasons.append(f"height:{features.height_mm:g}>{requirement.max_height_mm:g}")
    return reasons


def _relative_error(actual: float | None, expected: float | None) -> float | None:
    if expected is None:
        return None
    if actual is None:
        return 2.0
    return abs(actual - expected) / max(abs(expected), 1e-9)


def _score(
    requirement: PatternRequirement,
    features: PatternFeatures,
) -> tuple[float, dict[str, float]]:
    weighted: list[tuple[str, float, float]] = []
    for name, actual, expected, weight in (
        ("width", features.width_mm, requirement.width_mm, 1.0),
        ("height", features.height_mm, requirement.height_mm, 1.0),
        ("pitch", features.pitch_mm, requirement.pitch_mm, 1.5),
    ):
        error = _relative_error(actual, expected)
        if error is not None:
            weighted.append((name, error, weight))
    if not weighted:
        return 0.0, {}
    terms = {name: error for name, error, _ in weighted}
    score = sum(error * weight for _, error, weight in weighted) / sum(
        weight for _, _, weight in weighted
    )
    return score, terms


def recommend_patterns(
    patterns: list[LibraryPattern],
    requirement: PatternRequirement | dict[str, object],
    *,
    limit: int = 10,
) -> RecommendationResult:
    if limit < 1 or limit > 100:
        raise DocumentError("pattern recommendation limit must be between 1 and 100")
    parsed = (
        requirement
        if isinstance(requirement, PatternRequirement)
        else PatternRequirement.model_validate(requirement)
    )
    accepted: list[PatternCandidate] = []
    rejected: list[RejectedPattern] = []
    for pattern in patterns:
        features = extract_pattern_features(pattern)
        reasons = _hard_filter(parsed, features)
        if reasons:
            rejected.append(
                RejectedPattern(
                    pattern_id=pattern.stable_id,
                    name=pattern.name,
                    reasons=reasons,
                )
            )
            continue
        score, terms = _score(parsed, features)
        accepted.append(
            PatternCandidate(
                pattern_id=pattern.stable_id,
                name=pattern.name,
                style=pattern.style,
                score=score,
                score_terms=terms,
                features=features,
            )
        )
    accepted.sort(key=lambda item: (item.score, item.name.casefold(), item.pattern_id))
    rejected.sort(key=lambda item: (item.name.casefold(), item.pattern_id))
    return RecommendationResult(
        requirement=parsed,
        candidates=accepted[:limit],
        rejected=rejected,
        total_patterns=len(patterns),
        compatible_patterns=len(accepted),
    )


def requirement_sha256(requirement: PatternRequirement) -> str:
    payload = requirement.model_dump_json(exclude_none=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PatternFeedbackStore:
    """Append-only JSONL feedback store containing derived metadata only."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(
        self,
        requirement: PatternRequirement,
        *,
        pattern_id: str,
        decision: Literal["accepted", "rejected", "corrected"],
        corrected_pattern_id: str | None = None,
        note: str = "",
    ) -> PatternFeedbackRecord:
        record = PatternFeedbackRecord(
            requirement_sha256=requirement_sha256(requirement),
            pattern_id=pattern_id,
            decision=decision,
            corrected_pattern_id=corrected_pattern_id,
            note=note,
        )
        encoded = (record.model_dump_json() + "\n").encode("utf-8")
        if len(encoded) > 4096:
            raise DocumentError("pattern feedback record exceeds 4 KiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return record

    def read(self) -> list[PatternFeedbackRecord]:
        if not self.path.exists():
            return []
        records: list[PatternFeedbackRecord] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    records.append(PatternFeedbackRecord.model_validate_json(line))
                except ValueError as exc:
                    raise DocumentError(
                        f"invalid pattern feedback record at line {line_number}: {exc}"
                    ) from exc
        return records


def evaluate_recommender(
    patterns: list[LibraryPattern],
    cases: list[EvaluationCase],
) -> EvaluationMetrics:
    if not cases:
        return EvaluationMetrics(
            case_count=0,
            top1_accuracy=0.0,
            top3_accuracy=0.0,
            forbidden_rejection_rate=1.0,
            compatible_candidate_rate=0.0,
        )
    top1 = 0
    top3 = 0
    forbidden_total = 0
    forbidden_rejected = 0
    compatible_total = 0
    for case in cases:
        result = recommend_patterns(patterns, case.requirement, limit=100)
        ids = [item.pattern_id for item in result.candidates]
        expected = set(case.expected_pattern_ids)
        top1 += int(bool(ids) and ids[0] in expected)
        top3 += int(bool(expected.intersection(ids[:3])))
        forbidden = set(case.forbidden_pattern_ids)
        forbidden_total += len(forbidden)
        forbidden_rejected += len(forbidden - set(ids))
        compatible_total += len(ids)
    return EvaluationMetrics(
        case_count=len(cases),
        top1_accuracy=top1 / len(cases),
        top3_accuracy=top3 / len(cases),
        forbidden_rejection_rate=(
            forbidden_rejected / forbidden_total if forbidden_total else 1.0
        ),
        compatible_candidate_rate=compatible_total / (len(patterns) * len(cases))
        if patterns
        else 0.0,
    )
