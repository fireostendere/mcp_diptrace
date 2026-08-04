# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


error_boundary = Path("src/diptrace_mcp/error_boundary.py")
replace_once(
    error_boundary,
    "from functools import wraps\n",
    "from functools import partial, wraps\n",
)
replace_once(
    error_boundary,
    "from typing import Any, TypeVar, cast\n\nfrom mcp import types\n",
    "from typing import Any, TypeVar, cast\n\nimport anyio\nfrom mcp import types\n",
)
replace_once(
    error_boundary,
    "    mcp_result: bool = False,\n) -> _F:\n",
    "    mcp_result: bool = False,\n    offload_sync: bool = False,\n) -> _F:\n",
)
replace_once(
    error_boundary,
    """    @wraps(function)
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
""",
    """    if offload_sync:

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
""",
)

server = Path("src/diptrace_mcp/server.py")
replace_once(
    server,
    "        tool.fn = wrap_tool_callable(tool.fn, tool.name, mcp_result=True)\n\n        original_validate = tool.fn_metadata.call_fn_with_arg_validation\n",
    """        tool.fn = wrap_tool_callable(
            tool.fn,
            tool.name,
            mcp_result=True,
            offload_sync=True,
        )
        if getattr(tool.fn, "__diptrace_mcp_thread_offload__", False):
            object.__setattr__(tool, "is_async", True)

        original_validate = tool.fn_metadata.call_fn_with_arg_validation
""",
)

boundary_test = Path("tests/test_error_boundary.py")
replace_once(
    boundary_test,
    "    result = tool.fn(str(tmp_path / \"missing.xml\"))\n\n    assert result.isError is True\n",
    "    result = asyncio.run(tool.fn(str(tmp_path / \"missing.xml\")))\n\n    assert result.isError is True\n",
)
replace_once(
    boundary_test,
    "    assert result.structuredContent[\"error\"][\"code\"] == \"OBJECT_NOT_FOUND\"\n",
    "    assert result.structuredContent[\"error\"][\"code\"] == \"OBJECT_NOT_FOUND\"\n    assert getattr(tool.fn, \"__diptrace_mcp_thread_offload__\", False) is True\n    assert tool.is_async is True\n",
)

readme = Path("README.md")
replace_once(
    readme,
    "The synchronous FastMCP worker-thread contract and connected responsiveness probes are documented in [Async Execution and Event-Loop Safety](docs/ASYNC_EXECUTION.md).",
    "The project-owned worker-thread boundary around FastMCP v1 and connected responsiveness probes are documented in [Async Execution and Event-Loop Safety](docs/ASYNC_EXECUTION.md).",
)
readme_ru = Path("README_RU.md")
replace_once(
    readme_ru,
    "Синхронный worker-thread контракт FastMCP и connected responsiveness-тесты описаны в [Async Execution and Event-Loop Safety](docs/ASYNC_EXECUTION.md).",
    "Проектный worker-thread boundary вокруг FastMCP v1 и connected responsiveness-тесты описаны в [Async Execution and Event-Loop Safety](docs/ASYNC_EXECUTION.md).",
)

testing = Path("docs/TESTING.md")
replace_once(
    testing,
    "The public MCP tools intentionally remain synchronous callables. FastMCP\nexecutes that surface through its AnyIO worker-thread boundary. The static\nregistry audit rejects an accidental async tool until it receives an explicit\nnon-blocking review, while connected protocol probes prove that synthetic\nblocking-I/O and CPU-heavy calls do not prevent an event-loop heartbeat. See\n[ASYNC_EXECUTION.md](ASYNC_EXECUTION.md) for cancellation and mutation limits.\n",
    "FastMCP v1 invokes synchronous tools directly from its async execution path.\nDipTrace MCP therefore replaces each registered synchronous callable with a\nproject-owned async wrapper that uses `anyio.to_thread.run_sync`. The registry\naudit requires that boundary on every public tool, while connected protocol\nprobes prove that synthetic blocking-I/O and CPU-heavy calls do not prevent an\nevent-loop heartbeat. See [ASYNC_EXECUTION.md](ASYNC_EXECUTION.md) for\ncancellation, GIL, process-worker, and mutation limits.\n",
)
