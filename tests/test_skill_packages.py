from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest
from jsonschema import Draft202012Validator
from yaml import safe_load

from diptrace_mcp.errors import DocumentError
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
SERVER_PATHS = (
    ROOT / "src" / "diptrace_mcp" / "server.py",
    ROOT / "src" / "diptrace_mcp" / "server_runtime.py",
)
SURVIVORS = {
    "pcb-project-intake",
    "library-quality-audit",
    "schematic-erc-review",
    "testpoint-planner",
    "critical-net-router",
    "signal-integrity-review",
    "release-gate",
    "diptrace-evidence-capture",
}
EVIDENCE_CLASSES = {
    "caller",
    "document",
    "analytical",
    "heuristic",
    "external_solver",
    "operator",
}
TOOL_PREFIXES = (
    "add_",
    "analyze_",
    "apply_",
    "calculate_",
    "commit_",
    "find_",
    "get_",
    "list_",
    "plan_",
    "preview_",
    "record_",
    "review_",
    "route_",
    "run_",
    "validate_",
)
CLI_ALLOWLIST = {
    "abort",
    "check",
    "finalize",
    "init",
    "open_save",
    "record",
    "reexport",
    "resume",
    "source",
    "status",
}
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
BACKTICK_IDENTIFIER = re.compile(r"`([a-z][a-z0-9_]*)`")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def catalog() -> list[dict[str, Any]]:
    value = load_json(SKILLS_ROOT / "catalog.json")
    assert isinstance(value, list)
    return value


def registered_tools() -> set[str]:
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
        if any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        ):
            names.add(node.name)
    return names


def skill_files() -> list[Path]:
    return sorted(SKILLS_ROOT.glob("*/SKILL.md"))


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\n(?P<header>.*?)\n---\n(?P<body>.*)", text, re.DOTALL)
    assert match is not None, f"invalid frontmatter framing: {path}"
    metadata = safe_load(match.group("header"))
    assert isinstance(metadata, dict)
    assert set(metadata) == {"name", "description"}
    assert all(isinstance(value, str) and value for value in metadata.values())
    return metadata, match.group("body")


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def test_mechanical_survival_rule_produces_exactly_eight_distinct_skills() -> None:
    entries = catalog()
    assert 5 <= len(entries) <= 8
    assert len(entries) == 8
    assert {entry["slug"] for entry in entries} == SURVIVORS
    assert len({entry["trigger"] for entry in entries}) == 8
    assert (SKILLS_ROOT / "SURVIVAL_CRITERIA.md").exists()
    assert {path.parent.name for path in skill_files()} == SURVIVORS

    for entry in entries:
        metadata, body = parse_frontmatter(SKILLS_ROOT / entry["slug"] / "SKILL.md")
        assert metadata["name"] == entry["slug"]
        assert entry["trigger"] in metadata["description"]
        assert "../shared/result.schema.json" in body
        assert "public `tools/list` for exact callable names" in body
        assert "`get_capabilities` for" in body
        assert len(body.splitlines()) < 500


def test_consolidation_removes_duplicate_generated_package_artifacts() -> None:
    banned_directories = {"agents", "evals", "examples", "schemas"}
    for slug in SURVIVORS:
        package = SKILLS_ROOT / slug
        assert not any(
            path.is_dir() and path.name in banned_directories
            for path in package.rglob("*")
        )
        assert not (package / "README.md").exists()
    assert not list(SKILLS_ROOT.glob("*/schemas/result.schema.json"))
    assert (SKILLS_ROOT / "shared" / "result.schema.json").is_file()
    prose = "\n".join(path.read_text(encoding="utf-8") for path in SKILLS_ROOT.rglob("*.md"))
    assert "500 normalized physical" not in prose
    assert "500 physical objects" not in prose
    assert "500 conservatively counted affected" in prose


def test_every_catalog_capability_is_a_registered_public_tool() -> None:
    tools = registered_tools()
    for entry in catalog():
        assert set(entry["capabilities"]) <= tools, entry["slug"]
        if entry["mode"] == "preview_write":
            assert "rollback_transaction" in entry["capabilities"], entry["slug"]

    capability_map = load_json(SKILLS_ROOT / "capability-map.json")
    assert "tools/list for exact callable names" in capability_map["discovery_rule"]
    assert "get_capabilities for session, document, feature" in capability_map[
        "discovery_rule"
    ]
    for name, mapping in capability_map["runtime_tools"].items():
        assert mapping["runtime_tool"] in tools, name

    assert capability_map["runtime_tools"]["run_ngspice_simulation"][
        "runtime_tool"
    ] == "run_ngspice_simulation"
    assert capability_map["runtime_tools"]["run_openems_stripline_analysis"][
        "runtime_tool"
    ] == "run_openems_stripline_analysis"
    unavailable = capability_map["unavailable_contracts"]
    assert "run_ngspice_simulation" not in unavailable
    assert "run_openems_stripline_analysis" not in unavailable


def test_every_backticked_tool_like_name_is_real_or_explicit_cli() -> None:
    tools = registered_tools()
    errors: list[str] = []
    for path in [*skill_files(), *SKILLS_ROOT.rglob("references/*.md")]:
        text = path.read_text(encoding="utf-8")
        for token in BACKTICK_IDENTIFIER.findall(text):
            if token.startswith(TOOL_PREFIXES) and token not in tools | CLI_ALLOWLIST:
                errors.append(f"{path.relative_to(ROOT)}: {token}")
    assert not errors, "Unknown backticked tool-like names:\n" + "\n".join(errors)


def test_all_skill_relative_markdown_links_exist() -> None:
    missing: list[str] = []
    for path in SKILLS_ROOT.rglob("*.md"):
        for raw in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            value = unquote(raw.strip().split(maxsplit=1)[0])
            if not value or value.startswith(("#", "/", "~", "$")) or SCHEME.match(value):
                continue
            value = value.split("#", 1)[0].split("?", 1)[0]
            if value and not (path.parent / value).resolve().exists():
                missing.append(f"{path.relative_to(ROOT)}: {raw}")
    assert not missing, "Missing skill link targets:\n" + "\n".join(missing)


def test_shared_result_schema_is_strict_and_evidence_typed() -> None:
    schema = load_json(SKILLS_ROOT / "shared" / "result.schema.json")
    Draft202012Validator.check_schema(schema)
    assert set(schema["$defs"]["evidence_class"]["enum"]) == EVIDENCE_CLASSES
    assert schema["additionalProperties"] is False

    example = {
        "skill": "pcb-project-intake",
        "status": "completed",
        "summary": "Bounded inventory completed.",
        "document": {
            "path": "board.dip",
            "kind": "pcb",
            "sha256": "1" * 64,
        },
        "evidence": [
            {
                "id": "document-1",
                "evidence_class": "document",
                "claim": "Document identity was read.",
                "source": "get_document_info",
                "sha256": "1" * 64,
            }
        ],
        "findings": [],
        "measurements": [],
        "actions": [],
        "resources": [],
        "skipped_checks": [],
        "limits": [
            {
                "name": "page_limit",
                "value": 100,
                "source": "get_capabilities",
            }
        ],
    }
    Draft202012Validator(schema).validate(example)
    measurement = schema["properties"]["measurements"]["items"]
    assert measurement["additionalProperties"] is False
    assert "evidence_class" in measurement["required"]
    assert "evidence_ids" in measurement["required"]


def test_quantitative_skill_defaults_match_public_tool_schemas() -> None:
    tools = create_server()._tool_manager._tools
    testpoint = tools["find_testpoint_candidates"].parameters["properties"]
    assert testpoint["probe_diameter"]["default"] == 1.0
    assert testpoint["clearance"]["default"] == 0.5
    assert testpoint["grid"]["default"] == 2.54
    assert testpoint["candidates_per_net"]["default"] == 10

    text = (SKILLS_ROOT / "testpoint-planner" / "SKILL.md").read_text(encoding="utf-8")
    for expected in ("1.0 mm", "0.5 mm", "2.54 mm", "1 through 100", "5,000"):
        assert expected in text

    library = tools["query_library_items"].parameters["properties"]
    assert library["limit"]["default"] == 100
    DipTraceService._validate_page(0, 1)
    DipTraceService._validate_page(0, 500)
    for invalid in (0, 501):
        with pytest.raises(DocumentError, match="between 1 and 500"):
            DipTraceService._validate_page(0, invalid)
    library_text = (
        SKILLS_ROOT / "library-quality-audit" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "default to 100 records and accept 1 through 500" in library_text


def test_signal_integrity_scope_and_validity_claims_match_implementation() -> None:
    text = (
        SKILLS_ROOT / "signal-integrity-review" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "`microstrip`" in text
    assert "`differential_microstrip`" in text
    assert "`symmetric_stripline`" in text
    assert "Differential stripline: unavailable" in text
    assert "0.1 <= width/height <= 10" in text
    assert "gap/height >= 0.01" in text
    assert "0.01 <= width/height <= 100" in text
    assert "width/free_height < 0.35" in text
    assert "thickness/free_height < 0.25" in text
    assert "Finite copper thickness is not corrected in the coupled branch" in text
    assert "`get_stackup`" in text
    assert "get_physical_stackup" not in text
    assert "For openEMS retain request SHA-256, solver version, convergence" in text
    assert "For ngspice retain the netlist SHA-256, job status, return code/log summary" in text
    assert "exposes no executable version, convergence field, or result SHA-256" in text


def test_evidence_skill_preserves_stage_roles_and_confirmation_boundary() -> None:
    text = (
        SKILLS_ROOT / "diptrace-evidence-capture" / "SKILL.md"
    ).read_text(encoding="utf-8")
    ordered = [
        "**Candidate capture:**",
        "**Candidate finalization:**",
        "**Dry-run ingest:**",
        "**MCP validation:**",
        "**Explicit confirmation:**",
        "**Metadata record:**",
    ]
    positions = [text.index(marker) for marker in ordered]
    assert positions == sorted(positions)
    for role in ("`source`", "`open_save`", "`reexport`"):
        assert role in text
    assert "candidate_only=true" in text
    assert "never grants high trust" in text

    workflow = (
        SKILLS_ROOT
        / "diptrace-evidence-capture"
        / "references"
        / "operator-workflow.md"
    ).read_text(encoding="utf-8")
    assert workflow.index("--stage source") < workflow.index("--stage open_save")
    assert workflow.index("--stage open_save") < workflow.index("--stage reexport")
    assert workflow.index("validate_roundtrip_evidence") < workflow.index(
        "record_roundtrip_evidence"
    )
    assert "get_document_info" in workflow
    assert "explicit confirmation" in workflow
    assert "64-lowercase-hex-characters" in workflow


def test_evidence_cli_mirrors_are_exact_and_synthetic_forward_path_is_safe(
    tmp_path: Path,
) -> None:
    mirrors = {
        ROOT / "scripts" / "capture_diptrace_evidence.py": (
            SKILLS_ROOT
            / "diptrace-evidence-capture"
            / "scripts"
            / "capture_diptrace_evidence.py"
        ),
        ROOT / "scripts" / "ingest_fixtures.py": (
            SKILLS_ROOT
            / "diptrace-evidence-capture"
            / "scripts"
            / "ingest_fixtures.py"
        ),
    }
    for maintained, mirror in mirrors.items():
        assert mirror.read_bytes() == maintained.read_bytes()

    acceptance = ROOT / "tests" / "fixtures" / "acceptance"
    before = tree_hash(acceptance)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [
            sys.executable,
            str(mirrors[ROOT / "scripts" / "ingest_fixtures.py"]),
            "--dry-run",
            "--synthetic",
            "--json",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["synthetic"] is True
    assert payload["apply_available"] is False
    assert payload["trust"]["trust_promoted"] is False
    assert tree_hash(acceptance) == before


def test_generator_check_covers_links_capabilities_mirrors_and_hashes() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_pcb_skills.py"), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "8 skills" in completed.stdout
    assert "links, capabilities, mirrors, and hashes" in completed.stdout


def test_wheel_ships_only_the_consolidated_catalog_with_skill_payload_under_400_kib(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
            ".",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    wheels = list(tmp_path.glob("diptrace_mcp-*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]

    source_files = {
        path.relative_to(SKILLS_ROOT).as_posix(): path.read_bytes()
        for path in SKILLS_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert sum(len(content) for content in source_files.values()) <= 400 * 1024
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        delivered = {
            name.removeprefix("diptrace_mcp/skills/"): archive.read(name)
            for name in names
            if name.startswith("diptrace_mcp/skills/") and not name.endswith("/")
        }
        extract_root = tmp_path / "installed"
        archive.extractall(extract_root)
    assert delivered == source_files
    assert not any("/agents/" in name or "/evals/" in name for name in names)

    installed_skills = extract_root / "diptrace_mcp" / "skills"
    broken: list[str] = []
    for path in installed_skills.rglob("*.md"):
        for raw in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            value = unquote(raw.strip().split(maxsplit=1)[0])
            if not value or value.startswith(("#", "/", "~", "$")) or SCHEME.match(value):
                continue
            value = value.split("#", 1)[0].split("?", 1)[0]
            resolved = (path.parent / value).resolve()
            try:
                resolved.relative_to(installed_skills.resolve())
            except ValueError:
                broken.append(f"{path.relative_to(installed_skills)}: escapes wheel: {raw}")
                continue
            if not resolved.exists():
                broken.append(f"{path.relative_to(installed_skills)}: missing: {raw}")
    assert not broken, "Broken installed skill links:\n" + "\n".join(broken)
