from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_OPERATOR_EVIDENCE_DOC = "SCHEMATIC_AUTHORING_VALIDATION_2026-08-10.md"


def _is_verbatim_operator_evidence(path: Path, line: str) -> bool:
    """Allow original-language operator verdict quotes only in the dated validation journal."""
    lowered = line.casefold()
    return (
        path.name == _OPERATOR_EVIDENCE_DOC
        and "operator" in lowered
        and "verdict" in lowered
        and '"' in line
    )


def test_public_markdown_is_english_only() -> None:
    files = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    violations: list[str] = []

    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _CYRILLIC.search(line) and not _is_verbatim_operator_evidence(path, line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line}")

    assert not violations, "Cyrillic text remains in public documentation:\n" + "\n".join(
        violations
    )
