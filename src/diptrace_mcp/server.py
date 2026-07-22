from __future__ import annotations

import argparse
import json
import os
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .config import Settings
from .service import DipTraceService
from .xml_document import XmlEdit


class XmlEditInput(BaseModel):
    operation: Literal[
        "set_text",
        "set_attribute",
        "remove_attribute",
        "append_xml",
        "replace_xml",
        "delete_element",
    ]
    xpath: str = Field(min_length=1, max_length=512)
    value: str | None = None
    attribute: str | None = None
    expected_matches: int = Field(default=1, ge=1, le=1000)


def create_server(settings: Settings | None = None) -> FastMCP:
    service = DipTraceService(settings or Settings.from_env())
    mcp = FastMCP(
        name="DipTrace MCP",
        instructions=(
            "Inspect and safely edit DipTrace XML. Without a path, tools use the active live "
            "DipTrace bridge session. Prefer semantic tools with preview/commit/rollback. "
            "Low-level XML edits remain available for expert use."
        ),
        json_response=True,
    )

    @mcp.tool()
    def diptrace_status() -> dict[str, Any]:
        """Show server paths and the active DipTrace bridge session, if any."""
        return service.status()

    @mcp.tool()
    def get_capabilities(path: str | None = None) -> dict[str, Any]:
        """Return supported source types, adapters, limits and current feature availability."""
        return service.get_capabilities(path)

    @mcp.tool()
    def get_document_info(path: str | None = None) -> dict[str, Any]:
        """Return document identity, type, version, size, sha256 and compatibility."""
        return service.document_info(path)

    @mcp.tool()
    def get_board_model(path: str | None = None) -> dict[str, Any]:
        """Return the normalized PCB model for a DipTrace board document."""
        return service.board_model(path)

    @mcp.tool()
    def get_schematic_model(path: str | None = None) -> dict[str, Any]:
        """Return the normalized schematic model for a DipTrace schematic document."""
        return service.schematic_model(path)

    @mcp.tool()
    def scan_component_libraries(
        root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        """Find standalone DipTrace Component Library XML files inside allowed roots."""
        return service.scan_component_libraries(root, recursive)

    @mcp.tool()
    def scan_pattern_libraries(
        root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        """Find standalone DipTrace Pattern Library XML files inside allowed roots."""
        return service.scan_pattern_libraries(root, recursive)

    @mcp.tool()
    def query_library_items(
        path: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Query normalized components or patterns in a standalone library."""
        return service.query_library_items(path, query, offset, limit)

    @mcp.tool()
    def get_library_component(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Get one normalized component-library item by stable id or exact name."""
        return service.get_library_component(path, stable_id, name)

    @mcp.tool()
    def get_library_pattern(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Get one normalized pattern-library item by stable id or exact name."""
        return service.get_library_pattern(path, stable_id, name)

    @mcp.tool()
    def validate_library_component(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Validate component pins, attached pattern and pin-to-pad mapping."""
        return service.validate_library_component(path, stable_id, name)

    @mcp.tool()
    def validate_library_pattern(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Validate pattern pad numbering, styles, geometry, holes and annular rings."""
        return service.validate_library_pattern(path, stable_id, name)

    @mcp.tool()
    def validate_pin_pad_mapping(
        path: str,
        stable_id: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Validate component pin numbers against pads of its embedded attached pattern."""
        return service.validate_pin_pad_mapping(path, stable_id, name)

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
        external_records: list[dict[str, Any]], path: str | None = None
    ) -> dict[str, Any]:
        """Compare typed external BOM rows with normalized design records by RefDes."""
        return service.compare_bom_to_design(external_records, path=path)

    @mcp.tool()
    def find_missing_component_fields(
        required_fields: list[str], path: str | None = None
    ) -> dict[str, Any]:
        """Find components missing explicit required BOM fields."""
        return service.find_missing_component_fields(required_fields, path=path)

    @mcp.tool()
    def group_bom(
        path: str | None = None, include_dnp: bool = True
    ) -> dict[str, Any]:
        """Group BOM records by exact sourcing identity."""
        return service.group_bom(path, include_dnp=include_dnp)

    @mcp.tool()
    def detect_duplicate_bom_items(path: str | None = None) -> dict[str, Any]:
        """List identical BOM identity groups containing multiple RefDes."""
        return service.detect_duplicate_bom_items(path)

    @mcp.tool()
    def validate_mpn_consistency(path: str | None = None) -> dict[str, Any]:
        """Detect one MPN mapped to conflicting manufacturer/value/pattern metadata."""
        return service.validate_mpn_consistency(path)

    @mcp.tool()
    def validate_value_pattern_consistency(path: str | None = None) -> dict[str, Any]:
        """Detect value/pattern inconsistency across multi-part units and shared MPNs."""
        return service.validate_value_pattern_consistency(path)

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
        )

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

    @mcp.tool()
    def query_objects(
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "stable_id",
    ) -> dict[str, Any]:
        """Structured query over the normalized model."""
        return service.query_objects(path, selector, offset, limit, sort_by)

    @mcp.tool()
    def get_object(stable_id: str, path: str | None = None) -> dict[str, Any]:
        """Return one normalized object by stable id."""
        return service.get_object(stable_id, path)

    @mcp.tool()
    def get_connectivity_graph(path: str | None = None) -> dict[str, Any]:
        """Return normalized logical endpoints and separate physical PCB ratlines."""
        return service.get_connectivity_graph(path)

    @mcp.tool()
    def scan_diptrace_documents(
        root: str | None = None,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """Find DipTrace XML/native-XML documents inside an allowed directory."""
        return service.scan_documents(root, recursive)

    @mcp.tool()
    def summarize_design(path: str | None = None) -> dict[str, Any]:
        """Summarize a PCB or schematic: components, nets, layers, sheets and connectivity."""
        return service.summarize(path)

    @mcp.tool()
    def list_components(
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List and search PCB components or grouped schematic component parts."""
        return service.components(path, query, offset, limit)

    @mcp.tool()
    def get_component(refdes: str, path: str | None = None) -> dict[str, Any]:
        """Get one component, its parts/pads and all connected nets by reference designator."""
        return service.component(refdes, path)

    @mcp.tool()
    def list_nets(
        path: str | None = None,
        query: str | None = None,
        include_endpoints: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List PCB or schematic nets with component endpoints."""
        return service.nets(path, query, include_endpoints, offset, limit)

    @mcp.tool()
    def get_design_rules(path: str | None = None) -> dict[str, Any]:
        """Read PCB DRC/routing rules or schematic ERC settings from DipTrace XML."""
        return service.rules(path)

    @mcp.tool()
    def read_xml_fragment(
        xpath: str = ".",
        path: str | None = None,
        max_matches: int = 25,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        """Read bounded XML fragments using ElementTree-compatible XPath."""
        return service.read_xml(path, xpath, max_matches, max_characters)

    @mcp.tool()
    def apply_xml_edits(
        edits: list[XmlEditInput],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Preview edits, or write them with the preview SHA-256, match guards and backups."""
        operations = [XmlEdit(**edit.model_dump()) for edit in edits]
        return service.apply_edits(operations, path, dry_run, expected_sha256)

    @mcp.tool()
    def create_schematic_document(
        path: str,
        sheets: list[str] | None = None,
        units: str = "mm",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new DipTrace Schematic XML document inside the workspace."""
        return service.create_document(
            "schematic", path, sheets=sheets, units=units, overwrite=overwrite
        )

    @mcp.tool()
    def create_pcb_document(
        path: str,
        pcb: dict[str, Any] | None = None,
        units: str = "mm",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new DipTrace PCB XML document (outline, layers, stackup, rules).

        This is synthetic MCP-generated content. It has the correct XML structure
        but has NOT been verified by DipTrace open/save. Use create_document_from_seed
        with a real DipTrace export when DipTrace compatibility is required.
        """
        return service.create_document("pcb", path, pcb=pcb, units=units, overwrite=overwrite)

    @mcp.tool()
    def create_document_from_seed(
        seed_path: str,
        target_path: str,
        expected_seed_sha256: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a new project document by copying an existing DipTrace-shaped XML seed.

        The seed must be valid DipTrace XML (PCB, Schematic, ComponentLibrary, or
        PatternLibrary). The copy preserves all unknown XML, line endings, and
        unsupported sections.

        Trust model: The client cannot assign a validation level. Trust is derived
        exclusively from verifiable metadata (provenance sidecar) found alongside
        the seed. If no metadata is present, the copy defaults to
        synthetic_parser_only.

        This is the recommended way to start a new project when DipTrace
        compatibility is required, as opposed to create_pcb_document/create_schematic_document
        which produce synthetic MCP-generated XML.
        """
        return service.create_document_from_seed(
            seed_path,
            target_path,
            expected_seed_sha256=expected_seed_sha256,
            overwrite=overwrite,
        )

    @mcp.tool()
    def begin_transaction(
        path: str | None = None,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a transaction snapshot for a document or live session."""
        return service.begin_transaction(path, expected_sha256, notes)

    @mcp.tool()
    def stage_operations(txid: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Attach semantic operations to an existing transaction."""
        return service.stage_operations(txid, operations)

    @mcp.tool()
    def preview_transaction(txid: str) -> dict[str, Any]:
        """Render a transaction preview without writing to disk."""
        return service.preview_transaction(txid)

    @mcp.tool()
    def validate_transaction(txid: str) -> dict[str, Any]:
        """Validate a staged transaction and return the same preview payload."""
        return service.validate_transaction(txid)

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

    @mcp.tool()
    def list_transactions() -> dict[str, Any]:
        """List known transactions."""
        return service.list_transactions()

    @mcp.tool()
    def move_components(
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Lock selected PCB components or schematic parts."""
        return service.set_component_lock(
            selector, True, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def unlock_components(
        selector: dict[str, Any] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Unlock selected PCB components or schematic parts."""
        return service.set_component_lock(
            selector, False, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def set_component_properties(
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any],
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
        selector: dict[str, Any],
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
        selector: dict[str, Any],
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
        selector: dict[str, Any],
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
        selector: dict[str, Any],
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
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List free board text and component silk/assembly markings."""
        return service.list_board_texts(path, selector)

    @mcp.tool()
    def move_board_texts(
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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

    @mcp.tool()
    def set_pin_no_connect(
        no_connect: bool,
        selector: dict[str, Any] | None = None,
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
    def set_component_fields(
        fields: dict[str, str],
        selector: dict[str, Any] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        """Set custom fields on selected schematic parts or PCB components."""
        return service.set_component_properties(
            selector,
            fields=fields,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
            allow_locked=allow_locked,
        )

    @mcp.tool()
    def rename_net(
        new_name: str,
        selector: dict[str, Any] | None = None,
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
    def connect_pins(
        net: str,
        pins: list[dict[str, Any]],
        allow_reconnect: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Connect part pins to a net; the net is created when missing."""
        return service.connect_pins(
            net, pins, allow_reconnect, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def disconnect_pins(
        selector: dict[str, Any] | None = None,
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
        points: list[dict[str, Any]],
        start: dict[str, Any],
        end: dict[str, Any],
        sheet: int = 0,
        hidden_power: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a wire to a schematic net (official Wire/Points XML structure)."""
        return service.add_wire(
            net, points, start, end, sheet, hidden_power, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def delete_wire(
        selector: dict[str, Any] | None = None,
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
        font_size: int = 10,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a net-bound text label shape to a schematic sheet."""
        return service.add_net_label(
            net, x, y, sheet, text, font_size, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def set_panelization(
        panel: dict[str, Any],
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

    @mcp.tool()
    def update_net_class_rules(
        class_name: str,
        layer: str | None = None,
        width: float | None = None,
        min_width: float | None = None,
        max_width: float | None = None,
        clearance: float | None = None,
        neck_width: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Update verified per-layer width and clearance fields of a PCB net class."""
        return service.update_net_class_rules(
            class_name,
            layer=layer,
            width=width,
            min_width=min_width,
            max_width=max_width,
            clearance=clearance,
            neck_width=neck_width,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def assign_nets_to_class(
        class_name: str,
        selector: dict[str, Any] | None = None,
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
    def set_diff_pair_rules(
        class_name: str,
        differential_gap: float,
        width: float | None = None,
        neck_width: float | None = None,
        max_uncoupled_length: float | None = None,
        tolerance: float | None = None,
        layer: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Update documented differential-pair fields on an existing net class."""
        return service.update_net_class_rules(
            class_name,
            layer=layer,
            width=width,
            neck_width=neck_width,
            differential_gap=differential_gap,
            max_uncoupled_length=max_uncoupled_length,
            tolerance=tolerance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def set_length_constraints(
        class_name: str,
        fixed_length: float,
        length_delta: float,
        check_length: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set documented fixed-length and tolerance fields on an existing net class."""
        return service.update_net_class_rules(
            class_name,
            check_length=check_length,
            fixed_length=fixed_length,
            length_delta=length_delta,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def list_testpoints(
        path: str | None = None,
        selector: dict[str, Any] | None = None,
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
        testpoints: list[dict[str, Any]],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add explicit standalone-pad testpoints and connect them to existing nets atomically."""
        return service.add_testpoints(
            testpoints, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def move_testpoints(
        selector: dict[str, Any] | None = None,
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
        selector: dict[str, Any] | None = None,
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
    def check_silkscreen(path: str | None = None) -> dict[str, Any]:
        """Run the implemented deterministic silkscreen checks."""
        return service.run_review(
            path,
            profile="silkscreen",
            categories={"silkscreen"},
        )

    @mcp.tool()
    def plan_silkscreen(
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        clearance: float = 0.2,
        board_edge_clearance: float = 0.2,
        grid: float = 0.25,
        search_steps: int = 4,
        include_board_texts: bool = False,
        avoid_component_bodies: bool = False,
    ) -> dict[str, Any]:
        """Generate and persist a deterministic legal silkscreen placement plan."""
        return service.plan_silkscreen(
            path,
            selector=selector,
            clearance=clearance,
            board_edge_clearance=board_edge_clearance,
            grid=grid,
            search_steps=search_steps,
            include_board_texts=include_board_texts,
            avoid_component_bodies=avoid_component_bodies,
        )

    @mcp.tool()
    def apply_silkscreen_plan(
        plan_id: str,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Stage or commit a stored silkscreen plan as one semantic transaction."""
        return service.apply_silkscreen_plan(
            plan_id,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def analyze_placement(
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
    ) -> dict[str, Any]:
        """Measure current component overlap, containment and placement score."""
        return service.analyze_placement(
            path,
            selector=selector,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
        )

    @mcp.tool()
    def generate_placement_candidates(
        selector: dict[str, Any],
        path: str | None = None,
        region: dict[str, float] | None = None,
        allowed_sides: list[Literal["Top", "Bottom"]] | None = None,
        allowed_rotations: list[float] | None = None,
        grid: float = 0.5,
        search_steps: int = 8,
        max_candidates_per_component: int = 256,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        deterministic_seed: int = 0,
        time_budget_ms: int = 5_000,
        respect_keepouts: bool = True,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Generate bounded deterministic local placement candidates."""
        return service.generate_placement_candidates(
            selector,
            path,
            region=region,
            allowed_sides=allowed_sides or [],
            allowed_rotations=allowed_rotations or [],
            grid=grid,
            search_steps=search_steps,
            max_candidates_per_component=max_candidates_per_component,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            deterministic_seed=deterministic_seed,
            time_budget_ms=time_budget_ms,
            respect_keepouts=respect_keepouts,
            weights=weights or {},
        )

    @mcp.tool()
    def score_placement(
        placements: list[dict[str, Any]],
        path: str | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Score an explicit component placement proposal without editing XML."""
        return service.score_placement(
            placements,
            path,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=weights,
        )

    @mcp.tool()
    def plan_component_placement(
        selector: dict[str, Any],
        path: str | None = None,
        region: dict[str, float] | None = None,
        allowed_sides: list[Literal["Top", "Bottom"]] | None = None,
        allowed_rotations: list[float] | None = None,
        grid: float = 0.5,
        search_steps: int = 8,
        max_candidates_per_component: int = 256,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        deterministic_seed: int = 0,
        time_budget_ms: int = 5_000,
        respect_keepouts: bool = True,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Create a validated deterministic local component-placement plan."""
        return service.plan_component_placement(
            selector,
            path,
            region=region,
            allowed_sides=allowed_sides or [],
            allowed_rotations=allowed_rotations or [],
            grid=grid,
            search_steps=search_steps,
            max_candidates_per_component=max_candidates_per_component,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            deterministic_seed=deterministic_seed,
            time_budget_ms=time_budget_ms,
            respect_keepouts=respect_keepouts,
            weights=weights or {},
        )

    @mcp.tool()
    def legalize_component_placement(
        selector: dict[str, Any],
        path: str | None = None,
        grid: float = 0.5,
        search_steps: int = 8,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        time_budget_ms: int = 5_000,
    ) -> dict[str, Any]:
        """Plan local moves that remove component overlap and containment violations."""
        return service.plan_component_placement(
            selector,
            path,
            grid=grid,
            search_steps=search_steps,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            time_budget_ms=time_budget_ms,
        )

    @mcp.tool()
    def apply_component_placement_plan(
        plan_id: str,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Stage or commit a stored component-placement plan transactionally."""
        return service.apply_component_placement_plan(
            plan_id,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def add_trace(
        net: str,
        start_object_id: str,
        end_object_id: str,
        points: list[dict[str, Any]],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add an explicit validated trace path between two normalized pad endpoints."""
        return service.add_trace(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            points=points,
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def replace_trace(
        trace_id: str,
        points: list[dict[str, Any]],
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Replace trace geometry while preserving both connected endpoints."""
        return service.replace_trace(
            trace_id,
            points,
            layer=layer,
            width=width,
            clearance=clearance,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def delete_trace(
        selector: dict[str, Any],
        allow_connectivity_regression: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Delete selected traces; connectivity regression requires explicit opt-in."""
        return service.delete_trace(
            selector,
            allow_connectivity_regression=allow_connectivity_regression,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def set_trace_width(
        selector: dict[str, Any],
        width: float,
        segment_indices: list[int] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set selected trace segment widths with exported DRC minimum checks."""
        return service.set_trace_width(
            selector,
            width,
            segment_indices=segment_indices,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def add_via(
        trace_id: str,
        x: float,
        y: float,
        via_style: str,
        layer_before: str | None = None,
        layer_after: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Add a verified ViaStyle trace point on an existing segment."""
        return service.add_via(
            trace_id,
            x,
            y,
            via_style,
            layer_before=layer_before,
            layer_after=layer_after,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def move_via(
        selector: dict[str, Any],
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Move selected trace-point vias transactionally."""
        return service.move_via(
            selector,
            dx=dx,
            dy=dy,
            absolute_x=absolute_x,
            absolute_y=absolute_y,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def delete_via(
        selector: dict[str, Any],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Remove ViaStyle from selected trace points."""
        return service.delete_via(
            selector,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def set_via_style(
        selector: dict[str, Any],
        via_style: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Set an existing verified project ViaStyle on selected vias."""
        return service.set_via_style(
            selector,
            via_style,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def list_unrouted_connections(
        path: str | None = None,
        nets: list[str] | None = None,
    ) -> dict[str, Any]:
        """List exported ratlines with normalized pad endpoints and lengths."""
        return service.list_unrouted_connections(path, nets=nets)

    @mcp.tool()
    def get_route_details(
        trace_id: str | None = None,
        net: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Return trace segments, per-layer geometric length and via counts."""
        return service.get_route_details(trace_id=trace_id, net=net, path=path)

    @mcp.tool()
    def get_stackup(path: str | None = None) -> dict[str, Any]:
        """Return the normalized physical layer stack without inventing missing Dk values."""
        return service.get_stackup(path)

    @mcp.tool()
    def measure_net_lengths(
        path: str | None = None,
        nets: list[str] | None = None,
        effective_dielectric_constant: float | None = None,
    ) -> dict[str, Any]:
        """Measure geometric centerline lengths and optional preliminary delay."""
        return service.measure_net_lengths(
            path,
            nets=nets,
            effective_dielectric_constant=effective_dielectric_constant,
        )

    @mcp.tool()
    def analyze_length_group(
        nets: list[str],
        tolerance_mm: float | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Compare routed geometric lengths for an explicit group of nets."""
        return service.analyze_length_group(nets, tolerance_mm=tolerance_mm, path=path)

    @mcp.tool()
    def list_differential_pairs(
        path: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List normalized DipTrace project differential pairs and their rules."""
        return service.list_differential_pairs(path, offset=offset, limit=limit)

    @mcp.tool()
    def get_differential_pair(pair: str, path: str | None = None) -> dict[str, Any]:
        """Get one differential pair by stable id, XML id or exact name."""
        return service.get_differential_pair(pair, path)

    @mcp.tool()
    def analyze_differential_pair(
        pair: str, path: str | None = None
    ) -> dict[str, Any]:
        """Measure pair lengths, skew, via balance, coupled length and edge gap."""
        return service.analyze_differential_pair(pair, path)

    @mcp.tool()
    def analyze_differential_pairs(path: str | None = None) -> dict[str, Any]:
        """Analyze all normalized project differential pairs."""
        return service.analyze_differential_pairs(path)

    @mcp.tool()
    def validate_differential_pair(
        pair: str, path: str | None = None
    ) -> dict[str, Any]:
        """Evaluate available exported rules for one differential pair."""
        return service.validate_differential_pair(pair, path)

    @mcp.tool()
    def calculate_impedance(
        structure: Literal[
            "microstrip", "differential_microstrip", "symmetric_stripline"
        ],
        width_mm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        gap_mm: float | None = None,
        frequency_hz: float | None = None,
        target_ohm: float | None = None,
        tolerance_ohm: float | None = None,
    ) -> dict[str, Any]:
        """Calculate a preliminary analytical impedance with explicit assumptions."""
        return service.calculate_impedance(
            structure=structure,
            width_mm=width_mm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            gap_mm=gap_mm,
            frequency_hz=frequency_hz,
            target_ohm=target_ohm,
            tolerance_ohm=tolerance_ohm,
        )

    @mcp.tool()
    def suggest_trace_geometry_for_impedance(
        target_ohm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        minimum_width_mm: float,
        maximum_width_mm: float,
        tolerance_ohm: float = 0.01,
    ) -> dict[str, Any]:
        """Synthesize a bounded microstrip width using the analytical model."""
        return service.suggest_trace_geometry_for_impedance(
            target_ohm=target_ohm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            minimum_width_mm=minimum_width_mm,
            maximum_width_mm=maximum_width_mm,
            tolerance_ohm=tolerance_ohm,
        )

    @mcp.tool()
    def analyze_stackup_for_impedance(path: str | None = None) -> dict[str, Any]:
        """Find only complete outer-layer microstrip geometries in the physical stackup."""
        return service.analyze_stackup_for_impedance(path)

    @mcp.tool()
    def validate_impedance_constraints(
        constraints: list[dict[str, Any]], path: str | None = None
    ) -> dict[str, Any]:
        """Validate explicit net/layer/target constraints against routed widths and stackup."""
        return service.validate_impedance_constraints(constraints, path=path)

    @mcp.tool()
    def analyze_controlled_impedance(
        constraints: list[dict[str, Any]], path: str | None = None
    ) -> dict[str, Any]:
        """Analyze explicit controlled-impedance nets; no target is inferred silently."""
        return service.analyze_controlled_impedance_nets(constraints, path=path)

    @mcp.tool()
    def list_copper_pours(
        path: str | None = None, offset: int = 0, limit: int = 100
    ) -> dict[str, Any]:
        """List normalized copper-pour boundaries and refill-state metadata."""
        return service.list_copper_pours(path, offset=offset, limit=limit)

    @mcp.tool()
    def analyze_plane_continuity(path: str | None = None) -> dict[str, Any]:
        """Inspect exported pour boundaries without claiming final-refill continuity."""
        return service.analyze_plane_continuity(path)

    @mcp.tool()
    def analyze_return_path(
        path: str | None = None,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
        stitching_radius_mm: float = 2.0,
    ) -> dict[str, Any]:
        """Run geometry-based reference-plane and return-via heuristics."""
        return service.analyze_return_path(
            path,
            nets=nets,
            reference_nets=reference_nets,
            stitching_radius_mm=stitching_radius_mm,
        )

    @mcp.tool()
    def route_connection(
        net: str,
        start_object_id: str,
        end_object_id: str,
        layer: str,
        width: float,
        clearance: float = 0.2,
        grid: float = 0.5,
        bend_cost: float = 0.2,
        preferred_layers: list[str] | None = None,
        start_layer: str | None = None,
        end_layer: str | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        max_detour: float = 3.0,
        max_nodes: int = 100_000,
        time_budget_ms: int = 5_000,
        avoid_component_bodies: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route one pad-to-pad connection with bounded deterministic 45-degree A*."""
        return service.route_connection(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            bend_cost=bend_cost,
            preferred_layers=preferred_layers,
            start_layer=start_layer,
            end_layer=end_layer,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            max_nodes=max_nodes,
            time_budget_ms=time_budget_ms,
            avoid_component_bodies=avoid_component_bodies,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def route_net(
        net: str,
        layer: str,
        width: float,
        clearance: float = 0.2,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route exported ratline connections for one net transactionally."""
        return service.route_net(
            net,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            preferred_layers=preferred_layers,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def route_connections(
        connections: list[dict[str, Any]],
        ripup_retry: bool = True,
        max_ripup_attempts: int = 4,
        ordering: Literal["input", "congestion_aware"] = "congestion_aware",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route multiple connections sequentially with bounded rip-up/retry."""
        return service.route_connections(
            connections,
            ripup_retry=ripup_retry,
            max_ripup_attempts=max_ripup_attempts,
            ordering=ordering,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def analyze_routing_congestion(
        connections: list[dict[str, Any]],
        ordering: Literal["input", "congestion_aware"] = "congestion_aware",
        path: str | None = None,
    ) -> dict[str, Any]:
        """Rank route connections by deterministic corridor congestion without editing."""
        return service.analyze_routing_congestion(
            connections,
            ordering=ordering,
            path=path,
        )

    @mcp.tool()
    def route_diff_pair(
        pair: str,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float = 0.2,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Route both nets from one coupled centerline with symmetric via insertion."""
        return service.route_diff_pair(
            pair,
            layer=layer,
            preferred_layers=preferred_layers,
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def plan_diff_pair_route(
        pair: str,
        layer: str,
        preferred_layers: list[str] | None = None,
        width: float | None = None,
        gap: float | None = None,
        clearance: float = 0.2,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Persist a coupled differential-pair route plan and deterministic preview."""
        return service.plan_diff_pair_route(
            pair,
            layer=layer,
            preferred_layers=preferred_layers,
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            path=path,
        )

    @mcp.tool()
    def plan_route_nets(
        nets: list[str],
        layer: str,
        width: float,
        clearance: float = 0.2,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Persist a sequential bounded local route plan for up to 20 connections."""
        return service.plan_route_nets(
            nets,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            preferred_layers=preferred_layers,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            path=path,
        )

    @mcp.tool()
    def apply_route_plan(
        plan_id: str,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Stage or commit a stored local route plan as one transaction."""
        return service.apply_route_plan(
            plan_id,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

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

    @mcp.tool()
    def import_autorouter_ses(
        plan_id: str,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Preview or commit a previously inspected SES route plan transactionally."""
        return service.import_autorouter_ses(
            plan_id,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
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

    @mcp.tool()
    def run_drc(path: str | None = None) -> dict[str, Any]:
        """Run implemented offline PCB geometry and connectivity checks."""
        return service.run_review(
            path,
            profile="drc_basic",
            categories={"placement", "connectivity", "clearance"},
        )

    @mcp.tool()
    def run_connectivity_check(path: str | None = None) -> dict[str, Any]:
        """Run deterministic PCB or schematic connectivity checks."""
        return service.run_review(
            path,
            profile="connectivity",
            categories={"connectivity"},
        )

    @mcp.tool()
    def run_silkscreen_check(path: str | None = None) -> dict[str, Any]:
        """Run implemented offline silkscreen overlap checks."""
        return service.run_review(
            path,
            profile="silkscreen",
            categories={"silkscreen"},
        )

    @mcp.tool()
    def run_component_clearance_check(path: str | None = None) -> dict[str, Any]:
        """Run component overlap and board-containment checks."""
        return service.run_review(
            path,
            profile="component_clearance",
            categories={"placement"},
        )

    @mcp.tool()
    def run_erc(path: str | None = None) -> dict[str, Any]:
        """Run implemented offline schematic connectivity and metadata checks."""
        return service.run_review(
            path,
            profile="erc_basic",
            categories={"connectivity", "metadata"},
        )

    @mcp.tool()
    def run_board_review(path: str | None = None) -> dict[str, Any]:
        """Aggregate all currently registered deterministic PCB checks."""
        return service.run_review(path, profile="board_review")

    @mcp.tool()
    def run_schematic_review(path: str | None = None) -> dict[str, Any]:
        """Aggregate deterministic schematic connectivity, metadata and BOM checks."""
        return service.run_review(path, profile="schematic_review")

    @mcp.tool()
    def run_manufacturing_review(path: str | None = None) -> dict[str, Any]:
        """Run available offline DFM geometry and stackup checks."""
        return service.run_review(
            path, profile="dfm_basic", categories={"manufacturing"}
        )

    @mcp.tool()
    def run_manufacturing_geometry_check(path: str | None = None) -> dict[str, Any]:
        """Run deterministic minimum feature, edge, drill and annular-ring checks."""
        return service.run_review(
            path, profile="manufacturing_geometry", categories={"manufacturing"}
        )

    @mcp.tool()
    def run_assembly_review(path: str | None = None) -> dict[str, Any]:
        """Run available footprint/design-cache assembly checks."""
        return service.run_review(path, profile="dfa_basic", categories={"assembly"})

    @mcp.tool()
    def run_testability_review(path: str | None = None) -> dict[str, Any]:
        """Review explicit standalone testpoint coverage."""
        return service.run_review(path, profile="dft_basic", categories={"testability"})

    @mcp.tool()
    def run_bom_review(path: str | None = None) -> dict[str, Any]:
        """Review deterministic manufacturer/MPN/DNP metadata completeness."""
        return service.run_review(path, profile="bom_basic", categories={"bom"})

    @mcp.tool()
    def run_thermal_review(path: str | None = None) -> dict[str, Any]:
        """Review explicit power and thermal-strategy metadata when available."""
        return service.run_review(path, profile="thermal_basic", categories={"thermal"})

    @mcp.tool()
    def get_findings(report_id: str) -> dict[str, Any]:
        """Read all structured findings from a stored review report."""
        return service.get_findings(report_id)

    @mcp.tool()
    def get_finding(finding_id: str) -> dict[str, Any]:
        """Read one structured finding by deterministic id."""
        return service.get_finding(finding_id)

    @mcp.tool()
    def finish_live_session(action: Literal["apply", "cancel"]) -> dict[str, Any]:
        """Tell the DipTrace bridge to import working XML or discard the live session."""
        return service.finish_live_session(action)

    @mcp.resource("diptrace://status", mime_type="application/json")
    def status_resource() -> str:
        """Current DipTrace MCP configuration and live-session state."""
        return json.dumps(service.status(), ensure_ascii=False, indent=2)

    @mcp.resource("diptrace://capabilities", mime_type="application/json")
    def capabilities_resource() -> str:
        """Current capability discovery payload."""
        return json.dumps(service.get_capabilities(), ensure_ascii=False, indent=2)

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
            raise ValueError("Review report does not belong to the requested document")
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
        return json.dumps(
            service.transactions.read(txid).model_dump(),
            ensure_ascii=False,
            indent=2,
        )

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

    @mcp.prompt()
    def review_diptrace_design(scope: str = "full") -> str:
        """Create a safe workflow prompt for reviewing the active DipTrace design."""
        return (
            "Review the active DipTrace design. First call diptrace_status and summarize_design. "
            f"Review scope: {scope}. Inspect components, nets and design rules as needed. Report "
            "findings with exact RefDes/net names. Do not edit unless explicitly requested. "
            "If edits are requested, preview with dry_run=true, explain the diff, then commit "
            "with the returned before_sha256 and finish the live session only after confirmation."
        )

    @mcp.prompt()
    def review_board_before_release(scope: str = "full") -> str:
        return (
            "Review the board before release. Start with get_capabilities, summarize_design, "
            "get_board_model, get_design_rules and a focused query_objects pass. Stop if any "
            "capability is unavailable."
        )

    @mcp.prompt()
    def place_selected_components_safely(scope: str = "selected") -> str:
        return (
            "Place selected components safely. Inspect the current model, build a transaction, "
            "preview it, review the diff and commit only after confirming no locked parts move."
        )

    @mcp.prompt()
    def review_schematic_before_layout(scope: str = "full") -> str:
        return (
            "Review the schematic before layout. Inspect components, nets, ERC settings and "
            "the connection graph, then summarize blocking issues and missing metadata."
        )

    @mcp.prompt()
    def place_decoupling_network(component_selector: str, region: str = "local") -> str:
        return (
            f"Required inputs: target selector={component_selector}; allowed region={region}. "
            "Call get_capabilities, query_objects, get_connectivity_graph, analyze_placement, "
            "generate_placement_candidates and plan_component_placement. The model decides which "
            "parts form the decoupling network. Inspect SVG/JSON preview before any write; apply "
            "the selected plan as a dry-run transaction, then run localized DRC. Stop on ambiguous "
            "nets, locked objects, unknown body geometry, SHA conflict or any DRC regression."
        )

    @mcp.prompt()
    def route_critical_net(net: str, constraints: str = "use exported rules") -> str:
        return (
            f"Required net={net}; constraints={constraints}. Call get_capabilities, get_stackup, "
            "list_unrouted_connections and get_route_details. Use route_connection or "
            "plan_route_nets only when bounded 45-degree routing satisfies the "
            "constraints. Inspect route preview and dry-run transaction before commit; rerun "
            "connectivity and DRC after write. "
            "The model chooses routing priority. Vias require explicit layers/style/budget. Stop "
            "if push-and-shove or unknown rules are required, or if connectivity/DRC regresses."
        )

    @mcp.prompt()
    def route_diff_pair_with_constraints(pair: str) -> str:
        return (
            f"Required differential pair={pair}. Call get_capabilities, get_stackup, "
            "get_differential_pair, analyze_differential_pair and analyze_stackup_for_impedance. "
            "Use calculate_impedance with differential_microstrip, then plan_diff_pair_route. "
            "Inspect SVG/JSON and skew/via metrics before apply_route_plan; rerun pair validation "
            "and DRC after commit. The model decides whether analytical assumptions are "
            "acceptable. "
            "Stop on incomplete stackup, incompatible pad spacing, unresolved DRC or SHA conflict."
        )

    @mcp.prompt()
    def clean_silkscreen_for_manufacturing(scope: str = "whole board") -> str:
        return (
            f"Required scope={scope}. Call check_silkscreen, plan_silkscreen, inspect the "
            "plan score, "
            "unresolved labels and SVG preview, then apply_silkscreen_plan with dry_run=true. The "
            "model decides how to handle unresolved labels. Commit only after preview; rerun "
            "check_silkscreen and manufacturing review. Stop on locked labels, incomplete mask "
            "geometry, unexpected scope or a new finding."
        )

    @mcp.prompt()
    def add_testpoints_for_fixture(target_nets: str, side: str = "Top") -> str:
        return (
            f"Required target nets={target_nets}; probe side={side}. Call get_connectivity_graph, "
            "list_testpoints, review_testpoint_coverage and find_testpoint_candidates. The model "
            "chooses coverage priority. Stage add_testpoints as a dry-run transaction and inspect "
            "preview before commit; rerun testability and DRC checks. Stop if accessibility "
            "is only "
            "estimated, keepout data is incomplete or coverage would duplicate an existing point."
        )

    @mcp.prompt()
    def review_return_paths(nets: str) -> str:
        return (
            f"Required nets={nets}. Call get_stackup, list_copper_pours, analyze_plane_continuity "
            "and analyze_return_path. Treat results as geometry-based heuristics, not "
            "full-wave SI. "
            "The model decides criticality and remediation. Stop if reference layers, plane net or "
            "refilled copper geometry are unknown; report skipped checks and confidence."
        )

    @mcp.prompt()
    def prepare_fabrication_export(scope: str = "whole board") -> str:
        return (
            f"Required release scope={scope}. Run board, manufacturing, connectivity and stackup "
            "reviews first. Stop on blocking findings or incomplete stackup. Call "
            "export_fabrication_outputs only for the generic review manifest; it does not generate "
            "Gerber or NC drill. The model decides release readiness and must not label "
            "this bundle "
            "fabrication-ready."
        )

    @mcp.prompt()
    def prepare_assembly_export(variant: str = "default") -> str:
        return (
            f"Required variant={variant}. Run assembly, BOM and silkscreen reviews, then call "
            "export_assembly_outputs for generic placement/BOM artifacts. Stop on DNP ambiguity, "
            "missing pattern/MPN or unknown coordinate convention. The model selects variant "
            "policy "
            "and must map the generic CSV to the assembler outside MCP."
        )

    @mcp.prompt(name="review_bom")
    def review_bom_workflow(variant: str = "all") -> str:
        return (
            f"Required variant={variant}. Call get_bom, review_bom, find_missing_component_fields, "
            "validate_mpn_consistency and validate_value_pattern_consistency. The model decides "
            "substitution policy. Stop on DNP/variant ambiguity; no internet sourcing is performed."
        )

    @mcp.prompt()
    def compare_schematic_and_pcb(schematic_path: str, pcb_path: str) -> str:
        return (
            f"Required schematic={schematic_path}; PCB={pcb_path}. Read both document infos, call "
            "compare_schematic_to_pcb and inspect RefDes, value, net and endpoint deltas. The "
            "model decides whether differences are intentional. Stop before edits on ambiguous "
            "pin-to-pad "
            "mapping or source SHA changes."
        )

    @mcp.prompt()
    def synchronize_schematic_to_pcb(schematic_path: str, pcb_path: str) -> str:
        return (
            f"Synchronize schematic={schematic_path} into PCB={pcb_path}. First call "
            "compare_schematic_to_pcb and inspect component libraries. Supply explicit "
            "pattern_style and multi-part pin_map entries wherever XML evidence is missing. "
            "Call sync_schematic_to_pcb with dry_run=true, inspect the XML/SVG preview and "
            "commit with the returned source SHA only after pin-to-pad mapping is complete. "
            "Then legalize placement and rerun connectivity and DRC."
        )

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server for DipTrace XML and live projects")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("DIPTRACE_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.environ.get("DIPTRACE_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DIPTRACE_MCP_PORT", "8765")),
    )
    args = parser.parse_args(argv)
    server = create_server()
    server.settings.host = args.host
    server.settings.port = args.port
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
