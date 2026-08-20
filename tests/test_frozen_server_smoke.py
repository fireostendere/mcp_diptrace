from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_frozen_smoke_is_stdlib_only_and_cleans_processes() -> None:
    source = (ROOT / "scripts/frozen_server_smoke.py").read_text(encoding="utf-8")

    assert "subprocess.Popen" in source
    assert "shell=False" in source
    assert "tools/list" in source
    assert "get_capabilities" in source
    assert "get_document_info" in source
    assert "def _stop_process" in source
    assert "process.wait(timeout=shutdown_timeout)" in source
    assert '"--shutdown-timeout"' in source
    assert "process.kill()" in source
    assert "from mcp" not in source
