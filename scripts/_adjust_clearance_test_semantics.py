from pathlib import Path

path = Path("tests/test_review.py")
text = path.read_text(encoding="utf-8")
old = """    assert metrics[\"clearance_review_complete\"] is False
    assert metrics[\"netclass_rules_ignored\"] is False
    assert metrics[\"clearance_rule_status\"][\"partial_review\"] is True
"""
new = """    assert metrics[\"clearance_review_complete\"] is False
    assert trace_metrics[\"clearance_rule_status\"][\"netclass_rules_ignored\"] is False
    assert metrics[\"netclass_rules_ignored\"] is True
    assert metrics[\"clearance_rule_status\"][\"partial_review\"] is True
"""
if text.count(old) != 1:
    raise RuntimeError("Expected one generated NetClass status assertion block")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
