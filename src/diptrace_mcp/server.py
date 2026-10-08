"""Stable executable/import seam for the MCP runtime."""
from __future__ import annotations

from . import server_runtime as _runtime
from .server_inputs import (
    _DRY_RUN_DESCRIPTION as _DRY_RUN_DESCRIPTION,
)
from .server_inputs import (
    DISTANCE_UNITS_DESCRIPTION as DISTANCE_UNITS_DESCRIPTION,
)
from .server_inputs import (
    ImpedanceConstraintInput as ImpedanceConstraintInput,
)
from .server_runtime import create_server as create_server


def main(argv: list[str] | None = None) -> None:
    _runtime.main(argv)


if __name__ == "__main__":
    main()
