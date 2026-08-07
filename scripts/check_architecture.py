#!/usr/bin/env python3
"""Fail closed when the Facade decomposition regresses into large monoliths."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMITS = {
    "src/diptrace_mcp/server.py": 120,
    "src/diptrace_mcp/service.py": 2900,
}
REQUIRED = (
    "src/diptrace_mcp/server_inputs.py",
    "src/diptrace_mcp/server_runtime.py",
    "src/diptrace_mcp/adapter_common.py",
    "src/diptrace_mcp/services/container.py",
)


def main() -> int:
    failures: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            failures.append(f"missing architecture module: {relative}")
    for relative, max_lines in LIMITS.items():
        path = ROOT / relative
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > max_lines:
            failures.append(f"{relative}: {count} lines exceeds {max_lines}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: architecture decomposition guardrails are satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
