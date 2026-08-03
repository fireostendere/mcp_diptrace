from pathlib import Path

path = Path("src/diptrace_mcp/review.py")
text = path.read_text(encoding="utf-8")

start_marker = '    if not rules_available:\n'
end_marker = '    maximum_clearance = '
start = text.index(start_marker)
end = text.index(end_marker, start)
block = text[start:end]

assignment = '        warning_codes = ["trace_clearance_rules_unavailable"]'
if block.count(assignment) != 1:
    raise RuntimeError("Expected one unavailable-rule warning list in early-return block")
block = block.replace(
    assignment,
    '        unavailable_warning_codes = ["trace_clearance_rules_unavailable"]',
    1,
)

warning_code_reference = '            "warning_code": warning_codes[0],'
if block.count(warning_code_reference) != 1:
    raise RuntimeError("Expected one unavailable-rule warning code reference")
block = block.replace(
    warning_code_reference,
    '            "warning_code": unavailable_warning_codes[0],',
    1,
)

warning_list_reference = '"warning_codes": warning_codes,'
reference_count = block.count(warning_list_reference)
if reference_count < 1:
    raise RuntimeError("Expected unavailable-rule warning list references")
block = block.replace(
    warning_list_reference,
    '"warning_codes": unavailable_warning_codes,',
)

text = text[:start] + block + text[end:]
path.write_text(text, encoding="utf-8")
