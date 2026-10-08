from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult

from diptrace_mcp.config import Settings
from diptrace_mcp.error_boundary import exception_to_error_result
from diptrace_mcp.errors import EditError, InvalidArgumentError, ObjectNotFoundError
from diptrace_mcp.server import create_server
from diptrace_mcp.server_inputs import DipTraceFastMCP


def test_domain_error_has_stable_code_and_redacted_details() -> None:
    result = exception_to_error_result(
        ObjectNotFoundError(
            "No object at /home/private/board.xml",
            details={
                "path": "/home/private/board.xml",
                "object_id": "component_1",
                "xml": "<Component Secret='no'>...</Component>",
            },
        )
    )

    assert result == {
        "ok": False,
        "error": {
            "code": "OBJECT_NOT_FOUND",
            "message": "No object at [path redacted]",
            "details": {"object_id": "component_1"},
            "retryable": False,
        },
    }
    json.dumps(result)


def _call_boundary(function: Any) -> dict[str, Any]:
    """Register one tool on the project server class and call it like a client."""

    server = DipTraceFastMCP(name="boundary-test", version="0")
    server.tool()(function)
    result = asyncio.run(server.call_tool(function.__name__, {}))
    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert isinstance(result.structuredContent, dict)
    return result.structuredContent


def test_unexpected_exception_does_not_cross_boundary() -> None:
    def broken() -> None:
        raise KeyError("internal secret")

    result = _call_boundary(broken)

    assert result["ok"] is False
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(result).casefold()
    assert "traceback" not in json.dumps(result).casefold()


def test_typed_invalid_argument_is_bounded_as_invalid_argument() -> None:
    def invalid() -> None:
        raise InvalidArgumentError("unsupported unit: furlong")

    result = _call_boundary(invalid)

    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["retryable"] is False


def test_connectivity_conflict_uses_existing_public_conflict_code() -> None:
    result = exception_to_error_result(
        EditError("Pin is not on the requested net", code="connectivity_conflict")
    )

    assert result["error"]["code"] == "CONFLICT"
    assert result["error"]["retryable"] is True


def test_unexpected_value_error_is_internal_not_user_error() -> None:
    def broken() -> None:
        raise ValueError("internal invariant details")

    result = _call_boundary(broken)

    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert "invariant details" not in json.dumps(result)


def test_async_tool_uses_the_same_contract() -> None:
    async def broken() -> None:
        raise AssertionError("invariant details")

    result = _call_boundary(broken)

    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["error"]["details"] == {
        "exception_type": "AssertionError",
        "see": "server stderr log",
    }
    assert "invariant details" not in json.dumps(result)


def test_registered_tool_uses_the_public_boundary(tmp_path: Path) -> None:
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    server = create_server(settings)

    result = asyncio.run(
        server.call_tool("get_document_info", {"path": str(tmp_path / "missing.xml")})
    )

    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["ok"] is False
    assert result.structuredContent["error"]["code"] == "OBJECT_NOT_FOUND"
    serialized = json.dumps(result.structuredContent)
    assert "Traceback" not in serialized
    assert str(tmp_path) not in serialized
