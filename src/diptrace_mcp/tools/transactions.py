"""Transaction lifecycle."""
from __future__ import annotations

from typing import Any

from ..operations import (
    StagedOperationInput,
)
from ..server_inputs import (
    DipTraceFastMCP,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def begin_transaction(
        path: str | None = None,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a transaction snapshot for a document or live session."""
        return service.begin_transaction(path, expected_sha256, notes)

    @mcp.tool()
    def stage_operations(
        txid: str,
        operations: list[StagedOperationInput],
    ) -> dict[str, Any]:
        """Attach registered semantic operations to an existing transaction."""
        return service.stage_operations(
            txid,
            [operation.model_dump() for operation in operations],
        )

    @mcp.tool()
    def preview_transaction(txid: str) -> dict[str, Any]:
        """Store preview artifacts and return bounded metadata without changing the design."""
        return service.preview_transaction(txid)

    @mcp.tool()
    def commit_transaction(txid: str, expected_sha256: str | None = None) -> dict[str, Any]:
        """Commit a staged transaction after verifying the source SHA-256."""
        return service.commit_transaction(txid, expected_sha256)

    @mcp.tool()
    def rollback_transaction(
        txid: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Restore a transaction snapshot or backup."""
        return service.rollback_transaction(txid, expected_sha256)

    @mcp.tool(
        capability_keys=[
            "write_capabilities.apply_component_placement_plan",
            "write_capabilities.apply_schematic_placement_repair_plan",
            "write_capabilities.apply_silkscreen_plan",
            "write_capabilities.apply_route_plan",
            "write_capabilities.autorouter_ses_import",
        ]
    )
    def apply_plan(
        plan_id: str,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Stage or commit a stored placement, repair, silkscreen, route or SES-import plan."""
        return service.apply_plan(
            plan_id,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def list_transactions() -> dict[str, Any]:
        """List persisted transaction ids, document hashes, states and operation counts."""
        return service.list_transactions()
