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
