"""Board-level edits: nets and classes, panel, pours, outline, testpoints, sync."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..operations import (
    AddTestpointOperation,
)
from ..server_inputs import (
    ComponentSyncMappingInput,
    DipTraceFastMCP,
    PanelizationInput,
    SelectorInput,
    SyncPlacementInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def compare_schematic_to_pcb(
        schematic_path: str, pcb_path: str
    ) -> dict[str, Any]:
        """Compare RefDes, values, net names and pin/pad endpoint sets."""
        return service.compare_schematic_to_pcb(schematic_path, pcb_path)

    @mcp.tool()
    def sync_schematic_to_pcb(
        schematic_path: str,
        pcb_path: str,
        component_mappings: list[ComponentSyncMappingInput] | None = None,
        placement: SyncPlacementInput | None = None,
        pattern_library_paths: list[str] | None = None,
        update_existing_properties: bool = True,
        create_ratlines: bool = True,
        allow_reconnect: bool = False,
        reconciliation_mode: Literal["additive", "exact"] = "additive",
        allow_locked_reconciliation: bool = False,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        expected_schematic_sha256: Annotated[
            str | None,
            Field(description="Schematic SHA from the dry run; required to commit."),
        ] = None,
    ) -> dict[str, Any]:
        """Additively synchronize schematic components, nets and ratlines into a PCB."""
        return service.sync_schematic_to_pcb(
            schematic_path,
            pcb_path,
            component_mappings=component_mappings,
            placement=placement,
            pattern_library_paths=pattern_library_paths,
            update_existing_properties=update_existing_properties,
            create_ratlines=create_ratlines,
            allow_reconnect=allow_reconnect,
            reconciliation_mode=reconciliation_mode,
            allow_locked_reconciliation=allow_locked_reconciliation,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            expected_schematic_sha256=expected_schematic_sha256,
        )

    @mcp.tool()
    def rename_net(
        new_name: str,
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Rename selected PCB or schematic nets with duplicate-name protection."""
        return service.rename_net(
            selector, new_name, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def set_panelization(
        panel: PanelizationInput,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set official DipTrace panelization parameters on a PCB document."""
        return service.set_panelization(panel, path, dry_run, expected_sha256, txid)

    @mcp.tool()
    def clear_panelization(
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Remove panelization settings from a PCB document."""
        return service.clear_panelization(path, dry_run, expected_sha256, txid)

    @mcp.tool(
        description=(
            "Create or replace full-board four-spoke pours of one net, with optional "
            "stitching vias placed clear of parts, pads, traces, vias, keepouts and "
            "silkscreen. Re-running replaces this net's earlier stitching vias. Copper "
            "needs a native refill."
        )
    )
    def add_copper_pours(
        net: str,
        layers: Annotated[
            list[str] | None, Field(description="Copper layer names; default Top and Bottom.")
        ] = None,
        clearance_mm: float = 0.2,
        board_clearance_mm: float = 0.2,
        spoke_width_mm: float = 0.3,
        stitch_pitch_mm: Annotated[
            float | None,
            Field(description="Grid pitch for free stitching vias of this net; omit for none."),
        ] = None,
        stitch_edge_mm: float = 1.0,
        extra_vias: Annotated[
            list[dict[str, float]] | None,
            Field(description="Explicit free via positions as {x, y} in mm."),
        ] = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """See the tool description."""
        return service.add_copper_pours(
            net,
            layers=layers,
            clearance_mm=clearance_mm,
            board_clearance_mm=board_clearance_mm,
            spoke_width_mm=spoke_width_mm,
            stitch_pitch_mm=stitch_pitch_mm,
            stitch_edge_mm=stitch_edge_mm,
            extra_vias=extra_vias,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def delete_copper_pours(
        net: str,
        layers: list[str] | None = None,
        remove_stitching_vias: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Remove copper pours of one net (all layers or the named ones) and its stitching vias."""
        return service.delete_copper_pours(
            net,
            layers=layers,
            remove_stitching_vias=remove_stitching_vias,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool(
        description=(
            "Replace the board outline polygon. Refused when the outline is locked or when "
            "a component, pad, via, trace or pour boundary inside the current outline would "
            "fall outside the new one. Mounting holes, cutouts and arcs are not authored "
            "here."
        )
    )
    def set_board_outline(
        points: Annotated[
            list[dict[str, float]],
            Field(description="Outline corners in order as {x, y} in mm; straight edges only."),
        ],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """See the tool description."""
        return service.set_board_outline(points, path, dry_run, expected_sha256, txid)

    @mcp.tool()
    def update_net_class_rules(
        class_name: str,
        layer: str | None = None,
        width: float | None = None,
        min_width: float | None = None,
        max_width: float | None = None,
        clearance: float | None = None,
        neck_width: float | None = None,
        differential_gap: float | None = None,
        max_uncoupled_length: float | None = None,
        tolerance: float | None = None,
        check_length: bool | None = None,
        fixed_length: float | None = None,
        length_delta: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Update verified width, clearance, differential-pair and length fields of a net class."""
        return service.update_net_class_rules(
            class_name,
            layer=layer,
            width=width,
            min_width=min_width,
            max_width=max_width,
            clearance=clearance,
            neck_width=neck_width,
            differential_gap=differential_gap,
            max_uncoupled_length=max_uncoupled_length,
            tolerance=tolerance,
            check_length=check_length,
            fixed_length=fixed_length,
            length_delta=length_delta,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def assign_nets_to_class(
        class_name: str,
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Assign selected PCB or schematic nets to an existing net class."""
        return service.assign_nets_to_class(
            selector, class_name, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def list_testpoints(
        path: str | None = None,
        selector: SelectorInput | None = None,
    ) -> dict[str, Any]:
        """List explicit TP standalone-pad components in a PCB document."""
        return service.list_testpoints(path, selector)

    @mcp.tool()
    def find_testpoint_candidates(
        target_nets: list[str],
        path: str | None = None,
        side: Literal["Top", "Bottom"] = "Top",
        probe_diameter: float = 1.0,
        clearance: float = 0.5,
        grid: float = 2.54,
        candidates_per_net: int = 10,
    ) -> dict[str, Any]:
        """Generate deterministic free-grid testpoint candidates for selected nets."""
        return service.find_testpoint_candidates(
            target_nets,
            path=path,
            side=side,
            probe_diameter=probe_diameter,
            clearance=clearance,
            grid=grid,
            candidates_per_net=candidates_per_net,
        )

    @mcp.tool()
    def add_testpoints(
        testpoints: list[AddTestpointOperation],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add explicit standalone-pad testpoints and connect them to existing nets atomically."""
        return service.add_testpoints(
            [testpoint.model_dump() for testpoint in testpoints],
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    @mcp.tool()
    def move_testpoints(
        selector: SelectorInput | None = None,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        grid_snap: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Move explicit standalone-pad testpoints transactionally."""
        return service.move_testpoints(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            grid_snap=grid_snap,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def remove_testpoints(
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Remove explicit standalone-pad testpoints and their net/pattern references."""
        return service.remove_testpoints(
            selector, path, dry_run, expected_sha256, txid, allow_locked
        )

    @mcp.tool()
    def review_testpoint_coverage(
        target_nets: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Measure explicit standalone-pad testpoint coverage for selected or all nets."""
        return service.review_testpoint_coverage(target_nets, path)

    @mcp.tool()
    def list_copper_pours(
        path: str | None = None, offset: int = 0, limit: int = 100
    ) -> dict[str, Any]:
        """List normalized copper-pour boundaries and refill-state metadata."""
        return service.list_copper_pours(path, offset=offset, limit=limit)
