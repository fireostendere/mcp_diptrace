#!/usr/bin/env python3
"""Capture a PCB quality-gate result as a small RAG-readable memory note."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def event_id(report: dict[str, Any]) -> str:
    stable = {key: value for key, value in report.items() if key != "captured_at"}
    return hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def render_event(report: dict[str, Any]) -> str:
    gates = ", ".join(
        f"{item['number']}={item['status']}" for item in report.get("gates", [])
    ) or "none"
    artifacts = report.get("artifacts", {})
    board = artifacts.get("board", {})
    schematic = artifacts.get("schematic", {})
    recorded_shas = report.get("recorded_shas", {})
    quality = report.get("quality") or {}
    blocked = report.get("blocked") or ["none"]
    pending = report.get("pending") or ["none"]
    marker = f"<!-- quality-gate-event: {event_id(report)} -->"
    qc_line = (
        f"- Headless QC: hard errors={quality.get('hard_error_count', 'unknown')}, "
        f"warnings={quality.get('warning_count', 'unknown')}, "
        f"unrouted={quality.get('unrouted_connection_count', 'unknown')}, "
        f"score={quality.get('score', 'unknown')}"
    )
    findings = quality.get("findings") or []
    finding_lines = "\n".join(
        f"- `{item['severity']}` `{item['code']}`: {item['message']}"
        for item in findings
    ) or "- none"
    blocked_lines = "\n".join(f"- {item}" for item in blocked)
    pending_lines = "\n".join(f"- {item}" for item in pending)
    return f"""{marker}
## {report.get('captured_at', 'unknown')} — {report.get('status', 'UNKNOWN')}

- Project: `{report.get('project', 'unknown')}`
- Handoff: `{report.get('handoff', 'unknown')}`
- Gates: {gates}
- Board: `{board.get('path', 'unknown')}`
- Board SHA-256: `{board.get('sha256', 'unknown')}`
- Schematic: `{schematic.get('path', 'unknown')}`
- Schematic SHA-256: `{schematic.get('sha256', 'unknown')}`
- Recorded input SHA-256: `{recorded_shas.get('input schematic', 'unknown')}`
- Recorded board SHA-256: `{recorded_shas.get('current board', 'unknown')}`
{qc_line}

### Blocking evidence

{blocked_lines}

### Pending gates

{pending_lines}

### QC findings

{finding_lines}

"""


def append_event(path: Path, report: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    marker = f"<!-- quality-gate-event: {event_id(report)} -->"
    if marker in existing:
        return False
    separator = "\n" if existing and not existing.endswith("\n") else ""
    # ponytail: no cross-process lock; duplicate event IDs are harmless and
    # append mode avoids losing a concurrent checkpoint.
    with path.open("a", encoding="utf-8") as stream:
        stream.write(separator + render_event(report))
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="directory containing PCB_BUILD.md")
    parser.add_argument(
        "--memory",
        type=Path,
        default=None,
        help="Markdown file to append (default: docs/engineering-memory/quality-gates.md)",
    )
    parser.add_argument("--centerline-x", default="")
    parser.add_argument("--centerline-y", default="")
    parser.add_argument("--board", type=Path, default=None)
    parser.add_argument("--schematic", type=Path, default=None)
    args = parser.parse_args()

    project = args.project.resolve()
    memory = args.memory or project / "docs/engineering-memory/quality-gates.md"
    if not memory.is_absolute():
        memory = project / memory
    command = [
        sys.executable,
        str(Path(__file__).with_name("pcb_quality_gate.py")),
        str(project),
        "--json",
    ]
    if args.centerline_x:
        command += ["--centerline-x", args.centerline_x]
    if args.centerline_y:
        command += ["--centerline-y", args.centerline_y]
    if args.board is not None:
        command += ["--board", str(args.board)]
    if args.schematic is not None:
        command += ["--schematic", str(args.schematic)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return completed.returncode or 1
    if append_event(memory, report):
        print(f"memory appended: {memory}")
    else:
        print(f"memory unchanged: event {event_id(report)} already recorded")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
