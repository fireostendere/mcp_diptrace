from __future__ import annotations

import pytest

from diptrace_mcp import semantic_compiler
from diptrace_mcp.errors import EditError
from diptrace_mcp.operations import (
    _OPERATION_TYPES,
    MoveComponentsOperation,
    SemanticOperation,
)


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


def test_semantic_dispatch_preserves_exact_subclass_and_unsupported_behavior() -> None:
    exact = MoveComponentsOperation(dx=1.0)
    expected = semantic_compiler.SEMANTIC_OPERATION_HANDLERS[MoveComponentsOperation]
    assert semantic_compiler._semantic_operation_handler(exact) is expected

    class DerivedMoveComponentsOperation(MoveComponentsOperation):
        pass

    derived = DerivedMoveComponentsOperation(dx=1.0)
    assert semantic_compiler._semantic_operation_handler(derived) is expected

    unsupported = SemanticOperation(kind="not_registered")
    with pytest.raises(EditError, match="Unsupported semantic operation kind"):
        semantic_compiler._semantic_operation_handler(unsupported)
