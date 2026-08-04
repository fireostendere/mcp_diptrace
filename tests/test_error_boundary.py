from __future__ import annotations

import asyncio
import json
from pathlib import Path

from diptrace_mcp.config import Settings
from diptrace_mcp.error_boundary import (
    exception_to_error_result,
    wrap_tool_callable,
)
from diptrace_mcp.errors import InvalidArgumentError, ObjectNotFoundError
from diptrace_mcp.server import create_server


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


def test_unexpected_exception_does_not_cross_boundary() -> None:
    def broken() -> None:
        raise KeyError("internal secret")

    result = wrap_tool_callable(broken, "test_tool")()

    assert result["ok"] is False
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(result).casefold()
    assert "traceback" not in json.dumps(result).casefold()


def test_typed_invalid_argument_is_bounded_as_invalid_argument() -> None:
    def invalid() -> None:
        raise InvalidArgumentError("unsupported unit: furlong")

    result = wrap_tool_callable(invalid, "units_tool")()

    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert result["error"]["retryable"] is False


def test_unexpected_value_error_is_internal_not_user_error() -> None:
    def broken() -> None:
        raise ValueError("internal invariant details")

    result = wrap_tool_callable(broken, "broken_tool")()

    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert "invariant details" not in json.dumps(result)


def test_async_tool_uses_the_same_contract() -> None:
    async def broken() -> None:
        raise AssertionError("invariant details")

    result = asyncio.run(wrap_tool_callable(broken, "async_tool")())

    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert result["error"]["details"] == {}


def test_registered_tool_uses_the_public_boundary(tmp_path: Path) -> None:
    settings = Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / "state",
    )
    server = create_server(settings)
    tool = server._tool_manager._tools["get_document_info"]

    result = asyncio.run(tool.fn(str(tmp_path / "missing.xml")))

    assert result.isError is True
    assert result.structuredContent is not None
    assert result.structuredContent["ok"] is False
    assert result.structuredContent["error"]["code"] == "OBJECT_NOT_FOUND"
    assert getattr(tool.fn, "__diptrace_mcp_thread_offload__", False) is True
    assert tool.is_async is True
    serialized = json.dumps(result.structuredContent)
    assert "Traceback" not in serialized
    assert str(tmp_path) not in serialized
