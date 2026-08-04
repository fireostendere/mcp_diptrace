from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from ..domain import (
    DocumentInfo,
    FieldSolverRequest,
)
from ..errors import (
    DocumentError,
    Sha256MismatchError,
)
from ..external_adapters import ExternalJobManager
from ..jobs import JobStore, job_resources
from ..operations import (
    SemanticOperation,
)
from ..plans import PlanStore
from ..specctra import (
    export_dsn,
    parse_ses,
    session_to_operations,
)
from ..xml_document import (
    DipTraceDocument,
)
from .context import DocumentGateway, ServiceContext, read_success

PreviewSemanticOperations = Callable[[DipTraceDocument, list[SemanticOperation]], dict[str, Any]]


class ApplyStoredPlan(Protocol):
    def __call__(
        self,
        plan_id: str,
        *,
        expected_plan_type: str,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]: ...


class ExternalJobsService:
    def __init__(
        self,
        context: ServiceContext,
        gateway: DocumentGateway,
        plan_store: PlanStore,
        job_store: JobStore,
        external_job_manager: ExternalJobManager,
        preview_semantic_operations: PreviewSemanticOperations,
        apply_stored_plan: ApplyStoredPlan,
    ) -> None:
        self.context = context
        self.gateway = gateway
        self.plan_store = plan_store
        self.job_store = job_store
        self.external_job_manager = external_job_manager
        self.preview_semantic_operations = preview_semantic_operations
        self.apply_stored_plan = apply_stored_plan

    def export_autorouter_dsn(
        self,
        path: str | None = None,
        *,
        design_name: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        dsn = export_dsn(snapshot, design_name=design_name)
        record = self.external_job_manager.create_export_job(
            snapshot.info,
            target.path,
            dsn,
            manifest={
                "format": "Specctra DSN",
                "serializer": "diptrace-mcp-bounded-v1",
                "document_id": snapshot.info.document_id,
                "source_sha256": snapshot.info.sha256,
                "coordinate_units": "mm",
                "resolution": 1000,
                "assumptions": [
                    "DipTrace board coordinates are emitted directly in Specctra millimetres.",
                    "Only embedded pattern shapes accepted by capability validation are emitted.",
                    "Quoted tokens use only printable ASCII excluding quote and backslash; "
                    "no escape convention is assumed.",
                ],
            },
        )
        response = read_success(
            snapshot.info,
            {"job": record.model_dump(mode="json")},
            resources=job_resources(record.jobid),
            limitations=[
                "The bounded serializer rejects cutouts, keepouts, pours and unsupported "
                "pad shapes, plus identifiers requiring unverified escaping or encoding."
            ],
        )
        response["job"] = record.model_dump(mode="json")
        return response

    def run_external_autorouter(
        self,
        path: str | None = None,
        *,
        dsn_job_id: str | None = None,
        dsn_path: str | None = None,
        max_passes: int = 100,
        threads: int = 1,
        timeout_seconds: int | None = None,
        ignore_net_classes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.context.policy.require_external_execution(operation="run_external_autorouter")
        if dsn_job_id is not None and dsn_path is not None:
            raise DocumentError("Pass either dsn_job_id or dsn_path, not both")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if dsn_job_id is not None:
            export_job = self.job_store.read(dsn_job_id)
            if export_job.job_type != "dsn_export" or export_job.status != "completed":
                raise DocumentError("dsn_job_id must identify a completed DSN export job")
            if export_job.source_sha256 != snapshot.info.sha256:
                raise Sha256MismatchError(
                    "DSN export was created from a different document revision",
                    details={
                        "dsn_source_sha256": export_job.source_sha256,
                        "current_sha256": snapshot.info.sha256,
                    },
                )
            dsn = self.job_store.artifact_path(dsn_job_id, "input.dsn").read_bytes()
        elif dsn_path is not None:
            source = self.context.settings.resolve_allowed_path(dsn_path)
            if source.stat().st_size > self.context.settings.max_document_bytes:
                raise DocumentError("DSN input exceeds the document size limit")
            dsn = source.read_bytes()
        else:
            dsn = export_dsn(snapshot)
        record = self.external_job_manager.start_freerouting(
            snapshot.info,
            target.path,
            dsn,
            max_passes=max_passes,
            threads=threads,
            timeout_seconds=timeout_seconds,
            ignore_net_classes=list(ignore_net_classes or []),
        )
        response = read_success(
            snapshot.info,
            {"job": record.model_dump(mode="json")},
            resources=job_resources(record.jobid),
        )
        response["job"] = record.model_dump(mode="json")
        return response

    def inspect_autorouter_result(
        self,
        jobid: str,
        path: str | None = None,
        *,
        via_style: str | None = None,
    ) -> dict[str, Any]:
        job = self.job_store.read(jobid)
        if job.job_type != "freerouting" or job.status != "completed":
            raise DocumentError(
                "Autorouter result inspection requires a completed Freerouting job",
                details={"jobid": jobid, "status": job.status, "job_type": job.job_type},
            )
        target_path = path or job.target_path
        if target_path is None:
            raise DocumentError("Autorouter job has no associated DipTrace target")
        document, target = self.gateway.load(target_path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.info.sha256 != job.source_sha256:
            raise Sha256MismatchError(
                "DipTrace document changed after the autorouter job was created",
                details={
                    "job_source_sha256": job.source_sha256,
                    "current_sha256": snapshot.info.sha256,
                },
            )
        ses_path = self.job_store.artifact_path(jobid, "output.ses")
        session = parse_ses(
            ses_path.read_bytes(), max_bytes=self.context.settings.max_document_bytes
        )
        operation_plan = session_to_operations(snapshot, session, via_style=via_style)
        plan_record = None
        resources = job_resources(jobid)
        if operation_plan.operations:
            preview = self.preview_semantic_operations(
                document, cast(list[SemanticOperation], operation_plan.operations)
            )
            plan_record = self.plan_store.create(
                plan_type="autorouter_ses_import",
                document_id=snapshot.info.document_id,
                source_sha256=snapshot.info.sha256,
                target_path=target.path,
                config={"jobid": jobid, "via_style": via_style},
                operations=[
                    operation.model_dump(mode="json") for operation in operation_plan.operations
                ],
                changed_ids=sorted({operation.net for operation in operation_plan.operations}),
                unresolved=operation_plan.skipped,
                candidates=[item.model_dump(mode="json") for item in session.routes],
                score={"imported_length_mm": float(operation_plan.metrics["imported_length_mm"])},
                metrics=operation_plan.metrics,
                assumptions=[
                    "SES coordinates are converted using the routes resolution scope.",
                    "Only non-branching two-endpoint nets without existing traces are importable.",
                ],
                warnings=session.warnings,
                limitations=[
                    "Branched nets and partial replacement of existing routing are "
                    "inspection-only.",
                    "Via-containing routes require an explicit DipTrace via_style mapping.",
                ],
            )
            plan_resources = self.plan_store.store_preview(
                plan_record.plan_id,
                svg=preview["svg"],
                geometry={
                    **preview["json"],
                    "jobid": jobid,
                    "ses_metrics": operation_plan.metrics,
                },
                diff=preview["diff"],
            )
            resources.extend(plan_resources)
            plan_record = self.plan_store.read(plan_record.plan_id)
        return read_success(
            snapshot.info,
            {
                "session": session.model_dump(mode="json"),
                "inspection": {
                    **operation_plan.metrics,
                    "imported_nets": operation_plan.imported_nets,
                    "skipped": operation_plan.skipped,
                },
                "plan": plan_record.model_dump(mode="json") if plan_record else None,
            },
            resources=resources,
            limitations=[
                "Inspection is geometric/topological and never trusts external DRC results."
            ],
        )

    def import_autorouter_ses(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self.apply_stored_plan(
            plan_id,
            expected_plan_type="autorouter_ses_import",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def run_ngspice_simulation(
        self,
        *,
        netlist: str | None = None,
        netlist_path: str | None = None,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Run a user-supplied ngspice netlist as a bounded external batch job."""

        self.context.policy.require_external_execution(operation="run_ngspice_simulation")
        if (netlist is None) == (netlist_path is None):
            raise DocumentError("Pass exactly one of netlist or netlist_path")
        max_netlist_bytes = 256 * 1024
        if netlist_path is not None:
            source = self.context.settings.resolve_allowed_path(netlist_path)
            if source.stat().st_size > max_netlist_bytes:
                raise DocumentError("Netlist file exceeds the 256 KiB limit")
            netlist_bytes = source.read_bytes()
        else:
            assert netlist is not None
            netlist_bytes = netlist.encode("utf-8")
        if len(netlist_bytes) > max_netlist_bytes:
            raise DocumentError("Netlist exceeds the 256 KiB limit")
        info: DocumentInfo | None = None
        target_path: Path | None = None
        if path is not None:
            document, target = self.gateway.load(path)
            info = self.context.model_cache.get(document, live_session=target.is_live).info
            target_path = target.path
        record = self.external_job_manager.start_ngspice(
            info,
            target_path,
            netlist_bytes,
            timeout_seconds=timeout_seconds,
        )
        return {
            "ok": True,
            "document": info.model_dump() if info is not None else None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": [],
            "limitations": [
                "The netlist is user-supplied; the server does not verify its electrical "
                "correctness.",
                "Simulation results are ngspice output, not in-circuit measurements.",
            ],
            "resources": job_resources(record.jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def run_openems_stripline_analysis(
        self,
        *,
        width_mm: float,
        copper_thickness_mm: float,
        lower_dielectric_height_mm: float,
        upper_dielectric_height_mm: float,
        dielectric_constant: float,
        frequencies_hz: list[float],
        dielectric_loss_tangent: float = 0.0,
        conductor_conductivity_s_per_m: float = 58_000_000.0,
        trace_length_mm: float = 20.0,
        port_impedance_ohm: float = 50.0,
        mesh_cells_per_wavelength: int = 30,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Start a bounded off-center/centered stripline field-solver job."""

        self.context.policy.require_external_execution(operation="run_openems_stripline_analysis")
        request = FieldSolverRequest(
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            lower_dielectric_height_mm=lower_dielectric_height_mm,
            upper_dielectric_height_mm=upper_dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            dielectric_loss_tangent=dielectric_loss_tangent,
            conductor_conductivity_s_per_m=conductor_conductivity_s_per_m,
            frequencies_hz=frequencies_hz,
            trace_length_mm=trace_length_mm,
            port_impedance_ohm=port_impedance_ohm,
            mesh_cells_per_wavelength=mesh_cells_per_wavelength,
        )
        info: DocumentInfo | None = None
        target_path: Path | None = None
        if path is not None:
            document, target = self.gateway.load(path)
            info = self.context.model_cache.get(document, live_session=target.is_live).info
            target_path = target.path
        record = self.external_job_manager.start_openems(
            info,
            target_path,
            request,
            timeout_seconds=timeout_seconds,
        )
        return {
            "ok": True,
            "document": info.model_dump() if info is not None else None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": [],
            "limitations": [
                "The result is produced by the configured openEMS runner and is not a "
                "fabrication guarantee.",
                "Mesh, port, convergence, material, and loss assumptions remain part of the "
                "solver result and must be reviewed.",
            ],
            "resources": job_resources(record.jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }
