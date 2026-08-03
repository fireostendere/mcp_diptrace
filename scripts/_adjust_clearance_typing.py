from pathlib import Path

path = Path("src/diptrace_mcp/review.py")
text = path.read_text(encoding="utf-8")
if text.count('        warning_codes = ["trace_clearance_rules_unavailable"]') != 1:
    raise RuntimeError("Expected one unavailable-rule warning list")
text = text.replace(
    '        warning_codes = ["trace_clearance_rules_unavailable"]',
    '        unavailable_warning_codes = ["trace_clearance_rules_unavailable"]',
    1,
)
if text.count('            "warning_code": warning_codes[0],') != 1:
    raise RuntimeError("Expected one unavailable-rule warning code reference")
text = text.replace(
    '            "warning_code": warning_codes[0],',
    '            "warning_code": unavailable_warning_codes[0],',
    1,
)
if text.count('            "warning_codes": warning_codes,') != 2:
    raise RuntimeError("Expected two unavailable-rule warning list references")
text = text.replace(
    '            "warning_codes": warning_codes,',
    '            "warning_codes": unavailable_warning_codes,',
)
path.write_text(text, encoding="utf-8")
