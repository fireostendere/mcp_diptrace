#!/usr/bin/env python3
"""Standalone quality gate over a project's PCB_BUILD.md handoff.

Verifies what the prose handoff only claims:
  1. Gate table is parseable and monotonic (no PASS above a non-PASS gate).
  2. Recorded SHAs match the actual schematic/board files on disk.
  3. The final board passes the offline headless QC (review_pcb_quality,
     hard_error_count == 0) — the same gate the build scripts assert.

Exit code: 0 = consistent (pending manual gates are reported, not fatal),
1 = BLOCKED (violations listed). Manual gates (native DRC, media) stay manual.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.pcb_quality import PCBQualityConfig, review_pcb_quality
from diptrace_mcp.xml_document import DipTraceDocument

MAX_XML_BYTES = 128 * 1024 * 1024
OK_STATUSES = {"PASS"}
OPEN_STATUSES = {"PENDING", "TODO", "MANUAL"}
GATE_ROW = re.compile(r"^\|\s*(\d+)\.\s*(.+?)\s*\|\s*([A-Za-z_ ]+?)\s*\|")
SHA_LINE = re.compile(r"^(.*?) SHA-256:\s*`([0-9a-f]{64})`", re.MULTILINE)


def parse_handoff(text: str) -> tuple[dict[int, tuple[str, str]], dict[str, str]]:
    gates: dict[int, tuple[str, str]] = {}
    for line in text.splitlines():
        row = GATE_ROW.match(line)
        if row:
            gates[int(row.group(1))] = (row.group(2), row.group(3).upper())
    shas = {label.strip().casefold(): digest for label, digest in SHA_LINE.findall(text)}
    return gates, shas


def check_order(gates: dict[int, tuple[str, str]]) -> list[str]:
    violations: list[str] = []
    for number in sorted(gates):
        name, status = gates[number]
        if status in OK_STATUSES:
            continue
        if status not in OPEN_STATUSES and status != "FAIL":
            violations.append(f"gate {number} ({name}): unknown status '{status}'")
            continue
        for later in sorted(gates):
            if later <= number:
                continue
            later_name, later_status = gates[later]
            if later_status in OK_STATUSES:
                violations.append(
                    f"gate {later} ({later_name}) is PASS while earlier gate "
                    f"{number} ({name}) is {status}"
                )
        break
    return violations


def resolve_unique(project: Path, pattern: str) -> Path | None:
    candidates = [
        item for item in project.glob(pattern)
        if not item.name.startswith("~") and not item.name.startswith(".")
    ]
    return candidates[0] if len(candidates) == 1 else None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_board_qc(board: Path, centerline_x: list[str], centerline_y: list[str]) -> object:
    document = DipTraceDocument.load(board, MAX_XML_BYTES)
    snapshot = build_snapshot(document)
    return review_pcb_quality(
        snapshot,
        config=PCBQualityConfig(
            centerline_groups={"x": centerline_x, "y": centerline_y},
        ),
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="directory containing PCB_BUILD.md")
    parser.add_argument("--centerline-x", default="", help="comma-separated refdes on the x datum")
    parser.add_argument("--centerline-y", default="", help="comma-separated refdes on the y datum")
    parser.add_argument("--board", type=Path, default=None, help="explicit board file override")
    args = parser.parse_args()

    handoff = args.project / "PCB_BUILD.md"
    blocked: list[str] = []
    if not handoff.is_file():
        print(f"BLOCKED: no PCB_BUILD.md in {args.project}")
        return 1
    gates, shas = parse_handoff(handoff.read_text(encoding="utf-8"))
    if not gates:
        blocked.append("PCB_BUILD.md has no parseable gate table rows")
    blocked += check_order(gates)

    board = args.board or resolve_unique(args.project, "*-pcb.dipxml")
    board_sha = shas.get("current board")
    if board is None or board_sha is None:
        blocked.append("cannot verify current board SHA (no unique *-pcb.dipxml or no record)")
    elif sha256_of(board) != board_sha:
        blocked.append(f"board SHA stale: {board.name} does not match PCB_BUILD.md record")

    schematic = resolve_unique(args.project, "*.dchxml")
    schematic_sha = shas.get("input schematic")
    if schematic is not None and schematic_sha is not None and sha256_of(schematic) != schematic_sha:
        blocked.append(f"schematic SHA stale: {schematic.name} does not match PCB_BUILD.md record")

    if board is not None:
        quality = run_board_qc(
            board,
            [item for item in args.centerline_x.split(",") if item],
            [item for item in args.centerline_y.split(",") if item],
        )
        errors = [item for item in quality.findings if item.severity == "error"]
        warnings = [item for item in quality.findings if item.severity == "warning"]
        blocked += [f"QC error [{item.code}] {item.message}" for item in errors]
        for item in warnings:
            print(f"warning [{item.code}] {item.message}")
        print(
            f"QC: hard_errors={quality.hard_error_count} warnings={quality.warning_count} "
            f"score={quality.score:.1f} unrouted={quality.unrouted_connection_count} "
            f"stitch_coverage={quality.stitching_coverage_ratio}"
        )

    pending = [
        f"gate {number} ({name})"
        for number, (name, status) in sorted(gates.items())
        if status in OPEN_STATUSES | {"FAIL"}
    ]
    if blocked:
        print("BLOCKED:")
        for item in blocked:
            print(f"  - {item}")
        return 1
    print("PASS: handoff consistent, headless QC green")
    if pending:
        print("Pending manual gates: " + "; ".join(pending))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
