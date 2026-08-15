from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp import __version__, server_runtime
from diptrace_mcp.config import Settings

ROOT = Path(__file__).parents[1]


def test_frozen_server_delegates_to_production_main() -> None:
    source = (ROOT / "src/diptrace_mcp/frozen_server.py").read_text(encoding="utf-8")

    assert "from diptrace_mcp.server import main" in source
    assert "server.run" not in source


def test_server_spec_is_explicit_and_uses_onedir_collect() -> None:
    spec = (ROOT / "packaging/diptrace_mcp_server.spec").read_text(encoding="utf-8")

    assert "Analysis(" in spec
    assert "COLLECT(" in spec
    assert 'name="diptrace_mcp_server"' in spec
    assert 'collect_submodules(\n        "mcp.server",' in spec
    assert 'collect_submodules(\n        "mcp.shared",' in spec
    assert 'collect_submodules("diptrace_mcp")' in spec
    assert 'copy_metadata("mcp")' in spec
    assert "tests" not in spec.split("excludes =", 1)[1].split("]", 1)[0]
    assert "onefile" not in spec.lower()


def test_packaging_constraints_pin_pyinstaller_and_geometry_inputs() -> None:
    constraints = (ROOT / "packaging/windows-constraints.txt").read_text(encoding="utf-8")

    assert "pyinstaller==6.14.2" in constraints
    assert "shapely==2.1.2" in constraints
    assert "mcp==1.28.1" in constraints


def test_server_version_contract_is_stable() -> None:
    assert __version__ == "0.3.0"


def test_runtime_registry_is_json_and_spec_does_not_collect_forbidden_sources() -> None:
    registry = json.loads(
        (ROOT / "src/diptrace_mcp/data/trusted_provenance_registry.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(registry, dict)
    spec = (ROOT / "packaging/diptrace_mcp_server.spec").read_text(encoding="utf-8")
    assert "tests/fixtures" not in spec
    assert "reference/diptrace-xml/sources" not in spec
    assert "reference/diptrace-xml/extracted_text" not in spec


def test_skill_data_destinations_are_directories_without_filename_duplication() -> None:
    spec = (ROOT / "packaging/diptrace_mcp_server.spec").read_text(encoding="utf-8")

    assert "relative.parent" in spec
    assert "relative_to(directory).as_posix()" not in spec


def _resolve_schema(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if not isinstance(ref, str):
        return schema
    assert ref.startswith("#/")
    value: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[token]
    assert isinstance(value, dict)
    return value


def _schema_sample(schema: dict[str, Any], root: dict[str, Any]) -> Any:
    schema = _resolve_schema(schema, root)
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return next((value for value in enum if value is not None), enum[0])
    for union_key in ("anyOf", "oneOf"):
        branches = schema.get(union_key)
        if isinstance(branches, list) and branches:
            branch = next(
                (
                    item
                    for item in branches
                    if isinstance(item, dict) and item.get("type") != "null"
                ),
                branches[0],
            )
            assert isinstance(branch, dict)
            return _schema_sample(branch, root)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0])
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        assert isinstance(properties, dict)
        assert isinstance(required, list)
        return {
            name: _schema_sample(properties[name], root)
            for name in required
            if name in properties and isinstance(properties[name], dict)
        }
    if schema_type == "array":
        minimum = int(schema.get("minItems", 0))
        item_schema = schema.get("items", {})
        assert isinstance(item_schema, dict)
        return [_schema_sample(item_schema, root) for _ in range(minimum)]
    if schema_type == "boolean":
        return False
    if schema_type == "integer":
        if "minimum" in schema:
            return int(schema["minimum"])
        if "exclusiveMinimum" in schema:
            return int(schema["exclusiveMinimum"]) + 1
        return 1
    if schema_type == "number":
        if "minimum" in schema:
            return float(schema["minimum"])
        if "exclusiveMinimum" in schema:
            return float(schema["exclusiveMinimum"]) + 1.0
        return 1.0
    if schema_type == "string" or schema_type is None:
        pattern = str(schema.get("pattern", ""))
        if "0-9a-f" in pattern and "64" in pattern:
            return "0" * 64
        minimum = max(1, int(schema.get("minLength", 1)))
        return "x" * minimum
    raise AssertionError(f"Unsupported JSON schema shape: {schema!r}")


def _minimal_tool_payload(schema: dict[str, Any]) -> dict[str, Any]:
    value = _schema_sample(schema, schema)
    assert isinstance(value, dict)
    return value


class _RecordingService:
    instance: _RecordingService | None = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.calls: list[str] = []
        type(self).instance = self

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(name)
            if name == "finish_live_session":
                return {
                    "session_id": "session",
                    "requested_action": "apply",
                    "requested_at": "2026-08-10T00:00:00Z",
                    "expected_sha256": "0" * 64,
                    "outcome": "not_acknowledged",
                    "local_bridge_status": "active",
                    "written": False,
                    "diptrace_host_acknowledged": False,
                    "acknowledgement_scope": "local_bridge_exchange_only",
                    "message": "synthetic delegation probe",
                }
            if name == "abandon_live_session":
                return {
                    "session_id": "session",
                    "outcome": "abandoned",
                    "local_bridge_status": "abandoned",
                    "written": False,
                    "reason": "synthetic",
                    "diptrace_host_acknowledged": False,
                    "acknowledgement_scope": "local_session_state_only",
                    "message": "synthetic delegation probe",
                }
            return {"ok": True, "method": name}

        return call


def test_every_public_tool_wrapper_reaches_the_service_with_schema_valid_input(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Exercise the real FastMCP/Pydantic wrapper surface without domain side effects."""

    async def verify() -> None:
        monkeypatch.setattr(server_runtime, "DipTraceService", _RecordingService)
        settings = Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / "state",
        )
        server = server_runtime.create_server(settings)
        service = _RecordingService.instance
        assert service is not None

        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=10),
        ) as session:
            listed = await session.list_tools()
            exercised: list[str] = []
            not_delegated: list[str] = []
            for tool in listed.tools:
                before = len(service.calls)
                payload = _minimal_tool_payload(tool.inputSchema)
                await session.call_tool(tool.name, payload)
                if len(service.calls) > before:
                    exercised.append(tool.name)
                else:
                    not_delegated.append(tool.name)

        assert len(listed.tools) >= 150
        assert len(exercised) >= 150, not_delegated

    asyncio.run(verify())
