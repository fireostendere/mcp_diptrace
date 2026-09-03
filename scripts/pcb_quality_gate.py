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
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.pcb_quality import PCBQualityConfig, review_pcb_quality
from diptrace_mcp.xml_document import DipTraceDocument

MAX_XML_BYTES = 128 * 1024 * 1024
OK_STATUSES = {"PASS"}
OPEN_STATUSES = {"PENDING", "TODO", "MANUAL", "PARTIAL"}
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
        # Mirror the build() QC config: the CP2102 thermal via cluster under
        # exposed pad 29 is a deliberate same-net stitch (see PCB_BUILD.md).
        config=PCBQualityConfig(
            via_pad_clearance_mm=0.13,
            allow_thermal_via_in_pad=True,
            centerline_groups={"x": centerline_x, "y": centerline_y},
        ),
    )


def _report(
    *,
    project: Path,
    handoff: Path,
    gates: dict[int, tuple[str, str]],
    shas: dict[str, str],
    board: Path | None,
    schematic: Path | None,
    quality: object | None,
    blocked: list[str],
    pending: list[str],
) -> dict[str, object]:
    artifacts: dict[str, object] = {}
    for role, path in (("board", board), ("schematic", schematic)):
        if path is None:
            continue
        artifacts[role] = {"path": str(path), "sha256": sha256_of(path)}
    quality_payload: dict[str, object] | None = None
    if quality is not None:
        quality_payload = {
            "hard_error_count": quality.hard_error_count,
            "warning_count": quality.warning_count,
            "score": quality.score,
            "unrouted_connection_count": quality.unrouted_connection_count,
            "stitching_coverage_ratio": quality.stitching_coverage_ratio,
            "ground_stitching_via_count": quality.ground_stitching_via_count,
            "findings": [
                {
                    "code": item.code,
                    "category": item.category,
                    "severity": item.severity,
                    "message": item.message,
                }
                for item in quality.findings
            ],
        }
    return {
        "schema": "diptrace-engineering-memory/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "project": str(project.resolve()),
        "handoff": str(handoff.resolve()),
        "status": "BLOCKED" if blocked else "CONSISTENT",
        "gates": [
            {"number": number, "name": name, "status": status}
            for number, (name, status) in sorted(gates.items())
        ],
        "recorded_shas": shas,
        "artifacts": artifacts,
        "quality": quality_payload,
        "blocked": blocked,
        "pending": pending,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path, help="directory containing PCB_BUILD.md")
    parser.add_argument("--centerline-x", default="", help="comma-separated refdes on the x datum")
    parser.add_argument("--centerline-y", default="", help="comma-separated refdes on the y datum")
    parser.add_argument("--board", type=Path, default=None, help="explicit board file override")
    parser.add_argument(
        "--schematic", type=Path, default=None, help="explicit schematic file override"
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args()

    project = args.project.resolve()
    handoff = project / "PCB_BUILD.md"
    blocked: list[str] = []
    if not handoff.is_file():
        if args.json:
            print(json.dumps({
                "schema": "diptrace-engineering-memory/v1",
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "project": str(project),
                "status": "BLOCKED",
                "blocked": [f"no PCB_BUILD.md in {project}"],
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
        print(f"BLOCKED: no PCB_BUILD.md in {project}")
        return 1
    gates, shas = parse_handoff(handoff.read_text(encoding="utf-8"))
    if not gates:
        blocked.append("PCB_BUILD.md has no parseable gate table rows")
    blocked += check_order(gates)

    board = args.board or resolve_unique(project, "*-pcb.dipxml")
    if board is not None and not board.is_absolute():
        board = project / board
    board_sha = shas.get("current board")
    if board is None:
        blocked.append("cannot verify current board SHA (no unique *-pcb.dipxml)")
    elif board_sha is None:
        blocked.append("cannot verify current board SHA (PCB_BUILD.md has no record)")
    elif sha256_of(board) != board_sha:
        blocked.append(f"board SHA stale: {board.name} does not match PCB_BUILD.md record")

    schematic = args.schematic or resolve_unique(project, "*.dchxml")
    if schematic is not None and not schematic.is_absolute():
        schematic = project / schematic
    schematic_sha = shas.get("input schematic")
    if schematic is None:
        blocked.append("cannot verify input schematic SHA (no unique *.dchxml)")
    elif schematic_sha is None:
        blocked.append("cannot verify input schematic SHA (PCB_BUILD.md has no record)")
    elif sha256_of(schematic) != schematic_sha:
        blocked.append(f"schematic SHA stale: {schematic.name} does not match PCB_BUILD.md record")

    quality = None
    quality_warnings: list[str] = []
    quality_summary = ""
    if board is not None:
        quality = run_board_qc(
            board,
            [item for item in args.centerline_x.split(",") if item],
            [item for item in args.centerline_y.split(",") if item],
        )
        errors = [item for item in quality.findings if item.severity == "error"]
        warnings = [item for item in quality.findings if item.severity == "warning"]
        blocked += [f"QC error [{item.code}] {item.message}" for item in errors]
        quality_warnings = [f"warning [{item.code}] {item.message}" for item in warnings]
        quality_summary = (
            f"QC: hard_errors={quality.hard_error_count} warnings={quality.warning_count} "
            f"score={quality.score:.1f} unrouted={quality.unrouted_connection_count} "
            f"stitch_coverage={quality.stitching_coverage_ratio}"
        )

    pending = [
        f"gate {number} ({name})"
        for number, (name, status) in sorted(gates.items())
        if status in OPEN_STATUSES | {"FAIL"}
    ]
    report = _report(
        project=project,
        handoff=handoff,
        gates=gates,
        shas=shas,
        board=board,
        schematic=schematic,
        quality=quality,
        blocked=blocked,
        pending=pending,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if blocked else 0
    for warning in quality_warnings:
        print(warning)
    if quality_summary:
        print(quality_summary)
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
