"""Safe, stable exception translation at the public MCP tool boundary."""

from __future__ import annotations

import inspect
import json
import logging
import math
import re
from collections.abc import Awaitable, Callable
from functools import partial, wraps
from typing import Any, TypeVar, cast

import anyio
from mcp import types
from pydantic import ValidationError

from .errors import DipTraceMcpError

logger = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable[..., Any])
_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/][^\s,;]+|/(?:[^\s,;]+/)+[^\s,;]*|\\\\[^\s,;]+)")
_XML_RE = re.compile(r"<[^>]{1,512}>")
_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "credential",
    "traceback",
    "stack",
    "raw_xml",
    "xml_content",
    "xml",
    "exception",
    "cause",
)
_PATH_KEY_PARTS = ("path", "filename", "username", "user_name")

_DOMAIN_CODE_MAP = {
    "invalid_argument": "INVALID_ARGUMENT",
    "scope_required": "INVALID_ARGUMENT",
    "ambiguous_selector": "INVALID_ARGUMENT",
    "geometry_invalid": "VALIDATION_ERROR",
    "schema_parse_error": "VALIDATION_ERROR",
    "schema_write_error": "VALIDATION_ERROR",
    "roundtrip_validation_failed": "VALIDATION_ERROR",
    "placement_illegal": "VALIDATION_ERROR",
    "routing_failed": "VALIDATION_ERROR",
    "connectivity_regression": "VALIDATION_ERROR",
    "drc_regression": "VALIDATION_ERROR",
    "insufficient_stackup_data": "VALIDATION_ERROR",
    "object_not_found": "OBJECT_NOT_FOUND",
    "document_not_found": "OBJECT_NOT_FOUND",
    "transaction_not_found": "OBJECT_NOT_FOUND",
    "no_active_session": "OBJECT_NOT_FOUND",
    "conflict": "CONFLICT",
    "transaction_conflict": "CONFLICT",
    "sha256_mismatch": "CONFLICT",
    "evidence_output_conflict": "CONFLICT",
    "connectivity_conflict": "CONFLICT",
    "confirmation_required": "SAFETY_GATE",
    "policy_denied": "SAFETY_GATE",
    "locked_object": "SAFETY_GATE",
    "safety_gate": "SAFETY_GATE",
    "path_access_denied": "SAFETY_GATE",
    "capability_unavailable": "UNSUPPORTED_OPERATION",
    "unsupported_operation": "UNSUPPORTED_OPERATION",
    "unknown_net_class": "VALIDATION_ERROR",
    "external_tool_unavailable": "EXTERNAL_TOOL_ERROR",
    "external_tool_failed": "EXTERNAL_TOOL_ERROR",
    "job_timeout": "EXTERNAL_TOOL_ERROR",
    "job_cancelled": "EXTERNAL_TOOL_ERROR",
    "internal_error": "INTERNAL_ERROR",
}
_NON_RETRYABLE_PUBLIC_CODES = {
    "INVALID_ARGUMENT",
    "OBJECT_NOT_FOUND",
    "VALIDATION_ERROR",
    "SAFETY_GATE",
    "UNSUPPORTED_OPERATION",
    "INTERNAL_ERROR",
}


def _safe_text(value: object, *, fallback: str = "") -> str:
    text = str(value)
    text = _XML_RE.sub("[XML content redacted]", text)
    text = _PATH_RE.sub("[path redacted]", text)
    return text[:512] if text else fallback


def _safe_key(key: object) -> str | None:
    candidate = str(key)
    lowered = candidate.casefold()
    if any(part in lowered for part in _SECRET_KEY_PARTS + _PATH_KEY_PARTS):
        return None
    return candidate[:128]


def _safe_value(value: object, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[details truncated]"
    if value is None or isinstance(value, (bool, int, str)):
        return _safe_text(value) if isinstance(value, str) else value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = _safe_key(key)
            if safe_key is not None:
                result[safe_key] = _safe_value(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:100]]
    return _safe_text(value)


def _validation_details(exc: ValidationError) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for item in exc.errors(include_url=False):
        location = [str(part) for part in item.get("loc", ())]
        errors.append(
            {
                "field": ".".join(location) if location else None,
                "type": str(item.get("type", "invalid")),
                "message": _safe_text(item.get("msg", "Invalid value")),
            }
        )
    return {"fields": errors[:100]}


def exception_to_error_result(exc: BaseException) -> dict[str, Any]:
    """Translate an exception without serializing its cause or implementation data."""

    if isinstance(exc, DipTraceMcpError):
        payload = exc.payload
        code = _DOMAIN_CODE_MAP.get(payload.code, "INTERNAL_ERROR")
        details = _safe_value(payload.details)
        if not isinstance(details, dict):
            details = {}
        if payload.object_ids:
            details.setdefault("object_ids", [str(item)[:256] for item in payload.object_ids[:100]])
        if payload.suggested_action:
            details.setdefault("suggested_action", _safe_text(payload.suggested_action))
        retryable = False if code in _NON_RETRYABLE_PUBLIC_CODES else bool(payload.recoverable)
        return {
            "ok": False,
            "error": {
                "code": code,
                "message": _safe_text(payload.message, fallback="The requested operation failed."),
                "details": details,
                "retryable": retryable,
            },
        }

    if isinstance(exc, ValidationError):
        return {
            "ok": False,
            "error": {
                "code": "INVALID_ARGUMENT",
                "message": "One or more arguments are invalid.",
                "details": _validation_details(exc),
                "retryable": False,
            },
        }

    if isinstance(exc, ValueError):
        return {
            "ok": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal validation failure occurred while executing the tool.",
                "details": {},
                "retryable": False,
            },
        }

    if isinstance(exc, OSError):
        return {
            "ok": False,
            "error": {
                "code": "EXTERNAL_TOOL_ERROR",
                "message": "A filesystem or external-tool operation failed.",
                "details": {},
                "retryable": True,
            },
        }

    return {
        "ok": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred while executing the tool.",
            "details": {},
            "retryable": False,
        },
    }


def error_result_to_mcp_result(result: dict[str, Any]) -> types.CallToolResult:
    """Render the stable envelope using MCP's native error bit as well."""

    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, sort_keys=True),
            )
        ],
        structuredContent=result,
        isError=True,
    )


def invoke_with_error_boundary(
    function: Callable[..., Any],
    tool_name: str,
    *args: Any,
    mcp_result: bool = False,
    **kwargs: Any,
) -> Any:
    """Call a synchronous service/tool function using the public error contract."""

    try:
        return function(*args, **kwargs)
    except Exception as exc:
        if not isinstance(exc, (DipTraceMcpError, ValidationError)):
            logger.exception("Unexpected failure in MCP tool %s", tool_name)
        result = exception_to_error_result(exc)
        return error_result_to_mcp_result(result) if mcp_result else result


def wrap_tool_callable(
    function: _F,
    tool_name: str,
    *,
    mcp_result: bool = False,
    offload_sync: bool = False,
) -> _F:
    """Wrap sync or async registered functions while preserving their signature."""

    if inspect.iscoroutinefunction(function):

        @wraps(function)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await cast(Awaitable[Any], function(*args, **kwargs))
            except Exception as exc:
                if not isinstance(exc, (DipTraceMcpError, ValidationError)):
                    logger.exception("Unexpected failure in MCP tool %s", tool_name)
                result = exception_to_error_result(exc)
                return error_result_to_mcp_result(result) if mcp_result else result

        wrapped = cast(_F, async_wrapper)
        cast(Any, wrapped).__diptrace_mcp_error_boundary__ = True
        return wrapped

    if offload_sync:

        @wraps(function)
        async def thread_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                call = partial(function, *args, **kwargs)
                return await anyio.to_thread.run_sync(
                    call,
                    abandon_on_cancel=False,
                )
            except Exception as exc:
                if not isinstance(exc, (DipTraceMcpError, ValidationError)):
                    logger.exception("Unexpected failure in MCP tool %s", tool_name)
                result = exception_to_error_result(exc)
                return error_result_to_mcp_result(result) if mcp_result else result

        wrapped = cast(_F, thread_wrapper)
        cast(Any, wrapped).__diptrace_mcp_error_boundary__ = True
        cast(Any, wrapped).__diptrace_mcp_thread_offload__ = True
        return wrapped

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return invoke_with_error_boundary(
            function,
            tool_name,
            *args,
            mcp_result=mcp_result,
            **kwargs,
        )

    wrapped = cast(_F, wrapper)
    cast(Any, wrapped).__diptrace_mcp_error_boundary__ = True
    return wrapped
