from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_documentation_state_guard_accepts_current_repository() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_documentation_state.py", "--root", str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "documentation state: ok" in result.stdout


def test_stale_tool_count_is_reported(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from check_documentation_state import stale_tool_counts
    finally:
        sys.path.pop(0)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/USAGE.md").write_text(
        "within the 167-tool surface\n152 registered MCP tools\nthe 167-tool `v0.4.0` contract\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/REVIEW_2026-01-01.md").write_text("159 tools\n", encoding="utf-8")

    assert stale_tool_counts(tmp_path, 152) == [
        "docs/USAGE.md:1: states 167 tools; the frozen snapshot has 152"
    ]
