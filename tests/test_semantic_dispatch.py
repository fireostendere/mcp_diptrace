from __future__ import annotations

from diptrace_mcp import semantic_compiler
from diptrace_mcp.operations import _OPERATION_TYPES


def test_semantic_dispatch_covers_the_complete_operation_registry() -> None:
    registered = set(_OPERATION_TYPES.values())
    dispatched = set(semantic_compiler.SEMANTIC_OPERATION_HANDLERS)

    assert dispatched == registered, {
        "missing": sorted(item.__name__ for item in registered - dispatched),
        "unexpected": sorted(item.__name__ for item in dispatched - registered),
    }
    assert all(
        callable(handler)
        for handler in semantic_compiler.SEMANTIC_OPERATION_HANDLERS.values()
    )
