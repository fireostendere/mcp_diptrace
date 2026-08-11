#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from diptrace_mcp.evidence_report import build_evidence_report, render_evidence_report_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic review-only report from a finalized DipTrace capture candidate."
    )
    parser.add_argument("candidate", help="Finalized *.candidate.json manifest")
    parser.add_argument("--capture-root", required=True, help="Allowed root used by capture_diptrace_evidence.py")
    parser.add_argument("--markdown", help="Optional Markdown report output path")
    parser.add_argument("--json-output", help="Optional JSON report output path")
    return parser


def run_cli(arguments: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    report = build_evidence_report(args.candidate, args.capture_root)
    payload = report.model_dump(mode="json")
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.markdown:
        Path(args.markdown).write_text(
            render_evidence_report_markdown(report),
            encoding="utf-8",
        )
    if not args.json_output and not args.markdown:
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
