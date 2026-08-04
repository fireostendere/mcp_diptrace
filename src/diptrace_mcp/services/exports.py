from __future__ import annotations

from typing import Any, Literal

from ..errors import (
    CapabilityUnavailableError,
)
from ..exports import (
    ExportStore,
    create_bom_export,
    create_release_manifest,
    export_resources,
)
from .context import DocumentGateway, ServiceContext, read_success


class ExportService:
    def __init__(
        self, context: ServiceContext, gateway: DocumentGateway, export_store: ExportStore
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.export_store = export_store

    def export_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        record = create_bom_export(self.export_store, snapshot, include_dnp=include_dnp)
        return read_success(
            snapshot.info,
            {"export": record.model_dump(mode="json")},
            resources=export_resources(record),
            limitations=record.limitations,
        )

    def export_fabrication_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        if request_native_outputs:
            raise CapabilityUnavailableError(
                "Authoritative Gerber/NC drill export is unavailable from confirmed XML semantics. "
                "Call with request_native_outputs=false to create a review manifest bundle.",
                details={"not_generated": ["gerber", "nc_drill", "odb++", "ipc-2581"]},
            )
        return self._export_release_manifest(
            path,
            export_type="fabrication_manifest",
            include_dnp=include_dnp,
        )

    def export_assembly_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = False,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        if request_native_outputs:
            raise CapabilityUnavailableError(
                "Authoritative vendor-specific assembly output is unavailable. "
                "Call with request_native_outputs=false for generic placement and BOM artifacts.",
                details={"not_generated": ["vendor_cpl", "assembly_drawing"]},
            )
        return self._export_release_manifest(
            path,
            export_type="assembly_manifest",
            include_dnp=include_dnp,
        )

    def _export_release_manifest(
        self,
        path: str | None,
        *,
        export_type: Literal["fabrication_manifest", "assembly_manifest"],
        include_dnp: bool,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        record = create_release_manifest(
            self.export_store,
            snapshot,
            export_type=export_type,
            include_dnp=include_dnp,
        )
        return read_success(
            snapshot.info,
            {"export": record.model_dump(mode="json")},
            resources=export_resources(record),
            limitations=record.limitations,
        )

    def list_exports(self) -> dict[str, Any]:
        records = self.export_store.list()
        return {
            "ok": True,
            "document": None,
            "result": {
                "matched_count": len(records),
                "exports": [record.model_dump(mode="json") for record in records],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def export_resource(self, export_id: str, artifact: str) -> str:
        return self.export_store.artifact(export_id, artifact).decode("utf-8", errors="strict")
