#!/usr/bin/env python3
"""Build a clean-room factual inventory from project-owned XML observations.

This generator intentionally does not read PDFs, extracted documentation text,
or source-derived inventories.  It records only XML element/attribute names,
observed scalar values, and project-authored provenance for the supplied
synthetic fixtures or independently collected controlled exports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

if __package__:
    from .spec_inventory_integrity import validate_inventory
else:
    from spec_inventory_integrity import validate_inventory

INVENTORY_SCHEMA_VERSION = "diptrace-factual-inventory-v1"
DEFAULT_SOURCE_ROOT = Path("tests/fixtures")
_SOURCE_KINDS = {"synthetic_fixture", "controlled_real_export"}
_CONFIDENCES = {"synthetic", "observed"}
_DECIMAL_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_INTEGER_RE = re.compile(r"^[+-]?\d+$")


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _value_type(values: list[str]) -> str:
    if values and all(value in {"Y", "N", "y", "n", "true", "false"} for value in values):
        return "boolean"
    if values and all(_INTEGER_RE.fullmatch(value) for value in values):
        return "integer"
    if values and all(_DECIMAL_RE.fullmatch(value) for value in values):
        return "decimal"
    return "text"


def _relative_source_path(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _source_files(source: Path | Iterable[Path]) -> list[Path]:
    if isinstance(source, Path):
        candidates = sorted(source.rglob("*.xml")) if source.is_dir() else [source]
    else:
        candidates = sorted(Path(item) for item in source)
    if not candidates:
        raise FileNotFoundError(f"No XML fixture or controlled export found at {source}")
    if any(path.suffix.casefold() != ".xml" for path in candidates):
        raise ValueError("clean-room factual inventory accepts XML files only")
    return candidates


def _fixture_record(
    path: Path,
    repository_root: Path,
    metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    source = root if _local_name(root.tag) == "Source" else root
    relative = _relative_source_path(path, repository_root)
    metadata = dict(metadata or {})
    source_kind = str(metadata.get("source_kind", "synthetic_fixture"))
    if source_kind not in _SOURCE_KINDS:
        raise ValueError(f"unsupported source_kind for {relative}: {source_kind}")
    default_confidence = "observed" if source_kind == "controlled_real_export" else "synthetic"
    confidence = str(metadata.get("confidence", default_confidence))
    if confidence not in _CONFIDENCES:
        raise ValueError(f"unsupported confidence for {relative}: {confidence}")
    source_type = str(metadata.get("source_type") or source.get("Type", "")) or None
    version = str(metadata.get("diptrace_version") or source.get("Version", "")) or None
    build = str(metadata.get("diptrace_build", "")) or None
    evidence_id = str(metadata.get("evidence_id") or f"{source_kind}:{relative}")
    redistribution_basis = str(
        metadata.get(
            "redistribution_basis",
            "project-authored test design"
            if source_kind == "synthetic_fixture"
            else "controlled export pending acceptance audit",
        )
    )
    contains_third_party_design = bool(metadata.get("contains_third_party_design", False))
    if contains_third_party_design:
        raise ValueError(f"third-party design is not accepted in {relative}")
    source_record = {
        "file": relative,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "source_kind": source_kind,
        "diptrace_version": version,
        "diptrace_build": build,
        "source_type": source_type,
        "evidence_id": evidence_id,
        "confidence": confidence,
        "redistribution_basis": redistribution_basis,
        "contains_third_party_design": contains_third_party_design,
    }
    return source_record, {"root": root, "source_record": source_record}


def build_inventory(
    source: Path | Iterable[Path] = DEFAULT_SOURCE_ROOT,
    *,
    repository_root: Path | None = None,
    provenance: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic factual inventory from XML fixture observations."""

    root = (repository_root or Path(__file__).resolve().parents[1]).resolve()
    source_paths = _source_files(source)
    source_records: list[dict[str, Any]] = []
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    element_children: dict[str, set[str]] = defaultdict(set)
    element_names: set[str] = set()

    for path in source_paths:
        relative = _relative_source_path(path, root)
        metadata = (provenance or {}).get(relative) or (provenance or {}).get(path.name)
        source_record, parsed = _fixture_record(path, root, metadata)
        source_records.append(source_record)
        fixture_root: ET.Element = parsed["root"]
        for element in fixture_root.iter():
            tag = _local_name(element.tag)
            element_names.add(tag)
            for child in element:
                element_children[tag].add(_local_name(child.tag))
            for attribute, raw_value in sorted(element.attrib.items()):
                key = (tag, attribute)
                fact = observed.setdefault(
                    key,
                    {
                        "element": tag,
                        "attribute": attribute,
                        "observed_values": [],
                        "source_files": [],
                        "diptrace_versions": [],
                        "diptrace_builds": [],
                        "source_kinds": [],
                        "evidence_ids": [],
                        "confidences": [],
                    },
                )
                if raw_value not in fact["observed_values"]:
                    fact["observed_values"].append(raw_value)
                if source_record["file"] not in fact["source_files"]:
                    fact["source_files"].append(source_record["file"])
                if (
                    source_record["diptrace_version"]
                    and source_record["diptrace_version"]
                    not in fact["diptrace_versions"]
                ):
                    fact["diptrace_versions"].append(source_record["diptrace_version"])
                if source_record["diptrace_build"] and source_record["diptrace_build"] not in fact[
                    "diptrace_builds"
                ]:
                    fact["diptrace_builds"].append(source_record["diptrace_build"])
                for internal_field, source_field in (
                    ("source_kinds", "source_kind"),
                    ("evidence_ids", "evidence_id"),
                    ("confidences", "confidence"),
                ):
                    value = source_record[source_field]
                    if value not in fact[internal_field]:
                        fact[internal_field].append(value)

    source_kinds = {str(item["source_kind"]) for item in source_records}
    confidences = {str(item["confidence"]) for item in source_records}
    if len(source_kinds) != 1 or len(confidences) != 1:
        raise ValueError(
            "one inventory run must use one source_kind and one confidence; "
            "build separate inventories for synthetic and controlled observations"
        )
    inventory_source_kind = next(iter(source_kinds))

    facts: list[dict[str, Any]] = []
    for (element, attribute), fact in sorted(observed.items()):
        versions = sorted(fact.pop("diptrace_versions"))
        builds = sorted(fact.pop("diptrace_builds"))
        source_kinds_for_fact = sorted(fact.pop("source_kinds"))
        evidence_ids = sorted(fact.pop("evidence_ids"))
        confidences_for_fact = sorted(fact.pop("confidences"))
        values = sorted(fact.pop("observed_values"))
        facts.append(
            {
                "element": element,
                "attribute": attribute,
                "value_type": _value_type(values),
                "observed_values": values,
                "source_kind": source_kinds_for_fact[0],
                "source_files": sorted(fact.pop("source_files")),
                "diptrace_version": versions[0] if len(versions) == 1 else None,
                "diptrace_build": builds[0] if len(builds) == 1 else None,
                "evidence_id": evidence_ids[0]
                if len(evidence_ids) == 1
                else f"{inventory_source_kind}-inventory-v1",
                "confidence": confidences_for_fact[0],
                "notes": "Project-authored factual summary of observed XML data.",
            }
        )

    # ``elements`` is a structural index for the existing coverage reporter;
    # its fields are generated from the factual records and contain no prose
    # copied from an external specification.
    by_element: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in facts:
        by_element[fact["element"]].append(fact)
    elements: dict[str, Any] = {}
    for element in sorted(element_names):
        attributes = {
            fact["attribute"]: {
                "type": fact["value_type"],
                "observed_values": fact["observed_values"],
            }
            for fact in by_element.get(element, [])
        }
        elements[element] = {
            "attributes": attributes,
            "text_content": [],
            "children": sorted(element_children.get(element, set())),
            "source_kind": inventory_source_kind,
        }

    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "generated_by": "scripts/extract_spec_inventory.py",
        "source_policy": (
            "Project-authored factual observations only; no PDF, extracted documentation "
            "text, normative prose, or source-derived descriptions are included."
        ),
        "sources": sorted(source_records, key=lambda item: item["file"]),
        "facts": facts,
        "elements": elements,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean-room XML factual inventory")
    parser.add_argument(
        "--sources",
        default=str(DEFAULT_SOURCE_ROOT),
        help="XML fixture file or directory; only *.xml is accepted",
    )
    parser.add_argument("--out", default="reference/diptrace-xml/spec_inventory.json")
    parser.add_argument(
        "--provenance",
        type=Path,
        help=(
            "JSON metadata mapping relative XML paths to source_kind, DipTrace version/build, "
            "evidence_id, confidence and redistribution fields"
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    try:
        provenance = None
        if args.provenance is not None:
            decoded = json.loads(args.provenance.read_text(encoding="utf-8"))
            entries = decoded.get("sources") if isinstance(decoded, dict) else None
            if isinstance(entries, list):
                provenance = {
                    str(item["file"]): dict(item)
                    for item in entries
                    if isinstance(item, dict) and "file" in item
                }
            elif isinstance(entries, dict):
                provenance = {str(key): dict(value) for key, value in entries.items()}
            else:
                raise ValueError("provenance JSON must contain a sources list or object")
        inventory = build_inventory(
            Path(args.sources), repository_root=repository_root, provenance=provenance
        )
        validate_inventory(inventory, repository_root)
    except (OSError, ET.ParseError, UnicodeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    rendered = _canonical_json(inventory)
    output = Path(args.out)
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            print(f"FAIL: {output} differs from clean-room inventory", file=sys.stderr)
            return 1
        print(f"OK: {output} matches clean-room inventory")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(
        f"Wrote {output} from {len(inventory['sources'])} XML sources and "
        f"{len(inventory['facts'])} facts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
