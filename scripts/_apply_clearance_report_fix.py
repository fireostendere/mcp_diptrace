from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


review_path = Path("src/diptrace_mcp/review.py")

replace_once(
    review_path,
    """CheckFunction = Callable[[DocumentSnapshot], tuple[list[Finding], dict[str, Any]]]\n\n\n@dataclass(frozen=True, slots=True)\n""",
    """CheckFunction = Callable[[DocumentSnapshot], tuple[list[Finding], dict[str, Any]]]\n\nMAX_SKIPPED_PAIR_REASONS = 100\n\n\ndef _append_bounded_reason(\n    reasons: list[dict[str, Any]],\n    reason: dict[str, Any],\n    *,\n    total: int,\n) -> int:\n    next_total = total + 1\n    if len(reasons) < MAX_SKIPPED_PAIR_REASONS:\n        reasons.append(reason)\n    return next_total\n\n\n@dataclass(frozen=True, slots=True)\n""",
)

replace_once(
    review_path,
    """    base_status = clearance_rule_status(snapshot, operation=\"offline_clearance_review\")\n    rules_available = bool(clearance_by_layer or netclass_clearances)\n    maximum_clearance = max([*clearance_by_layer.values(), *netclass_clearances], default=0.0)\n""",
    """    base_status = clearance_rule_status(snapshot, operation=\"offline_clearance_review\")\n    rules_available = bool(clearance_by_layer or netclass_clearances)\n    if not rules_available:\n        warning_codes = [\"trace_clearance_rules_unavailable\"]\n        final_status = {\n            **base_status,\n            \"clearance_review_complete\": False,\n            \"partial_review\": True,\n            \"warning_code\": warning_codes[0],\n            \"warning_codes\": warning_codes,\n        }\n        segment_count = sum(\n            max(0, len(trace.attributes.get(\"points\", [])) - 1)\n            for trace in snapshot.board.traces\n        )\n        return [], {\n            \"segments_checked\": segment_count,\n            \"candidate_pairs_checked\": 0,\n            \"candidate_pairs_not_enumerated\": True,\n            \"evaluated_pairs\": 0,\n            \"skipped_unresolved_net_pairs\": 0,\n            \"skipped_clearance_resolution_pairs\": 0,\n            \"skipped_netclass_pairs\": 0,\n            \"skipped_pair_reasons\": [\n                {\n                    \"reason_code\": \"trace_clearance_rules_unavailable\",\n                    \"scope\": \"check\",\n                }\n            ],\n            \"skipped_pair_reasons_total\": 1,\n            \"skipped_pair_reasons_truncated\": False,\n            \"warning_codes\": warning_codes,\n            \"clearance_review_complete\": False,\n            \"clearance_rule_status\": final_status,\n            \"partial_skipped\": \"trace_clearance_rules_unavailable\",\n        }\n    maximum_clearance = max([*clearance_by_layer.values(), *netclass_clearances], default=0.0)\n""",
)

replace_once(
    review_path,
    """    skipped_pair_reasons: list[dict[str, Any]] = []\n    warning_codes: set[str] = set()\n    if not rules_available:\n        warning_codes.add(\"trace_clearance_rules_unavailable\")\n        skipped_pair_reasons.append(\n            {\n                \"reason_code\": \"trace_clearance_rules_unavailable\",\n                \"scope\": \"check\",\n            }\n        )\n""",
    """    skipped_pair_reasons: list[dict[str, Any]] = []\n    skipped_pair_reasons_total = 0\n    warning_codes: set[str] = set()\n""",
)

replace_once(
    review_path,
    """        candidates = (\n            index.query(BBox(**segment.bbox), layers={segment.layer or \"\"})\n            if rules_available\n            else (\n                item\n                for item in segment_records\n                if item.layer == segment.layer\n            )\n        )\n""",
    """        candidates = index.query(\n            BBox(**segment.bbox),\n            layers={segment.layer or \"\"},\n        )\n""",
)

replace_once(
    review_path,
    """                skipped_pair_reasons.append(\n                    {\n                        \"reason_code\": \"trace_net_unresolved\",\n                        \"pair_segment_ids\": [first, second],\n                        \"unresolved_sides\": unresolved_sides,\n                    }\n                )\n""",
    """                skipped_pair_reasons_total = _append_bounded_reason(\n                    skipped_pair_reasons,\n                    {\n                        \"reason_code\": \"trace_net_unresolved\",\n                        \"pair_segment_ids\": [first, second],\n                        \"unresolved_sides\": unresolved_sides,\n                    },\n                    total=skipped_pair_reasons_total,\n                )\n""",
)

replace_once(
    review_path,
    """                skipped_pair_reasons.append(\n                    {\n                        \"reason_code\": \"trace_netclass_unresolved\",\n                        \"pair_segment_ids\": [first, second],\n                        \"details\": {\n                            \"net_ids\": [\n                                value for value in (segment.net_id, other.net_id) if value\n                            ],\n                            \"unresolved_class_reference\": str(\n                                exc.details.get(\"unresolved_class_reference\", \"unknown\")\n                            ),\n                        },\n                    }\n                )\n""",
    """                skipped_pair_reasons_total = _append_bounded_reason(\n                    skipped_pair_reasons,\n                    {\n                        \"reason_code\": \"trace_netclass_unresolved\",\n                        \"pair_segment_ids\": [first, second],\n                        \"details\": {\n                            \"net_ids\": [\n                                value for value in (segment.net_id, other.net_id) if value\n                            ],\n                            \"unresolved_class_reference\": str(\n                                exc.details.get(\"unresolved_class_reference\", \"unknown\")\n                            ),\n                        },\n                    },\n                    total=skipped_pair_reasons_total,\n                )\n""",
)

replace_once(
    review_path,
    """                skipped_pair_reasons.append(\n                    {\n                        \"reason_code\": unavailable_code,\n                        \"pair_segment_ids\": [first, second],\n                        \"details\": {\n                            \"layer_id\": layer,\n                            \"net_ids\": [\n                                value for value in (segment.net_id, other.net_id) if value\n                            ],\n                        },\n                    }\n                )\n""",
    """                skipped_pair_reasons_total = _append_bounded_reason(\n                    skipped_pair_reasons,\n                    {\n                        \"reason_code\": unavailable_code,\n                        \"pair_segment_ids\": [first, second],\n                        \"details\": {\n                            \"layer_id\": layer,\n                            \"net_ids\": [\n                                value for value in (segment.net_id, other.net_id) if value\n                            ],\n                        },\n                    },\n                    total=skipped_pair_reasons_total,\n                )\n""",
)

replace_once(
    review_path,
    """    partial = bool(\n        not rules_available\n        or skipped_unresolved_net_pairs\n        or skipped_clearance_resolution_pairs\n    )\n""",
    """    partial = bool(\n        skipped_unresolved_net_pairs or skipped_clearance_resolution_pairs\n    )\n""",
)

replace_once(
    review_path,
    """        final_status.update(\n            {\n                \"netclass_rules_ignored\": True,\n                \"partial_review\": True,\n                \"warning_code\": sorted(warning_codes)[0],\n                \"warning_codes\": sorted(warning_codes),\n            }\n        )\n""",
    """        final_status.update(\n            {\n                \"partial_review\": True,\n                \"warning_code\": sorted(warning_codes)[0],\n                \"warning_codes\": sorted(warning_codes),\n            }\n        )\n""",
)

replace_once(
    review_path,
    """        \"skipped_pair_reasons\": skipped_pair_reasons,\n        \"warning_codes\": sorted(warning_codes),\n""",
    """        \"skipped_pair_reasons\": skipped_pair_reasons,\n        \"skipped_pair_reasons_total\": skipped_pair_reasons_total,\n        \"skipped_pair_reasons_truncated\": (\n            skipped_pair_reasons_total > len(skipped_pair_reasons)\n        ),\n        \"candidate_pairs_not_enumerated\": False,\n        \"warning_codes\": sorted(warning_codes),\n""",
)

replace_once(
    review_path,
    """    if partial:\n        metrics[\"partial_skipped\"] = (\n            \"trace_clearance_rules_unavailable\"\n            if not rules_available and candidate_pairs_checked == 0\n            else \"trace_clearance_partial\"\n        )\n""",
    """    if partial:\n        metrics[\"partial_skipped\"] = \"trace_clearance_partial\"\n""",
)

replace_once(
    review_path,
    """        check_status = check_metrics.get(\"clearance_rule_status\")\n        if check_metrics.get(\"clearance_review_complete\") is False:\n            metrics[\"clearance_review_complete\"] = False\n        if isinstance(check_status, dict) and check_status.get(\n            \"netclass_rules_ignored\", False\n        ):\n            metrics[\"netclass_rules_ignored\"] = True\n            metrics[\"clearance_rule_status\"] = {\n                **metrics[\"clearance_rule_status\"],\n                \"netclass_rules_ignored\": True,\n                \"clearance_review_complete\": metrics[\"clearance_review_complete\"],\n                \"warning_code\": check_status.get(\n                    \"warning_code\", \"netclass_rules_ignored\"\n                ),\n                \"warning_codes\": check_status.get(\n                    \"warning_codes\", [check_status.get(\"warning_code\", \"netclass_rules_ignored\")]\n                ),\n            }\n""",
    """        check_status = check_metrics.get(\"clearance_rule_status\")\n        check_incomplete = check_metrics.get(\"clearance_review_complete\") is False\n        if check_incomplete:\n            metrics[\"clearance_review_complete\"] = False\n            if isinstance(check_status, dict):\n                warning_codes = check_status.get(\"warning_codes\", [])\n                if not isinstance(warning_codes, list):\n                    warning_codes = []\n                warning_code = check_status.get(\"warning_code\")\n                if warning_code is not None and warning_code not in warning_codes:\n                    warning_codes = [*warning_codes, warning_code]\n                metrics[\"clearance_rule_status\"] = {\n                    **metrics[\"clearance_rule_status\"],\n                    \"clearance_review_complete\": False,\n                    \"partial_review\": True,\n                    \"warning_code\": warning_code,\n                    \"warning_codes\": warning_codes,\n                }\n        if isinstance(check_status, dict) and check_status.get(\n            \"netclass_rules_ignored\", False\n        ):\n            metrics[\"netclass_rules_ignored\"] = True\n            metrics[\"clearance_rule_status\"] = {\n                **metrics[\"clearance_rule_status\"],\n                \"netclass_rules_ignored\": True,\n            }\n""",
)


test_path = Path("tests/test_review.py")
replace_once(
    test_path,
    """import pytest\n\nfrom diptrace_mcp.adapters import build_snapshot\n""",
    """import pytest\n\nimport diptrace_mcp.review as review_module\nfrom diptrace_mcp.adapters import build_snapshot\n""",
)

replace_once(
    test_path,
    """    assert metrics[\"clearance_review_complete\"] is False\n    assert metrics[\"netclass_rules_ignored\"] is True\n\n\ndef test_trace_clearance_discloses_unknown_netclass_and_does_not_find_violation() -> None:\n""",
    """    assert metrics[\"clearance_review_complete\"] is False\n    assert metrics[\"netclass_rules_ignored\"] is False\n    assert metrics[\"clearance_rule_status\"][\"partial_review\"] is True\n\n\ndef test_trace_clearance_discloses_unknown_netclass_and_does_not_find_violation() -> None:\n""",
)

replace_once(
    test_path,
    """def test_trace_clearance_reports_whole_check_skip_when_rules_are_absent() -> None:\n    snapshot = _trace_pair_snapshot(remove_rules=True)\n\n    findings, metrics, skipped, _ = run_checks(snapshot, categories={\"clearance\"})\n\n    trace_metrics = metrics[\"pcb.trace_clearance\"]\n    assert findings == []\n    assert skipped == [\n        {\"check_id\": \"pcb.trace_clearance\", \"reason\": \"trace_clearance_partial\"}\n    ]\n    assert trace_metrics[\"candidate_pairs_checked\"] >= 1\n    assert trace_metrics[\"evaluated_pairs\"] == 0\n    assert trace_metrics[\"skipped_clearance_resolution_pairs\"] >= 1\n    assert trace_metrics[\"warning_codes\"] == [\"trace_clearance_rules_unavailable\"]\n    assert any(\n        item[\"reason_code\"] == \"trace_clearance_rules_unavailable\"\n        and item.get(\"scope\") == \"check\"\n        for item in trace_metrics[\"skipped_pair_reasons\"]\n    )\n\n\n""",
    """def test_trace_clearance_reports_whole_check_skip_when_rules_are_absent() -> None:\n    snapshot = _trace_pair_snapshot(remove_rules=True)\n\n    findings, metrics, skipped, _ = run_checks(snapshot, categories={\"clearance\"})\n\n    trace_metrics = metrics[\"pcb.trace_clearance\"]\n    assert findings == []\n    assert skipped == [\n        {\n            \"check_id\": \"pcb.trace_clearance\",\n            \"reason\": \"trace_clearance_rules_unavailable\",\n        }\n    ]\n    assert trace_metrics[\"candidate_pairs_checked\"] == 0\n    assert trace_metrics[\"candidate_pairs_not_enumerated\"] is True\n    assert trace_metrics[\"evaluated_pairs\"] == 0\n    assert trace_metrics[\"skipped_clearance_resolution_pairs\"] == 0\n    assert trace_metrics[\"skipped_pair_reasons_total\"] == 1\n    assert trace_metrics[\"skipped_pair_reasons_truncated\"] is False\n    assert trace_metrics[\"warning_codes\"] == [\"trace_clearance_rules_unavailable\"]\n    assert trace_metrics[\"skipped_pair_reasons\"] == [\n        {\n            \"reason_code\": \"trace_clearance_rules_unavailable\",\n            \"scope\": \"check\",\n        }\n    ]\n    assert metrics[\"netclass_rules_ignored\"] is False\n    assert metrics[\"clearance_review_complete\"] is False\n\n\n""",
)

replace_once(
    test_path,
    """def test_router_and_trace_review_use_the_same_netclass_clearance() -> None:\n""",
    """def test_trace_clearance_bounds_skipped_pair_reason_details(\n    monkeypatch: pytest.MonkeyPatch,\n) -> None:\n    monkeypatch.setattr(review_module, \"MAX_SKIPPED_PAIR_REASONS\", 1)\n    snapshot = _trace_pair_snapshot(add_second_unresolved=True)\n\n    _, metrics, _, _ = run_checks(snapshot, categories={\"clearance\"})\n\n    trace_metrics = metrics[\"pcb.trace_clearance\"]\n    assert trace_metrics[\"skipped_pair_reasons_total\"] > 1\n    assert len(trace_metrics[\"skipped_pair_reasons\"]) == 1\n    assert trace_metrics[\"skipped_pair_reasons_truncated\"] is True\n    assert trace_metrics[\"clearance_review_complete\"] is False\n\n\ndef test_router_and_trace_review_use_the_same_netclass_clearance() -> None:\n""",
)


docs_path = Path("docs/REVIEW_ENGINE.md")
replace_once(
    docs_path,
    """Unresolved pairs produce no violation finding because no safe effective rule was\ncalculated, but they set `clearance_review_complete: false`, add a stable\n`warning_codes` value, and appear in report-level `skipped_reasons` with the\npair segment ids and safe unresolved-net/class details. A missing rule set is\nalso a partial result; when possible, all same-layer unlike-net candidates are\ncounted before the resolver reports the rule as unavailable. A skipped pair is\nnever counted as evaluated or compliant.\n""",
    """Unresolved pairs produce no violation finding because no safe effective rule was\ncalculated, but they set `clearance_review_complete: false`, add a stable\n`warning_codes` value, and appear in report-level `skipped_reasons` with safe\nunresolved-net/class details. Detailed pair reasons are bounded by\n`MAX_SKIPPED_PAIR_REASONS`; `skipped_pair_reasons_total` and\n`skipped_pair_reasons_truncated` disclose omitted detail records. A missing rule\nset returns a whole-check partial result without enumerating quadratic same-layer\npairs; `candidate_pairs_not_enumerated: true` makes that boundary explicit. A\nskipped pair is never counted as evaluated or compliant.\n\n`netclass_rules_ignored` is reserved for paths that actually ignore or cannot\nresolve NetClass rules. An absent owning net still makes the clearance review\npartial, but it does not by itself claim that a NetClass rule was ignored.\n""",
)


changelog_path = Path("CHANGELOG.md")
replace_once(
    changelog_path,
    """- make unresolved trace-clearance pairs explicit and publish their structured\n  skip reasons and effective clearance rule sources;\n""",
    """- make unresolved trace-clearance pairs explicit and publish their structured\n  skip reasons and effective clearance rule sources;\n- bound partial trace-clearance detail output, avoid quadratic pair enumeration\n  when rules are unavailable, and separate partial-review status from actual\n  NetClass-rule omission;\n""",
)
