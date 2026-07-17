#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate and verify the repository's data-driven DipTrace PCB skill packages."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
CATALOG_PATH = SKILLS_ROOT / "catalog.json"
CAPABILITY_MAP_PATH = SKILLS_ROOT / "capability-map.json"
DEPENDENCY_CONTRACTS_PATH = SKILLS_ROOT / "dependency-contracts.json"
SERVER_PATH = ROOT / "src" / "diptrace_mcp" / "server.py"

BLOCKED_EXAMPLE_IDS = {6, 8, 45, 47}
STATUS_VALUES = [
    "completed",
    "partial",
    "blocked_by_capability",
    "blocked_by_input",
    "failed",
]
DELIVERABLE_SCHEMA_KINDS = {
    "generic_v1",
    "release_decision_v1",
    "requirements_manifest_v1",
}
DISCOVERY_CONTROL_TOOLS = [
    "diptrace_status",
    "get_capabilities",
]
DOCUMENT_CONTROL_TOOL = "get_document_info"
TRANSACTION_CONTROL_TOOLS = [
    "begin_transaction",
    "stage_operations",
    "preview_transaction",
    "validate_transaction",
    "commit_transaction",
    "rollback_transaction",
    "run_erc",
    "run_drc",
    "run_connectivity_check",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def registered_tools() -> set[str]:
    tree = ast.parse(SERVER_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            function = decorator.func
            if isinstance(function, ast.Attribute) and function.attr == "tool":
                names.add(node.name)
    return names


def quote_yaml(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sentence_case(value: str) -> str:
    """Capitalize prose bullets without changing acronyms or the remaining text."""
    return value[:1].upper() + value[1:]


def short_description(entry: dict[str, Any]) -> str:
    value = f"DipTrace: {entry['title']}"
    if len(value) > 64:
        value = value[:61].rstrip() + "..."
    if len(value) < 25:
        value += " workflow"
    return value


def render_openai_yaml(entry: dict[str, Any]) -> str:
    default_prompt = f"Use ${entry['slug']}: {entry['runtime']}"
    return (
        "interface:\n"
        f"  display_name: {quote_yaml(entry['title'])}\n"
        f"  short_description: {quote_yaml(short_description(entry))}\n"
        f"  default_prompt: {quote_yaml(default_prompt)}\n"
    )


def output_key(value: str, index: int, used: set[str]) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    if not key:
        key = f"deliverable_{index:02d}"
    candidate = key
    suffix = 2
    while candidate in used:
        candidate = f"{key}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def deliverable_map(entry: dict[str, Any]) -> dict[str, str]:
    used: set[str] = set()
    return {
        output_key(name, index, used): name
        for index, name in enumerate(entry["outputs"], start=1)
    }


def effective_capabilities(entry: dict[str, Any]) -> list[str]:
    """Add mandatory discovery/write controls without changing the target catalog."""
    targets = [*DISCOVERY_CONTROL_TOOLS, DOCUMENT_CONTROL_TOOL, *entry["capabilities"]]
    if entry["mode"] == "preview_write":
        targets.extend(TRANSACTION_CONTROL_TOOLS)
    return list(dict.fromkeys(targets))


def resolve_capabilities(
    entry: dict[str, Any],
    capability_map: dict[str, Any],
    tools: set[str],
) -> list[dict[str, Any]]:
    aliases = capability_map["aliases"]
    missing = capability_map["missing"]
    limitations = capability_map["limitations"]
    overrides = capability_map.get("context_overrides", {}).get(entry["slug"], {})
    resolved: list[dict[str, Any]] = []
    for target in effective_capabilities(entry):
        override = overrides.get(target)
        alias = aliases.get(target)
        runtime_tool = alias["runtime_tool"] if alias else target
        note_parts: list[str] = []
        if alias:
            note_parts.append(alias["note"])
        if runtime_tool in limitations:
            note_parts.append(limitations[runtime_tool])
        if override:
            state = override["state"]
            contract = override.get("contract")
            note_parts.append(override["note"])
            if state == "incompatible":
                runtime_tool = None
        elif target in missing:
            state = "missing"
            contract = missing[target]
            runtime_tool = None
        elif runtime_tool in tools:
            state = "alias" if alias else "exact"
            contract = None
        else:
            raise ValueError(
                f"{entry['slug']}: capability {target!r} is neither registered nor mapped"
            )
        if runtime_tool is not None and runtime_tool not in tools:
            raise ValueError(
                f"{entry['slug']}: resolved runtime tool {runtime_tool!r} is not registered"
            )
        resolved.append(
            {
                "target": target,
                "state": state,
                "runtime_tool": runtime_tool,
                "contract": contract,
                "note": " ".join(note_parts) or "Use only when document capabilities allow it.",
            }
        )
    return resolved


def capability_table(resolutions: list[dict[str, Any]]) -> str:
    rows = [
        "| Target contract | Callable runtime tool | State | Required handling |",
        "| --- | --- | --- | --- |",
    ]
    for item in resolutions:
        runtime = f"`{item['runtime_tool']}`" if item["runtime_tool"] else "—"
        if item["state"] in {"missing", "incompatible"}:
            handling = (
                f"Do not call the target name. Use dependency contract "
                f"`{item['contract']}`; block only dependent stages."
            )
        elif item["state"] == "conditional":
            handling = (
                f"Use the runtime tool only for its bounded subset. For the full request use "
                f"`{item['contract']}`."
            )
        else:
            handling = item["note"]
        rows.append(
            f"| `{item['target']}` | {runtime} | `{item['state']}` | {handling} |"
        )
    return "\n".join(rows)


def dependency_section(
    resolutions: list[dict[str, Any]], contracts: dict[str, Any]
) -> str:
    contract_ids = sorted(
        {item["contract"] for item in resolutions if item.get("contract")}
    )
    if not contract_ids:
        return (
            "No known static dependency gap exists for the target contract. Runtime discovery "
            "still wins; if a document disables a required capability, emit the same structured "
            "dependency report instead of falling back silently."
        )
    sections: list[str] = []
    for contract_id in contract_ids:
        contract = contracts[contract_id]
        sections.extend(
            [
                f"### `{contract_id}`",
                "",
                contract["purpose"],
                "",
                "Required inputs: " + "; ".join(contract["inputs"]) + ".",
                "",
                "Required outputs: " + "; ".join(contract["outputs"]) + ".",
                "",
                "Invariants: " + "; ".join(contract["invariants"]) + ".",
            ]
        )
        sections.append("")
    return "\n".join(sections).rstrip()


def render_write_policy(entry: dict[str, Any]) -> str:
    mode = entry["mode"]
    if entry["slug"] == "pcb-skill-evaluator":
        return """This skill evaluates only disposable, isolated fixtures; it never writes the selected user design.

- Require a compatible `execute_agent_fixture` adapter that proves fixture isolation, deterministic seed, scope and baseline SHA-256. Without it, return `blocked_by_capability` with `agent-eval-runtime-v1`.
- The adapter may exercise the guarded preview/commit path only inside its cloned fixture. Never redirect an evaluation transaction to an active document or user working copy.
- Inspect the returned tool trace and transaction ledger. `rollback_transaction` may be called only for a transaction whose adapter evidence identifies the same isolated fixture and SHA-256.
- Require rollback evidence for every committed fixture write. Treat an unrolled committed fixture, overlapping write scope or hidden tool call as a critical safety failure.
- Keep this skill result's `transactions` empty; return the adapter ledger through a hashed resource URI and the scorecard deliverable.

Successful evaluation is not permission to install, publish or mutate the evaluated skill or design."""
    if mode == "read_only":
        return """This skill is read-only by default.

- Always complete `diptrace_status` → `get_capabilities` before analysis.
- When the workflow is bound to a document, resolve it with `get_document_info` and capture its SHA-256 before reading domain models. For a genuine pre-design workflow, record `pre_design` applicability and hash the normalized input bundle instead of inventing a document identity.
- Do not call mutating tools, open a write transaction, or export a state-changing artifact.
- Keep `planned_changes` descriptive and keep `transactions` empty.
- If the user later requests a mutation, hand off to a write-capable skill and preserve this report as baseline evidence.
- A review-only request can be `completed`; a requested mutation cannot be reported as completed by this skill.
- Steps 3–7 of the write sequence are `not_applicable` in read-only scope. Never create a no-op transaction merely to satisfy the sequence."""
    if mode == "artifact_export":
        checks = ", ".join(f"`{item}`" for item in entry.get("post_checks", []))
        return f"""This skill may create bounded output artifacts but must not mutate the source design.

1. Call `diptrace_status`, then `get_capabilities`; read the exact document and capture its source SHA-256 before export.
2. Define the exact revision, variant, profile and output scope.
3. Run only the supported exporter and inspect every returned resource URI.
4. Run the applicable minimal checks: {checks or 'the checks required by the selected profile'}.
5. Record file purpose and SHA-256 for each artifact. Do not reuse a stale output directory.
6. Never label a generic manifest as a native manufacturing package. If the requested adapter is absent, return `blocked_by_capability` with the exact dependency contract.

Artifact generation does not authorize a design commit. Any later design change requires the full semantic transaction pipeline."""
    checks = ", ".join(f"`{item}`" for item in entry.get("post_checks", []))
    return f"""Use the guarded semantic write pipeline only when the requested stage is supported and the user has authorized that stage.

1. Call `diptrace_status`, then `get_capabilities`. Read the exact document with `get_document_info` plus the required domain model and freeze its source SHA-256, selectors, region/layers and allowed operations.
2. Read locked objects, keepouts, user constraints, explicit no-connects, DNP state and waivers. Never set an `allow_locked` override unless the user names the exact object.
3. Start `begin_transaction(expected_sha256=<baseline SHA-256>)`. Stage typed semantic operations with `stage_operations`; when a semantic tool is called directly, pass `dry_run=true` and the transaction ID. Staging is itself non-committing; never use `dry_run=false` as a substitute for commit.
4. Call `preview_transaction`, then `validate_transaction`; inspect the semantic diff plus SVG/JSON resources. Treat validation as the mandatory post-preview gate.
5. Commit only after explicit confirmation with `commit_transaction(txid, expected_sha256=<validated source SHA-256>)`. Never infer confirmation from a request for a plan or preview.
6. Re-read document identity and SHA-256, then rerun every applicable regression check. For schematic or mixed documents run `run_erc`; for PCB or mixed documents run `run_drc`; for schematic, PCB or mixed documents always run `run_connectivity_check`. Also run the affected domain checks from: {checks or '`validate_transaction`'}. Record a check as `not_applicable` only when the document kind makes it invalid; an unavailable applicable check blocks success.
7. Compare the post-checks with the baseline. Stop on any regression. If a commit occurred, call `rollback_transaction(txid, expected_sha256=<committed SHA-256>)`, verify the restored SHA and rerun the same applicable ERC/DRC/connectivity checks. Never return `completed` while a regression or failed rollback remains.

Preview generation is not authorization to commit. Unsupported semantic writes must use the dependency report, never raw XML as a workaround."""


def render_skill(
    entry: dict[str, Any],
    resolutions: list[dict[str, Any]],
    contracts: dict[str, Any],
) -> str:
    description = (
        f"Orchestrate DipTrace MCP for {entry['title']}: {entry['objective']} "
        "Use when the user requests this workflow for a DipTrace schematic, PCB, library, "
        "review, or explicitly bounded project scope. Start with capability discovery; never "
        "simulate unavailable tools or write without a guarded preview."
    )
    inputs = "\n".join(f"- {item}" for item in entry["inputs"])
    workflow = "\n".join(
        f"{index}. {sentence_case(item)}."
        for index, item in enumerate(entry["workflow"], start=3)
    )
    outputs = "\n".join(f"- `{name}`" for name in entry["outputs"])
    acceptance = "\n".join(
        f"- {sentence_case(item)}." for item in entry["acceptance"]
    )
    return f"""---
name: {entry['slug']}
description: {quote_yaml(description)}
---

# {entry['title']}

## Purpose

{entry['objective']}

Priority: `{entry['priority']}`. Declared maturity: `{entry['maturity']}`. Treat maturity as planning metadata, not runtime proof of availability.

## Applicability

Use this skill for the complete workflow described by the trigger, for a bounded subsystem, or to resume an interrupted run from current document state. It may consume an offline DipTrace XML document or the active live document. Resolve every file/session explicitly; never guess which revision is active.

Required inputs:

{inputs}

## Do not use

- Do not use it as a substitute for missing datasheets, manufacturer profiles, lab measurements, certification or solver evidence.
- Do not edit raw XML, reimplement parsing, DRC, geometry, placement, routing, impedance or transaction logic inside the skill.
- Do not claim global or solver-backed results from bounded or heuristic MCP checks.
- Do not operate outside the explicit document, selector, region, layer, variant and revision scope.

## Capability discovery

The first two MCP calls must be ordered and sequential: `diptrace_status`, then `get_capabilities`. Do not reverse or parallelize them. When a document is known, read its exact identity and SHA-256 with `get_document_info`, then call `get_capabilities` again with that exact path so document-specific policy, adapters and feature limits replace the generic report. Use the client runtime tool inventory as the callable-name source of truth.

{capability_table(resolutions)}

Names in the Target contract column are conceptual contracts. Only a non-empty name in the Callable runtime tool column may be invoked. Re-resolve at every run; the table documents this repository revision but does not override runtime discovery.

## Workflow

0. Record the request, allowed scope and policy profile. Call `diptrace_status`, then `get_capabilities`.
1. Read the exact document with `get_document_info` and the required domain model; record revision/session and source SHA-256 before any semantic operation. For a genuinely pre-design task with no document, hash the normalized input bundle and set applicability to `pre_design`; never invent a document SHA.
2. Separate user facts, document facts, external facts and assumptions. For write-capable work, preserve the mandatory dry-run → preview → validation → expected-SHA commit → applicable ERC/DRC/connectivity → stop/rollback order from the write policy.
{workflow}
{len(entry['workflow']) + 3}. Validate the result against `schemas/result.schema.json`; store large graphs, models, previews and reports as resource URIs.
{len(entry['workflow']) + 4}. Evaluate every acceptance criterion and emit evidence or an explicit skipped check.

## Findings

Every finding must carry severity, confidence, rationale, suggested action and an object locator. The locator contains exact RefDes, nets, stable object IDs, layers and coordinates when those exist. For pre-design work, keep those arrays empty and set locator applicability to `pre_design`; never invent an object or coordinate.

Separate deterministic MCP findings from engineering heuristics. Preserve explicit no-connects, DNP, waivers and user constraints. A waiver is not suppression: retain the underlying finding and link the waiver ID. Set `blocks_completion` only when the finding prevents completion of the requested workflow or mandatory evidence collection; an open design-critical finding may coexist with a completed review report.

## Stop conditions

- Return `blocked_by_input` when an ambiguous or missing fact can change topology, safety, ratings, pin mapping, units, coordinate datum, scope or acceptance. Continue independent stages only.
- Return `blocked_by_capability` when the requested dependent stage has no compatible runtime tool or adapter. Include contract ID, inputs, outputs, invariants and affected stages.
- Return `partial` when independent deliverables are valid but optional or dependent checks remain unavailable. List every skipped check and its impact.
- Return `failed` for an actual tool, validation, SHA, commit or rollback failure. Do not convert an exception into a successful narrative.
- Never return `completed` with a missing mandatory check, unresolved critical/error regression, stale SHA, failed post-check, ambiguous identity or unverified requested output.

## Write policy

{render_write_policy(entry)}

## Dependency contracts

{dependency_section(resolutions, contracts)}

The canonical machine-readable contracts are in `../dependency-contracts.json`. A dependency report is a request for an MCP/runtime extension, not permission to implement a brittle parser, geometry approximation or raw XML patch in this skill.

## Outputs

{outputs}

Return the required common fields: `status`, `summary`, `document_identity`, `inputs_used`, `assumptions`, `findings`, `planned_changes`, `transactions`, `resources`, `skipped_checks`, `confidence` and `next_actions`. Also return `dependency_report`, `acceptance_evidence` and all skill-specific `deliverables`.

Status semantics:

- `completed`: the requested scope and every mandatory acceptance check have evidence.
- `partial`: valid independent work exists, with precise limitations.
- `blocked_by_capability`: an exact dependency contract blocks the requested stage.
- `blocked_by_input`: a named missing or ambiguous input blocks the requested stage.
- `failed`: execution or validation failed and success was not claimed.

`completed` describes execution of the requested workflow, not approval of the design. In particular, `release-gate` carries the independent `PASS|BLOCKED` decision in its release-decision deliverable.

## Acceptance criteria

{acceptance}

## Failure modes

- Capability advertised globally but disabled for the selected document: trust document discovery and degrade explicitly.
- Tool name exists but semantics are weaker than the target contract: use only the documented subset and never upgrade the claim.
- Large output is truncated: return a bounded summary plus resource URI.
- Source changes after analysis or preview: stop on SHA mismatch and rebuild the plan from the new source.
- Locked object, keepout, waiver, DNP or explicit no-connect conflicts with the plan: preserve it and return the conflict.
- External adapter, profile or solver is absent or unversioned: block the dependent result; do not synthesize a substitute.

## Examples and evals

- `examples/result.example.json` is a schema-valid representative result.
- `evals/scenarios.json` defines the happy path, read-only policy, missing capability, ambiguous input and safety/regression cases.
- `evals/assertions.json` defines tool selection, graceful degradation, write gating, scope/locks, output validation, post-check and false-success assertions.

Runtime prompt example:

> {entry['runtime']}
"""


def attribute_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "value", "unit", "source_id"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "value": {"type": ["string", "number", "integer", "boolean", "null"]},
            "unit": {"type": ["string", "null"]},
            "source_id": {"type": ["string", "null"]},
        },
    }


def attribute_match(name: str, value_schema: dict[str, Any]) -> dict[str, Any]:
    """Return a strict-enough `contains` predicate for a named artifact attribute."""
    return {
        "required": ["name", "value"],
        "properties": {
            "name": {"const": name},
            "value": value_schema,
        },
    }


def artifact_entry_schema(kind: str) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "label", "attributes"],
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "label": {"type": "string", "minLength": 1},
            "attributes": {
                "type": "array",
                "uniqueItems": True,
                "items": attribute_schema(),
            },
        },
    }
    if kind == "requirements_manifest_v1":
        schema["properties"]["id"]["pattern"] = r"^REQ-[A-Z0-9][A-Z0-9._-]*$"
        schema["properties"]["attributes"].update(
            {
                "minItems": 3,
                "allOf": [
                    {
                        "contains": attribute_match(
                            "priority",
                            {
                                "type": "string",
                                "enum": [
                                    "P0",
                                    "P1",
                                    "P2",
                                    "P3",
                                    "must",
                                    "should",
                                    "could",
                                    "critical",
                                    "high",
                                    "medium",
                                    "low",
                                ],
                            },
                        ),
                        "minContains": 1,
                        "maxContains": 1,
                    },
                    {
                        "contains": attribute_match(
                            "source", {"type": "string", "minLength": 1}
                        ),
                        "minContains": 1,
                        "maxContains": 1,
                    },
                    {
                        "contains": attribute_match(
                            "verification_method",
                            {"type": "string", "minLength": 1},
                        ),
                        "minContains": 1,
                        "maxContains": 1,
                    },
                ],
            }
        )
    elif kind == "release_decision_v1":
        schema["properties"]["attributes"].update(
            {
                "minItems": 1,
                "allOf": [
                    {
                        "contains": attribute_match(
                            "decision", {"type": "string", "enum": ["PASS", "BLOCKED"]}
                        ),
                        "minContains": 1,
                        "maxContains": 1,
                    }
                ],
            }
        )
    return schema


def artifact_schema(name: str, kind: str = "generic_v1") -> dict[str, Any]:
    if kind not in DELIVERABLE_SCHEMA_KINDS:
        raise ValueError(f"Unknown deliverable schema kind: {kind}")
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "name",
            "status",
            "summary",
            "resource_uri",
            "entries",
            "evidence_ids",
        ],
        "properties": {
            "name": {"type": "string", "const": name},
            "status": {
                "type": "string",
                "enum": ["available", "partial", "unavailable", "not_requested"],
            },
            "summary": {"type": "string", "minLength": 1},
            "resource_uri": {
                "anyOf": [
                    {"type": "string", "pattern": "^[a-z][a-z0-9+.-]*://"},
                    {"type": "null"},
                ]
            },
            "entries": {
                "type": "array",
                "uniqueItems": True,
                "items": artifact_entry_schema(kind),
            },
            "evidence_ids": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
        },
    }
    if kind in {"requirements_manifest_v1", "release_decision_v1"}:
        schema["properties"]["entries"]["minItems"] = 1
    if kind == "release_decision_v1":
        schema["properties"]["entries"]["maxItems"] = 1
        schema["properties"]["evidence_ids"]["minItems"] = 1
    return schema


def transaction_schema(sha_or_null: dict[str, Any]) -> dict[str, Any]:
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    uri = {"type": "string", "pattern": "^[a-z][a-z0-9+.-]*://"}
    null = {"type": "null"}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "txid",
            "state",
            "source_sha256",
            "preview_sha256",
            "committed_sha256",
            "preview_uri",
            "validation",
            "post_checks",
            "rollback",
        ],
        "properties": {
            "txid": {"type": "string", "minLength": 1},
            "state": {
                "type": "string",
                "enum": [
                    "planned",
                    "staged",
                    "validated",
                    "committed",
                    "rolled_back",
                    "failed",
                ],
            },
            "source_sha256": sha,
            "preview_sha256": sha_or_null,
            "committed_sha256": sha_or_null,
            "preview_uri": {"anyOf": [uri, null]},
            "validation": {"type": ["string", "null"]},
            "post_checks": {
                "type": "array",
                "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "rollback": {"type": ["string", "null"]},
        },
        "allOf": [
            {
                "if": {"properties": {"state": {"enum": ["planned", "staged"]}}},
                "then": {
                    "properties": {
                        "preview_sha256": null,
                        "committed_sha256": null,
                        "preview_uri": null,
                    }
                },
            },
            {
                "if": {"properties": {"state": {"const": "validated"}}},
                "then": {
                    "properties": {
                        "preview_sha256": sha,
                        "committed_sha256": null,
                        "preview_uri": uri,
                        "validation": {"type": "string", "minLength": 1},
                        "post_checks": {"minItems": 1},
                        "rollback": {"type": "string", "minLength": 1},
                    }
                },
            },
            {
                "if": {
                    "properties": {"state": {"enum": ["committed", "rolled_back"]}}
                },
                "then": {
                    "properties": {
                        "preview_sha256": sha,
                        "committed_sha256": sha,
                        "preview_uri": uri,
                        "validation": {"type": "string", "minLength": 1},
                        "post_checks": {"minItems": 1},
                        "rollback": {"type": "string", "minLength": 1},
                    }
                },
            },
        ],
    }


def result_schema(entry: dict[str, Any]) -> dict[str, Any]:
    deliverables = deliverable_map(entry)
    deliverable_kinds = entry.get("deliverable_schemas", {})
    unknown_outputs = set(deliverable_kinds) - set(entry["outputs"])
    if unknown_outputs:
        raise ValueError(
            f"{entry['slug']}: deliverable schema metadata refers to unknown outputs: "
            f"{sorted(unknown_outputs)}"
        )
    sha_or_null = {
        "anyOf": [
            {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            {"type": "null"},
        ]
    }
    string_or_null = {"type": ["string", "null"]}
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://github.com/fireostendere/mcp_diptrace/skills/"
            f"{entry['slug']}/schemas/result.schema.json"
        ),
        "title": f"{entry['slug']} result",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "status",
            "summary",
            "document_identity",
            "inputs_used",
            "assumptions",
            "findings",
            "planned_changes",
            "transactions",
            "resources",
            "skipped_checks",
            "confidence",
            "next_actions",
            "dependency_report",
            "acceptance_evidence",
            "deliverables",
        ],
        "properties": {
            "status": {"type": "string", "enum": STATUS_VALUES},
            "summary": {"type": "string", "minLength": 1},
            "document_identity": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "document_id",
                    "path",
                    "kind",
                    "revision",
                    "session_id",
                    "source_sha256",
                ],
                "properties": {
                    "document_id": string_or_null,
                    "path": string_or_null,
                    "kind": {
                        "type": ["string", "null"],
                        "enum": ["pcb", "schematic", "component_library", "pattern_library", "mixed", "pre_design", None],
                    },
                    "revision": string_or_null,
                    "session_id": string_or_null,
                    "source_sha256": sha_or_null,
                },
            },
            "inputs_used": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "input_id",
                        "kind",
                        "source",
                        "value_summary",
                        "verified",
                        "confidence",
                    ],
                    "properties": {
                        "input_id": {"type": "string", "minLength": 1},
                        "kind": {
                            "type": "string",
                            "enum": ["fact", "requirement", "measurement", "document", "profile", "user_statement"],
                        },
                        "source": {"type": "string", "minLength": 1},
                        "value_summary": {"type": "string", "minLength": 1},
                        "verified": {"type": "boolean"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "assumptions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["assumption_id", "statement", "source", "impact", "confidence", "blocking"],
                    "properties": {
                        "assumption_id": {"type": "string", "minLength": 1},
                        "statement": {"type": "string", "minLength": 1},
                        "source": {"type": "string", "minLength": 1},
                        "impact": {"type": "string", "minLength": 1},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "blocking": {"type": "boolean"},
                    },
                },
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "finding_id",
                        "category",
                        "severity",
                        "confidence",
                        "title",
                        "rationale",
                        "locator",
                        "measured",
                        "required",
                        "delta",
                        "units",
                        "rule_source",
                        "suggested_action",
                        "preview_uri",
                        "waiver_id",
                        "resolution",
                        "blocks_completion",
                    ],
                    "properties": {
                        "finding_id": {"type": "string", "minLength": 1},
                        "category": {"type": "string", "minLength": 1},
                        "severity": {"type": "string", "enum": ["critical", "error", "warning", "info"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "title": {"type": "string", "minLength": 1},
                        "rationale": {"type": "string", "minLength": 1},
                        "locator": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["refdes", "nets", "object_ids", "layers", "locations", "applicability"],
                            "properties": {
                                "refdes": {"type": "array", "items": {"type": "string"}},
                                "nets": {"type": "array", "items": {"type": "string"}},
                                "object_ids": {"type": "array", "items": {"type": "string"}},
                                "layers": {"type": "array", "items": {"type": "string"}},
                                "locations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["description", "x_mm", "y_mm"],
                                        "properties": {
                                            "description": {"type": "string", "minLength": 1},
                                            "x_mm": {"type": ["number", "null"]},
                                            "y_mm": {"type": ["number", "null"]},
                                        },
                                    },
                                },
                                "applicability": {"type": "string", "enum": ["exact", "pre_design", "not_available"]},
                            },
                        },
                        "measured": {"type": ["number", "null"]},
                        "required": {"type": ["number", "null"]},
                        "delta": {"type": ["number", "null"]},
                        "units": string_or_null,
                        "rule_source": string_or_null,
                        "suggested_action": {"type": "string", "minLength": 1},
                        "preview_uri": {
                            "anyOf": [
                                {"type": "string", "pattern": "^[a-z][a-z0-9+.-]*://"},
                                {"type": "null"},
                            ]
                        },
                        "waiver_id": string_or_null,
                        "resolution": {
                            "type": "string",
                            "enum": ["open", "resolved", "waived"],
                        },
                        "blocks_completion": {"type": "boolean"},
                    },
                    "allOf": [
                        {
                            "if": {
                                "properties": {"resolution": {"const": "waived"}}
                            },
                            "then": {
                                "properties": {
                                    "waiver_id": {"type": "string", "minLength": 1}
                                }
                            },
                        }
                    ],
                },
            },
            "planned_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["change_id", "scope", "operation_kind", "target_ids", "locked_target_ids", "rationale", "risk", "requires_confirmation", "preview_uri", "post_checks"],
                    "properties": {
                        "change_id": {"type": "string", "minLength": 1},
                        "scope": {"type": "string", "minLength": 1},
                        "operation_kind": {"type": "string", "minLength": 1},
                        "target_ids": {"type": "array", "items": {"type": "string"}},
                        "locked_target_ids": {"type": "array", "items": {"type": "string"}},
                        "rationale": {"type": "string", "minLength": 1},
                        "risk": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "requires_confirmation": {"type": "boolean"},
                        "preview_uri": {
                            "anyOf": [
                                {"type": "string", "pattern": "^[a-z][a-z0-9+.-]*://"},
                                {"type": "null"},
                            ]
                        },
                        "post_checks": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "transactions": {
                "type": "array",
                "items": transaction_schema(sha_or_null),
            },
            "resources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["uri", "mime_type", "purpose", "sha256"],
                    "properties": {
                        "uri": {"type": "string", "pattern": "^[a-z][a-z0-9+.-]*://"},
                        "mime_type": {"type": "string", "minLength": 1},
                        "purpose": {"type": "string", "minLength": 1},
                        "sha256": sha_or_null,
                    },
                },
            },
            "skipped_checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["check_id", "reason", "impact", "mandatory"],
                    "properties": {
                        "check_id": {"type": "string", "minLength": 1},
                        "reason": {"type": "string", "minLength": 1},
                        "impact": {"type": "string", "minLength": 1},
                        "mandatory": {"type": "boolean"},
                    },
                },
            },
            "confidence": {
                "type": "object",
                "additionalProperties": False,
                "required": ["overall", "basis", "rationale"],
                "properties": {
                    "overall": {"type": "number", "minimum": 0, "maximum": 1},
                    "basis": {"type": "string", "enum": ["deterministic", "mixed", "heuristic", "insufficient"]},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
            "next_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["action_id", "description", "owner", "blocking", "requires_user_confirmation", "depends_on"],
                    "properties": {
                        "action_id": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "owner": {"type": "string", "minLength": 1},
                        "blocking": {"type": "boolean"},
                        "requires_user_confirmation": {"type": "boolean"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "dependency_report": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["capability", "contract_id", "reason", "impact", "dependent_stages", "state"],
                    "properties": {
                        "capability": {"type": "string", "minLength": 1},
                        "contract_id": {"type": "string", "minLength": 1},
                        "reason": {"type": "string", "minLength": 1},
                        "impact": {"type": "string", "minLength": 1},
                        "dependent_stages": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                        "state": {"type": "string", "enum": ["missing", "incompatible", "conditional"]},
                    },
                },
            },
            "acceptance_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["criterion", "status", "evidence_ids", "rationale"],
                    "properties": {
                        "criterion": {"type": "string", "minLength": 1},
                        "status": {"type": "string", "enum": ["passed", "failed", "not_checked"]},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "rationale": {"type": "string", "minLength": 1},
                    },
                },
            },
            "deliverables": {
                "type": "object",
                "additionalProperties": False,
                "required": list(deliverables),
                "properties": {
                    key: artifact_schema(
                        name, deliverable_kinds.get(name, "generic_v1")
                    )
                    for key, name in deliverables.items()
                },
            },
        },
    }
    completion_deliverables = {
        key: {
            "properties": {
                "status": {"const": "available"},
                "evidence_ids": {"minItems": 1},
            },
            "anyOf": [
                {"properties": {"entries": {"minItems": 1}}},
                {
                    "properties": {
                        "resource_uri": {
                            "type": "string",
                            "pattern": "^[a-z][a-z0-9+.-]*://",
                        }
                    }
                },
            ],
        }
        for key in deliverables
    }
    acceptance_constraints: dict[str, Any] = {
        "minItems": len(entry["acceptance"]),
        "maxItems": len(entry["acceptance"]),
        "items": {
            "properties": {
                "status": {"const": "passed"},
                "evidence_ids": {"minItems": 1},
            }
        },
        "allOf": [
            {
                "contains": {
                    "required": ["criterion"],
                    "properties": {"criterion": {"const": criterion}},
                },
                "minContains": 1,
                "maxContains": 1,
            }
            for criterion in entry["acceptance"]
        ],
    }
    completed_properties: dict[str, Any] = {
        "inputs_used": {"minItems": 1},
        "assumptions": {
            "items": {"properties": {"blocking": {"const": False}}}
        },
        "findings": {
            "items": {
                "properties": {"blocks_completion": {"const": False}}
            }
        },
        "planned_changes": {
            "items": {
                "properties": {"locked_target_ids": {"maxItems": 0}}
            }
        },
        "transactions": {
            "items": {
                "properties": {
                    "state": {"enum": ["validated", "committed"]}
                }
            }
        },
        "skipped_checks": {
            "items": {"properties": {"mandatory": {"const": False}}}
        },
        "confidence": {
            "properties": {"basis": {"not": {"const": "insufficient"}}}
        },
        "next_actions": {
            "items": {"properties": {"blocking": {"const": False}}}
        },
        "dependency_report": {"maxItems": 0},
        "acceptance_evidence": acceptance_constraints,
        "deliverables": {"properties": completion_deliverables},
        "document_identity": {
            "properties": {
                "document_id": {"type": "string", "minLength": 1},
                "kind": {"type": "string"},
                "revision": {"type": "string", "minLength": 1},
                "source_sha256": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            }
        },
    }
    if entry["mode"] == "artifact_export":
        completed_properties["resources"] = {
            "minItems": 1,
            "items": {
                "properties": {
                    "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
                }
            },
        }
        for item in completion_deliverables.values():
            item["properties"]["resource_uri"] = {
                "type": "string",
                "pattern": "^[a-z][a-z0-9+.-]*://",
            }
    schema["allOf"] = [
        {
            "if": {"properties": {"status": {"const": "completed"}}},
            "then": {"properties": completed_properties},
        },
        {
            "if": {
                "properties": {"status": {"const": "blocked_by_capability"}}
            },
            "then": {"properties": {"dependency_report": {"minItems": 1}}},
        },
        {
            "if": {"properties": {"status": {"const": "blocked_by_input"}}},
            "then": {
                "anyOf": [
                    {
                        "properties": {
                            "assumptions": {
                                "contains": {
                                    "required": ["blocking"],
                                    "properties": {"blocking": {"const": True}},
                                }
                            }
                        }
                    },
                    {
                        "properties": {
                            "next_actions": {
                                "contains": {
                                    "required": ["blocking"],
                                    "properties": {"blocking": {"const": True}},
                                }
                            }
                        }
                    },
                ]
            },
        },
    ]
    if entry["mode"] == "read_only":
        schema["allOf"].append({"properties": {"transactions": {"maxItems": 0}}})
    elif entry["mode"] == "preview_write":
        schema["allOf"].append(
            {
                "if": {"properties": {"planned_changes": {"minItems": 1}}},
                "then": {
                    "properties": {
                        "transactions": {
                            "minItems": 1,
                            "contains": {
                                "required": ["state"],
                                "properties": {
                                    "state": {"enum": ["validated", "committed"]}
                                },
                            },
                        }
                    }
                },
            }
        )
    if entry["slug"] == "release-gate":
        decision_key = output_key("release decision", 1, set())
        pass_decision = {
            "properties": {
                "deliverables": {
                    "properties": {
                        decision_key: {
                            "properties": {
                                "entries": {
                                    "contains": {
                                        "properties": {
                                            "attributes": {
                                                "contains": attribute_match(
                                                    "decision", {"const": "PASS"}
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        schema["allOf"].append(
            {
                "if": pass_decision,
                "then": {
                    "properties": {
                        "findings": {
                            "items": {
                                "properties": {
                                    "severity": {"enum": ["warning", "info"]}
                                }
                            }
                        }
                    }
                },
            }
        )
        schema["allOf"].append(
            {
                "if": {"properties": {"status": {"not": {"const": "completed"}}}},
                "then": {
                    "properties": {
                        "deliverables": {
                            "properties": {
                                decision_key: {
                                    "properties": {
                                        "entries": {
                                            "items": {
                                                "properties": {
                                                    "attributes": {
                                                        "contains": attribute_match(
                                                            "decision",
                                                            {"const": "BLOCKED"},
                                                        )
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
            }
        )
    return schema


def example_status(entry: dict[str, Any], resolutions: list[dict[str, Any]]) -> str:
    gaps = [
        item
        for item in resolutions
        if item["state"] in {"missing", "incompatible", "conditional"}
    ]
    if not gaps:
        return "completed"
    if entry["id"] in BLOCKED_EXAMPLE_IDS:
        return "blocked_by_capability"
    return "partial"


def artifact_example_entry(
    entry: dict[str, Any], key: str, name: str, status: str
) -> dict[str, Any] | None:
    kind = entry.get("deliverable_schemas", {}).get(name, "generic_v1")
    if kind == "requirements_manifest_v1":
        return {
            "id": "REQ-001",
            "label": "The device shall satisfy the fixture requirement.",
            "attributes": [
                {
                    "name": "priority",
                    "value": "P0",
                    "unit": None,
                    "source_id": "input-001",
                },
                {
                    "name": "source",
                    "value": "fixture:happy_path",
                    "unit": None,
                    "source_id": "input-001",
                },
                {
                    "name": "verification_method",
                    "value": "Verify against the named acceptance fixture.",
                    "unit": None,
                    "source_id": "fixture:happy_path",
                },
            ],
        }
    if kind == "release_decision_v1":
        return {
            "id": "release-decision-001",
            "label": "Evidence-based release gate decision",
            "attributes": [
                {
                    "name": "decision",
                    "value": "PASS" if status == "completed" else "BLOCKED",
                    "unit": None,
                    "source_id": (
                        "fixture:happy_path"
                        if status == "completed"
                        else "dependency-report:0"
                    ),
                }
            ],
        }
    if status != "completed":
        return None
    return {
        "id": f"{key}-001",
        "label": name,
        "attributes": [
            {
                "name": "verification_status",
                "value": "verified",
                "unit": None,
                "source_id": "fixture:happy_path",
            }
        ],
    }


def result_example(
    entry: dict[str, Any], resolutions: list[dict[str, Any]]
) -> dict[str, Any]:
    gaps = [
        item
        for item in resolutions
        if item["state"] in {"missing", "incompatible", "conditional"}
    ]
    status = example_status(entry, resolutions)
    deliverables = deliverable_map(entry)
    available_status = "available" if status == "completed" else (
        "unavailable" if status == "blocked_by_capability" else "partial"
    )
    document_kind = "pre_design" if entry["id"] in {1, 2} else "pcb"
    preview_complete = status == "completed" and entry["mode"] == "preview_write"
    artifact_complete = status == "completed" and entry["mode"] == "artifact_export"
    preview_uri = "diptrace://transaction/example-tx/preview.json"
    artifact_uri = "diptrace://export/example-export/manifest.json"
    dependency_report = [
        {
            "capability": item["target"],
            "contract_id": item["contract"],
            "reason": item["note"] or "No compatible runtime tool is advertised.",
            "impact": "The dependent stage cannot be represented as a verified MCP result.",
            "dependent_stages": ["requested dependent stage"],
            "state": item["state"],
        }
        for item in gaps
    ]
    deliverable_entries = {
        key: (
            [example_entry]
            if (
                example_entry := artifact_example_entry(entry, key, name, status)
            )
            else []
        )
        for key, name in deliverables.items()
    }
    completed_evidence_ids = [
        "input-001",
        *[
            item["id"]
            for entries in deliverable_entries.values()
            for item in entries
        ],
    ]
    resources: list[dict[str, Any]] = []
    if preview_complete:
        resources.append(
            {
                "uri": preview_uri,
                "mime_type": "application/json",
                "purpose": "Validated semantic transaction preview.",
                "sha256": "1" * 64,
            }
        )
    if artifact_complete:
        resources.append(
            {
                "uri": artifact_uri,
                "mime_type": "application/json",
                "purpose": "Representative revision-bound generated artifact manifest.",
                "sha256": "2" * 64,
            }
        )
    return {
        "status": status,
        "summary": (
            "Representative fixture result with all mandatory evidence."
            if status == "completed"
            else "Representative honest degradation result for the current capability profile."
        ),
        "document_identity": {
            "document_id": (
                "fixture-input-bundle" if document_kind == "pre_design" else "example-document"
            ),
            "path": None if document_kind == "pre_design" else "fixtures/example.xml",
            "kind": document_kind,
            "revision": "fixture-r1",
            "session_id": None,
            "source_sha256": "0" * 64,
        },
        "inputs_used": [
            {
                "input_id": "input-001",
                "kind": "user_statement",
                "source": "fixture:happy_path",
                "value_summary": entry["inputs"][0],
                "verified": status == "completed",
                "confidence": 1.0 if status == "completed" else 0.5,
            }
        ],
        "assumptions": [],
        "findings": [],
        "planned_changes": (
            [
                {
                    "change_id": "change-001",
                    "scope": "fixture:explicit-scope",
                    "operation_kind": "typed_semantic_preview",
                    "target_ids": ["fixture-object-001"],
                    "locked_target_ids": [],
                    "rationale": "Representative validated preview for the requested dry-run scope.",
                    "risk": "low",
                    "requires_confirmation": True,
                    "preview_uri": preview_uri,
                    "post_checks": entry.get("post_checks", []),
                }
            ]
            if preview_complete
            else []
        ),
        "transactions": (
            [
                {
                    "txid": "example-tx",
                    "state": "validated",
                    "source_sha256": "0" * 64,
                    "preview_sha256": "1" * 64,
                    "committed_sha256": None,
                    "preview_uri": preview_uri,
                    "validation": "Preview reparsed; affected regression checks passed.",
                    "post_checks": entry.get("post_checks", []),
                    "rollback": "Rollback the uncommitted transaction; source remains unchanged.",
                }
            ]
            if preview_complete
            else []
        ),
        "resources": resources,
        "skipped_checks": [
            {
                "check_id": item["target"],
                "reason": "No compatible current runtime capability for this fixture profile.",
                "impact": "Dependent evidence is unavailable.",
                "mandatory": status == "blocked_by_capability",
            }
            for item in gaps
        ],
        "confidence": {
            "overall": 1.0 if status == "completed" else (0.0 if status == "blocked_by_capability" else 0.5),
            "basis": "deterministic" if status == "completed" else ("insufficient" if status == "blocked_by_capability" else "mixed"),
            "rationale": "Fixture evidence and capability gaps are represented explicitly.",
        },
        "next_actions": (
            [
                {
                    "action_id": "action-001",
                    "description": "Provide the dependency contract before resuming the blocked stage.",
                    "owner": "MCP maintainer",
                    "blocking": status == "blocked_by_capability",
                    "requires_user_confirmation": False,
                    "depends_on": [item["contract"] for item in gaps],
                }
            ]
            if gaps
            else (
                [
                    {
                        "action_id": "action-001",
                        "description": "Commit only if the user explicitly approves this validated preview.",
                        "owner": "user",
                        "blocking": False,
                        "requires_user_confirmation": True,
                        "depends_on": ["example-tx"],
                    }
                ]
                if preview_complete
                else []
            )
        ),
        "dependency_report": dependency_report,
        "acceptance_evidence": [
            {
                "criterion": criterion,
                "status": "passed" if status == "completed" else "not_checked",
                "evidence_ids": completed_evidence_ids if status == "completed" else [],
                "rationale": (
                    "Verified by the representative fixture."
                    if status == "completed"
                    else "Dependent evidence is unavailable in this capability profile."
                ),
            }
            for criterion in entry["acceptance"]
        ],
        "deliverables": {
            key: {
                "name": name,
                "status": (
                    "available"
                    if entry.get("deliverable_schemas", {}).get(name)
                    == "release_decision_v1"
                    else available_status
                ),
                "summary": (
                    "Available in the representative fixture."
                    if status == "completed"
                    else "Limited by the declared dependency report."
                ),
                "resource_uri": artifact_uri if artifact_complete else None,
                "entries": deliverable_entries[key],
                "evidence_ids": (
                    [item["id"] for item in deliverable_entries[key]]
                    if deliverable_entries[key]
                    else []
                ),
            }
            for key, name in deliverables.items()
        },
    }


def scenarios(
    entry: dict[str, Any], resolutions: list[dict[str, Any]]
) -> dict[str, Any]:
    del resolutions
    fixture_request = re.sub(r"<[^>]+>", "fixture-value", entry["runtime"])
    happy_status = "completed"
    read_only_status = "completed" if entry["mode"] == "read_only" else "partial"
    return {
        "schema_version": "1.0.0",
        "skill": entry["slug"],
        "scenarios": [
            {
                "id": "happy_path",
                "title": "Golden happy path with every required contract available",
                "request": fixture_request,
                "policy_profile": "interactive_edit" if entry["mode"] == "preview_write" else "review",
                "capability_profile": "full_contract_fixture",
                "expected_status": [happy_status],
                "first_tool": "diptrace_status",
                "required_tool_prefix": DISCOVERY_CONTROL_TOOLS,
                "mutating_tool_calls": entry["mode"] == "preview_write",
                "commit_allowed": False,
                "requires_dependency_report": False,
                "completed_forbidden": False,
            },
            {
                "id": "read_only",
                "title": "Read-only policy does not leak a write",
                "request": fixture_request + " Work strictly read-only.",
                "policy_profile": "read_only",
                "capability_profile": "full_contract_fixture",
                "expected_status": [read_only_status],
                "first_tool": "diptrace_status",
                "required_tool_prefix": DISCOVERY_CONTROL_TOOLS,
                "mutating_tool_calls": False,
                "commit_allowed": False,
                "requires_dependency_report": False,
                "completed_forbidden": entry["mode"] != "read_only",
            },
            {
                "id": "missing_capability",
                "title": "Critical tool family is absent",
                "request": fixture_request,
                "policy_profile": "review",
                "capability_profile": "required_family_absent",
                "expected_status": ["blocked_by_capability"],
                "first_tool": "diptrace_status",
                "required_tool_prefix": DISCOVERY_CONTROL_TOOLS,
                "mutating_tool_calls": False,
                "commit_allowed": False,
                "requires_dependency_report": True,
                "completed_forbidden": True,
            },
            {
                "id": "ambiguous_input",
                "title": "Safety-relevant input is ambiguous",
                "request": fixture_request + " Units or the revision are unknown.",
                "policy_profile": "review",
                "capability_profile": "current_repo",
                "expected_status": ["blocked_by_input"],
                "first_tool": "diptrace_status",
                "required_tool_prefix": DISCOVERY_CONTROL_TOOLS,
                "mutating_tool_calls": False,
                "commit_allowed": False,
                "requires_dependency_report": False,
                "completed_forbidden": True,
            },
            {
                "id": "safety_regression",
                "title": "Locked object, stale SHA or new regression rejects success",
                "request": fixture_request
                + " A locked object is in scope and the SHA changed after preview.",
                "policy_profile": "interactive_edit",
                "capability_profile": "current_repo",
                "expected_status": ["partial", "failed"],
                "first_tool": "diptrace_status",
                "required_tool_prefix": DISCOVERY_CONTROL_TOOLS,
                "mutating_tool_calls": entry["mode"] == "preview_write",
                "commit_allowed": False,
                "requires_dependency_report": False,
                "completed_forbidden": True,
            },
        ],
    }


def evals(entry: dict[str, Any], resolutions: list[dict[str, Any]]) -> dict[str, Any]:
    callable_tools = sorted(
        {
            item["runtime_tool"]
            for item in resolutions
            if item["runtime_tool"] is not None
        }
    )
    missing_targets = sorted(
        {
            item["target"]
            for item in resolutions
            if item["state"] in {"missing", "incompatible"}
        }
    )
    return {
        "schema_version": "1.0.0",
        "skill": entry["slug"],
        "evals": [
            {
                "id": "tool_selection",
                "scenario": "happy_path",
                "assertions": [
                    {"kind": "first_tool", "equals": "diptrace_status"},
                    {
                        "kind": "required_tool_prefix",
                        "equals": DISCOVERY_CONTROL_TOOLS,
                    },
                    {"kind": "callable_tools_registered", "equals": callable_tools},
                    {"kind": "never_call_target_names", "equals": missing_targets},
                ],
            },
            {
                "id": "graceful_degradation",
                "scenario": "missing_capability",
                "assertions": [
                    {"kind": "status", "equals": "blocked_by_capability"},
                    {"kind": "dependency_report_required", "equals": True},
                    {"kind": "false_success_forbidden", "equals": True},
                ],
            },
            {
                "id": "write_policy",
                "scenario": "read_only",
                "assertions": [
                    {"kind": "mutating_tool_calls", "equals": False},
                    {"kind": "commit", "equals": False},
                    {"kind": "transactions_empty", "equals": True},
                ],
            },
            {
                "id": "preview_and_post_checks",
                "scenario": "happy_path",
                "assertions": [
                    {
                        "kind": "write_order",
                        "equals": (
                            [
                                "diptrace_status",
                                "get_capabilities",
                                "document_sha",
                                "scope",
                                "locks",
                                "typed_semantic_dry_run",
                                "preview",
                                "validation",
                                "expected_sha256_commit",
                                "applicable_erc_drc_connectivity",
                                "stop_or_rollback",
                            ]
                            if entry["mode"] == "preview_write"
                            else ["no_design_write"]
                        ),
                    },
                    {"kind": "minimal_post_checks", "equals": entry.get("post_checks", [])},
                    {
                        "kind": "document_check_matrix",
                        "equals": {
                            "schematic": ["run_erc", "run_connectivity_check"],
                            "pcb": ["run_drc", "run_connectivity_check"],
                            "mixed": [
                                "run_erc",
                                "run_drc",
                                "run_connectivity_check",
                            ],
                        },
                    },
                ],
            },
            {
                "id": "scope_and_locks",
                "scenario": "safety_regression",
                "assertions": [
                    {"kind": "changed_ids_subset_scope", "equals": True},
                    {"kind": "changed_ids_disjoint_locked", "equals": True},
                    {"kind": "stale_sha_commit", "equals": False},
                ],
            },
            {
                "id": "output_validation",
                "scenario": "happy_path",
                "assertions": [
                    {"kind": "json_schema", "equals": "schemas/result.schema.json"},
                    {"kind": "additional_properties", "equals": False},
                    {"kind": "resource_uri_for_large_output", "equals": True},
                ],
            },
            {
                "id": "no_false_success",
                "scenario": "safety_regression",
                "assertions": [
                    {"kind": "completed_on_regression", "equals": False},
                    {"kind": "completed_with_mandatory_skip", "equals": False},
                    {"kind": "rollback_evidence_on_failed_postcheck", "equals": True},
                ],
            },
        ],
    }


def expected_files(
    entry: dict[str, Any],
    resolutions: list[dict[str, Any]],
    contracts: dict[str, Any],
) -> dict[Path, str]:
    directory = SKILLS_ROOT / entry["slug"]
    return {
        directory / "SKILL.md": render_skill(entry, resolutions, contracts),
        directory / "agents" / "openai.yaml": render_openai_yaml(entry),
        directory / "schemas" / "result.schema.json": dump_json(result_schema(entry)),
        directory / "examples" / "result.example.json": dump_json(
            result_example(entry, resolutions)
        ),
        directory / "evals" / "scenarios.json": dump_json(
            scenarios(entry, resolutions)
        ),
        directory / "evals" / "assertions.json": dump_json(evals(entry, resolutions)),
    }


def initialize_skill(entry: dict[str, Any], init_script: Path) -> None:
    command = [
        sys.executable,
        str(init_script),
        entry["slug"],
        "--path",
        str(SKILLS_ROOT),
        "--interface",
        f"display_name={entry['title']}",
        "--interface",
        f"short_description={short_description(entry)}",
        "--interface",
        f"default_prompt=Use ${entry['slug']}: {entry['runtime']}",
    ]
    subprocess.run(command, check=True)


def validate_catalog(catalog: list[dict[str, Any]]) -> None:
    if len(catalog) != 57:
        raise ValueError(f"Expected 57 skills, got {len(catalog)}")
    ids = [entry["id"] for entry in catalog]
    if ids != list(range(1, 58)):
        raise ValueError("Skill IDs must be contiguous from 1 through 57")
    slugs = [entry["slug"] for entry in catalog]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Skill slugs must be unique")
    for entry in catalog:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", entry["slug"]):
            raise ValueError(f"Invalid skill slug: {entry['slug']}")
        if len(entry["slug"]) > 64:
            raise ValueError(f"Skill slug exceeds 64 characters: {entry['slug']}")
        if entry["mode"] not in {"read_only", "preview_write", "artifact_export"}:
            raise ValueError(f"Invalid mode for {entry['slug']}: {entry['mode']}")
        for field in ("inputs", "capabilities", "workflow", "outputs", "acceptance"):
            if not entry.get(field):
                raise ValueError(f"{entry['slug']}: {field} must not be empty")
        deliverable_schemas = entry.get("deliverable_schemas", {})
        if not isinstance(deliverable_schemas, dict):
            raise ValueError(
                f"{entry['slug']}: deliverable_schemas must map output names to schema kinds"
            )
        unknown_outputs = set(deliverable_schemas) - set(entry["outputs"])
        if unknown_outputs:
            raise ValueError(
                f"{entry['slug']}: deliverable_schemas contains unknown outputs: "
                f"{sorted(unknown_outputs)}"
            )
        unknown_kinds = set(deliverable_schemas.values()) - DELIVERABLE_SCHEMA_KINDS
        if unknown_kinds:
            raise ValueError(
                f"{entry['slug']}: unknown deliverable schema kinds: {sorted(unknown_kinds)}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if generated files are stale")
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="Initialize missing packages with skill-creator before rendering",
    )
    parser.add_argument(
        "--init-script",
        type=Path,
        help="Path to skill-creator's init_skill.py; required with --initialize",
    )
    args = parser.parse_args()
    if args.initialize and args.init_script is None:
        parser.error("--init-script is required with --initialize")

    catalog = load_json(CATALOG_PATH)
    capability_map = load_json(CAPABILITY_MAP_PATH)
    contracts = load_json(DEPENDENCY_CONTRACTS_PATH)["contracts"]
    validate_catalog(catalog)
    tools = registered_tools()
    stale: list[str] = []
    for entry in catalog:
        directory = SKILLS_ROOT / entry["slug"]
        if not directory.exists():
            if args.check:
                stale.append(f"missing package: {entry['slug']}")
                continue
            if not args.initialize:
                raise RuntimeError(
                    f"Missing {directory}; rerun with --initialize and skill-creator init_skill.py"
                )
            initialize_skill(entry, args.init_script.resolve())
        resolutions = resolve_capabilities(entry, capability_map, tools)
        for path, content in expected_files(entry, resolutions, contracts).items():
            if args.check:
                if not path.is_file():
                    stale.append(f"missing file: {path.relative_to(ROOT)}")
                elif path.read_text(encoding="utf-8") != content:
                    stale.append(f"stale file: {path.relative_to(ROOT)}")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        for item in stale:
            print(item)
        return 1
    action = "verified" if args.check else "generated"
    print(f"{action} {len(catalog)} PCB skill packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
