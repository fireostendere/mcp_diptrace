"""Schematic authoring and schematic placement repair."""
from __future__ import annotations

from typing import Any, Literal

from ..operations import (
    PinEndpoint,
    WireEndpoint,
    WirePathPoint,
)
from ..reference_rules import EngineeringRulePack
from ..schematic_ensemble import SchematicEnsembleConfig
from ..server_inputs import (
    DipTraceFastMCP,
    SchematicEnsembleConfigInput,
    SchematicRepairMoveInput,
    SelectorInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def set_pin_no_connect(
        no_connect: bool,
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set or clear intentional no-connect on selected schematic pins."""
        return service.set_pin_no_connect(
            selector, no_connect, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def add_sheet(
        name: str,
        sheet_type: str = "Normal",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a new sheet to a schematic document."""
        return service.add_sheet(name, sheet_type, path, dry_run, expected_sha256, txid)

    @mcp.tool()
    def place_part(
        component_style: str,
        refdes: str,
        x: float,
        y: float,
        pin_count: int,
        name: str | None = None,
        value: str = "",
        sheet: int = 0,
        angle_deg: float = 0.0,
        component_part: int = 0,
        part_number: int = 0,
        part_refdes: str | None = None,
        part_name: str | None = None,
        allow_shared_refdes: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Place a new schematic part referencing a library ComponentStyle."""
        return service.place_part(
            component_style,
            refdes,
            x,
            y,
            pin_count=pin_count,
            name=name,
            value=value,
            sheet=sheet,
            angle_deg=angle_deg,
            component_part=component_part,
            part_number=part_number,
            part_refdes=part_refdes,
            part_name=part_name,
            allow_shared_refdes=allow_shared_refdes,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def place_builtin_component(
        component: str,
        refdes: str,
        x: float,
        y: float,
        value: str | None = None,
        sheet: int = 0,
        angle_deg: float = 0.0,
        path: str | None = None,
        diptrace_root: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Find an installed component by catalog id/name and place a private schematic copy."""
        return service.place_builtin_component(
            component,
            refdes,
            x,
            y,
            value=value,
            sheet=sheet,
            angle_deg=angle_deg,
            path=path,
            diptrace_root=diptrace_root,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def connect_pins(
        net: str,
        pins: list[PinEndpoint],
        allow_reconnect: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Connect part pins to a net; the net is created when missing."""
        return service.connect_pins(
            net,
            [pin.model_dump() for pin in pins],
            allow_reconnect,
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    @mcp.tool()
    def disconnect_pins(
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Disconnect selected schematic pins from their nets."""
        return service.disconnect_pins(selector, path, dry_run, expected_sha256, txid)

    @mcp.tool()
    def add_wire(
        net: str,
        points: list[WirePathPoint],
        start: WireEndpoint,
        end: WireEndpoint,
        sheet: int = 0,
        hidden_power: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a wire to a schematic net (official Wire/Points XML structure)."""
        return service.add_wire(
            net,
            [point.model_dump() for point in points],
            start.model_dump(),
            end.model_dump(),
            sheet,
            hidden_power,
            path,
            dry_run,
            expected_sha256,
            txid,
        )

    @mcp.tool(capability_keys=["write_capabilities.schematic_authoring"])
    def plan_add_wire(
        net: str,
        points: list[WirePathPoint],
        start: WireEndpoint,
        end: WireEndpoint,
        sheet: int = 0,
        hidden_power: bool = False,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Preview add_wire without writing; inspect accept_route and feedback before applying."""
        return service.plan_add_wire(
            net, [point.model_dump() for point in points],
            start.model_dump(), end.model_dump(), sheet, hidden_power, path,
        )

    @mcp.tool()
    def delete_wire(
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Delete selected schematic wires without touching net connectivity."""
        return service.delete_wire(selector, path, dry_run, expected_sha256, txid)

    @mcp.tool()
    def add_net_label(
        net: str,
        x: float,
        y: float,
        sheet: int = 0,
        text: str | None = None,
        font_size: int = 4,
        horizontal_align: Literal["Left", "Center", "Right"] = "Left",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a net-bound text label shape to a schematic sheet."""
        return service.add_net_label(
            net, x, y, sheet, text, font_size, path, dry_run, expected_sha256, txid,
            horizontal_align=horizontal_align,
        )

    @mcp.tool(
        description=(
            "Delete schematic parts and their net membership. Delete wires attached to "
            "their pins in the same transaction; a wire left on a deleted pin is refused."
        )
    )
    def delete_parts(
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """See the tool description."""
        return service.delete_parts(selector, path, dry_run, expected_sha256, txid)

    @mcp.tool(
        description=(
            "Delete the visual labels of one schematic net, on one sheet or all. "
            "Connectivity is unaffected: labels are annotations."
        )
    )
    def delete_net_labels(
        net: str,
        sheet: int | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """See the tool description."""
        return service.delete_net_labels(
            net,
            sheet=sheet,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def rank_schematic_placement_candidates(
        path: str | None = None,
        engineering_rules: EngineeringRulePack | None = None,
        config: SchematicEnsembleConfigInput | None = None,
    ) -> dict[str, Any]:
        """Rank schematic candidates with optional sourced rules and bounded config."""
        return service.rank_schematic_placement_candidates(
            path,
            engineering_rules=engineering_rules,
            config=None if config is None else SchematicEnsembleConfig.model_validate(config),
        )

    @mcp.tool()
    def plan_schematic_placement_repair(
        path: str | None = None,
        moves: list[SchematicRepairMoveInput] | None = None,
    ) -> dict[str, Any]:
        """Plan placement repair and selective affected-net reroute; wired-safe, moves are fixed."""
        return service.plan_schematic_placement_repair(
            path,
            moves=[move.model_dump() for move in moves] if moves else None,
        )
