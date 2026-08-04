"""Schematic-to-PCB comparison and guarded synchronization plans."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from ..design_compare import compare_schematic_to_pcb as compare_design_snapshots
from ..operations import SemanticOperation
from ..synchronization import ComponentSyncMapping, SyncPlacement, build_sync_plan
from .context import DocumentGateway, ServiceContext, read_success

SemanticWrite = Callable[
    [SemanticOperation, str | None, bool, str | None, str | None],
    dict[str, Any],
]


class SynchronizationService:
    """Implementation for schematic/PCB comparison and synchronization."""

    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        semantic_write: SemanticWrite,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.semantic_write = semantic_write

    def compare_schematic_to_pcb(self, schematic_path: str, pcb_path: str) -> dict[str, Any]:
        schematic_document, schematic_target = self.gateway.load(schematic_path)
        pcb_document, pcb_target = self.gateway.load(pcb_path)
        schematic = self.context.model_cache.get(
            schematic_document, live_session=schematic_target.is_live
        )
        pcb = self.context.model_cache.get(pcb_document, live_session=pcb_target.is_live)
        result = compare_design_snapshots(schematic, pcb)
        return read_success(
            schematic.info,
            {
                **result,
                "pcb_document": pcb.info.model_dump(mode="json"),
            },
            limitations=result["limitations"],
        )

    def sync_schematic_to_pcb(
        self,
        schematic_path: str,
        pcb_path: str,
        *,
        component_mappings: list[dict[str, Any]] | None = None,
        placement: dict[str, Any] | None = None,
        pattern_library_paths: list[str] | None = None,
        update_existing_properties: bool = True,
        create_ratlines: bool = True,
        allow_reconnect: bool = False,
        reconciliation_mode: Literal["additive", "exact"] = "additive",
        allow_locked_reconciliation: bool = False,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        schematic_document, _ = self.gateway.load(schematic_path)
        pcb_document, _ = self.gateway.load(pcb_path)
        pattern_documents = [self.gateway.load(path)[0] for path in pattern_library_paths or []]
        plan = build_sync_plan(
            schematic_document,
            pcb_document,
            mappings=[
                ComponentSyncMapping.model_validate(item) for item in component_mappings or []
            ],
            placement=SyncPlacement.model_validate(placement or {}),
            pattern_documents=pattern_documents,
            update_existing_properties=update_existing_properties,
            create_ratlines=create_ratlines,
            allow_reconnect=allow_reconnect,
            reconciliation_mode=reconciliation_mode,
            allow_locked_reconciliation=allow_locked_reconciliation,
        )
        response = self.semantic_write(
            plan.operation,
            pcb_path,
            dry_run,
            expected_sha256,
            txid,
        )
        response["warnings"] = [*plan.warnings, *response.get("warnings", [])]
        response["limitations"] = [
            *plan.limitations,
            *response.get("limitations", []),
        ]
        response.setdefault("result", {})["schematic_source"] = {
            "path": str(schematic_document.path),
            "sha256": schematic_document.sha256,
        }
        return response
