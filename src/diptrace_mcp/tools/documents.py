"""Status, document identity, normalized models, queries, raw XML and live sessions."""
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError

from ..domain import BoardModelSection
from ..errors import EditError, Sha256MismatchError
from ..scaffolding import (
    DEFAULT_FORMAT_VERSION,
)
from ..server_inputs import (
    AbandonLiveSessionResult,
    DipTraceFastMCP,
    ExpectedLiveWorkingSha256Input,
    ExpectedTargetSha256Input,
    FinishLiveSessionResult,
    FormatVersionInput,
    PcbScaffoldInput,
    RoundtripEvidenceInput,
    SelectorInput,
    XmlEditInput,
)
from ..service import DipTraceService
from ..services.xml_writes import MAX_RAW_XML_EDITS, _finalize_raw_edit_response
from ..xml_document import XmlEdit, sha256_bytes

MAX_XML_EDITS_FILE_BYTES = 128 * 1024

def register(mcp: DipTraceFastMCP, service: DipTraceService) -> None:
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
    def apply_xml_edits_from_file(
        edits_path: str,
        expected_edits_sha256: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Load 1–50 hash-bound XML edits from an allowed UTF-8 JSON file."""
        if not dry_run and (not expected_edits_sha256 or not expected_sha256):
            raise EditError(
                "expected_edits_sha256 and expected_sha256 are required when dry_run=false"
            )
        edit_file = service.settings.resolve_allowed_path(edits_path)
        if not edit_file.is_file():
            raise EditError("edits_path must identify a regular JSON file")
        with edit_file.open("rb") as handle:
            raw_edits = handle.read(MAX_XML_EDITS_FILE_BYTES + 1)
        if len(raw_edits) > MAX_XML_EDITS_FILE_BYTES:
            raise EditError("Edit file exceeds the 128 KiB limit")
        actual_edits_sha256 = sha256_bytes(raw_edits)
        if expected_edits_sha256 and actual_edits_sha256 != expected_edits_sha256:
            raise Sha256MismatchError(
                "Edit file changed since its SHA-256 was recorded",
                details={
                    "expected_edits_sha256": expected_edits_sha256,
                    "current_edits_sha256": actual_edits_sha256,
                },
            )
        try:
            payload = json.loads(raw_edits.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EditError("Edit file must contain valid UTF-8 JSON") from exc
        if not isinstance(payload, list):
            raise EditError("Edit file must contain a flat JSON array of edits")
        if not 1 <= len(payload) <= MAX_RAW_XML_EDITS:
            raise EditError(
                f"Edit file must contain between 1 and {MAX_RAW_XML_EDITS} edits"
            )
        try:
            operations = [
                XmlEdit(**XmlEditInput.model_validate(edit, extra="forbid").model_dump())
                for edit in payload
            ]
        except ValidationError as exc:
            raise EditError("Edit file contains invalid edit operations") from exc
        result = service.apply_edits(operations, path, dry_run, expected_sha256)
        result["edits_file_sha256"] = actual_edits_sha256
        return _finalize_raw_edit_response(result)

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
