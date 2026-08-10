from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")


def test_public_markdown_is_english_only() -> None:
    files = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    violations: list[str] = []

    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _CYRILLIC.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line}")

    assert not violations, "Cyrillic text remains in public documentation:\n" + "\n".join(
        violations
    )
