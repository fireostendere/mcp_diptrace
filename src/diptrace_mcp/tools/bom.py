"""BOM reads, BOM review and generic export artifacts."""
from __future__ import annotations

from typing import Any

from ..server_inputs import (
    DipTraceFastMCP,
    ExternalBomRecordInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def get_bom(
        path: str | None = None,
        grouped: bool = False,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        """Return a normalized schematic or PCB BOM with multi-part RefDes deduplication."""
        return service.get_bom(path, grouped=grouped, include_dnp=include_dnp)

    @mcp.tool()
    def review_bom(path: str | None = None) -> dict[str, Any]:
        """Review BOM identity, DNP and value/pattern/MPN consistency."""
        return service.review_bom(path)

    @mcp.tool()
    def compare_bom_to_design(
        external_records: list[ExternalBomRecordInput],
        path: str | None = None,
    ) -> dict[str, Any]:
        """Compare typed external BOM rows with normalized design records by RefDes."""
        return service.compare_bom_to_design(
            [record.model_dump() for record in external_records],
            path=path,
        )

    @mcp.tool()
    def find_missing_component_fields(
        required_fields: list[str], path: str | None = None
    ) -> dict[str, Any]:
        """Find components missing explicit required BOM fields."""
        return service.find_missing_component_fields(required_fields, path=path)

    @mcp.tool()
    def export_bom(
        path: str | None = None, include_dnp: bool = True
    ) -> dict[str, Any]:
        """Export a generic UTF-8 CSV BOM and provenance manifest as bounded resources."""
        return service.export_bom(path, include_dnp=include_dnp)

    @mcp.tool()
    def export_fabrication_outputs(
        path: str | None = None,
        include_dnp: bool = True,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        """Export a release-review manifest; native Gerber/drill requests fail explicitly."""
        return service.export_fabrication_outputs(
            path,
            include_dnp=include_dnp,
            request_native_outputs=request_native_outputs,
        )

    @mcp.tool()
    def export_assembly_outputs(
        path: str | None = None,
        include_dnp: bool = False,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        """Export generic BOM/placement artifacts; vendor-native requests fail explicitly."""
        return service.export_assembly_outputs(
            path,
            include_dnp=include_dnp,
            request_native_outputs=request_native_outputs,
        )

    @mcp.tool()
    def list_exports() -> dict[str, Any]:
        """List persistent export records without exposing state-directory paths."""
        return service.list_exports()
