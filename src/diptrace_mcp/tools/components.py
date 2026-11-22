"""Component and board-text edits."""
from __future__ import annotations

from typing import Any, Literal

from ..server_inputs import (
    DipTraceFastMCP,
    SelectorInput,
)
from ..service import DipTraceService


def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
    @mcp.tool()
    def move_components(
        selector: SelectorInput | None = None,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        grid_snap: float | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Move one or more components transactionally."""
        return service.move_components(
            selector,
            dx,
            dy,
            absolute_x,
            absolute_y,
            path,
            dry_run,
            expected_sha256,
            txid,
            grid_snap,
            allow_locked,
        )

    @mcp.tool()
    def set_component_value(
        value: str,
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set the value of one or more components transactionally."""
        return service.set_component_value(selector, value, path, dry_run, expected_sha256, txid)

    @mcp.tool()
    def rotate_components(
        angle_deg: float,
        selector: SelectorInput | None = None,
        mode: Literal["absolute", "relative"] = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allowed_angles: list[float] | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Rotate selected PCB components or schematic parts transactionally."""
        return service.rotate_components(
            selector,
            angle_deg,
            mode,
            path,
            dry_run,
            expected_sha256,
            txid,
            allowed_angles,
            allow_locked,
        )

    @mcp.tool()
    def set_component_side(
        side: Literal["Top", "Bottom"],
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Move selected PCB components to the top or bottom side."""
        return service.set_component_side(
            selector, side, path, dry_run, expected_sha256, txid, allow_locked
        )

    @mcp.tool()
    def lock_components(
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        locked: bool = True,
    ) -> dict[str, Any]:
        """Lock (locked=true) or unlock (locked=false) selected components or parts."""
        return service.set_component_lock(
            selector, locked, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def set_component_properties(
        selector: SelectorInput | None = None,
        name: str | None = None,
        value: str | None = None,
        refdes: str | None = None,
        fields: dict[str, str] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Set RefDes, name, value or custom fields on selected components."""
        return service.set_component_properties(
            selector,
            name=name,
            value=value,
            refdes=refdes,
            fields=fields,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def set_component_pattern(
        selector: SelectorInput,
        pattern_style: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Swap to one embedded pattern only when pad mapping is preserved exactly."""
        return service.set_component_pattern(
            selector,
            pattern_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def align_components(
        selector: SelectorInput,
        alignment: Literal["left", "center_x", "right", "top", "center_y", "bottom"],
        target_value: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Align PCB component body bboxes as one semantic transaction."""
        return service.align_components(
            selector,
            alignment,
            target_value=target_value,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def distribute_components(
        selector: SelectorInput,
        axis: Literal["x", "y"],
        mode: Literal["centers", "gaps"] = "centers",
        spacing: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Distribute at least three PCB components transactionally."""
        return service.distribute_components(
            selector,
            axis,
            mode=mode,
            spacing=spacing,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def group_components(
        selector: SelectorInput,
        group_id: int | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Create or reuse a documented DipTrace PCB group transactionally."""
        return service.group_components(
            selector,
            group_id=group_id,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def ungroup_components(
        selector: SelectorInput,
        remove_empty_groups: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Remove selected components from groups and prune only empty groups."""
        return service.ungroup_components(
            selector,
            remove_empty_groups=remove_empty_groups,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def list_board_texts(
        path: str | None = None,
        selector: SelectorInput | None = None,
    ) -> dict[str, Any]:
        """List free board text and component silk/assembly markings."""
        return service.list_board_texts(path, selector)

    @mcp.tool()
    def move_board_texts(
        selector: SelectorInput | None = None,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Move free board text or component markings in board coordinates."""
        return service.move_board_texts(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def rotate_board_texts(
        angle_deg: float,
        selector: SelectorInput | None = None,
        mode: Literal["absolute", "relative"] = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Rotate free board text or component markings."""
        return service.rotate_board_texts(
            selector,
            angle_deg,
            mode,
            path,
            dry_run,
            expected_sha256,
            txid,
            allow_locked,
        )

    @mcp.tool()
    def set_text_visibility(
        visibility: Literal["Show", "Hide", "Common"],
        selector: SelectorInput | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Set visibility for component silk/assembly markings."""
        return service.set_text_visibility(
            selector,
            visibility,
            path,
            dry_run,
            expected_sha256,
            txid,
            allow_locked,
        )

    @mcp.tool()
    def set_text_style(
        selector: SelectorInput | None = None,
        font_size: int | None = None,
        font_width: float | None = None,
        horizontal_align: Literal["Left", "Center", "Right"] | None = None,
        vertical_align: Literal["Top", "Center", "Bottom"] | None = None,
        mirrored: bool | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Set verified style attributes on free PCB text shapes."""
        return service.set_text_style(
            selector,
            font_size=font_size,
            font_width=font_width,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            mirrored=mirrored,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )
