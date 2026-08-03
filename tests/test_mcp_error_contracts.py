from __future__ import annotations

import asyncio
import inspect
import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import CallToolResult

from diptrace_mcp.config import Settings
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"


def _settings(state_dir: Path) -> Settings:
    return Settings(
        workspace=FIXTURES,
        allowed_roots=(FIXTURES,),
        state_dir=state_dir,
    )


def _assert_wire_error(
    result: CallToolResult,
    expected_code: str,
    *,
    state_dir: Path,
) -> None:
    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert isinstance(result.structuredContent, dict)
    assert result.structuredContent["ok"] is False
    assert result.structuredContent["error"]["code"] == expected_code

    text_items = [item for item in result.content if getattr(item, "type", None) == "text"]
    assert len(text_items) == 1
    decoded = json.loads(text_items[0].text)
    assert decoded == result.structuredContent

    serialized = json.dumps(result.model_dump(mode="json"), sort_keys=True)
    assert "CallToolResult" not in serialized
    assert "Traceback" not in serialized
    assert str(state_dir) not in serialized
    assert "/tmp/fixture-secret/" not in serialized
    assert "INTERNAL_SECRET_VALUE" not in serialized


async def _call(
    state_dir: Path,
    name: str,
    arguments: dict[str, Any],
) -> CallToolResult:
    server = create_server(_settings(state_dir))
    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
    ) as session:
        result = await session.call_tool(name, arguments)
    assert isinstance(result, CallToolResult)
    return result


def test_missing_document_is_bounded_through_connected_mcp_session(tmp_path: Path) -> None:
    async def verify() -> None:
        result = await _call(
            tmp_path / "missing-document-state",
            "get_document_info",
            {"path": "missing.xml"},
        )
        _assert_wire_error(
            result,
            "OBJECT_NOT_FOUND",
            state_dir=tmp_path / "missing-document-state",
        )

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("validate_impedance_constraints", {}),
        (
            "get_board_model",
            {"path": "pcb.xml", "section": "traces", "limit": "bad"},
        ),
        (
            "validate_impedance_constraints",
            {
                "constraints": [
                    {
                        "net": "N",
                        "layer": "0",
                        "target_ohm": math.nan,
                    }
                ]
            },
        ),
        (
            "validate_roundtrip_evidence",
            {
                "path": "pcb.xml",
                "evidence": {
                    "source": {
                        "path": "source.xml",
                        "sha256": "0" * 64,
                        "extra": "forbidden",
                    },
                    "saved": {"path": "saved.xml", "sha256": "1" * 64},
                },
            },
        ),
    ],
)
def test_schema_failures_are_invalid_argument_through_connected_session(
    name: str,
    arguments: dict[str, Any],
    tmp_path: Path,
) -> None:
    async def verify() -> None:
        result = await _call(tmp_path / "schema-state", name, arguments)
        _assert_wire_error(result, "INVALID_ARGUMENT", state_dir=tmp_path / "schema-state")

    asyncio.run(verify())


def test_typed_domain_value_error_and_oserror_are_bounded_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def verify() -> None:
        typed = await _call(
            tmp_path / "typed-state",
            "get_document_info",
            {"path": "missing.xml"},
        )
        _assert_wire_error(typed, "OBJECT_NOT_FOUND", state_dir=tmp_path / "typed-state")

        def raise_value_error(self: DipTraceService, path: str | None = None) -> dict[str, Any]:
            raise ValueError("INTERNAL_SECRET_VALUE")

        monkeypatch.setattr(DipTraceService, "document_info", raise_value_error)
        value_error = await _call(
            tmp_path / "value-state",
            "get_document_info",
            {"path": "pcb.xml"},
        )
        _assert_wire_error(value_error, "INTERNAL_ERROR", state_dir=tmp_path / "value-state")

        def raise_os_error(self: DipTraceService, path: str | None = None) -> dict[str, Any]:
            raise OSError("/tmp/fixture-secret/SECRET_PATH")

        monkeypatch.setattr(DipTraceService, "document_info", raise_os_error)
        os_error = await _call(
            tmp_path / "os-state",
            "get_document_info",
            {"path": "pcb.xml"},
        )
        _assert_wire_error(os_error, "EXTERNAL_TOOL_ERROR", state_dir=tmp_path / "os-state")

        for exception, state_name in (
            (KeyError("INTERNAL_SECRET_KEY"), "key-state"),
            (AssertionError("INTERNAL_SECRET_ASSERTION"), "assert-state"),
        ):
            def raise_unexpected(
                self: DipTraceService,
                path: str | None = None,
                *,
                _exception: BaseException = exception,
            ) -> dict[str, Any]:
                raise _exception

            monkeypatch.setattr(DipTraceService, "document_info", raise_unexpected)
            result = await _call(
                tmp_path / state_name,
                "get_document_info",
                {"path": "pcb.xml"},
            )
            _assert_wire_error(
                result,
                "INTERNAL_ERROR",
                state_dir=tmp_path / state_name,
            )

    asyncio.run(verify())


def test_successful_tool_result_is_not_nested_by_boundary(tmp_path: Path) -> None:
    async def verify() -> None:
        fixture_root = FIXTURES.resolve()
        server = create_server(
            Settings(
                workspace=fixture_root,
                allowed_roots=(fixture_root,),
                state_dir=tmp_path / "success-state",
            )
        )
        async with create_connected_server_and_client_session(
            server,
            read_timeout_seconds=timedelta(seconds=10),
        ) as session:
            result = await session.call_tool(
                "get_document_info",
                {"path": "pcb.xml"},
            )
        assert isinstance(result, CallToolResult)
        assert result.isError is False
        assert isinstance(result.structuredContent, dict)
        assert result.structuredContent["ok"] is True
        assert not any(
            "CallToolResult" in str(item)
            for item in result.structuredContent.values()
        )

    asyncio.run(verify())


@pytest.mark.parametrize(
    ("group", "name", "arguments", "expected_code"),
    [
        ("document lookup", "get_document_info", {"path": "missing.xml"}, "OBJECT_NOT_FOUND"),
        (
            "units/numeric",
            "validate_impedance_constraints",
            {"constraints": [{"net": "N", "layer": "0", "target_ohm": 0}]},
            "INVALID_ARGUMENT",
        ),
        (
            "transactions",
            "commit_transaction",
            {"txid": "transaction_" + "0" * 16},
            "OBJECT_NOT_FOUND",
        ),
        (
            "routing",
            "route_connection",
            {
                "net": "VCC",
                "start_object_id": "missing-start",
                "end_object_id": "missing-end",
                "layer": "0",
                "width": 0.2,
                "path": "missing.xml",
            },
            "OBJECT_NOT_FOUND",
        ),
        ("review", "run_board_review", {"path": "missing.xml"}, "OBJECT_NOT_FOUND"),
        ("live-session", "finish_live_session", {"action": "cancel"}, "OBJECT_NOT_FOUND"),
        (
            "external adapter",
            "run_ngspice_simulation",
            {"netlist": ".end"},
            "EXTERNAL_TOOL_ERROR",
        ),
    ],
)
def test_representative_tool_groups_use_one_error_contract(
    group: str,
    name: str,
    arguments: dict[str, Any],
    expected_code: str,
    tmp_path: Path,
) -> None:
    async def verify() -> None:
        result = await _call(tmp_path / f"{group.replace(' ', '-')}-state", name, arguments)
        _assert_wire_error(
            result,
            expected_code,
            state_dir=tmp_path / f"{group.replace(' ', '-')}-state",
        )

    asyncio.run(verify())


def test_every_registered_tool_has_all_boundary_layers(tmp_path: Path) -> None:
    server = create_server(_settings(tmp_path / "registry-state"))
    tools = server._tool_manager._tools

    assert len(tools) == 159
    for tool in tools.values():
        assert getattr(tool.fn, "__diptrace_mcp_error_boundary__", False), tool.name
        assert getattr(
            tool.fn_metadata.call_fn_with_arg_validation,
            "__diptrace_mcp_validation_boundary__",
            False,
        ), tool.name
        assert getattr(tool.run, "__diptrace_mcp_run_boundary__", False), tool.name
        assert not inspect.iscoroutinefunction(inspect.unwrap(tool.fn)), tool.name
