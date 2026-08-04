#!/usr/bin/env python3
"""Validate safety classifications in ``SERVICE_DECOMPOSITION.md``.

The inventory is a review artifact, so this check combines the Facade
signatures with a conservative AST audit of delegated domain implementations.
Persistent-state writers are classified as ``M``; there is no ambiguous third
classification.  A write-capable method must never be classified as read-only
or as having no side effects.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import TypeAlias

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "src" / "diptrace_mcp" / "service.py"
INVENTORY_PATH = ROOT / "docs" / "SERVICE_DECOMPOSITION.md"

# These methods mutate stores, provenance, jobs, sessions, or documents even
# though their public signatures do not expose the common ``dry_run`` switch.
ALWAYS_WRITE_CAPABLE = frozenset(
    {
        "set_workflow_prompt_names",
        "_atomic_write_bytes",
        "_write_provenance_sidecar_callback",
        "_invalidate_document_trust_after_write_callback",
        "_run_semantic_write",
        "_run_semantic_operations",
        "invalidate_document_trust_after_write",
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

MethodNode: TypeAlias = ast.FunctionDef | ast.AsyncFunctionDef

PERSISTENT_CALL_NAMES = frozenset(
    {
        "abandon_active",
        "atomic_write_bytes",
        "cancel",
        "create",
        "create_report",
        "delete",
        "finish",
        "guard_working_mutation",
        "mark_committed",
        "mark_failed",
        "mark_rolled_back",
        "mkdir",
        "mutate_working",
        "remove",
        "start_freerouting",
        "start_ngspice",
        "start_openems",
        "store",
        "store_backup",
        "store_preview",
        "store_provenance_backup",
        "store_snapshot",
        "unlink",
        "update",
        "write_bytes",
        "write_text",
    }
)
FILESYSTEM_CALL_NAMES = frozenset({"mkdir", "unlink", "write_bytes", "write_text"})
PERSISTENT_FUNCTION_PREFIXES = (
    "atomic_write",
    "create_",
    "record_",
    "save_",
    "store_",
    "update_",
    "write_",
)
PURE_FUNCTION_NAMES = frozenset(
    {
        "_apply_bounded_semantic_operations",
        "apply_semantic_operations",
    }
)


def _all_methods() -> dict[str, MethodNode]:
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


def _public_methods() -> dict[str, MethodNode]:
    return {
        name: method
        for name, method in _all_methods().items()
        if not name.startswith("_")
    }


def _facade_service_classes() -> dict[str, str]:
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    service = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DipTraceService"
    )
    initializer = next(
        node
        for node in service.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "__init__"
    )
    result: dict[str, str] = {}
    for node in ast.walk(initializer):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr.endswith("_service")
            ):
                result[target.attr] = node.value.func.id
    return result


def _delegated_service_targets() -> dict[str, tuple[str, str]]:
    """Return public Facade methods and their constructed service class targets."""

    service_classes = _facade_service_classes()
    result: dict[str, tuple[str, str]] = {}
    for name, method in _public_methods().items():
        body = list(method.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            continue
        returned = body[0].value
        if not isinstance(returned, ast.Call) or not isinstance(returned.func, ast.Attribute):
            continue
        service = returned.func.value
        if not (
            isinstance(service, ast.Attribute)
            and isinstance(service.value, ast.Name)
            and service.value.id == "self"
            and service.attr in service_classes
        ):
            continue
        result[name] = (service_classes[service.attr], returned.func.attr)
    return result


def _domain_methods() -> dict[tuple[str, str], MethodNode]:
    result: dict[tuple[str, str], MethodNode] = {}
    for path in sorted((ROOT / "src" / "diptrace_mcp" / "services").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[(node.name, member.name)] = member
    return result


def _has_persistent_call(
    method: MethodNode,
    class_methods: dict[str, MethodNode],
    seen: set[str],
) -> bool:
    if method.name in seen:
        return False
    seen.add(method.name)
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Attribute):
            receiver_is_self_owned = any(
                isinstance(candidate, ast.Name) and candidate.id == "self"
                for candidate in ast.walk(function.value)
            )
            if (
                function.attr in FILESYSTEM_CALL_NAMES
                or (receiver_is_self_owned and function.attr in PERSISTENT_CALL_NAMES)
                or (
                    receiver_is_self_owned
                    and any(
                        function.attr.startswith(prefix)
                        for prefix in PERSISTENT_FUNCTION_PREFIXES
                    )
                )
            ):
                return True
            if (
                isinstance(function.value, ast.Name)
                and function.value.id == "self"
                and function.attr in class_methods
                and _has_persistent_call(class_methods[function.attr], class_methods, seen)
            ):
                return True
        elif isinstance(function, ast.Name):
            if function.id in PURE_FUNCTION_NAMES:
                continue
            if function.id in PERSISTENT_CALL_NAMES or any(
                function.id.startswith(prefix) for prefix in PERSISTENT_FUNCTION_PREFIXES
            ):
                return True
    return False


def _delegated_persistent_methods() -> set[str]:
    methods = _domain_methods()
    targets = _delegated_service_targets()
    result: set[str] = set()
    for facade_name, (class_name, target_name) in targets.items():
        target = methods.get((class_name, target_name))
        if target is None:
            continue
        class_methods = {
            name: method
            for (candidate_class, name), method in methods.items()
            if candidate_class == class_name
        }
        if _has_persistent_call(target, class_methods, set()):
            result.add(facade_name)
    return result


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
    result.update(_delegated_persistent_methods())
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
        if read_mutate != "M":
            errors.append(
                f"write-capable method {name} is classified {read_mutate!r}, "
                "but must be marked M"
            )
        if side_effects.lower().startswith("none;"):
            errors.append(
                f"write-capable method {name} has a no-side-effect inventory entry"
            )

    persistent_descriptions = (
        "creates ",
        "persists",
        "stores ",
        "updates ",
        "writes ",
        "record.json",
        "planstore",
        "exportstore",
        "findingstore",
        "transactionstore",
        "provenance sidecar",
        "semantic write",
        "session state",
    )
    for name, (read_mutate, side_effects) in rows.items():
        lowered = side_effects.lower()
        if read_mutate not in {"R", "M"}:
            errors.append(
                f"{name} has unsupported R/M classification {read_mutate!r}; "
                "use R for pure reads or M for any persistent-state mutation"
            )
        if read_mutate == "R" and any(
            marker in lowered for marker in persistent_descriptions
        ):
            errors.append(
                f"{name} is classified R but its side-effect description indicates "
                f"persistent state: {side_effects!r}"
            )
        if read_mutate == "M" and lowered.startswith("none;"):
            errors.append(f"{name} is classified M but has no side effects")

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
