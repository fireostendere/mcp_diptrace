#!/usr/bin/env python3
"""Report format coverage: compare spec inventory against code.

Usage:
    python scripts/report_format_coverage.py

With --check, verifies the committed docs/FORMAT_COVERAGE.md matches a fresh run.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


def _load_inventory(inventory_path: Path) -> dict[str, Any]:
    """Load the spec inventory JSON."""
    with open(inventory_path, encoding="utf-8") as f:
        return json.load(f)


def _find_source_files(src_dir: Path) -> list[Path]:
    """Find all Python source files in the src directory."""
    return sorted(src_dir.rglob("*.py"))


def _extract_string_literals_from_file(filepath: Path) -> set[str]:
    """Extract all string literals from a Python file using AST."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return set()

    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
    return strings


def _check_element_in_source(
    element_name: str,
    all_strings: dict[str, set[str]],
) -> tuple[bool, bool]:
    """Check if an element name appears as a string literal in reader or writer code.

    Returns (is_normalized, is_written).
    """
    # Reader modules (normalize/parse XML into domain objects)
    reader_modules = {"adapters.py", "library_adapters.py", "synchronization.py"}
    # Writer modules (produce XML from domain objects)
    writer_modules = {"semantic_compiler.py", "routing_compiler.py", "scaffolding.py"}

    is_normalized = False
    is_written = False

    for filename, strings in all_strings.items():
        basename = filename.split("/")[-1]
        if basename in reader_modules and element_name in strings:
            is_normalized = True
        if basename in writer_modules and element_name in strings:
            is_written = True

    return is_normalized, is_written


def _check_attribute_in_source(
    element_name: str,
    attr_name: str,
    all_strings: dict[str, set[str]],
) -> tuple[bool, bool]:
    """Check if an attribute name appears as a string literal in reader or writer code.

    Returns (is_normalized, is_written).
    """
    reader_modules = {"adapters.py", "library_adapters.py", "synchronization.py"}
    writer_modules = {"semantic_compiler.py", "routing_compiler.py", "scaffolding.py"}

    is_normalized = False
    is_written = False

    for filename, strings in all_strings.items():
        basename = filename.split("/")[-1]
        if basename in reader_modules and attr_name in strings:
            is_normalized = True
        if basename in writer_modules and attr_name in strings:
            is_written = True

    return is_normalized, is_written


def compute_coverage(
    inventory: dict[str, Any],
    src_dir: Path,
) -> dict[str, Any]:
    """Compute format coverage by comparing spec inventory against source code."""
    source_files = _find_source_files(src_dir)

    # Extract all string literals from each file
    all_strings: dict[str, set[str]] = {}
    for filepath in source_files:
        strings = _extract_string_literals_from_file(filepath)
        all_strings[str(filepath)] = strings

    elements = inventory.get("elements", {})

    # Classify each element
    normalized_elements: list[str] = []
    written_elements: list[str] = []
    passthrough_elements: list[str] = []

    # Also track attribute-level coverage
    element_attr_coverage: dict[str, dict[str, str]] = {}

    for elem_name, elem_data in sorted(elements.items()):
        is_norm, is_written = _check_element_in_source(elem_name, all_strings)

        if is_norm:
            normalized_elements.append(elem_name)
        elif is_written:
            written_elements.append(elem_name)
        else:
            passthrough_elements.append(elem_name)

        # Check attributes
        attr_coverage: dict[str, str] = {}
        for attr_name in elem_data.get("attributes", {}):
            a_norm, a_written = _check_attribute_in_source(elem_name, attr_name, all_strings)
            if a_norm:
                attr_coverage[attr_name] = "normalized"
            elif a_written:
                attr_coverage[attr_name] = "written"
            else:
                attr_coverage[attr_name] = "passthrough"
        element_attr_coverage[elem_name] = attr_coverage

    total = len(elements)
    norm_count = len(normalized_elements)
    written_count = len(written_elements)
    pass_count = len(passthrough_elements)

    coverage_pct = ((norm_count + written_count) / total * 100) if total > 0 else 0

    result = {
        "summary": {
            "total_elements": total,
            "normalized": norm_count,
            "written": written_count,
            "passthrough": pass_count,
            "coverage_percent": round(coverage_pct, 1),
        },
        "normalized_elements": normalized_elements,
        "written_elements": written_elements,
        "passthrough_elements": passthrough_elements,
        "attribute_coverage": element_attr_coverage,
    }

    return result


def _format_coverage_markdown(
    coverage: dict[str, Any],
    inventory: dict[str, Any],
) -> str:
    """Format coverage report as Markdown."""
    summary = coverage["summary"]
    lines = [
        "# DipTrace XML Format Coverage",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total elements in spec | {summary['total_elements']} |",
        f"| Normalized (reader produces typed field) | {summary['normalized']} |",
        f"| Written (writer can create/modify) | {summary['written']} |",
        f"| Passthrough (unknown XML, kept byte-for-byte) | {summary['passthrough']} |",
        f"| **Coverage** | **{summary['coverage_percent']}%** |",
        "",
        "## Normalized Elements",
        "",
    ]

    for elem in coverage["normalized_elements"]:
        lines.append(f"- `{elem}`")

    lines.extend([
        "",
        "## Written Elements",
        "",
    ])

    for elem in coverage["written_elements"]:
        lines.append(f"- `{elem}`")

    lines.extend([
        "",
        "## Passthrough Elements",
        "",
    ])

    for elem in coverage["passthrough_elements"]:
        lines.append(f"- `{elem}`")

    lines.extend([
        "",
        "## What Passthrough Means",
        "",
        "Passthrough elements survive byte-for-byte **only** while no operation regenerates",
        "their parent subtree. The following operations regenerate whole subtrees and will",
        "destroy any passthrough data within them:",
        "",
        "- `routing_compiler.py` `_write_points` — regenerates trace point lists",
        "- Ratlines rewrite — regenerates the entire `<Ratlines>` section",
        "- Copper pour refill (if implemented) — regenerates `<CopperPour>` content",
        "",
        "Any edit to a passthrough element's parent container that triggers a full rewrite",
        "will silently lose the passthrough data. This is the expected behaviour: the tool",
        "only preserves what it understands.",
        "",
    ])

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report DipTrace XML format coverage")
    parser.add_argument("--inventory", default="reference/diptrace-xml/spec_inventory.json",
                        help="Path to spec inventory JSON")
    parser.add_argument("--src", default="src/diptrace_mcp",
                        help="Path to source code directory")
    parser.add_argument("--out", default="docs/FORMAT_COVERAGE.md",
                        help="Output Markdown path")
    parser.add_argument("--check", action="store_true",
                        help="Verify committed file matches fresh computation")
    args = parser.parse_args()

    inventory_path = Path(args.inventory)
    src_dir = Path(args.src)
    out_path = Path(args.out)

    if not inventory_path.exists():
        print(f"FAIL: {inventory_path} not found. Run extract_spec_inventory.py first.",
              file=sys.stderr)
        return 1

    inventory = _load_inventory(inventory_path)
    coverage = compute_coverage(inventory, src_dir)
    report_md = _format_coverage_markdown(coverage, inventory)

    if args.check:
        if not out_path.exists():
            print(f"FAIL: {out_path} does not exist", file=sys.stderr)
            return 1
        existing = out_path.read_text(encoding="utf-8")
        if existing != report_md:
            print(f"FAIL: {out_path} differs from fresh computation", file=sys.stderr)
            # Show summary diff
            import difflib
            diff = list(difflib.unified_diff(
                existing.splitlines(), report_md.splitlines(),
                fromfile=str(out_path), tofile="fresh computation",
                lineterm="",
            ))
            for line in diff[:30]:
                print(f"  {line}", file=sys.stderr)
            return 1
        print(f"OK: {out_path} matches fresh computation")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")

    s = coverage["summary"]
    print(f"Coverage: {s['coverage_percent']}% ({s['normalized']} normalized + "
          f"{s['written']} written / {s['total_elements']} total)")
    print(f"Written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
