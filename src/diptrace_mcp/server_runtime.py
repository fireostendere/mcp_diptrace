from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from queue import Empty, Queue
from typing import Annotated, Any, Literal

import anyio
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.shared.message import SessionMessage
from pydantic import Field

from . import __version__
from .config import Settings
from .domain import BoardModelSection, QuerySelector
from .errors import ObjectNotFoundError
from .operations import (
    AddTestpointOperation,
    PinEndpoint,
    SetPanelizationOperation,
    StagedOperationInput,
    TracePathPoint,
    WireEndpoint,
    WirePathPoint,
)
from .pattern_recommendation import PatternRequirement
from .placement import PlacementProposal
from .reference_rules import EngineeringRulePack
from .routing import RouteConnectionConfig
from .scaffolding import (
    DEFAULT_FORMAT_VERSION,
    PcbScaffold,
)
from .server_inputs import (
    _INPUT_SCHEMA_RESOURCE,
    AbandonLiveSessionResult,
    ComponentSyncMappingInput,
    ExpectedLiveWorkingSha256Input,
    ExpectedTargetSha256Input,
    ExternalBomRecordInput,
    FinishLiveSessionResult,
    FormatVersionInput,
    ImpedanceConstraintInput,
    PanelizationInput,
    PcbScaffoldInput,
    RoundtripEvidenceInput,
    RouteConnectionInput,
    SchematicRepairMoveInput,
    SelectorInput,
    SyncPlacementInput,
    XmlEditInput,
    _finalize_tool_descriptions,
)
from .service import DipTraceService
from .synchronization import ComponentSyncMapping, SyncPlacement
from .xml_document import XmlEdit


def create_server(
    settings: Settings | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastMCP:
    service = DipTraceService(settings or Settings.from_env())
    mcp = FastMCP(
        name="DipTrace MCP",
        instructions=(
            "Inspect and safely edit DipTrace XML. Without a path, tools use the active live "
            "DipTrace bridge session. Prefer semantic tools with preview/commit/rollback. "
            "Low-level XML edits remain available for expert use. Stable object ids come from "
            "query_objects or normalized model/list tools; transaction, plan, report, export and "
            "job ids come from their corresponding create/run tools."
        ),
        json_response=True,
        host=host,
        port=port,
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
    def validate_roundtrip_evidence(
        path: str,
        evidence: RoundtripEvidenceInput,
    ) -> dict[str, Any]:
        (
            "Validate distinct allowed-root evidence roles and exact SHA bindings "
            "without writing.\n\n"
            "The bounded result is always authority=user_supplied and grants_high_trust=false."
        )

        reexport = evidence.reexport
        return service.validate_roundtrip_evidence(
            path,
            source_path=evidence.source.path,
            source_sha256=evidence.source.sha256,
            saved_path=evidence.saved.path,
            saved_sha256=evidence.saved.sha256,
            reexport_path=reexport.path if reexport is not None else None,
            reexport_sha256=reexport.sha256 if reexport is not None else None,
        )

    @mcp.tool()
    def record_roundtrip_evidence(
        path: str,
        evidence: RoundtripEvidenceInput,
    ) -> dict[str, Any]:
        (
            "Write a user-supplied evidence manifest and provenance sidecar, not design bytes.\n\n"
            "This explicitly writes metadata, returns written=true only after both files verify, "
            "remains authority=user_supplied, and can never grant high trust."
        )

        reexport = evidence.reexport
        return service.record_roundtrip_evidence(
            path,
            source_path=evidence.source.path,
            source_sha256=evidence.source.sha256,
            saved_path=evidence.saved.path,
            saved_sha256=evidence.saved.sha256,
            reexport_path=reexport.path if reexport is not None else None,
            reexport_sha256=reexport.sha256 if reexport is not None else None,
        )

    @mcp.tool()
    def get_board_model(
        path: str | None = None,
        section: Annotated[
            BoardModelSection,
            Field(description="Count-only summary or one normalized PCB collection."),
        ] = "summary",
        offset: Annotated[
            int,
            Field(ge=0, description="Zero-based record offset within the selected section."),
        ] = 0,
        limit: Annotated[
            int,
            Field(
                ge=1,
                le=500,
                description="Computational record cap; not an engineering limit.",
            ),
        ] = 100,
    ) -> dict[str, Any]:
        """Return one strictly byte-bounded PCB page or a count-only summary."""
        return service.board_model(path, section=section, offset=offset, limit=limit)

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
    def query_builtin_library_catalog(
        diptrace_root: str | None = None,
        kind: Literal["component", "pattern", "library"] = "component",
        query: str | None = None,
        offset: int = 0,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> dict[str, Any]:
        """Browse or search the installed DipTrace catalog without modifying native libraries."""
        return service.query_builtin_library_catalog(
            diptrace_root, kind, query, offset, limit
        )

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
        selector: SelectorInput | None = None,
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
        """Store a bounded diff resource, or write with its SHA/match guards and a backup."""
        operations = [XmlEdit(**edit.model_dump()) for edit in edits]
        return service.apply_edits(operations, path, dry_run, expected_sha256)

    @mcp.tool()
    def create_schematic_document(
        path: str,
        sheets: list[str] | None = None,
        units: Literal["mm", "inch", "mil"] = "mm",
        format_version: FormatVersionInput = DEFAULT_FORMAT_VERSION,
        overwrite: bool = False,
        expected_sha256: ExpectedTargetSha256Input | None = None,
    ) -> dict[str, Any]:
        """Create synthetic, not DipTrace-verified Schematic XML; overwrite needs current SHA."""
        return service.create_document(
            "schematic",
            path,
            sheets=sheets,
            units=units,
            format_version=format_version,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )

    @mcp.tool()
    def create_pcb_document(
        path: str,
        pcb: PcbScaffoldInput | None = None,
        units: Literal["mm", "inch", "mil"] = "mm",
        format_version: FormatVersionInput = DEFAULT_FORMAT_VERSION,
        overwrite: bool = False,
        expected_sha256: ExpectedTargetSha256Input | None = None,
    ) -> dict[str, Any]:
        (
            "Create a new DipTrace PCB XML document (outline, layers, stackup, rules).\n\n"
            "This is synthetic MCP-generated content. It has the correct XML structure "
            "but has NOT been verified by DipTrace open/save. Use create_document_from_seed "
            "with a real DipTrace export when DipTrace compatibility is required. Replacing "
            "an existing target requires its current SHA."
        )
        return service.create_document(
            "pcb",
            path,
            pcb=pcb,
            units=units,
            format_version=format_version,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )

    @mcp.tool()
    def create_document_from_seed(
        seed_path: str,
        target_path: str,
        expected_seed_sha256: str | None = None,
        overwrite: bool = False,
        expected_sha256: ExpectedTargetSha256Input | None = None,
    ) -> dict[str, Any]:
        (
            "Copy a valid DipTrace-shaped XML seed while preserving unknown XML.\n\n"
            "Validation is derived only from a verified provenance sidecar; without one, "
            "the copy is synthetic_parser_only. Prefer a real export seed when DipTrace "
            "compatibility matters. Replacing an existing target requires its current SHA."
        )
        return service.create_document_from_seed(
            seed_path,
            target_path,
            expected_seed_sha256=expected_seed_sha256,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
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
    def stage_operations(
        txid: str,
        operations: list[StagedOperationInput],
    ) -> dict[str, Any]:
        """Attach registered semantic operations to an existing transaction."""
        return service.stage_operations(
            txid,
            [operation.model_dump() for operation in operations],
        )

    @mcp.tool()
    def preview_transaction(txid: str) -> dict[str, Any]:
        """Store preview artifacts and return bounded metadata without changing the design."""
        return service.preview_transaction(txid)

    @mcp.tool()
    def validate_transaction(txid: str) -> dict[str, Any]:
        """Validate staged operations and return the same bounded preview metadata."""
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
        """List persisted transaction ids, document hashes, states and operation counts."""
        return service.list_transactions()

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
    ) -> dict[str, Any]:
        """Lock selected PCB components or schematic parts."""
        return service.set_component_lock(
            selector, True, path, dry_run, expected_sha256, txid
        )

    @mcp.tool()
    def unlock_components(
        selector: SelectorInput | None = None,
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
    def set_component_fields(
        fields: dict[str, str],
        selector: SelectorInput | None = None,
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
        selector: SelectorInput | None = None,
        clearance: float = 0.2,
        board_edge_clearance: float = 0.2,
        grid: float = 0.25,
        search_steps: int = 4,
        include_board_texts: bool = False,
        avoid_component_bodies: bool = True,
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
        selector: SelectorInput | None = None,
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
        selector: SelectorInput,
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
        placements: list[PlacementProposal],
        path: str | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Score an explicit component placement proposal without editing XML."""
        return service.score_placement(
            [placement.model_dump() for placement in placements],
            path,
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=weights,
        )

    @mcp.tool()
    def plan_component_placement(
        selector: SelectorInput,
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
        selector: SelectorInput,
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
    def rank_schematic_placement_candidates(
        path: str | None = None,
        engineering_rules: EngineeringRulePack | None = None,
    ) -> dict[str, Any]:
        """Rank schematic candidates with optional sourced engineering rules."""
        return service.rank_schematic_placement_candidates(
            path,
            engineering_rules=engineering_rules,
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

    @mcp.tool()
    def apply_schematic_placement_repair_plan(
        plan_id: str,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        """Stage or commit a stored schematic placement-repair plan transactionally."""
        return service.apply_schematic_placement_repair_plan(
            plan_id,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    @mcp.tool()
    def compare_pcb_placement_candidates(
        path: str | None = None,
        profiles: list[
            Literal["balanced", "critical_nets", "noise_aware", "support_compact"]
        ]
        | None = None,
        include_existing_board: bool = True,
        engineering_rules: EngineeringRulePack | None = None,
    ) -> dict[str, Any]:
        """Rank PCB A-D candidates with physics and optional sourced rules."""
        return service.compare_pcb_placement_candidates(
            path,
            profiles=profiles,
            include_existing_board=include_existing_board,
            engineering_rules=engineering_rules,
        )

    @mcp.tool()
    def recommend_patterns(
        requirement: PatternRequirement,
        path: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Rank compatible footprint patterns from a pattern library deterministically."""
        return service.recommend_patterns(requirement, path, limit=limit)

    @mcp.tool()
    def analyze_release_readiness(path: str | None = None) -> dict[str, Any]:
        """Report bounded DFM/DFA/DFT release-readiness findings from exported XML."""
        return service.analyze_release_readiness(path)

    @mcp.tool()
    def add_trace(
        net: str,
        start_object_id: str,
        end_object_id: str,
        points: list[TracePathPoint],
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
            points=[point.model_dump() for point in points],
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
        points: list[TracePathPoint],
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
            [point.model_dump() for point in points],
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
        selector: SelectorInput,
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
        selector: SelectorInput,
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
        selector: SelectorInput,
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
        selector: SelectorInput,
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
        selector: SelectorInput,
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
        constraints: list[ImpedanceConstraintInput],
        path: str | None = None,
    ) -> dict[str, Any]:
        """Validate explicit net/layer/target constraints against routed widths and stackup."""
        return service.validate_impedance_constraints(
            [constraint.model_dump() for constraint in constraints],
            path=path,
        )

    @mcp.tool()
    def analyze_controlled_impedance(
        constraints: list[ImpedanceConstraintInput],
        path: str | None = None,
    ) -> dict[str, Any]:
        """Analyze explicit controlled-impedance nets; no target is inferred silently."""
        return service.analyze_controlled_impedance_nets(
            [constraint.model_dump() for constraint in constraints],
            path=path,
        )

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
        stitching_radius_mm: float,
        path: str | None = None,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
    ) -> dict[str, Any]:
        (
            "Run low-confidence geometry heuristics with a caller-supplied radius.\n\n"
            "All distances are in millimetres, regardless of the document's own Units attribute."
        )
        return service.analyze_return_path(
            path,
            stitching_radius_mm=stitching_radius_mm,
            nets=nets,
            reference_nets=reference_nets,
        )

    @mcp.tool()
    def route_connection(
        net: str,
        start_object_id: str,
        end_object_id: str,
        layer: str,
        width: float,
        clearance: float | None = None,
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
        (
            "Route one pad-to-pad connection with bounded deterministic 45-degree A*.\n\n"
            "Omit clearance to use the applicable document DRC TraceToTrace rule."
        )
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
        clearance: float | None = None,
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
        """Route exported ratlines; omitted clearance comes from document DRC."""
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
        connections: list[RouteConnectionInput],
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
        connections: list[RouteConnectionInput],
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
        clearance: float | None = None,
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
        """Route a coupled pair; omitted clearance comes from document DRC."""
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
        clearance: float | None = None,
        grid: float = 0.025,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 8.0,
        max_detour: float = 3.0,
        start_pad_point_id: str | None = None,
        end_pad_point_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Plan a coupled route; omitted clearance comes from document DRC."""
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
        clearance: float | None = None,
        grid: float = 0.5,
        preferred_layers: list[str] | None = None,
        via_style: str | None = None,
        max_vias: int = 0,
        via_cost: float = 5.0,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Plan bounded routes; omitted clearance comes from document DRC."""
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
    def finish_live_session(
        action: Literal["apply", "cancel"],
        expected_sha256: ExpectedLiveWorkingSha256Input | None = None,
    ) -> FinishLiveSessionResult:
        """Request SHA-256-bound apply/cancel and report only local bridge finalization."""
        return FinishLiveSessionResult.model_validate(
            service.finish_live_session(action, expected_sha256)
        )

    @mcp.tool()
    def abandon_live_session(
        reason: Annotated[
            str,
            Field(
                min_length=1,
                max_length=500,
                description=(
                    "Operator reason for abandoning stale local session state without "
                    "applying its working XML."
                ),
            ),
        ],
    ) -> AbandonLiveSessionResult:
        """Abandon stale local session state without applying its working XML."""
        return AbandonLiveSessionResult.model_validate(
            service.abandon_live_session(reason)
        )

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
        """Review a requested PCB scope before release using available checks."""
        return (
            f"Review the board before release. Review scope: {scope}. "
            "Start with get_capabilities, summarize_design, "
            "get_board_model, get_design_rules and a focused query_objects pass. Stop if any "
            "capability is unavailable."
        )

    @mcp.prompt()
    def place_selected_components_safely(scope: str = "selected") -> str:
        """Plan and preview bounded component placement for a requested scope."""
        return (
            f"Place components safely. Placement scope: {scope}. "
            "Inspect the current model, build a transaction, "
            "preview it, review the diff and commit only after confirming no locked parts move."
        )

    @mcp.prompt()
    def review_schematic_before_layout(scope: str = "full") -> str:
        """Review a requested schematic scope before PCB layout begins."""
        return (
            f"Review the schematic before layout. Review scope: {scope}. "
            "Inspect components, nets, ERC settings and "
            "the connection graph, then summarize blocking issues and missing metadata."
        )

    @mcp.prompt()
    def place_decoupling_network(component_selector: str, region: str = "local") -> str:
        """Plan a bounded decoupling-network placement around selected components."""
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
        """Plan a bounded route for one explicitly named critical net."""
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
        """Plan a differential-pair route using explicit stackup and pair constraints."""
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
        """Plan and validate silkscreen cleanup for the requested board scope."""
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
        """Plan guarded testpoint coverage for explicitly selected nets."""
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
        """Review geometry-based return-path heuristics for selected nets."""
        return (
            f"Required nets={nets}. Call get_stackup, list_copper_pours, analyze_plane_continuity "
            "and analyze_return_path. Treat results as geometry-based heuristics, not "
            "full-wave SI. "
            "The model decides criticality and remediation. Stop if reference layers, plane net or "
            "refilled copper geometry are unknown; report skipped checks and confidence."
        )

    @mcp.prompt()
    def prepare_fabrication_export(scope: str = "whole board") -> str:
        """Review release readiness before creating a generic fabrication manifest."""
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
        """Review one assembly variant before creating generic assembly artifacts."""
        return (
            f"Required variant={variant}. Run assembly, BOM and silkscreen reviews, then call "
            "export_assembly_outputs for generic placement/BOM artifacts. Stop on DNP ambiguity, "
            "missing pattern/MPN or unknown coordinate convention. The model selects variant "
            "policy "
            "and must map the generic CSV to the assembler outside MCP."
        )

    @mcp.prompt(name="review_bom")
    def review_bom_workflow(variant: str = "all") -> str:
        """Review BOM metadata and consistency for the requested variant."""
        return (
            f"Required variant={variant}. Call get_bom, review_bom, find_missing_component_fields, "
            "validate_mpn_consistency and validate_value_pattern_consistency. The model decides "
            "substitution policy. Stop on DNP/variant ambiguity; no internet sourcing is performed."
        )

    @mcp.prompt()
    def compare_schematic_and_pcb(schematic_path: str, pcb_path: str) -> str:
        """Compare an explicit schematic and PCB without applying changes."""
        return (
            f"Required schematic={schematic_path}; PCB={pcb_path}. Read both document infos, call "
            "compare_schematic_to_pcb and inspect RefDes, value, net and endpoint deltas. The "
            "model decides whether differences are intentional. Stop before edits on ambiguous "
            "pin-to-pad "
            "mapping or source SHA changes."
        )

    @mcp.prompt()
    def synchronize_schematic_to_pcb(schematic_path: str, pcb_path: str) -> str:
        """Plan a guarded schematic-to-PCB synchronization workflow."""
        return (
            f"Synchronize schematic={schematic_path} into PCB={pcb_path}. First call "
            "compare_schematic_to_pcb and inspect component libraries. Supply explicit "
            "pattern_style and multi-part pin_map entries wherever XML evidence is missing. "
            "Call sync_schematic_to_pcb with dry_run=true, inspect the XML/SVG preview and "
            "commit with the returned source SHA only after pin-to-pad mapping is complete. "
            "Then legalize placement and rerun connectivity and DRC."
        )

    _finalize_tool_descriptions(mcp)
    service.set_workflow_prompt_names(tuple(mcp._prompt_manager._prompts))
    return mcp
async def _robust_stdio_server() -> Any:
    """Provide MCP stdio streams without anyio's stdin file wrapper.

    Some Windows/WSL combinations do not wake an ``anyio.wrap_file`` worker
    reliably for an inherited pipe. A dedicated reader thread keeps the
    protocol transport line-oriented while the MCP lifecycle remains owned by
    the pinned SDK server.
    """

    incoming: Queue[SessionMessage | Exception | None] = Queue()
    read_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_reader = anyio.create_memory_object_stream(0)

    def read_stdin() -> None:
        binary_stdin = getattr(sys.stdin, "buffer", sys.stdin)
        for raw_line in binary_stdin:
            line = (
                raw_line.decode("utf-8", errors="replace")
                if isinstance(raw_line, bytes)
                else raw_line
            )
            try:
                message = types.JSONRPCMessage.model_validate_json(line)
            except Exception as exc:  # protocol error is returned through MCP handling
                incoming.put(exc)
            else:
                incoming.put(SessionMessage(message))
        incoming.put(None)

    async def forward_input() -> None:
        try:
            while True:
                try:
                    message = incoming.get_nowait()
                except Empty:
                    await anyio.sleep(0.01)
                    continue
                if message is None:
                    return
                await read_writer.send(message)
        finally:
            await read_writer.aclose()

    async def forward_output() -> None:
        async with write_reader:
            async for message in write_reader:
                payload = message.message.model_dump_json(by_alias=True, exclude_none=True)
                sys.stdout.write(payload + "\n")
                sys.stdout.flush()

    threading.Thread(target=read_stdin, name="diptrace-mcp-stdin", daemon=True).start()
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(forward_input)
        task_group.start_soon(forward_output)
        yield read_stream, write_stream
async def _run_stdio(server: FastMCP) -> None:
    async with _robust_stdio_server() as (read_stream, write_stream):
        await server._mcp_server.run(
            read_stream,
            write_stream,
            server._mcp_server.create_initialization_options(),
        )
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP server for DipTrace XML and live projects")
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )
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
    server = create_server(host=args.host, port=args.port)
    use_frozen_stdio = bool(getattr(sys, "frozen", False)) or os.environ.get(
        "DIPTRACE_MCP_FROZEN_STDIO", ""
    ).strip().casefold() in {"1", "true", "yes"}
    if args.transport == "stdio" and use_frozen_stdio:
        anyio.run(_run_stdio, server)
    else:
        server.run(transport=args.transport)
if __name__ == "__main__":
    main()
