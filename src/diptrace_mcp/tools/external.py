"""External and native jobs, job state and the build-pipeline helpers."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..errors import EditError
from ..server_inputs import (
    DipTraceFastMCP,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def export_autorouter_dsn(
        path: str | None = None,
        design_name: str | None = None,
    ) -> dict[str, Any]:
        """Export a bounded Specctra DSN artifact when exact footprint geometry is available."""
        return service.export_autorouter_dsn(path, design_name=design_name)

    @mcp.tool()
    def run_external_autorouter(
        path: str | None = None,
        dsn_job_id: str | None = None,
        dsn_path: str | None = None,
        max_passes: int = 100,
        threads: int = 1,
        timeout_seconds: int | None = None,
        ignore_net_classes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Start an isolated bounded Freerouting CLI job; never invokes a shell."""
        return service.run_external_autorouter(
            path,
            dsn_job_id=dsn_job_id,
            dsn_path=dsn_path,
            max_passes=max_passes,
            threads=threads,
            timeout_seconds=timeout_seconds,
            ignore_net_classes=ignore_net_classes,
        )

    @mcp.tool()
    def inspect_autorouter_result(
        jobid: str,
        path: str | None = None,
        via_style: str | None = None,
    ) -> dict[str, Any]:
        """Parse and validate a completed SES artifact and create an import preview plan."""
        return service.inspect_autorouter_result(jobid, path, via_style=via_style)

    @mcp.tool(
        description=(
            "Start a native DipTrace check on a copy of a saved document as a background "
            "job (poll get_job_status / get_job_result). Needs an installed, reviewed "
            "DipTrace build and a policy that allows external execution; outputs land in "
            "the job directory."
        )
    )
    def run_native_check(
        check: Annotated[
            Literal["pcb_acceptance", "schematic_acceptance", "schematic_erc", "xml_export"],
            Field(
                description="pcb_acceptance: open, refill pours, DRC, save, re-export. "
                "schematic_acceptance: open, save, re-export. schematic_erc: the same plus "
                "native ERC capture. xml_export: native file to exchange XML."
            ),
        ],
        path: str,
        diptrace_root: Annotated[str, Field(description="DipTrace installation directory.")],
        timeout_seconds: int | None = None,
        startup_dialog_sha256: Annotated[
            list[Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]] | None,
            Field(strict=True, max_length=8, description=(
                "Exact client PNG SHA-256 values explicitly reviewed by the operator; "
                "no default approvals. Schematic checks: up to 8; XML export: up to 1; "
                "PCB acceptance: unsupported."
            )),
        ] = None,
    ) -> dict[str, Any]:
        """See the tool description."""
        return service.run_native_check(
            check, path, diptrace_root, timeout_seconds=timeout_seconds,
            startup_dialog_sha256=startup_dialog_sha256,
        )

    @mcp.tool(capability_keys=["read_capabilities.external_jobs"])
    def run_native_export(
        path: str,
        expected_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Export raw native PCB CAM evidence on a private copy; never fabrication signoff."""
        return service.run_native_export(
            path, expected_sha256, timeout_seconds=timeout_seconds,
        )

    @mcp.tool()
    def run_ngspice_simulation(
        netlist: str | None = None,
        netlist_path: str | None = None,
        path: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Run a user-supplied ngspice netlist in batch mode (requires DIPTRACE_MCP_NGSPICE)."""
        return service.run_ngspice_simulation(
            netlist=netlist,
            netlist_path=netlist_path,
            path=path,
            timeout_seconds=timeout_seconds,
        )

    @mcp.tool()
    def run_openems_stripline_analysis(
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
        """Run configured openEMS stripline analysis with a typed frequency sweep."""
        return service.run_openems_stripline_analysis(
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            lower_dielectric_height_mm=lower_dielectric_height_mm,
            upper_dielectric_height_mm=upper_dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            frequencies_hz=frequencies_hz,
            dielectric_loss_tangent=dielectric_loss_tangent,
            conductor_conductivity_s_per_m=conductor_conductivity_s_per_m,
            trace_length_mm=trace_length_mm,
            port_impedance_ohm=port_impedance_ohm,
            mesh_cells_per_wavelength=mesh_cells_per_wavelength,
            path=path,
            timeout_seconds=timeout_seconds,
        )

    @mcp.tool()
    def get_job_status(jobid: str) -> dict[str, Any]:
        """Return persistent external-job state and progress."""
        return service.get_job_status(jobid)

    @mcp.tool()
    def get_job_result(jobid: str) -> dict[str, Any]:
        """Return completed, partial or failed external-job result data."""
        return service.get_job_result(jobid)

    @mcp.tool()
    def cancel_job(jobid: str) -> dict[str, Any]:
        """Request cancellation of a running external job."""
        return service.cancel_job(jobid)

    @mcp.tool()
    def list_jobs(status: str | None = None) -> dict[str, Any]:
        """List persistent jobs, optionally filtered by exact status."""
        return service.list_jobs(status)

    # --- pipeline tools (Rev.A DUT controller + generic board build) ------

    @mcp.tool(
        description=(
            "Resolve an MPN to its LCSC part code and download component JSON + "
            "datasheet PDF from EasyEDA. Returns code, package, pin/pad counts and "
            "file paths for downstream schematic building."
        )
    )
    def pipeline_source_component(
        mpn_or_code: str,
        output_dir: str = "vendor",
    ) -> dict[str, Any]:
        """Resolve an MPN to its LCSC data and download it."""
        from diptrace_mcp.pipeline import lcsc_fetch
        service.policy.require_external_execution(operation="pipeline_source_component")
        service.policy.require_write(dry_run=False, operation="pipeline_source_component")
        target = service.settings.resolve_allowed_path(output_dir, must_exist=False)
        return lcsc_fetch(mpn_or_code, str(target))

    @mcp.tool(
        description=(
            "Transplant generated schematic/PCB content into a DipTrace-native "
            "template so the real editor parses it without hanging. Detects kind "
            "(schematic or PCB) automatically."
        )
    )
    def pipeline_nativeize_document(
        input_path: str,
        template_path: str,
        output_path: str,
    ) -> dict[str, Any]:
        """Transplant generated content into a DipTrace-native template."""
        from diptrace_mcp.pipeline import nativeize_document
        service.policy.require_write(dry_run=False, operation="pipeline_nativeize_document")
        resolve = service.settings.resolve_allowed_path
        target = resolve(output_path, must_exist=False)
        if target.exists():
            # No expected-SHA input on this tool, so it never replaces a document.
            raise EditError(
                "pipeline_nativeize_document does not overwrite an existing file",
                code="path_exists",
            )
        return nativeize_document(
            str(resolve(input_path)), str(resolve(template_path)), str(target)
        )

    @mcp.tool(
        description=(
            "Render Top + Bottom SVG previews of a .dipxml board without opening "
            "DipTrace. Shows outline, copper traces, pours, vias and board edge."
        )
    )
    def pipeline_render_board_preview(
        pcb_path: str,
        output_dir: str = ".",
    ) -> dict[str, Any]:
        """Render Top + Bottom SVG previews of a board."""
        from diptrace_mcp.pipeline import render_board_svg
        service.policy.require_write(dry_run=False, operation="pipeline_render_board_preview")
        resolve = service.settings.resolve_allowed_path
        return render_board_svg(
            str(resolve(pcb_path)), str(resolve(output_dir, must_exist=False))
        )
