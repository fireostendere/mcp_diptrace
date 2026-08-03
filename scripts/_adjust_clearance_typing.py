from pathlib import Path

path = Path("src/diptrace_mcp/review.py")
text = path.read_text(encoding="utf-8")
assignment = '        warning_codes = ["trace_clearance_rules_unavailable"]'
if text.count(assignment) != 1:
    raise RuntimeError("Expected one unavailable-rule warning list")
text = text.replace(
    assignment,
    '        unavailable_warning_codes = ["trace_clearance_rules_unavailable"]',
    1,
)
warning_code_reference = '            "warning_code": warning_codes[0],'
if text.count(warning_code_reference) != 1:
    raise RuntimeError("Expected one unavailable-rule warning code reference")
text = text.replace(
    warning_code_reference,
    '            "warning_code": unavailable_warning_codes[0],',
    1,
)
warning_list_reference = '"warning_codes": warning_codes,'
if warning_list_reference not in text:
    raise RuntimeError("Expected unavailable-rule warning list references")
text = text.replace(
    warning_list_reference,
    '"warning_codes": unavailable_warning_codes,',
)
path.write_text(text, encoding="utf-8")
