from __future__ import annotations

import json
from pathlib import Path

from diptrace_mcp.library_adapters import get_library_model
from diptrace_mcp.pattern_recommendation import (
    EvaluationCase,
    PatternFeedbackStore,
    PatternRequirement,
    evaluate_recommender,
    recommend_patterns,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _patterns():
    path = FIXTURES / "pattern_library.xml"
    document = DipTraceDocument.from_bytes(path, path.read_bytes())
    return get_library_model(document).patterns


def test_hard_filters_reject_incompatible_patterns() -> None:
    patterns = _patterns()
    result = recommend_patterns(
        patterns,
        PatternRequirement(
            pad_count=2,
            mounting="SMD",
            hole_count=0,
            required_pad_numbers=["1", "2"],
        ),
    )
    assert [item.name for item in result.candidates] == ["R_0603"]
    assert any(item.name == "HDR_1X02" for item in result.rejected)


def test_geometry_ranking_is_deterministic() -> None:
    patterns = _patterns()
    requirement = PatternRequirement(
        pad_count=2,
        mounting="SMD",
        width_mm=3.2,
        height_mm=1.6,
        pitch_mm=1.6,
        hole_count=0,
    )
    first = recommend_patterns(patterns, requirement)
    second = recommend_patterns(list(reversed(patterns)), requirement)
    assert [item.pattern_id for item in first.candidates] == [
        item.pattern_id for item in second.candidates
    ]
    assert first.candidates[0].name == "R_0603"


def test_unspecified_geometry_prefers_the_smallest_compatible_pattern() -> None:
    header = next(item for item in _patterns() if item.name == "HDR_1X02")
    oversized = header.model_copy(
        update={
            "stable_id": "library-pattern_oversized",
            "name": "HDR_1X02_ANGLED",
            "bbox": {"min_x": -7.0, "min_y": -5.0, "max_x": 7.0, "max_y": 5.0},
        }
    )

    result = recommend_patterns(
        [oversized, header],
        PatternRequirement(pad_count=2, mounting="Through", pitch_mm=2.54),
    )

    assert [item.name for item in result.candidates] == ["HDR_1X02", "HDR_1X02_ANGLED"]


def test_feedback_store_is_append_only_and_does_not_store_requirement_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "feedback.jsonl"
    store = PatternFeedbackStore(path)
    requirement = PatternRequirement(pad_count=2, mounting="SMD", pitch_mm=1.6)
    store.append(
        requirement,
        pattern_id="library-pattern_deadbeefdeadbeef",
        decision="accepted",
        note="verified against package dimensions",
    )
    store.append(
        requirement,
        pattern_id="library-pattern_deadbeefdeadbeef",
        decision="corrected",
        corrected_pattern_id="library-pattern_cafebabecafebabe",
    )
    records = store.read()
    assert len(records) == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert "requirement_sha256" in payload
    assert "pad_count" not in payload
    assert "xml" not in payload
    assert "datasheet" not in payload


def test_held_out_metrics_cover_top1_top3_and_forbidden_rejection() -> None:
    patterns = _patterns()
    resistor = next(item for item in patterns if item.name == "R_0603")
    header = next(item for item in patterns if item.name == "HDR_1X02")
    metrics = evaluate_recommender(
        patterns,
        [
            EvaluationCase(
                requirement=PatternRequirement(
                    pad_count=2,
                    mounting="SMD",
                    hole_count=0,
                    pitch_mm=1.6,
                ),
                expected_pattern_ids=[resistor.stable_id],
                forbidden_pattern_ids=[header.stable_id],
            )
        ],
    )
    assert metrics.top1_accuracy == 1.0
    assert metrics.top3_accuracy == 1.0
    assert metrics.forbidden_rejection_rate == 1.0
