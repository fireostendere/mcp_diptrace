"""Public MCP registrations, one module per domain."""
from . import (
    board,
    bom,
    components,
    documents,
    external,
    library,
    placement,
    prompts,
    resources,
    review,
    routing,
    schematic,
    signal_integrity,
    transactions,
)

# Registration order is the tools/list order clients see.
MODULES = (
    documents,
    library,
    bom,
    transactions,
    components,
    schematic,
    board,
    review,
    placement,
    routing,
    signal_integrity,
    external,
    resources,
    prompts,
)
