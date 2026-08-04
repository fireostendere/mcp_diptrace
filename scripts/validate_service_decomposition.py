#!/usr/bin/env python3
"""Validate the safety classifications in SERVICE_DECOMPOSITION.md.

The inventory is a review artifact, so this check derives conditional write
capability from the current Facade signatures and keeps an explicit list for
state-changing methods that do not expose ``dry_run``.  A write-capable method
must never be classified as read-only or as having no side effects.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "src" / "diptrace_mcp" / "service.py"
INVENTORY_PATH = ROOT / "docs" / "SERVICE_DECOMPOSITION.md"

# These methods mutate stores, provenance, jobs, sessions, or documents even
# though their public signatures do not expose the common ``dry_run`` switch.
ALWAYS_WRITE_CAPABLE = frozenset(
    {
        "set_workflow_prompt_names",
        "invalidate_document_trust_after_write",
        "group_bom",
        "record_roundtrip_evidence",
        "begin_transaction",
        "stage_operations",
        "commit_transaction",
        "rollback_transaction",
        "run_external_autorouter",
        "run_ngspice_simulation",
        "run_openems_stripline_analysis",
        "cancel_job",
        "apply_component_placement_plan",
        "apply_silkscreen_plan",
        "finish_live_session",
        "abandon_live_session",
    }
)


def _all_methods() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DipTraceService"
    )
    return {
        node.name: node
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _public_methods() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        name: method
        for name, method in _all_methods().items()
        if not name.startswith("_")
    }


def _write_capable_methods() -> set[str]:
    result = set(ALWAYS_WRITE_CAPABLE)
    for name, method in _public_methods().items():
        parameters = [
            *method.args.posonlyargs,
            *method.args.args,
            *method.args.kwonlyargs,
        ]
        if any(parameter.arg == "dry_run" for parameter in parameters):
            result.add(name)
    return result


def _inventory_rows() -> dict[str, tuple[str, str]]:
    rows: dict[str, tuple[str, str]] = {}
    for _line_number, line in enumerate(
        INVENTORY_PATH.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.startswith("| `"):
            continue
        cells = line.split("|")
        if len(cells) < 18:
            continue
        name = cells[1].strip(" `")
        rows[name] = (cells[5].strip(), cells[9].strip())
    return rows


def validate_inventory() -> list[str]:
    all_methods = _all_methods()
    rows = _inventory_rows()
    errors: list[str] = []

    missing = sorted(set(all_methods) - set(rows))
    extra = sorted(set(rows) - set(all_methods))
    if missing:
        errors.append(f"inventory is missing methods: {missing}")
    if extra:
        errors.append(f"inventory contains unknown methods: {extra}")

    write_capable = _write_capable_methods()
    for name in sorted(write_capable):
        if name not in rows:
            continue
        read_mutate, side_effects = rows[name]
        if read_mutate.startswith("R"):
            errors.append(
                f"write-capable method {name} is classified {read_mutate!r}, "
                "but must be marked M"
            )
        if side_effects.lower().startswith("none;"):
            errors.append(
                f"write-capable method {name} has a no-side-effect inventory entry"
            )

    required_side_effects = {
        "invalidate_document_trust_after_write": "provenance sidecar",
        "clear_panelization": "semantic write",
        "route_connection": "semantic write",
    }
    for name, phrase in required_side_effects.items():
        if name not in rows:
            continue
        if phrase not in rows[name][1].lower():
            errors.append(
                f"{name} side-effect entry must mention {phrase!r}; "
                f"got {rows[name][1]!r}"
            )

    if len(rows) != len(all_methods):
        errors.append(
            f"inventory row count mismatch: expected {len(all_methods)}, "
            f"got {len(rows)}"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args(argv)
    errors = validate_inventory()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        "OK: decomposition inventory covers "
                f"{len(_all_methods())} methods; "
        f"{len(_write_capable_methods())} write-capable methods are non-read-only"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
