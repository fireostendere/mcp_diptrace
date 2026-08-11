#!/usr/bin/env python3
"""Fail CI when evergreen documentation drifts from implemented repository state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TOOL_COUNT_DOCS = (
    "README.md",
    "docs/ROADMAP.md",
    "docs/TESTING.md",
    "docs/MCP_TOOLS.md",
    "docs/ARCHITECTURE.md",
)

FEATURE_DOCS: dict[str, tuple[str, ...]] = {
    "schematic_atomic_reroute.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/SCHEMATIC_LAYOUT_ENGINE.md",
        "docs/ROADMAP.md",
    ),
    "schematic_ensemble.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/SCHEMATIC_LAYOUT_ENGINE.md",
    ),
    "pcb_candidate_ensemble.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/PCB_DESIGN_ENGINE.md",
    ),
    "specctra_analysis.py": ("docs/EDA_INTELLIGENCE.md",),
    "xml_analysis.py": ("docs/EDA_INTELLIGENCE.md",),
    "evidence_report.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/EVIDENCE_CAPTURE.md",
    ),
    "cinematic_preflight.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/CINEMATIC_DEMO_MODE.md",
    ),
    "library_mutation_api.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/ARCHITECTURE.md",
    ),
}

STALE_PHRASES: dict[str, tuple[str, ...]] = {
    "CHANGELOG_NEXT.md": (
        "selective atomic re-route/replacement of existing schematic wires after "
        "placement repair remains future work",
    ),
    "docs/TESTING.md": (
        "Existing-wire selective reroute is not yet the default supported placement path",
    ),
}


def _read_text(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{relative}: cannot read: {exc}")
        return ""


def _snapshot_tool_count(root: Path, errors: list[str]) -> int | None:
    path = root / "reference/mcp-tools-list.snapshot.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"reference/mcp-tools-list.snapshot.json: cannot parse: {exc}")
        return None
    count = value.get("tool_count") if isinstance(value, dict) else None
    if not isinstance(count, int) or count < 1:
        errors.append("reference/mcp-tools-list.snapshot.json: invalid tool_count")
        return None
    return count


def check_documentation_state(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    tool_count = _snapshot_tool_count(root, errors)

    if tool_count is not None:
        for relative in TOOL_COUNT_DOCS:
            text = _read_text(root, relative, errors)
            if str(tool_count) not in text:
                errors.append(
                    f"{relative}: does not mention frozen public MCP tool count "
                    f"{tool_count}"
                )

    for module_name, docs in FEATURE_DOCS.items():
        module_path = root / "src/diptrace_mcp" / module_name
        if not module_path.is_file():
            errors.append(f"src/diptrace_mcp/{module_name}: implemented module is missing")
            continue
        for relative in docs:
            text = _read_text(root, relative, errors)
            if module_name not in text:
                errors.append(
                    f"{relative}: implemented module {module_name} is undocumented"
                )

    for relative, phrases in STALE_PHRASES.items():
        text = _read_text(root, relative, errors)
        for phrase in phrases:
            if phrase.casefold() in text.casefold():
                errors.append(f"{relative}: contains stale current-state claim: {phrase}")

    cinematic_host = _read_text(
        root,
        "src/diptrace_mcp/cinematic_host.py",
        errors,
    )
    if "from .cinematic_preflight import preflight_cinematic_manifest" not in cinematic_host:
        errors.append("cinematic_host.py: cinematic preflight is not imported")
    if "preflight_cinematic_manifest(manifest)" not in cinematic_host:
        errors.append("cinematic_host.py: playback does not enforce cinematic preflight")

    mutation_api = _read_text(
        root,
        "src/diptrace_mcp/library_mutation_api.py",
        errors,
    )
    if "public_registration=False" not in mutation_api:
        errors.append(
            "library_mutation_api.py: package-level preview must remain unregistered "
            "until the frozen MCP contract is intentionally revised"
        )

    return sorted(set(errors))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check evergreen documentation against implemented repository state."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (defaults to the script's repository)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    errors = check_documentation_state(args.root)
    if errors:
        print("documentation state: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("documentation state: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
