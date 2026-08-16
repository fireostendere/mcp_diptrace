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
    ),
    "schematic_ensemble.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/SCHEMATIC_LAYOUT_ENGINE.md",
    ),
    "schematic_topology.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/SCHEMATIC_LAYOUT_ENGINE.md",
        "docs/ARCHITECTURE.md",
    ),
    "schematic_rotation.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/SCHEMATIC_LAYOUT_ENGINE.md",
        "docs/ARCHITECTURE.md",
    ),
    "pcb_candidate_ensemble.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/PCB_DESIGN_ENGINE.md",
    ),
    "pcb_whole_board.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/PCB_DESIGN_ENGINE.md",
        "docs/ARCHITECTURE.md",
    ),
    "physics_estimates.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/PCB_DESIGN_ENGINE.md",
        "docs/ARCHITECTURE.md",
        "docs/ROADMAP.md",
    ),
    "evidence_campaign.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/ARCHITECTURE.md",
        "docs/ROADMAP.md",
    ),
    "advanced_review.py": ("docs/EDA_INTELLIGENCE.md",),
    "specctra_analysis.py": ("docs/EDA_INTELLIGENCE.md",),
    "xml_analysis.py": ("docs/EDA_INTELLIGENCE.md",),
    "evidence_report.py": ("docs/EDA_INTELLIGENCE.md",),
    "cinematic_preflight.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/CINEMATIC_DEMO_MODE.md",
    ),
    "library_mutation_api.py": (
        "docs/EDA_INTELLIGENCE.md",
        "docs/ARCHITECTURE.md",
    ),
}

SEMANTIC_DOC_MARKERS: dict[str, tuple[str, ...]] = {
    "docs/ROADMAP.md": (
        "selective reroute of explicit affected",
        "one dependency-safe semantic batch",
        "pcb_candidate_ensemble.py",
    ),
    "docs/EVIDENCE_CAPTURE.md": ("scripts/build_evidence_report.py",),
    "docs/USAGE.md": (
        "cinematic_host.play_manifest()",
        "public_registration=False",
        "scripts/check_documentation_state.py",
    ),
}

CURRENT_ACCEPTANCE_DOCS = (
    "README.md",
    "CHANGELOG.md",
    "CHANGELOG_NEXT.md",
    "docs/ROADMAP.md",
    "docs/TESTING.md",
    "docs/TECH_DEBT.md",
    "docs/MCP_DISTRIBUTION.md",
    "docs/RELEASE_PROCESS.md",
    "docs/AUTOMATABLE_ROADMAP_CLOSURE.md",
    "docs/EDA_INTELLIGENCE.md",
)

CURRENT_ACCEPTANCE_MARKERS = (
    "all 12 blocking manual gates are pass",
    "all 12 blocking manual gates pass",
    "all 12 blocking gates are pass",
    "all 12 blocking gates are therefore pass",
    "all 12 blocking gates pass",
    "12 of 12 blocking gates pass",
    "12 of 12 blocking manual gates pass",
)

CLIENT_EVIDENCE_DOCS = (
    "README.md",
    "docs/AUTOMATABLE_ROADMAP_CLOSURE.md",
    "docs/EDA_INTELLIGENCE.md",
)

CLIENT_EVIDENCE_MARKER_GROUPS = (
    ("separate machine",),
    (
        "codex was not installed",
        "did not have codex installed",
        "without codex installed",
    ),
)

GLOBAL_STALE_ACCEPTANCE_PHRASES = (
    "claude desktop restart is waived",
    "claude desktop restart remains waived",
    "claude_desktop_real_client_restart` is explicitly waived for the current campaign",
    "windows lifecycle gates remain pending",
    "windows lifecycle is the next formal gate",
    "custom_state_preservation` is next",
    "next campaign gate is `custom_state_preservation`",
)

PLATFORM_DOC_MARKERS: dict[str, tuple[str, ...]] = {
    "README.md": ("0.4.0", "docs/LINUX.md", "docs/MACOS.md"),
    "docs/LINUX.md": ("v0.4.0", "private Xvfb", "Ubuntu 24.04"),
    "docs/MACOS.md": ("v0.4.0", "Apple Silicon", "Intel", "hidden Win32 desktop"),
    "docs/HEADLESS_GUI.md": ("private Xvfb", "macOS hidden-desktop backend"),
    "docs/RELEASE_PROCESS.md": ("v0.4.0", "published", ".github/workflows/release.yml"),
}

PUBLISHED_RELEASE_DOCS = (
    "README.md",
    "CHANGELOG.md",
    "docs/ROADMAP.md",
    "docs/RELEASE_PROCESS.md",
    "docs/MCP_DISTRIBUTION.md",
    "docs/INSTALL_FROM_RELEASE.md",
    "docs/WINDOWS_INSTALLER.md",
)

PUBLISHED_RELEASE_STALE_PHRASES = (
    "version `v0.3.0` is the current published",
    "version `0.4.0` is the current unsigned development release candidate",
    "`v0.4.0` is the current release candidate",
    "release candidate — not yet published",
)

STALE_PHRASES: dict[str, tuple[str, ...]] = {
    "CHANGELOG_NEXT.md": (
        "selective atomic re-route/replacement of existing schematic wires after "
        "placement repair remains future work",
    ),
    "docs/TESTING.md": (
        "Existing-wire selective reroute is not yet the default supported placement path",
    ),
    "docs/ARCHITECTURE.md": (
        "selective atomic reroute of existing schematic wires after placement repair "
        "is not implemented",
        "the fuller iterative objective-history loop remain incomplete",
    ),
    "docs/EDA_INTELLIGENCE.md": (
        "arbitrary hand-authored multi-junction topology is not reconstructed",
    ),
    "docs/SCHEMATIC_LAYOUT_ENGINE.md": (
        "arbitrary hand-authored multi-junction topology and full steiner-tree optimization "
        "are still not reconstructed",
    ),
    "docs/USAGE.md": (
        "Selective atomic placement + affected-wire replacement remains future work",
    ),
    "docs/DOMAIN_MODEL.md": (
        "selective atomic replacement of existing wires after placement repair remains future work",
    ),
    "docs/PLACEMENT_ENGINE.md": (
        "schematic selective reroute transaction after movement is still pending",
    ),
}


def _read_text(root: Path, relative: str, errors: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{relative}: cannot read: {exc}")
        return ""


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


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

    for relative, markers in SEMANTIC_DOC_MARKERS.items():
        text = _read_text(root, relative, errors)
        normalized = _normalized(text)
        for marker in markers:
            if _normalized(marker) not in normalized:
                errors.append(f"{relative}: missing current-state marker: {marker}")

    for relative in CURRENT_ACCEPTANCE_DOCS:
        text = _read_text(root, relative, errors)
        normalized = _normalized(text)
        if not any(_normalized(marker) in normalized for marker in CURRENT_ACCEPTANCE_MARKERS):
            errors.append(
                f"{relative}: does not record the completed 12/12 blocking manual matrix"
            )
        for phrase in GLOBAL_STALE_ACCEPTANCE_PHRASES:
            if _normalized(phrase) in normalized:
                errors.append(
                    f"{relative}: contains stale current acceptance claim: {phrase}"
                )

    for relative in CLIENT_EVIDENCE_DOCS:
        text = _read_text(root, relative, errors)
        normalized = _normalized(text)
        for alternatives in CLIENT_EVIDENCE_MARKER_GROUPS:
            if not any(_normalized(marker) in normalized for marker in alternatives):
                errors.append(
                    f"{relative}: missing current Claude client evidence marker: "
                    f"one of {', '.join(alternatives)}"
                )

    for relative, phrases in STALE_PHRASES.items():
        text = _read_text(root, relative, errors)
        normalized = _normalized(text)
        for phrase in phrases:
            if _normalized(phrase) in normalized:
                errors.append(f"{relative}: contains stale current-state claim: {phrase}")

    for relative, markers in PLATFORM_DOC_MARKERS.items():
        text = _read_text(root, relative, errors)
        normalized = _normalized(text)
        for marker in markers:
            if _normalized(marker) not in normalized:
                errors.append(f"{relative}: missing platform/release marker: {marker}")

    try:
        release_state = json.loads((root / "release.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"release.json: cannot parse published state: {exc}")
        release_state = {}
    if str(release_state.get("release_status", "")).startswith("published-"):
        version = str(release_state.get("version", ""))
        for relative in PUBLISHED_RELEASE_DOCS:
            text = _read_text(root, relative, errors)
            normalized = _normalized(text)
            if version and version not in text:
                errors.append(f"{relative}: published release version {version} is missing")
            if "published" not in normalized:
                errors.append(f"{relative}: published release state is not documented")
            for phrase in PUBLISHED_RELEASE_STALE_PHRASES:
                if _normalized(phrase) in normalized:
                    errors.append(f"{relative}: contains stale published-release claim: {phrase}")

    headless_doc = _read_text(root, "docs/HEADLESS_GUI.md", errors)
    headless_folded = headless_doc.casefold()
    if "py -m diptrace_mcp.headless_gui smoke" not in headless_folded:
        errors.append("docs/HEADLESS_GUI.md: source smoke command must use the module entry point")
    if "py -m diptrace_mcp.headless_gui doctor" not in headless_folded:
        errors.append("docs/HEADLESS_GUI.md: source doctor command must use the module entry point")
    if "py -m diptrace_mcp.headless_gui roundtrip" not in headless_folded:
        errors.append(
            "docs/HEADLESS_GUI.md: source roundtrip command must use the module entry point"
        )
    for obsolete_command in (
        "\ndiptrace-mcp-headless-gui --help",
        "\ndiptrace-mcp-headless-gui smoke",
        "\ndiptrace-mcp-headless-gui doctor",
        "\ndiptrace-mcp-headless-gui roundtrip",
    ):
        if obsolete_command in headless_folded:
            errors.append(
                "docs/HEADLESS_GUI.md: advertises nonexistent source console command: "
                f"{obsolete_command.strip()}"
            )

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
