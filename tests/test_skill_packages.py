from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, Literal, Union

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ConfigDict, Field, ValidationError, create_model
from yaml import safe_load

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
SERVER_PATH = ROOT / "src" / "diptrace_mcp" / "server.py"

STATUS_VALUES = {
    "completed",
    "partial",
    "blocked_by_capability",
    "blocked_by_input",
    "failed",
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
PACKAGE_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "schemas/result.schema.json",
    "examples/result.example.json",
    "evals/scenarios.json",
    "evals/assertions.json",
}
COMMON_RESULT_FIELDS = {
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
}
SCENARIO_IDS = [
    "happy_path",
    "read_only",
    "missing_capability",
    "ambiguous_input",
    "safety_regression",
]
EVAL_IDS = [
    "tool_selection",
    "graceful_degradation",
    "write_policy",
    "preview_and_post_checks",
    "scope_and_locks",
    "output_validation",
    "no_false_success",
]
WRITE_ORDER = [
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
CYRILLIC = re.compile(r"[\u0400-\u04ff]")
REQUIRED_SECTIONS = [
    "## Purpose",
    "## Applicability",
    "## Do not use",
    "## Capability discovery",
    "## Workflow",
    "## Findings",
    "## Stop conditions",
    "## Write policy",
    "## Dependency contracts",
    "## Outputs",
    "## Acceptance criteria",
    "## Failure modes",
    "## Examples and evals",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def catalog() -> list[dict[str, Any]]:
    value = load_json(SKILLS_ROOT / "catalog.json")
    assert isinstance(value, list)
    return value


def registered_tools() -> set[str]:
    """Read the actual FastMCP registrations without depending on generator internals."""
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
                assert not decorator.args and not decorator.keywords, (
                    f"{node.name}: test parser must handle an explicit MCP tool-name override"
                )
                names.add(node.name)
    return names


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(?P<header>.*?)\n---\n(?P<body>.*)", text, re.DOTALL)
    assert match is not None, f"invalid frontmatter framing: {path}"
    metadata = safe_load(match.group("header"))
    assert isinstance(metadata, dict), f"frontmatter must be a mapping: {path}"
    assert all(isinstance(key, str) for key in metadata)
    assert all(isinstance(value, str) for value in metadata.values())
    return metadata, match.group("body")


def parse_openai_yaml(path: Path) -> dict[str, str]:
    data = safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data.keys() == {"interface"}
    interface = data["interface"]
    assert isinstance(interface, dict), f"interface must be a mapping: {path}"
    assert all(isinstance(key, str) for key in interface)
    assert all(isinstance(value, str) for value in interface.values())
    return interface


def capability_resolution(
    entry: dict[str, Any],
    capability_map: dict[str, Any],
    tools: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    overrides = capability_map["context_overrides"].get(entry["slug"], {})
    targets = [*DISCOVERY_CONTROL_TOOLS, DOCUMENT_CONTROL_TOOL, *entry["capabilities"]]
    if entry["mode"] == "preview_write":
        targets.extend(TRANSACTION_CONTROL_TOOLS)
    for target in dict.fromkeys(targets):
        alias = capability_map["aliases"].get(target)
        runtime_tool = alias["runtime_tool"] if alias else target
        override = overrides.get(target)
        if override:
            state = override["state"]
            contract = override["contract"]
            if state == "incompatible":
                runtime_tool = None
        elif target in capability_map["missing"]:
            state = "missing"
            contract = capability_map["missing"][target]
            runtime_tool = None
        elif alias:
            state = "alias"
            contract = None
        else:
            assert target in tools, f"{entry['slug']}: unmapped capability {target}"
            state = "exact"
            contract = None
        if runtime_tool is not None:
            assert runtime_tool in tools, (
                f"{entry['slug']}: {target} resolves to unregistered tool {runtime_tool}"
            )
        result.append(
            {
                "target": target,
                "runtime_tool": runtime_tool,
                "state": state,
                "contract": contract,
            }
        )
    return result


def capability_rows(body: str) -> list[dict[str, str | None]]:
    pattern = re.compile(
        r"^\| `(?P<target>[^`]+)` \| (?P<runtime>`[^`]+`|—) "
        r"\| `(?P<state>[^`]+)` \| (?P<handling>.*) \|$"
    )
    rows: list[dict[str, str | None]] = []
    for line in body.splitlines():
        match = pattern.fullmatch(line)
        if match is None:
            continue
        runtime = match.group("runtime")
        rows.append(
            {
                "target": match.group("target"),
                "runtime_tool": None if runtime == "—" else runtime.strip("`"),
                "state": match.group("state"),
                "handling": match.group("handling"),
            }
        )
    return rows


def assertions_by_kind(evaluation: dict[str, Any]) -> dict[str, Any]:
    assertions = evaluation["assertions"]
    result = {item["kind"]: item["equals"] for item in assertions}
    assert len(result) == len(assertions), f"duplicate assertion kind in {evaluation['id']}"
    return result


def walk_schema(schema: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(schema, dict):
        nodes.append(schema)
        for value in schema.values():
            nodes.extend(walk_schema(value))
    elif isinstance(schema, list):
        for value in schema:
            nodes.extend(walk_schema(value))
    return nodes


def status_constraint(schema: dict[str, Any], status: str) -> dict[str, Any]:
    for rule in schema.get("allOf", []):
        condition = rule.get("if", {}).get("properties", {}).get("status")
        if condition == {"const": status}:
            return rule["then"]
    raise AssertionError(f"missing status-dependent schema contract for {status}")


def schema_annotation(schema: dict[str, Any], path: str) -> Any:
    """Translate the generated JSON-Schema subset to a strict Pydantic type."""
    if "anyOf" in schema:
        choices = tuple(
            schema_annotation(choice, f"{path}_choice_{index}")
            for index, choice in enumerate(schema["anyOf"])
        )
        return Union.__getitem__(choices)
    if "enum" in schema:
        return Literal.__getitem__(tuple(schema["enum"]))

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        choices = tuple(
            schema_annotation({**schema, "type": item}, f"{path}_{item}")
            for item in schema_type
        )
        return Union.__getitem__(choices)
    if schema_type == "object":
        fields: dict[str, tuple[Any, Any]] = {}
        for name, child in schema["properties"].items():
            fields[name] = (schema_annotation(child, f"{path}_{name}"), ...)
        model_name = re.sub(r"[^A-Za-z0-9_]", "_", path)[-180:]
        return create_model(
            model_name,
            __config__=ConfigDict(extra="forbid", strict=True),
            **fields,
        )
    if schema_type == "array":
        annotation = list[schema_annotation(schema["items"], f"{path}_item")]
        if "minItems" in schema:
            return Annotated[annotation, Field(min_length=schema["minItems"])]
        return annotation

    primitives: dict[str, Any] = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "null": type(None),
    }
    assert schema_type in primitives, f"unsupported schema node at {path}: {schema}"
    constraints: dict[str, Any] = {}
    if "minLength" in schema:
        constraints["min_length"] = schema["minLength"]
    if "pattern" in schema:
        constraints["pattern"] = schema["pattern"]
    if "minimum" in schema:
        constraints["ge"] = schema["minimum"]
    if "maximum" in schema:
        constraints["le"] = schema["maximum"]
    annotation = primitives[schema_type]
    return Annotated[annotation, Field(**constraints)] if constraints else annotation


def test_skill_catalog_and_packages_are_discoverable() -> None:
    entries = catalog()
    assert len(entries) == 57
    assert [entry["id"] for entry in entries] == list(range(1, 58))
    slugs = [entry["slug"] for entry in entries]
    assert len(slugs) == len(set(slugs))
    assert set(slugs) == {
        path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()
    }

    for entry in entries:
        slug = entry["slug"]
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)
        assert len(slug) <= 64
        assert entry["mode"] in {"read_only", "preview_write", "artifact_export"}
        for key in ("inputs", "capabilities", "workflow", "outputs", "acceptance"):
            assert entry[key], f"{slug}: empty {key}"

        package = SKILLS_ROOT / slug
        files = {
            path.relative_to(package).as_posix()
            for path in package.rglob("*")
            if path.is_file()
        }
        assert files == PACKAGE_FILES, f"{slug}: incomplete or extraneous package files"
        assert not any(
            re.fullmatch(r"(?:temp_.+|.+_new|.+_v2)(?:\..+)?", path.name)
            for path in package.rglob("*")
        )

        metadata, body = parse_frontmatter(package / "SKILL.md")
        assert metadata.keys() == {"name", "description"}
        assert metadata["name"] == slug
        assert entry["title"] in metadata["description"]
        assert entry["objective"] in metadata["description"]
        assert "DipTrace" in metadata["description"]
        assert "<" not in metadata["description"]
        assert ">" not in metadata["description"]
        assert len(metadata["description"]) <= 1024
        assert len(body.splitlines()) < 500
        positions = [body.index(section) for section in REQUIRED_SECTIONS]
        assert positions == sorted(positions), f"{slug}: required sections are missing or reordered"
        assert "The first two MCP calls must be ordered and sequential" in body
        assert "`diptrace_status`, then `get_capabilities`" in body
        assert "`get_document_info`" in body
        assert "schemas/result.schema.json" in body
        assert "evals/scenarios.json" in body
        assert "evals/assertions.json" in body

        interface = parse_openai_yaml(package / "agents" / "openai.yaml")
        assert interface.keys() == {
            "display_name",
            "short_description",
            "default_prompt",
        }
        assert interface["display_name"] == entry["title"]
        assert 25 <= len(interface["short_description"]) <= 64
        assert interface["default_prompt"] == f"Use ${slug}: {entry['runtime']}"


def test_published_skill_resources_are_english() -> None:
    offenders: list[str] = []
    for path in sorted(SKILLS_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".md", ".yaml"}:
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if CYRILLIC.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{line_number}")
    assert not offenders, "Cyrillic remains in English skill resources: " + ", ".join(
        offenders
    )


def test_capability_contracts_match_registered_mcp_tools() -> None:
    entries = catalog()
    tools = registered_tools()
    capability_map = load_json(SKILLS_ROOT / "capability-map.json")
    contract_data = load_json(SKILLS_ROOT / "dependency-contracts.json")
    contracts = contract_data["contracts"]
    used_targets = {target for entry in entries for target in entry["capabilities"]}

    assert "get_capabilities" in tools
    assert capability_map["schema_version"] == "1.0.0"
    assert contract_data["schema_version"] == "1.0.0"
    assert set(capability_map["aliases"]) <= used_targets
    assert set(capability_map["missing"]) <= used_targets
    assert not (set(capability_map["aliases"]) & set(capability_map["missing"]))

    for target, alias in capability_map["aliases"].items():
        assert target not in tools, f"stale alias: {target} is now directly registered"
        assert alias["runtime_tool"] in tools
        assert alias["note"]
    for target, contract_id in capability_map["missing"].items():
        assert target not in tools, f"stale missing mapping: {target} is now registered"
        assert contract_id in contracts
    for tool, limitation in capability_map["limitations"].items():
        assert tool in tools
        assert limitation
    for contract_id, contract in contracts.items():
        assert set(contract) == {
            "purpose",
            "inputs",
            "outputs",
            "invariants",
            "failure_status",
        }
        assert contract["purpose"] and contract["inputs"] and contract["outputs"]
        assert contract["invariants"]
        assert contract["failure_status"] == "blocked_by_capability"
        assert re.fullmatch(r"[a-z0-9-]+-v[0-9]+", contract_id)

    by_slug = {entry["slug"]: entry for entry in entries}
    for slug, overrides in capability_map["context_overrides"].items():
        assert slug in by_slug
        for target, override in overrides.items():
            assert target in by_slug[slug]["capabilities"]
            assert override["state"] in {"incompatible", "conditional"}
            assert override["contract"] in contracts
            assert override["note"]

    for entry in entries:
        slug = entry["slug"]
        resolved = capability_resolution(entry, capability_map, tools)
        _, body = parse_frontmatter(SKILLS_ROOT / slug / "SKILL.md")
        rows = capability_rows(body)
        assert len(rows) == len(resolved), f"{slug}: capability table is incomplete"
        for expected, row in zip(resolved, rows, strict=True):
            assert row["target"] == expected["target"]
            assert row["runtime_tool"] == expected["runtime_tool"]
            assert row["state"] == expected["state"]
            if expected["contract"]:
                assert f"`{expected['contract']}`" in str(row["handling"])

        eval_data = load_json(SKILLS_ROOT / slug / "evals" / "assertions.json")
        tool_eval = next(item for item in eval_data["evals"] if item["id"] == "tool_selection")
        assertions = assertions_by_kind(tool_eval)
        assert assertions["first_tool"] == "diptrace_status"
        assert assertions["required_tool_prefix"] == DISCOVERY_CONTROL_TOOLS
        assert assertions["callable_tools_registered"] == sorted(
            {
                item["runtime_tool"]
                for item in resolved
                if item["runtime_tool"] is not None
            }
        )
        assert assertions["never_call_target_names"] == sorted(
            {
                item["target"]
                for item in resolved
                if item["state"] in {"missing", "incompatible"}
            }
        )


def test_result_schemas_are_strict_and_examples_validate_with_pydantic() -> None:
    for entry in catalog():
        slug = entry["slug"]
        package = SKILLS_ROOT / slug
        schema = load_json(package / "schemas" / "result.schema.json")
        example = load_json(package / "examples" / "result.example.json")

        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].endswith(f"/skills/{slug}/schemas/result.schema.json")
        assert schema["type"] == "object"
        assert set(schema["required"]) == COMMON_RESULT_FIELDS
        assert set(schema["properties"]) == COMMON_RESULT_FIELDS
        assert set(schema["properties"]["status"]["enum"]) == STATUS_VALUES

        object_nodes = [node for node in walk_schema(schema) if node.get("type") == "object"]
        assert object_nodes
        for node in object_nodes:
            assert node.get("additionalProperties") is False, f"{slug}: non-strict object"
            assert set(node["required"]) == set(node["properties"]), (
                f"{slug}: object fields must all be explicit and required"
            )

        result_model = schema_annotation(schema, f"{slug}_result")
        validated = result_model.model_validate(example, strict=True)
        assert validated.model_dump(mode="json") == example
        invalid_extra = copy.deepcopy(example)
        invalid_extra["unexpected"] = True
        with pytest.raises(ValidationError):
            result_model.model_validate(invalid_extra, strict=True)
        invalid_status = copy.deepcopy(example)
        invalid_status["status"] = "ready"
        with pytest.raises(ValidationError):
            result_model.model_validate(invalid_status, strict=True)

        deliverables = example["deliverables"]
        deliverable_schema = schema["properties"]["deliverables"]
        assert list(deliverables) == deliverable_schema["required"]
        assert [item["name"] for item in deliverables.values()] == entry["outputs"]
        for name, artifact in zip(
            entry["outputs"], deliverable_schema["properties"].values(), strict=True
        ):
            assert artifact["properties"]["name"]["const"] == name
        assert example["status"] in STATUS_VALUES
        if example["status"] == "completed":
            assert not example["dependency_report"]
            assert not any(item["mandatory"] for item in example["skipped_checks"])
            assert all(
                item["status"] == "passed" for item in example["acceptance_evidence"]
            )
            assert all(item["status"] == "available" for item in deliverables.values())
        elif example["status"] == "blocked_by_capability":
            assert example["dependency_report"]
            assert all(item["dependent_stages"] for item in example["dependency_report"])
            assert not any(
                item["status"] == "passed" for item in example["acceptance_evidence"]
            )


def test_result_schemas_encode_false_success_and_specialized_output_guards() -> None:
    for entry in catalog():
        slug = entry["slug"]
        package = SKILLS_ROOT / slug
        schema = load_json(package / "schemas" / "result.schema.json")
        example = load_json(package / "examples" / "result.example.json")
        completed = status_constraint(schema, "completed")["properties"]

        assert completed["dependency_report"]["maxItems"] == 0
        assert completed["skipped_checks"]["items"]["properties"]["mandatory"] == {
            "const": False
        }
        acceptance = completed["acceptance_evidence"]
        assert acceptance["minItems"] == acceptance["maxItems"] == len(
            entry["acceptance"]
        )
        assert acceptance["items"]["properties"]["status"] == {"const": "passed"}
        assert acceptance["items"]["properties"]["evidence_ids"]["minItems"] == 1
        assert completed["assumptions"]["items"]["properties"]["blocking"] == {
            "const": False
        }
        assert completed["findings"]["items"]["properties"]["blocks_completion"] == {
            "const": False
        }
        assert completed["next_actions"]["items"]["properties"]["blocking"] == {
            "const": False
        }
        identity = completed["document_identity"]["properties"]
        assert identity["document_id"]["type"] == "string"
        assert identity["revision"]["type"] == "string"
        assert identity["source_sha256"]["pattern"] == "^[0-9a-f]{64}$"

        for artifact in completed["deliverables"]["properties"].values():
            assert artifact["properties"]["status"] == {"const": "available"}
            assert artifact["properties"]["evidence_ids"]["minItems"] == 1
            assert artifact["anyOf"] == [
                {"properties": {"entries": {"minItems": 1}}},
                {
                    "properties": {
                        "resource_uri": {
                            "type": "string",
                            "pattern": "^[a-z][a-z0-9+.-]*://",
                        }
                    }
                },
            ]

        transaction = schema["properties"]["transactions"]["items"]
        assert transaction["properties"]["source_sha256"]["pattern"] == "^[0-9a-f]{64}$"
        state_conditions = {
            tuple(
                rule["if"]["properties"]["state"].get(
                    "enum", [rule["if"]["properties"]["state"].get("const")]
                )
            ): rule["then"]["properties"]
            for rule in transaction["allOf"]
        }
        committed = state_conditions[("committed", "rolled_back")]
        assert committed["preview_sha256"]["type"] == "string"
        assert committed["committed_sha256"]["type"] == "string"
        assert committed["post_checks"]["minItems"] == 1
        if entry["mode"] == "read_only":
            assert any(
                rule == {"properties": {"transactions": {"maxItems": 0}}}
                for rule in schema["allOf"]
            )
            assert example["transactions"] == []
        if entry["mode"] == "artifact_export" and example["status"] == "completed":
            assert example["resources"]
            assert all(item["sha256"] for item in example["resources"])

        if example["status"] == "completed":
            assert all(item["evidence_ids"] for item in example["acceptance_evidence"])
            assert all(
                artifact["evidence_ids"]
                and (artifact["entries"] or artifact["resource_uri"])
                for artifact in example["deliverables"].values()
            )

        if slug == "pcb-project-intake":
            manifest = schema["properties"]["deliverables"]["properties"][
                "requirements_manifest"
            ]
            entry_schema = manifest["properties"]["entries"]["items"]
            assert entry_schema["properties"]["id"]["pattern"].startswith("^REQ-")
            attribute_rules = entry_schema["properties"]["attributes"]["allOf"]
            assert {
                rule["contains"]["properties"]["name"]["const"]
                for rule in attribute_rules
            } == {"priority", "source", "verification_method"}
            requirement = example["deliverables"]["requirements_manifest"]["entries"][0]
            assert requirement["id"].startswith("REQ-")
        elif slug == "release-gate":
            decision = schema["properties"]["deliverables"]["properties"][
                "release_decision"
            ]
            assert decision["properties"]["entries"]["minItems"] == 1
            assert decision["properties"]["entries"]["maxItems"] == 1
            decision_rule = decision["properties"]["entries"]["items"]["properties"][
                "attributes"
            ]["allOf"][0]
            assert decision_rule["contains"]["properties"]["value"]["enum"] == [
                "PASS",
                "BLOCKED",
            ]
            attributes = example["deliverables"]["release_decision"]["entries"][0][
                "attributes"
            ]
            assert [item["value"] for item in attributes if item["name"] == "decision"] in (
                ["PASS"],
                ["BLOCKED"],
            )


def test_json_schema_rejects_adversarial_false_success_results() -> None:
    def load_pair(slug: str) -> tuple[Draft202012Validator, dict[str, Any]]:
        package = SKILLS_ROOT / slug
        schema = load_json(package / "schemas" / "result.schema.json")
        Draft202012Validator.check_schema(schema)
        example = load_json(package / "examples" / "result.example.json")
        validator = Draft202012Validator(schema)
        validator.validate(example)
        return validator, example

    intake_validator, intake = load_pair("pcb-project-intake")
    assert intake["status"] == "completed"

    mutations: list[dict[str, Any]] = []
    with_mandatory_skip = copy.deepcopy(intake)
    with_mandatory_skip["skipped_checks"].append(
        {
            "check_id": "mandatory-check",
            "reason": "fixture omission",
            "impact": "acceptance is unknown",
            "mandatory": True,
        }
    )
    mutations.append(with_mandatory_skip)

    with_unchecked_acceptance = copy.deepcopy(intake)
    with_unchecked_acceptance["acceptance_evidence"][0]["status"] = "not_checked"
    mutations.append(with_unchecked_acceptance)

    with_missing_dependency = copy.deepcopy(intake)
    with_missing_dependency["dependency_report"].append(
        {
            "capability": "fixture_capability",
            "contract_id": "domain-analyzer-v1",
            "reason": "fixture capability absent",
            "impact": "mandatory output unavailable",
            "dependent_stages": ["fixture stage"],
            "state": "missing",
        }
    )
    mutations.append(with_missing_dependency)

    with_unavailable_output = copy.deepcopy(intake)
    first_output = next(iter(with_unavailable_output["deliverables"].values()))
    first_output["status"] = "unavailable"
    mutations.append(with_unavailable_output)

    with_ambiguous_identity = copy.deepcopy(intake)
    with_ambiguous_identity["document_identity"]["document_id"] = None
    mutations.append(with_ambiguous_identity)

    with_blocking_action = copy.deepcopy(intake)
    with_blocking_action["next_actions"].append(
        {
            "action_id": "blocking-action",
            "description": "Provide mandatory evidence.",
            "owner": "user",
            "blocking": True,
            "requires_user_confirmation": True,
            "depends_on": ["mandatory-check"],
        }
    )
    mutations.append(with_blocking_action)

    for mutation in mutations:
        with pytest.raises(JsonSchemaValidationError):
            intake_validator.validate(mutation)

    preview_validator, preview = load_pair("functional-block-placement")
    assert preview["status"] == "completed" and preview["transactions"]
    invalid_commit = copy.deepcopy(preview)
    invalid_commit["transactions"][0]["state"] = "committed"
    invalid_commit["transactions"][0]["committed_sha256"] = None
    with pytest.raises(JsonSchemaValidationError):
        preview_validator.validate(invalid_commit)

    release_validator, release = load_pair("release-gate")
    invalid_decision = copy.deepcopy(release)
    decision_attributes = invalid_decision["deliverables"]["release_decision"][
        "entries"
    ][0]["attributes"]
    next(item for item in decision_attributes if item["name"] == "decision")[
        "value"
    ] = "UNKNOWN"
    with pytest.raises(JsonSchemaValidationError):
        release_validator.validate(invalid_decision)

    pass_with_critical_finding = copy.deepcopy(release)
    pass_with_critical_finding["findings"].append(
        {
            "finding_id": "critical-release-finding",
            "category": "release.blocker",
            "severity": "critical",
            "confidence": 1.0,
            "title": "Known release blocker",
            "rationale": "A PASS decision cannot coexist with a critical finding.",
            "locator": {
                "refdes": [],
                "nets": [],
                "object_ids": [],
                "layers": [],
                "locations": [],
                "applicability": "not_available",
            },
            "measured": None,
            "required": None,
            "delta": None,
            "units": None,
            "rule_source": "fixture:release-profile",
            "suggested_action": "Return a BLOCKED release decision.",
            "preview_uri": None,
            "waiver_id": None,
            "resolution": "open",
            "blocks_completion": False,
        }
    )
    with pytest.raises(JsonSchemaValidationError):
        release_validator.validate(pass_with_critical_finding)

    invalid_manifest = copy.deepcopy(intake)
    requirement_attributes = invalid_manifest["deliverables"][
        "requirements_manifest"
    ]["entries"][0]["attributes"]
    requirement_attributes[:] = [
        item for item in requirement_attributes if item["name"] != "verification_method"
    ]
    with pytest.raises(JsonSchemaValidationError):
        intake_validator.validate(invalid_manifest)


def test_scenarios_cover_required_safety_and_degradation_cases() -> None:
    for entry in catalog():
        slug = entry["slug"]
        data = load_json(SKILLS_ROOT / slug / "evals" / "scenarios.json")
        assert data["schema_version"] == "1.0.0"
        assert data["skill"] == slug
        assert [scenario["id"] for scenario in data["scenarios"]] == SCENARIO_IDS
        scenarios = {scenario["id"]: scenario for scenario in data["scenarios"]}

        for scenario in scenarios.values():
            assert scenario["first_tool"] == "diptrace_status"
            assert scenario["required_tool_prefix"] == DISCOVERY_CONTROL_TOOLS
            assert set(scenario["expected_status"]) <= STATUS_VALUES
            assert scenario["commit_allowed"] is False

        happy = scenarios["happy_path"]
        assert happy["capability_profile"] == "full_contract_fixture"
        assert "<" not in happy["request"] and ">" not in happy["request"]
        assert happy["expected_status"] == ["completed"]
        assert happy["mutating_tool_calls"] is (entry["mode"] == "preview_write")
        assert happy["completed_forbidden"] is False
        assert happy["requires_dependency_report"] is False

        read_only = scenarios["read_only"]
        assert read_only["capability_profile"] == "full_contract_fixture"
        assert read_only["policy_profile"] == "read_only"
        assert read_only["mutating_tool_calls"] is False
        assert read_only["completed_forbidden"] is (entry["mode"] != "read_only")

        missing = scenarios["missing_capability"]
        assert missing["expected_status"] == ["blocked_by_capability"]
        assert missing["requires_dependency_report"] is True
        assert missing["completed_forbidden"] is True
        assert missing["mutating_tool_calls"] is False

        ambiguous = scenarios["ambiguous_input"]
        assert ambiguous["expected_status"] == ["blocked_by_input"]
        assert ambiguous["completed_forbidden"] is True
        assert ambiguous["mutating_tool_calls"] is False

        regression = scenarios["safety_regression"]
        assert set(regression["expected_status"]) == {"partial", "failed"}
        assert regression["completed_forbidden"] is True


def test_evals_enforce_write_scope_locks_postchecks_and_no_false_success() -> None:
    for entry in catalog():
        slug = entry["slug"]
        data = load_json(SKILLS_ROOT / slug / "evals" / "assertions.json")
        assert data["schema_version"] == "1.0.0"
        assert data["skill"] == slug
        assert [evaluation["id"] for evaluation in data["evals"]] == EVAL_IDS
        evaluations = {item["id"]: item for item in data["evals"]}
        assert {item["scenario"] for item in data["evals"]} <= set(SCENARIO_IDS)

        degradation = assertions_by_kind(evaluations["graceful_degradation"])
        assert degradation == {
            "status": "blocked_by_capability",
            "dependency_report_required": True,
            "false_success_forbidden": True,
        }
        write_policy = assertions_by_kind(evaluations["write_policy"])
        assert write_policy == {
            "mutating_tool_calls": False,
            "commit": False,
            "transactions_empty": True,
        }
        preview = assertions_by_kind(evaluations["preview_and_post_checks"])
        expected_order = WRITE_ORDER if entry["mode"] == "preview_write" else [
            "no_design_write"
        ]
        assert preview["write_order"] == expected_order
        assert preview["minimal_post_checks"] == entry.get("post_checks", [])
        assert preview["document_check_matrix"] == {
            "schematic": ["run_erc", "run_connectivity_check"],
            "pcb": ["run_drc", "run_connectivity_check"],
            "mixed": ["run_erc", "run_drc", "run_connectivity_check"],
        }
        scope = assertions_by_kind(evaluations["scope_and_locks"])
        assert scope == {
            "changed_ids_subset_scope": True,
            "changed_ids_disjoint_locked": True,
            "stale_sha_commit": False,
        }
        output = assertions_by_kind(evaluations["output_validation"])
        assert output == {
            "json_schema": "schemas/result.schema.json",
            "additional_properties": False,
            "resource_uri_for_large_output": True,
        }
        false_success = assertions_by_kind(evaluations["no_false_success"])
        assert false_success == {
            "completed_on_regression": False,
            "completed_with_mandatory_skip": False,
            "rollback_evidence_on_failed_postcheck": True,
        }

        _, body = parse_frontmatter(SKILLS_ROOT / slug / "SKILL.md")
        write_section = body.split("## Write policy", 1)[1].split(
            "## Dependency contracts", 1
        )[0]
        if entry["mode"] == "preview_write":
            markers = [
                "`diptrace_status`, then `get_capabilities`",
                "freeze its source SHA-256",
                "locked objects",
                "`begin_transaction(",
                "`preview_transaction`",
                "`validate_transaction`",
                "explicit confirmation",
                "Re-read document identity",
                "`rollback_transaction(",
            ]
            marker_positions = [write_section.index(marker) for marker in markers]
            assert marker_positions == sorted(marker_positions), f"{slug}: unsafe write order"
            assert "`allow_locked`" in write_section
            assert (
                "`commit_transaction(txid, expected_sha256=<validated source SHA-256>)`"
                in write_section
            )
            assert "pass `dry_run=true`" in write_section
            assert "always run `run_connectivity_check`" in write_section
            assert "run `run_erc`" in write_section
            assert "run `run_drc`" in write_section
            assert "Preview generation is not authorization to commit" in write_section
            assert entry["post_checks"]
            for check in entry["post_checks"]:
                assert f"`{check}`" in write_section
        elif entry["mode"] == "read_only" and slug == "pcb-skill-evaluator":
            assert "disposable, isolated fixtures" in write_section
            assert "`execute_agent_fixture`" in write_section
            assert "`rollback_transaction`" in write_section
            assert "never writes the selected user design" in write_section
            assert "Keep this skill result's `transactions` empty" in write_section
        elif entry["mode"] == "read_only":
            assert "read-only by default" in write_section
            assert "Do not call mutating tools" in write_section
            assert "keep `transactions` empty" in write_section
        else:
            assert "must not mutate the source design" in write_section
            assert "Artifact generation does not authorize a design commit" in write_section

        assert "Never return `completed` with a missing mandatory check" in body
        assert "Locked object, keepout, waiver, DNP" in body
        assert "Stop on any regression" in body or entry["mode"] != "preview_write"


def test_generated_skill_packages_are_current() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_pcb_skills.py"), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "verified 57 PCB skill packages"
