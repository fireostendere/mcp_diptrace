"""MCP resources."""
from __future__ import annotations

import json

from ..domain import QuerySelector
from ..errors import ObjectNotFoundError
from ..operations import (
    SetPanelizationOperation,
)
from ..routing import RouteConnectionConfig
from ..scaffolding import (
    PcbScaffold,
)
from ..schematic_ensemble import SchematicEnsembleConfig
from ..server_inputs import (
    _INPUT_SCHEMA_RESOURCE,
    DipTraceFastMCP,
)
from ..service import DipTraceService
from ..synchronization import ComponentSyncMapping, SyncPlacement


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.resource("diptrace://status", mime_type="application/json")
    def status_resource() -> str:
        """Current DipTrace MCP configuration and live-session state."""
        return json.dumps(service.status(), ensure_ascii=False, indent=2)

    @mcp.resource("diptrace://capabilities", mime_type="application/json")
    def capabilities_resource() -> str:
        """Current capability discovery payload."""
        return json.dumps(service.get_capabilities(), ensure_ascii=False, indent=2)

    @mcp.resource(
        "diptrace://trusted-provenance-registry",
        mime_type="application/json",
    )
    def trusted_provenance_registry_resource() -> str:
        """Repository-owned exact-hash trust registry and current entry count."""

        return json.dumps(
            service.trusted_provenance_registry_report(),
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource(_INPUT_SCHEMA_RESOURCE, mime_type="application/json")
    def tool_input_schemas_resource() -> str:
        """Catalog of schemas for intentionally non-inlined high-cost tool inputs."""
        return json.dumps(
            {
                "query_selector": QuerySelector.model_json_schema(),
                "pcb_scaffold": PcbScaffold.model_json_schema(),
                "component_sync_mapping": ComponentSyncMapping.model_json_schema(),
                "sync_placement": SyncPlacement.model_json_schema(),
                "panelization": SetPanelizationOperation.model_json_schema(),
                "route_connection": RouteConnectionConfig.model_json_schema(),
                "schematic_ensemble_config": SchematicEnsembleConfig.model_json_schema(),
            },
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource(
        "diptrace://document/{document_id}/summary",
        mime_type="application/json",
    )
    def document_summary_resource(document_id: str) -> str:
        """Normalized summary for a document registered by a prior tool call."""
        return service.document_resource(document_id, "summary")

    @mcp.resource(
        "diptrace://document/{document_id}/board-model",
        mime_type="application/json",
    )
    def document_board_model_resource(document_id: str) -> str:
        """Normalized PCB model for a registered document."""
        return service.document_resource(document_id, "board-model")

    @mcp.resource(
        "diptrace://document/{document_id}/schematic-model",
        mime_type="application/json",
    )
    def document_schematic_model_resource(document_id: str) -> str:
        """Normalized schematic model for a registered document."""
        return service.document_resource(document_id, "schematic-model")

    @mcp.resource(
        "diptrace://document/{document_id}/stackup",
        mime_type="application/json",
    )
    def document_stackup_resource(document_id: str) -> str:
        """Normalized physical PCB layer stack for a registered document."""
        return service.document_resource(document_id, "stackup")

    @mcp.resource(
        "diptrace://document/{document_id}/connectivity",
        mime_type="application/json",
    )
    def document_connectivity_resource(document_id: str) -> str:
        """Normalized connectivity graph with logical and unrouted data separated."""
        return service.document_resource(document_id, "connectivity")

    @mcp.resource(
        "diptrace://document/{document_id}/library-model",
        mime_type="application/json",
    )
    def document_library_model_resource(document_id: str) -> str:
        """Normalized component or pattern library model for a registered document."""
        return service.document_resource(document_id, "library-model")

    @mcp.resource(
        "diptrace://document/{document_id}/review/{report_id}",
        mime_type="application/json",
    )
    def document_review_resource(document_id: str, report_id: str) -> str:
        """Stored structured review report."""
        report = service.findings.read(report_id)
        if report.document_id != document_id:
            raise ObjectNotFoundError(
                "Review report is not associated with the requested document",
                details={"report_id": report_id},
            )
        return service.review_resource(report_id)

    @mcp.resource(
        "diptrace://document/{document_id}/findings",
        mime_type="application/json",
    )
    def document_findings_resource(document_id: str) -> str:
        """Stored review reports and findings for a document."""
        return service.findings_resource(document_id)

    @mcp.resource(
        "diptrace://transaction/{txid}/summary",
        mime_type="application/json",
    )
    def transaction_summary_resource(txid: str) -> str:
        """Transaction summary JSON."""
        return service.transaction_summary_resource(txid)

    @mcp.resource(
        "diptrace://transaction/{txid}/operations",
        mime_type="application/json",
    )
    def transaction_operations_resource(txid: str) -> str:
        """Transaction operations JSON."""
        return json.dumps(
            service.transactions.read(txid).operations,
            ensure_ascii=False,
            indent=2,
        )

    @mcp.resource("diptrace://transaction/{txid}/diff", mime_type="text/plain")
    def transaction_diff_resource(txid: str) -> str:
        """Transaction diff text."""
        path = service.transactions.diff_path(txid)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @mcp.resource("diptrace://transaction/{txid}/preview.svg", mime_type="image/svg+xml")
    def transaction_preview_svg_resource(txid: str) -> str:
        """Transaction preview SVG."""
        path = service.transactions.preview_svg_path(txid)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @mcp.resource(
        "diptrace://transaction/{txid}/preview.json",
        mime_type="application/json",
    )
    def transaction_preview_json_resource(txid: str) -> str:
        """Transaction preview geometry JSON."""
        path = service.transactions.preview_json_path(txid)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @mcp.resource(
        "diptrace://raw-preview/{preview_id}/diff",
        mime_type="text/plain",
    )
    def raw_preview_diff_resource(preview_id: str) -> str:
        """Bounded raw XML-edit diff stored outside the tool response."""
        return service.raw_preview_diff_resource(preview_id)

    @mcp.resource("diptrace://plan/{plan_id}/summary", mime_type="application/json")
    def plan_summary_resource(plan_id: str) -> str:
        """Stored semantic plan JSON."""
        return service.plan_resource(plan_id, "summary")

    @mcp.resource("diptrace://plan/{plan_id}/preview.svg", mime_type="image/svg+xml")
    def plan_preview_svg_resource(plan_id: str) -> str:
        """Stored plan preview SVG."""
        return service.plan_resource(plan_id, "preview.svg")

    @mcp.resource(
        "diptrace://plan/{plan_id}/preview.json",
        mime_type="application/json",
    )
    def plan_preview_json_resource(plan_id: str) -> str:
        """Stored plan preview geometry and candidate scores."""
        return service.plan_resource(plan_id, "preview.json")

    @mcp.resource("diptrace://plan/{plan_id}/diff", mime_type="text/plain")
    def plan_diff_resource(plan_id: str) -> str:
        """Stored plan XML diff."""
        return service.plan_resource(plan_id, "diff")

    @mcp.resource("diptrace://job/{jobid}/status", mime_type="application/json")
    def job_status_resource(jobid: str) -> str:
        """Persistent job status JSON."""
        return service.job_resource(jobid, "status")

    @mcp.resource("diptrace://job/{jobid}/result", mime_type="application/json")
    def job_result_resource(jobid: str) -> str:
        """Persistent job result JSON."""
        return service.job_resource(jobid, "result")

    @mcp.resource("diptrace://job/{jobid}/log", mime_type="text/plain")
    def job_log_resource(jobid: str) -> str:
        """Bounded external job log."""
        return service.job_resource(jobid, "log")

    @mcp.resource("diptrace://job/{jobid}/input.dsn", mime_type="text/plain")
    def job_dsn_resource(jobid: str) -> str:
        """Specctra DSN job input artifact."""
        return service.job_resource(jobid, "input.dsn")

    @mcp.resource("diptrace://job/{jobid}/output.ses", mime_type="text/plain")
    def job_ses_resource(jobid: str) -> str:
        """Specctra SES job output artifact."""
        return service.job_resource(jobid, "output.ses")

    @mcp.resource("diptrace://job/{jobid}/manifest.json", mime_type="application/json")
    def job_manifest_resource(jobid: str) -> str:
        """External job provenance and typed option manifest."""
        return service.job_resource(jobid, "manifest.json")

    @mcp.resource(
        "diptrace://job/{jobid}/field_solver_input.json",
        mime_type="application/json",
    )
    def job_field_solver_input_resource(jobid: str) -> str:
        """Typed field-solver request artifact."""
        return service.job_resource(jobid, "field_solver_input.json")

    @mcp.resource(
        "diptrace://job/{jobid}/field_solver_result.json",
        mime_type="application/json",
    )
    def job_field_solver_result_resource(jobid: str) -> str:
        """Validated field-solver result artifact."""
        return service.job_resource(jobid, "field_solver_result.json")

    @mcp.resource(
        "diptrace://export/{export_id}/{artifact}",
        mime_type="text/plain",
    )
    def export_artifact_resource(export_id: str, artifact: str) -> str:
        """Bounded UTF-8 artifact from an isolated export directory."""
        return service.export_resource(export_id, artifact)
