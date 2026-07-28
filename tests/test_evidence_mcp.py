from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.config import Settings
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document
from diptrace_mcp.server import create_server


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _settings(workspace: Path) -> Settings:
    return Settings(
        workspace=workspace,
        allowed_roots=(workspace,),
        state_dir=workspace / ".state",
    )


def _write_roles(
    workspace: Path,
    *,
    source: bytes,
    saved: bytes,
    reexport: bytes,
) -> dict[str, Any]:
    workspace.mkdir()
    files = {
        "source.dip": source,
        "saved.dip": saved,
        "reexport.dip": reexport,
        "board.dip": reexport,
    }
    for name, data in files.items():
        (workspace / name).write_bytes(data)
    return {
        "source": {"path": "source.dip", "sha256": _sha256(source)},
        "saved": {"path": "saved.dip", "sha256": _sha256(saved)},
        "reexport": {"path": "reexport.dip", "sha256": _sha256(reexport)},
    }


async def _call_tool(
    settings: Settings,
    name: str,
    arguments: dict[str, Any],
) -> Any:
    server = create_server(settings)
    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
    ) as session:
        return await session.call_tool(name, arguments)


def _error_text(result: Any) -> str:
    return " ".join(
        str(getattr(item, "text", item))
        for item in result.content
    )


def test_evidence_tools_publish_typed_honest_schemas(tmp_path: Path) -> None:
    async def verify() -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        server = create_server(_settings(workspace))
        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=10),
        ) as session:
            tools = await session.list_tools()
            by_name = {tool.name: tool for tool in tools.tools}
            assert {
                "validate_roundtrip_evidence",
                "record_roundtrip_evidence",
            } <= by_name.keys()
            for name in (
                "validate_roundtrip_evidence",
                "record_roundtrip_evidence",
            ):
                schema = by_name[name].inputSchema
                assert schema["required"] == ["path", "evidence"]
                evidence_ref = schema["properties"]["evidence"]["$ref"]
                evidence_name = evidence_ref.rsplit("/", 1)[-1]
                evidence_schema = schema["$defs"][evidence_name]
                assert evidence_schema["required"] == ["source", "saved"]
                assert evidence_schema["additionalProperties"] is False
                role_ref = evidence_schema["properties"]["source"]["$ref"]
                role_name = role_ref.rsplit("/", 1)[-1]
                role_schema = schema["$defs"][role_name]
                assert role_schema["required"] == ["path", "sha256"]
                assert role_schema["properties"]["sha256"]["pattern"] == "^[0-9a-f]{64}$"
            assert "without writing" in (
                by_name["validate_roundtrip_evidence"].description or ""
            )
            record_description = (
                by_name["record_roundtrip_evidence"].description or ""
            )
            assert "not design bytes" in record_description
            assert "never grant high trust" in record_description

    asyncio.run(verify())


def test_validate_roundtrip_evidence_is_read_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    evidence = _write_roles(
        workspace,
        source=raw,
        saved=raw,
        reexport=raw,
    )
    original_files = {
        path.name: path.read_bytes()
        for path in workspace.glob("*.dip")
    }

    result = asyncio.run(
        _call_tool(
            _settings(workspace),
            "validate_roundtrip_evidence",
            {"path": "board.dip", "evidence": evidence},
        )
    )

    assert not result.isError
    payload = result.structuredContent
    assert payload is not None
    assert payload["ok"] is True
    assert payload["written"] is False
    assert payload["document_written"] is False
    assert payload["evidence_status"] == "recordable"
    assert payload["authority"] == "user_supplied"
    assert payload["grants_high_trust"] is False
    assert payload["semantic_comparison"]["passed"] is True
    assert payload["serialized_response_bytes"] <= payload["response_byte_limit"]
    assert {
        path.name: path.read_bytes()
        for path in workspace.glob("*.dip")
    } == original_files
    assert not (workspace / "board.dip.roundtrip-evidence.json").exists()
    assert not (workspace / "board.dip.provenance.json").exists()


def test_record_roundtrip_evidence_writes_only_untrusted_metadata(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    reordered = raw.replace(
        b'<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">',
        b'<Source Units="mm" Version="4.3.0.3" Type="DipTrace-PCB">',
        1,
    )
    assert reordered != raw
    evidence = _write_roles(
        workspace,
        source=raw,
        saved=reordered,
        reexport=reordered,
    )

    result = asyncio.run(
        _call_tool(
            _settings(workspace),
            "record_roundtrip_evidence",
            {"path": "board.dip", "evidence": evidence},
        )
    )

    assert not result.isError
    payload = result.structuredContent
    assert payload is not None
    assert payload["ok"] is True
    assert payload["written"] is True
    assert payload["document_written"] is False
    assert payload["evidence_status"] == "recorded"
    assert payload["authority"] == "user_supplied"
    assert payload["grants_high_trust"] is False
    assert (workspace / "board.dip").read_bytes() == reordered
    manifest_path = workspace / "board.dip.roundtrip-evidence.json"
    sidecar_path = workspace / "board.dip.provenance.json"
    manifest = json.loads(manifest_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())
    assert manifest["authority"] == "user_supplied"
    assert manifest["validation_level"] == "synthetic_operation_fixture"
    assert manifest["status"] == "recorded"
    assert manifest["semantic_comparison"]["ignored_normalizations"] == [
        "attribute_order"
    ]
    assert sidecar["authority"] == "user_supplied_evidence"
    assert sidecar["validation_level"] == "synthetic_operation_fixture"
    assert payload["evidence_manifest_sha256"] == _sha256(manifest_path.read_bytes())


def test_record_failed_semantic_comparison_stays_failed_and_untrusted(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    source = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    changed = build_pcb_document(PcbScaffold(width_mm=60.0, height_mm=30.0))
    evidence = _write_roles(
        workspace,
        source=source,
        saved=changed,
        reexport=changed,
    )

    result = asyncio.run(
        _call_tool(
            _settings(workspace),
            "record_roundtrip_evidence",
            {"path": "board.dip", "evidence": evidence},
        )
    )

    assert not result.isError
    payload = result.structuredContent
    assert payload is not None
    assert payload["ok"] is False
    assert payload["written"] is True
    assert payload["evidence_status"] == "failed"
    assert payload["grants_high_trust"] is False
    assert payload["semantic_comparison"]["passed"] is False
    manifest = json.loads(
        (workspace / "board.dip.roundtrip-evidence.json").read_text()
    )
    sidecar = json.loads((workspace / "board.dip.provenance.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["semantic_comparison"]["passed"] is False
    assert sidecar["provenance"] == "user_supplied_evidence_failed"
    assert sidecar["validation_level"] == "synthetic_operation_fixture"


def test_evidence_transport_rejects_tampered_sha_and_role_reuse(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    evidence = _write_roles(
        workspace,
        source=raw,
        saved=raw,
        reexport=raw,
    )
    evidence["source"]["sha256"] = "0" * 64
    tampered = asyncio.run(
        _call_tool(
            _settings(workspace),
            "validate_roundtrip_evidence",
            {"path": "board.dip", "evidence": evidence},
        )
    )
    assert tampered.isError
    assert "source SHA-256 mismatch" in _error_text(tampered)

    shared_evidence = {
        **evidence,
        "source": {
            "path": "saved.dip",
            "sha256": _sha256(raw),
        },
    }
    reused = asyncio.run(
        _call_tool(
            _settings(workspace),
            "record_roundtrip_evidence",
            {"path": "board.dip", "evidence": shared_evidence},
        )
    )
    assert reused.isError
    assert "must be different files" in _error_text(reused)
    assert not (workspace / "board.dip.roundtrip-evidence.json").exists()
    assert not (workspace / "board.dip.provenance.json").exists()


def test_evidence_transport_rejects_paths_outside_allowed_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    evidence = _write_roles(
        workspace,
        source=raw,
        saved=raw,
        reexport=raw,
    )
    outside = tmp_path / "outside.dip"
    outside.write_bytes(raw)
    evidence["source"] = {
        "path": str(outside),
        "sha256": _sha256(raw),
    }

    result = asyncio.run(
        _call_tool(
            _settings(workspace),
            "validate_roundtrip_evidence",
            {"path": "board.dip", "evidence": evidence},
        )
    )

    assert result.isError
    assert "outside allowed roots" in _error_text(result)
    assert not (workspace / "board.dip.roundtrip-evidence.json").exists()
    assert not (workspace / "board.dip.provenance.json").exists()
