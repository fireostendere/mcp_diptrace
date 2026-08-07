#!/usr/bin/env python3
"""Validate the consolidated skill catalog and generate its source hash manifest."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
CATALOG_PATH = SKILLS_ROOT / "catalog.json"
CAPABILITY_MAP_PATH = SKILLS_ROOT / "capability-map.json"
SHARED_SCHEMA_PATH = SKILLS_ROOT / "shared" / "result.schema.json"
MANIFEST_PATH = SKILLS_ROOT / "SOURCES.sha256"
SERVER_PATHS = (
    ROOT / "src" / "diptrace_mcp" / "server.py",
    ROOT / "src" / "diptrace_mcp" / "server_runtime.py",
)
PYPROJECT_PATH = ROOT / "pyproject.toml"

MIN_SURVIVORS = 5
MAX_SURVIVORS = 8
EXPECTED_SURVIVORS = 8
ALLOWED_MODES = {"read_only", "preview_write", "operator_assisted"}
BANNED_PACKAGE_DIRECTORIES = {"agents", "evals", "examples", "schemas"}
MIRRORS = {
    ROOT / "scripts" / "capture_diptrace_evidence.py": (
        SKILLS_ROOT
        / "diptrace-evidence-capture"
        / "scripts"
        / "capture_diptrace_evidence.py"
    ),
    ROOT / "scripts" / "ingest_fixtures.py": (
        SKILLS_ROOT / "diptrace-evidence-capture" / "scripts" / "ingest_fixtures.py"
    ),
}
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
FRONTMATTER = re.compile(r"\A---\n(?P<header>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)


class CatalogError(ValueError):
    """A deterministic skill-catalog validation error."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def registered_tools() -> set[str]:
    """Return the real FastMCP tool names without importing server runtime state."""

    tree = ast.Module(
        body=[
            node
            for path in SERVER_PATHS
            for node in ast.parse(path.read_text(encoding="utf-8")).body
        ],
        type_ignores=[],
    )
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "tool"
            ):
                names.add(node.name)
    return names


def _frontmatter(path: Path) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.fullmatch(path.read_text(encoding="utf-8"))
    if match is None:
        raise CatalogError(f"{path.relative_to(ROOT)}: invalid frontmatter framing")
    metadata: dict[str, str] = {}
    for line in match.group("header").splitlines():
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise CatalogError(f"{path.relative_to(ROOT)}: invalid frontmatter line {line!r}")
        metadata[key.strip()] = value.strip()
    if set(metadata) != {"name", "description"}:
        raise CatalogError(
            f"{path.relative_to(ROOT)}: frontmatter must contain only name and description"
        )
    return metadata, match.group("body")


def _resolve_markdown_link(source: Path, raw: str) -> Path | None:
    value = unquote(raw.strip().split(maxsplit=1)[0])
    if not value or value.startswith(("#", "/", "~", "$")) or SCHEME.match(value):
        return None
    value = value.split("#", 1)[0].split("?", 1)[0]
    if not value:
        return None
    resolved = (source.parent / value).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise CatalogError(
            f"{source.relative_to(ROOT)}: link escapes repository: {raw!r}"
        ) from exc
    return resolved


def _catalog_entries() -> list[dict[str, Any]]:
    value = load_json(CATALOG_PATH)
    if not isinstance(value, list):
        raise CatalogError("skills/catalog.json must be an array")
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise CatalogError(f"catalog entry {index} must be an object")
        required = {"slug", "title", "trigger", "mode", "capabilities"}
        if set(raw) != required:
            raise CatalogError(
                f"catalog entry {index} keys differ: {sorted(set(raw) ^ required)}"
            )
        if not all(isinstance(raw[key], str) and raw[key] for key in required - {"capabilities"}):
            raise CatalogError(f"catalog entry {index} has an empty string field")
        capabilities = raw["capabilities"]
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or not all(isinstance(item, str) and item for item in capabilities)
            or len(capabilities) != len(set(capabilities))
        ):
            raise CatalogError(f"{raw['slug']}: capabilities must be unique strings")
        entries.append(raw)
    return entries


def validate_catalog() -> list[dict[str, Any]]:
    entries = _catalog_entries()
    if not MIN_SURVIVORS <= len(entries) <= MAX_SURVIVORS:
        raise CatalogError(
            f"catalog must contain {MIN_SURVIVORS}..{MAX_SURVIVORS} survivors"
        )
    if len(entries) != EXPECTED_SURVIVORS:
        raise CatalogError(f"this consolidation must ship exactly {EXPECTED_SURVIVORS} skills")

    slugs = [entry["slug"] for entry in entries]
    triggers = [entry["trigger"] for entry in entries]
    if len(slugs) != len(set(slugs)):
        raise CatalogError("skill slugs must be unique")
    if len(triggers) != len(set(triggers)):
        raise CatalogError("skill trigger sentences must be distinct")
    if any(entry["mode"] not in ALLOWED_MODES for entry in entries):
        raise CatalogError("catalog contains an unsupported execution mode")

    expected_directories = {*slugs, "shared"}
    actual_directories = {
        path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()
    }
    if actual_directories != expected_directories:
        raise CatalogError(
            "skill directories differ from catalog: "
            f"missing={sorted(expected_directories - actual_directories)}, "
            f"extra={sorted(actual_directories - expected_directories)}"
        )

    tools = registered_tools()
    for entry in entries:
        missing = sorted(set(entry["capabilities"]) - tools)
        if missing:
            raise CatalogError(f"{entry['slug']}: unregistered capabilities: {missing}")
        package = SKILLS_ROOT / entry["slug"]
        skill_path = package / "SKILL.md"
        metadata, body = _frontmatter(skill_path)
        if metadata["name"] != entry["slug"]:
            raise CatalogError(f"{entry['slug']}: frontmatter name differs")
        if entry["trigger"] not in metadata["description"]:
            raise CatalogError(f"{entry['slug']}: distinct trigger is missing from description")
        if "../shared/result.schema.json" not in body:
            raise CatalogError(f"{entry['slug']}: shared result schema is not linked")
        if len(re.findall(r"\b\d+(?:\.\d+)?\b", body)) < 3:
            raise CatalogError(f"{entry['slug']}: quantitative operating content is missing")
        for child in package.rglob("*"):
            if child.is_dir() and child.name in BANNED_PACKAGE_DIRECTORIES:
                raise CatalogError(
                    f"{child.relative_to(ROOT)}: duplicated generated package directory is banned"
                )
            if child.is_file() and child.name == "README.md":
                raise CatalogError(f"{child.relative_to(ROOT)}: package-local README is banned")

    capability_map = load_json(CAPABILITY_MAP_PATH)
    if not isinstance(capability_map, dict):
        raise CatalogError("capability map must be an object")
    mapped = capability_map.get("runtime_tools")
    unavailable = capability_map.get("unavailable_contracts")
    if not isinstance(mapped, dict) or not isinstance(unavailable, dict):
        raise CatalogError("capability map sections are invalid")
    for key, value in mapped.items():
        if not isinstance(value, dict) or value.get("runtime_tool") not in tools:
            raise CatalogError(f"capability map target {key!r} is not a registered tool")
    for solver in ("run_ngspice_simulation", "run_openems_stripline_analysis"):
        if mapped.get(solver, {}).get("runtime_tool") != solver:
            raise CatalogError(f"{solver} must be mapped as a registered adapter")
        if solver in unavailable:
            raise CatalogError(f"{solver} is registered and cannot be marked unavailable")

    schema = load_json(SHARED_SCHEMA_PATH)
    if not isinstance(schema, dict) or schema.get("$schema") != (
        "https://json-schema.org/draft/2020-12/schema"
    ):
        raise CatalogError("shared result schema is not Draft 2020-12")

    for source in sorted(SKILLS_ROOT.rglob("*.md")):
        for match in MARKDOWN_LINK.finditer(source.read_text(encoding="utf-8")):
            resolved = _resolve_markdown_link(source, match.group(1))
            if resolved is not None and not resolved.exists():
                raise CatalogError(
                    f"{source.relative_to(ROOT)}: missing link target {match.group(1)!r}"
                )

    for maintained, mirror in MIRRORS.items():
        if maintained.read_bytes() != mirror.read_bytes():
            raise CatalogError(
                f"{mirror.relative_to(ROOT)} differs from {maintained.relative_to(ROOT)}"
            )
    return entries


def source_paths() -> list[Path]:
    """Return every file whose bytes define the delivered skill catalog."""

    paths = [
        PYPROJECT_PATH,
        Path(__file__).resolve(),
        *MIRRORS.keys(),
    ]
    paths.extend(
        path
        for path in SKILLS_ROOT.rglob("*")
        if path.is_file() and path != MANIFEST_PATH and "__pycache__" not in path.parts
    )
    unique = sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix())
    for path in unique:
        if path.is_symlink():
            raise CatalogError(f"skill source cannot be a symlink: {path.relative_to(ROOT)}")
    return unique


def render_manifest() -> str:
    lines = []
    for path in source_paths():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    return "\n".join(lines) + "\n"


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate consolidated DipTrace skills and generate SOURCES.sha256"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed source manifest is stale",
    )
    args = parser.parse_args(arguments)

    try:
        entries = validate_catalog()
        expected = render_manifest()
    except (CatalogError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.check:
        actual = MANIFEST_PATH.read_text(encoding="ascii") if MANIFEST_PATH.exists() else ""
        if actual != expected:
            print(f"FAIL: {MANIFEST_PATH.relative_to(ROOT)} is stale", file=sys.stderr)
            return 1
        print(
            f"OK: {len(entries)} skills, shared schema, links, capabilities, mirrors, and hashes"
        )
        return 0

    MANIFEST_PATH.write_text(expected, encoding="ascii")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)} for {len(entries)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
