#!/usr/bin/env python3
"""Report format coverage: compare spec inventory against code.

Usage:
    python scripts/report_format_coverage.py

With --check, verifies the committed docs/FORMAT_COVERAGE.md matches a fresh run.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__:
    from .spec_inventory_integrity import validate_inventory
else:
    from spec_inventory_integrity import validate_inventory

_READER_MODULES = frozenset(
    {
        "adapters.py",
        "advanced_review.py",
        "library_adapters.py",
        "synchronization.py",
    }
)
_WRITER_MODULES = frozenset(
    {"routing_compiler.py", "scaffolding.py", "semantic_compiler.py"}
)
_READER_ELEMENT_METHODS = frozenset(
    {"find", "findall", "findtext", "iter", "iterfind"}
)
_WRITER_ELEMENT_HELPERS = frozenset({"_named"})
_XML_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]*$")
_PATH_PREDICATE = re.compile(r"\[[^\]]*\]")


def _load_inventory(inventory_path: Path) -> dict[str, Any]:
    """Load the spec inventory JSON."""
    with open(inventory_path, encoding="utf-8") as f:
        return json.load(f)


def _find_source_files(src_dir: Path) -> list[Path]:
    """Find all Python source files in the src directory."""
    return sorted(src_dir.rglob("*.py"))


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _xml_path_names(value: str) -> list[str]:
    clean = _PATH_PREDICATE.sub("", value)
    result: list[str] = []
    for part in clean.split("/"):
        name = part.strip()
        if name in {"", ".", "..", "*"} or name.startswith("@"):
            continue
        if _XML_NAME.fullmatch(name):
            result.append(name)
    return result


def _split_xml_path(value: str) -> set[str]:
    """Return literal XML element names addressed by an ElementTree path."""
    return set(_xml_path_names(value))


def _dict_string_keys(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    return {
        value
        for key in node.keys
        if (value := _literal_string(key)) is not None
    }


@dataclass
class UsageFacts:
    read_elements: set[str] = field(default_factory=set)
    read_attributes: set[str] = field(default_factory=set)
    written_elements: set[str] = field(default_factory=set)
    written_attributes: set[str] = field(default_factory=set)
    all_literals: set[str] = field(default_factory=set)
    call_argument_literals: set[str] = field(default_factory=set)

    @property
    def bare_literals(self) -> set[str]:
        return self.all_literals - self.call_argument_literals


class XmlUsageVisitor(ast.NodeVisitor):
    """Collect literal XML names from calls, keeping prose/literals separate."""

    def __init__(self) -> None:
        self.facts = UsageFacts()

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.facts.all_literals.add(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        for argument in [*node.args, *(item.value for item in node.keywords)]:
            for child in ast.walk(argument):
                value = _literal_string(child)
                if value is not None:
                    self.facts.call_argument_literals.add(value)

        qualified = _qualified_name(node.func)
        method = node.func.attr if isinstance(node.func, ast.Attribute) else ""

        if (
            isinstance(node.func, ast.Attribute)
            and method in _READER_ELEMENT_METHODS
            and node.args
        ):
            path = _literal_string(node.args[0])
            if path is not None:
                self.facts.read_elements.update(_split_xml_path(path))
        elif isinstance(node.func, ast.Attribute) and method == "get" and node.args:
            attribute = _literal_string(node.args[0])
            if attribute is not None and _XML_NAME.fullmatch(attribute):
                self.facts.read_attributes.add(attribute)

        tag_argument: ast.AST | None = None
        attribute_arguments: list[ast.AST] = []
        if qualified in {"ET.Element", "Element"} and node.args:
            tag_argument = node.args[0]
            attribute_arguments = list(node.args[1:])
        elif qualified in {"ET.SubElement", "SubElement"} and len(node.args) >= 2:
            tag_argument = node.args[1]
            attribute_arguments = list(node.args[2:])
        elif qualified in _WRITER_ELEMENT_HELPERS and node.args:
            tag_argument = node.args[0]

        tag = _literal_string(tag_argument)
        if tag is not None and _XML_NAME.fullmatch(tag):
            self.facts.written_elements.add(tag)
        for argument in attribute_arguments:
            self.facts.written_attributes.update(_dict_string_keys(argument))
        for keyword in node.keywords:
            if keyword.arg == "attrib":
                self.facts.written_attributes.update(_dict_string_keys(keyword.value))

        if isinstance(node.func, ast.Attribute) and method == "set" and node.args:
            attribute = _literal_string(node.args[0])
            if attribute is not None and _XML_NAME.fullmatch(attribute):
                self.facts.written_attributes.add(attribute)

        self.generic_visit(node)


def _scan_source(source: str, *, filename: str = "<memory>") -> UsageFacts:
    tree = ast.parse(source, filename=filename)
    visitor = XmlUsageVisitor()
    visitor.visit(tree)
    return visitor.facts


def _scan_file(path: Path) -> UsageFacts:
    return _scan_source(path.read_text(encoding="utf-8"), filename=str(path))


def _partition_names(
    names: set[str],
    read: set[str],
    written: set[str],
    mentioned: set[str],
) -> dict[str, list[str]]:
    normalized = names & read
    written_only = (names & written) - normalized
    mentioned_only = (names & mentioned) - normalized - written_only
    passthrough = names - normalized - written_only - mentioned_only
    classes = {
        "normalized": sorted(normalized),
        "written": sorted(written_only),
        "mentioned_only": sorted(mentioned_only),
        "passthrough": sorted(passthrough),
    }
    class_sets = [set(values) for values in classes.values()]
    assert set().union(*class_sets) == names
    assert sum(len(values) for values in class_sets) == len(names)
    return classes


@dataclass(frozen=True, order=True)
class ContainerRewrite:
    module: str
    function: str
    container: str
    removed_children: tuple[str, ...] | None


def _assignment_container_tags(function: ast.FunctionDef) -> dict[str, str]:
    tags: dict[str, str] = {}
    for node in ast.walk(function):
        target: ast.AST | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        qualified = _qualified_name(value.func)
        method = value.func.attr if isinstance(value.func, ast.Attribute) else ""
        tag: str | None = None
        if method in {"find", "findall"} and value.args:
            path = _literal_string(value.args[0])
            names = _xml_path_names(path) if path is not None else []
            if names:
                tag = names[-1]
        elif qualified in {"ET.Element", "Element"} and value.args:
            tag = _literal_string(value.args[0])
        elif qualified in {"ET.SubElement", "SubElement"} and len(value.args) >= 2:
            tag = _literal_string(value.args[1])
        if tag is not None and _XML_NAME.fullmatch(tag):
            tags[target.id] = tag
    return tags


def _loop_removal(
    function: ast.FunctionDef,
    loop: ast.For,
) -> tuple[str, tuple[str, ...] | None] | None:
    if not isinstance(loop.target, ast.Name) or not isinstance(loop.iter, ast.Call):
        return None
    if _qualified_name(loop.iter.func) != "list" or len(loop.iter.args) != 1:
        return None
    selected = loop.iter.args[0]
    container_variable: str | None = None
    removed_children: tuple[str, ...] | None = None
    if isinstance(selected, ast.Name):
        container_variable = selected.id
    elif (
        isinstance(selected, ast.Call)
        and isinstance(selected.func, ast.Attribute)
        and selected.func.attr == "findall"
        and isinstance(selected.func.value, ast.Name)
        and selected.args
    ):
        container_variable = selected.func.value.id
        path = _literal_string(selected.args[0])
        if path is None:
            return None
        removed_children = tuple(sorted(_split_xml_path(path)))
    if container_variable is None:
        return None

    removes_target = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "remove"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == container_variable
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == loop.target.id
        for node in ast.walk(loop)
    )
    if not removes_target:
        return None
    tags = _assignment_container_tags(function)
    container = tags.get(container_variable)
    if container is None:
        return None
    return container, removed_children


def _container_rewrites(src_dir: Path) -> list[ContainerRewrite]:
    rewrites: set[ContainerRewrite] = set()
    for path in _find_source_files(src_dir):
        if path.name not in _WRITER_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in [
            node for node in tree.body if isinstance(node, ast.FunctionDef)
        ]:
            for loop in [node for node in ast.walk(function) if isinstance(node, ast.For)]:
                removal = _loop_removal(function, loop)
                if removal is None:
                    continue
                container, children = removal
                rewrites.add(
                    ContainerRewrite(
                        module=path.name,
                        function=function.name,
                        container=container,
                        removed_children=children,
                    )
                )
    return sorted(rewrites)


def compute_coverage(
    inventory: dict[str, Any],
    src_dir: Path,
) -> dict[str, Any]:
    """Compute format coverage by comparing spec inventory against source code."""
    elements = inventory.get("elements", {})
    read_elements: set[str] = set()
    read_attributes: set[str] = set()
    written_elements: set[str] = set()
    written_attributes: set[str] = set()
    mentioned: set[str] = set()

    for path in _find_source_files(src_dir):
        if path.name not in _READER_MODULES | _WRITER_MODULES:
            continue
        facts = _scan_file(path)
        mentioned.update(facts.bare_literals)
        if path.name in _READER_MODULES:
            read_elements.update(facts.read_elements)
            read_attributes.update(facts.read_attributes)
        if path.name in _WRITER_MODULES:
            written_elements.update(facts.written_elements)
            written_attributes.update(facts.written_attributes)

    classes = _partition_names(
        set(elements),
        read_elements,
        written_elements,
        mentioned,
    )
    element_attr_coverage: dict[str, dict[str, str]] = {}
    for elem_name, elem_data in sorted(elements.items()):
        attribute_names = set(elem_data.get("attributes", {}))
        attribute_classes = _partition_names(
            attribute_names,
            read_attributes,
            written_attributes,
            mentioned,
        )
        attr_coverage: dict[str, str] = {}
        for status, values in attribute_classes.items():
            attr_coverage.update(dict.fromkeys(values, status))
        element_attr_coverage[elem_name] = attr_coverage

    total = len(elements)
    norm_count = len(classes["normalized"])
    written_count = len(classes["written"])
    mentioned_count = len(classes["mentioned_only"])
    pass_count = len(classes["passthrough"])
    coverage_pct = ((norm_count + written_count) / total * 100) if total > 0 else 0
    attribute_count = sum(
        len(element.get("attributes", {})) for element in elements.values()
    )
    text_content_count = sum(
        len(element.get("text_content", [])) for element in elements.values()
    )
    omitted_when_count = sum(
        attribute.get("omitted_when") is not None
        for element in elements.values()
        for attribute in element.get("attributes", {}).values()
    )
    parent_count = sum(
        bool(element.get("children")) for element in elements.values()
    )
    child_edge_count = sum(
        len(element.get("children", [])) for element in elements.values()
    )

    return {
        "summary": {
            "total_elements": total,
            "total_attributes": attribute_count,
            "text_content_definitions": text_content_count,
            "explicit_omission_clauses": omitted_when_count,
            "parents_with_children": parent_count,
            "child_edges": child_edge_count,
            "normalized": norm_count,
            "written": written_count,
            "mentioned_only": mentioned_count,
            "passthrough": pass_count,
            "coverage_percent": round(coverage_pct, 1),
        },
        "normalized_elements": classes["normalized"],
        "written_elements": classes["written"],
        "mentioned_only_elements": classes["mentioned_only"],
        "passthrough_elements": classes["passthrough"],
        "attribute_coverage": element_attr_coverage,
        "container_rewrites": _container_rewrites(src_dir),
    }


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
        f"| XML attributes in spec | {summary['total_attributes']} |",
        f"| Element text-content definitions | {summary['text_content_definitions']} |",
        f"| Explicit attribute omission clauses | {summary['explicit_omission_clauses']} |",
        (
            "| Documented parent/child relationships | "
            f"{summary['child_edges']} across {summary['parents_with_children']} parents |"
        ),
        f"| Normalized (reader produces typed field) | {summary['normalized']} |",
        f"| Written only (writer can create/modify) | {summary['written']} |",
        f"| Mentioned only (literal, not an XML call) | {summary['mentioned_only']} |",
        f"| Passthrough (unknown XML, kept byte-for-byte) | {summary['passthrough']} |",
        f"| **Coverage** | **{summary['coverage_percent']}%** |",
        "",
        "## Inventory Provenance",
        "",
        "The inventory is generated from the three official PDFs named in",
        "[`spec_inventory.json`](../reference/diptrace-xml/spec_inventory.json). The PDFs",
        "are not redistributed. Canonical per-page text extracted with the pinned",
        "`pypdf==6.14.2` is committed under",
        "[`reference/diptrace-xml/extracted_text/`](../reference/diptrace-xml/extracted_text/),",
        "with both PDF and intermediate SHA-256 values recorded in the inventory.",
        "CI regenerates the inventory from that offline intermediate before computing this",
        "report. A maintainer with the original PDFs can independently re-extract the same",
        "intermediate and compare it byte-for-byte.",
        "",
        "Only literal XML examples introduce element names. Scalar element content is",
        "recorded separately from attributes, and prose that merely mentions `<Element>`",
        "does not change parser ownership. The public PDFs contain four explicit",
        "attribute-level absence clauses; no additional `omitted_when` conditions are",
        "inferred.",
        "",
        "## Normalized Elements",
        "",
    ]

    for elem in coverage["normalized_elements"]:
        lines.append(f"- `{elem}`")

    lines.extend([
        "",
        "## Written-Only Elements",
        "",
    ])

    for elem in coverage["written_elements"]:
        lines.append(f"- `{elem}`")

    lines.extend([
        "",
        "## Mentioned-Only Elements",
        "",
    ])

    for elem in coverage["mentioned_only_elements"]:
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
        "Passthrough elements survive byte-for-byte **only** while no operation removes or",
        "regenerates their parent subtree. The list below is derived from writer call sites",
        "that iterate existing children and remove them. A value of `none` means no child",
        "currently classified as passthrough was named by the inventory or removal path; it",
        "does not make undocumented children safe.",
        "",
    ])

    passthrough = set(coverage["passthrough_elements"])
    elements = inventory.get("elements", {})
    for rewrite in coverage["container_rewrites"]:
        if rewrite.removed_children is None:
            known_children = tuple(
                sorted(elements.get(rewrite.container, {}).get("children", []))
            )
            rendered = ", ".join(f"`<{name}>`" for name in known_children) or "unavailable"
            action = (
                f"clears all children of `<{rewrite.container}>` "
                f"(inventory children: {rendered})"
            )
        else:
            known_children = rewrite.removed_children
            rendered = ", ".join(f"`<{name}>`" for name in known_children) or "unknown"
            action = f"may remove {rendered} from `<{rewrite.container}>`"
        at_risk = sorted(set(known_children) & passthrough)
        rendered_risk = ", ".join(f"`{name}`" for name in at_risk) or "none"
        lines.append(
            f"- `{rewrite.module}::{rewrite.function}` {action}; "
            f"known passthrough children: {rendered_risk}."
        )

    lines.extend(
        [
            "",
            "Any operation listed above can discard matching passthrough children rather than",
            "preserve their original bytes. Unlisted dynamic removal sites remain unavailable",
            "to this static detector and must not be assumed safe.",
            "",
        ]
    )

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

    try:
        inventory = _load_inventory(inventory_path)
        validate_inventory(
            inventory,
            repository_root=Path(__file__).resolve().parents[1],
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: invalid specification inventory: {exc}", file=sys.stderr)
        return 1
    coverage = compute_coverage(inventory, src_dir)
    report_md = _format_coverage_markdown(coverage, inventory)

    if args.check:
        if not out_path.exists():
            print(f"FAIL: {out_path} does not exist", file=sys.stderr)
            return 1
        existing = out_path.read_text(encoding="utf-8")
        if existing != report_md:
            print(f"FAIL: {out_path} differs from fresh computation", file=sys.stderr)
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
    print(
        f"Coverage: {s['coverage_percent']}% ({s['normalized']} normalized + "
        f"{s['written']} written / {s['total_elements']} total; "
        f"{s['mentioned_only']} mentioned only)"
    )
    print(f"Written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
