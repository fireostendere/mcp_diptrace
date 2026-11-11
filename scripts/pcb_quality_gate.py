#!/usr/bin/env python3
"""Checkout entry point for the packaged quality gate (``diptrace_mcp.quality_gate``)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diptrace_mcp.quality_gate import (  # noqa: E402
    check_order,
    main,
    parse_fields,
    parse_handoff,
    run_board_qc,
    run_schematic_review,
)

__all__ = [
    "check_order",
    "main",
    "parse_fields",
    "parse_handoff",
    "run_board_qc",
    "run_schematic_review",
]

if __name__ == "__main__":
    raise SystemExit(main())
