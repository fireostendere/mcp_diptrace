#!/usr/bin/env python3
"""Check the complete public DipTraceService facade contract.

The committed manifest is generated from the exact base revision and records
every public method signature.  It also records every public facade method that
now delegates to a domain service, leaving an explicit allow-list for the
small set of methods that intentionally remain facade-owned.

Examples:

    python scripts/check_service_facade_contract.py --check
    python scripts/check_service_facade_contract.py --generate \
        --base-sha 1e1e8b7402533297795207ce2452b85eaea2e36c
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RELATIVE_PATH = Path("src/diptrace_mcp/service.py")
MANIFEST_PATH = ROOT / "reference" / "service-facade-contract.json"


def _class_node(source: str) -> ast.ClassDef:
    tree = ast.parse(source, filename=str(SOURCE_RELATIVE_PATH))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "DipTraceService":
            return node
    raise ValueError("DipTraceService class was not found")


def _unparse(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None


def _parameter_specs(method: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, object]]:
    arguments = method.args
    positional = [*arguments.posonlyargs, *arguments.args]
    positional_defaults = [None] * (len(positional) - len(arguments.defaults))
    positional_defaults.extend(arguments.defaults)

    specs: list[dict[str, object]] = []
    for argument, default in zip(positional, positional_defaults, strict=True):
        kind = "positional_only" if argument in arguments.posonlyargs else "positional_or_keyword"
        specs.append(
            {
                "name": argument.arg,
                "kind": kind,
                "annotation": _unparse(argument.annotation),
                "has_default": default is not None,
                "default": _unparse(default),
            }
        )

    if arguments.vararg is not None:
        specs.append(
            {
                "name": arguments.vararg.arg,
                "kind": "var_positional",
                "annotation": _unparse(arguments.vararg.annotation),
                "has_default": False,
                "default": None,
            }
        )

    for argument, default in zip(
        arguments.kwonlyargs, arguments.kw_defaults, strict=True
    ):
        specs.append(
            {
                "name": argument.arg,
                "kind": "keyword_only",
                "annotation": _unparse(argument.annotation),
                "has_default": default is not None,
                "default": _unparse(default),
            }
        )

    if arguments.kwarg is not None:
        specs.append(
            {
                "name": arguments.kwarg.arg,
                "kind": "var_keyword",
                "annotation": _unparse(arguments.kwarg.annotation),
                "has_default": False,
                "default": None,
            }
        )
    return specs


def _public_methods(source: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in _class_node(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


def _signature(method: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, object]:
    return {
        "name": method.name,
        "parameters": _parameter_specs(method),
        "return_annotation": _unparse(method.returns),
    }


class _DelegationVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.matches: set[tuple[str, str]] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        service = node.value
        if (
            isinstance(service, ast.Attribute)
            and isinstance(service.value, ast.Name)
            and service.value.id == "self"
            and service.attr.endswith("_service")
        ):
            self.matches.add((service.attr, node.attr))
        self.generic_visit(node)


def _delegation(method: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str] | None:
    visitor = _DelegationVisitor()
    visitor.visit(method)
    if not visitor.matches:
        return None
    if len(visitor.matches) != 1:
        raise ValueError(
            f"{method.name} has multiple domain-service delegation targets: "
            f"{sorted(visitor.matches)}"
        )
    service, target_method = next(iter(visitor.matches))
    return {"service": service, "method": target_method}


def _delegations(source: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for method in _public_methods(source):
        delegation = _delegation(method)
        if delegation is not None:
            result[method.name] = delegation
    return result


def _git_source(base_sha: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{base_sha}:{SOURCE_RELATIVE_PATH.as_posix()}"],
        cwd=ROOT,
        text=True,
    )


def _build_manifest(base_sha: str, current_source: str) -> dict[str, object]:
    base_signatures = [_signature(method) for method in _public_methods(_git_source(base_sha))]
    current_methods = _public_methods(current_source)
    current_delegations = _delegations(current_source)
    public_names = {method.name for method in current_methods}
    facade_owned = sorted(public_names - current_delegations.keys())
    return {
        "schema_version": 1,
        "base_sha": base_sha,
        "source": SOURCE_RELATIVE_PATH.as_posix(),
        "public_method_count": len(base_signatures),
        "delegated_method_count": len(current_delegations),
        "facade_owned_methods": facade_owned,
        "signatures": base_signatures,
        "delegations": [
            {"name": name, **current_delegations[name]}
            for name in sorted(current_delegations)
        ],
    }


def _load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _check(current_source: str) -> list[str]:
    manifest = _load_manifest()
    expected_signatures = manifest["signatures"]
    if not isinstance(expected_signatures, list):
        return ["manifest signatures must be a list"]

    actual_signatures = [_signature(method) for method in _public_methods(current_source)]
    errors: list[str] = []
    if actual_signatures != expected_signatures:
        errors.append(
            "public facade signature manifest mismatch; run the manifest diff "
            "to identify changed names, parameter kinds/defaults/annotations, "
            "or return annotations"
        )

    actual_delegations = _delegations(current_source)
    expected_delegations = {
        item["name"]: {"service": item["service"], "method": item["method"]}
        for item in manifest["delegations"]
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("service"), str)
        and isinstance(item.get("method"), str)
    }
    if actual_delegations != expected_delegations:
        errors.append(
            "facade delegation inventory mismatch; every expected explicit "
            "domain-service delegation must remain present and unchanged"
        )

    actual_owned = sorted(
        {method.name for method in _public_methods(current_source)} - actual_delegations.keys()
    )
    expected_owned = manifest["facade_owned_methods"]
    if actual_owned != expected_owned:
        errors.append(
            f"facade-owned method inventory mismatch: expected {expected_owned!r}, "
            f"got {actual_owned!r}"
        )

    expected_count = manifest["public_method_count"]
    if len(actual_signatures) != expected_count:
        errors.append(
            f"public method count mismatch: expected {expected_count}, "
            f"got {len(actual_signatures)}"
        )
    expected_delegated_count = manifest["delegated_method_count"]
    if len(actual_delegations) != expected_delegated_count:
        errors.append(
            f"delegated method count mismatch: expected {expected_delegated_count}, "
            f"got {len(actual_delegations)}"
        )
    return errors


def _json_text(manifest: dict[str, object]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--generate", action="store_true")
    parser.add_argument("--base-sha", help="base revision used for --generate")
    parser.add_argument("--output", type=Path, help="manifest output for --generate")
    args = parser.parse_args(list(argv) if argv is not None else None)
    current_source = (ROOT / SOURCE_RELATIVE_PATH).read_text(encoding="utf-8")

    if args.generate:
        if not args.base_sha:
            parser.error("--base-sha is required with --generate")
        manifest = _build_manifest(args.base_sha, current_source)
        text = _json_text(manifest)
        if args.output is None:
            sys.stdout.write(text)
        else:
            args.output.write_text(text, encoding="utf-8")
        return 0

    errors = _check(current_source)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    manifest = _load_manifest()
    print(
        "OK: public facade signatures and explicit delegations match "
        f"{manifest['public_method_count']} methods / "
        f"{manifest['delegated_method_count']} delegations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
