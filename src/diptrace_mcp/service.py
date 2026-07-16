from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from . import __version__, inspector
from .adapters import (
    DocumentSnapshot,
    build_snapshot,
    document_id_for,
    get_board_model,
    get_schematic_model,
)
from .bom import compare_bom_records, extract_bom, group_bom, review_bom
from .capabilities import get_capabilities as build_capabilities
from .config import Settings
from .connectivity import build_connectivity_graph
from .design_compare import compare_schematic_to_pcb as compare_design_snapshots
from .domain import (
    DocumentInfo,
    ImpedanceInput,
    JobStatus,
    LibraryComponent,
    LibraryPattern,
    ObjectRecord,
    PlanStatus,
    QueryRequest,
    QuerySelector,
    TransactionRecord,
)
from .errors import (
    CapabilityUnavailableError,
    ConfirmationRequiredError,
    ConnectivityRegressionError,
    DocumentError,
    DrcRegressionError,
    EditError,
    PathAccessError,
    RoundtripValidationError,
    SessionError,
    Sha256MismatchError,
    TransactionConflictError,
)
from .exports import (
    ExportStore,
    create_bom_export,
    create_release_manifest,
    export_resources,
)
from .external_adapters import ExternalJobManager
from .findings import FindingStore
from .geometry import BBox, Point, distance, point_in_polygon
from .impedance import (
    analyze_stackup,
    synthesize_microstrip_width,
)
from .impedance import calculate_impedance as calculate_impedance_estimate
from .jobs import JobStore, job_resources
from .lengths import analyze_differential_pair as analyze_pair_geometry
from .lengths import (
    measure_net_length,
    resolve_differential_pair,
    resolve_net,
)
from .library_adapters import (
    get_library_item,
    get_library_model,
    query_library_items,
    validate_library,
)
from .model_cache import ModelCache
from .operations import (
    AddTestpointOperation,
    AddTraceOperation,
    AddViaOperation,
    AssignNetsToClassOperation,
    DeleteTraceOperation,
    DeleteViaOperation,
    GroupComponentsOperation,
    MoveBoardTextsOperation,
    MoveComponentsOperation,
    MoveTestpointsOperation,
    MoveViaOperation,
    RemoveTestpointsOperation,
    RenameNetOperation,
    ReplaceTraceOperation,
    RotateBoardTextsOperation,
    RotateComponentsOperation,
    SemanticOperation,
    SetComponentLockOperation,
    SetComponentPatternOperation,
    SetComponentPropertiesOperation,
    SetComponentSideOperation,
    SetComponentValueOperation,
    SetPinNoConnectOperation,
    SetTextStyleOperation,
    SetTextVisibilityOperation,
    SetTraceWidthOperation,
    SetViaStyleOperation,
    UngroupComponentsOperation,
    UpdateNetClassRulesOperation,
    parse_semantic_operations,
)
from .placement import (
    PlacementConfig,
    PlacementProposal,
    PlacementWeights,
    analyze_placement,
    generate_placement_candidates,
    plan_component_placement,
    score_placement_proposal,
)
from .plans import PlanStore
from .policy import Policy
from .preview import render_preview_json, render_preview_svg
from .return_path import analyze_plane_continuity as analyze_plane_geometry
from .return_path import analyze_return_path as analyze_return_geometry
from .review import run_checks
from .routing import (
    DifferentialPairRouteConfig,
    RouteConnectionConfig,
    synthesize_differential_pair_route,
    synthesize_route,
)
from .semantic_compiler import SemanticApplyResult, apply_semantic_operations
from .sessions import SessionAction, SessionStore
from .silkscreen import SilkscreenPlanConfig, plan_silkscreen
from .specctra import (
    dsn_export_limitations,
    export_dsn,
    parse_ses,
    session_to_operations,
)
from .transactions import TransactionStore, default_risk, tx_preview_resources
from .xml_document import (
    DipTraceDocument,
    XmlEdit,
    atomic_write_bytes,
    sha256_bytes,
    unified_xml_diff,
    utc_now,
    write_with_backup,
)

_CANDIDATE_SUFFIXES = {".xml", ".dip", ".dch", ".eli", ".lib"}
_SOURCE_TAG = re.compile(br"<(?:Source|Library)\b([^>]*)>", re.IGNORECASE)
_SOURCE_ATTRIBUTE = re.compile(br"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*['\"]([^'\"]*)['\"]")


@dataclass(frozen=True)
class DocumentTarget:
    path: Path
    live_session_id: str | None = None

    @property
    def is_live(self) -> bool:
        return self.live_session_id is not None


class DipTraceService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.policy = Policy(settings.active_policy)
        self.sessions = SessionStore(settings.state_dir, settings.max_document_bytes)
        self.transactions = TransactionStore(settings.state_dir)
        self.plans = PlanStore(settings.state_dir)
        self.findings = FindingStore(settings.state_dir)
        self.jobs = JobStore(settings.state_dir)
        self.exports = ExportStore(settings.state_dir, settings.max_document_bytes)
        self.external_jobs = ExternalJobManager(settings, self.jobs)
        self.models = ModelCache()
        self._document_targets: dict[str, DocumentTarget] = {}

    def resolve_target(self, path: str | None) -> DocumentTarget:
        if path:
            return DocumentTarget(self.settings.resolve_allowed_path(path))
        active = self.sessions.active_metadata()
        if active is None:
            raise SessionError(
                "No active DipTrace session. Pass an XML path or launch Tools > Plugins > "
                "DipTrace MCP Bridge in DipTrace."
            )
        session_id = str(active["session_id"])
        return DocumentTarget(self.sessions.working_path(session_id), session_id)

    def load(self, path: str | None) -> tuple[DipTraceDocument, DocumentTarget]:
        target = self.resolve_target(path)
        document = DipTraceDocument.load(target.path, self.settings.max_document_bytes)
        self._document_targets[document_id_for(document)] = target
        return document, target

    def load_document_id(self, document_id: str) -> tuple[DipTraceDocument, DocumentTarget]:
        try:
            target = self._document_targets[document_id]
        except KeyError as exc:
            raise DocumentError(
                f"Document id is not registered in this server process: {document_id}",
                code="document_not_found",
                details={"document_id": document_id},
            ) from exc
        document = DipTraceDocument.load(target.path, self.settings.max_document_bytes)
        if document_id_for(document) != document_id:
            raise DocumentError(
                f"Document identity changed for registered path: {target.path}",
                code="document_not_found",
                details={"document_id": document_id},
            )
        return document, target

    def _snapshot(self, path: str | None) -> tuple[Any, DocumentTarget]:
        document, target = self.load(path)
        return self.models.get(document, live_session=target.is_live), target

    def status(self) -> dict[str, Any]:
        active = self.sessions.active_metadata()
        if active is not None:
            session_id = str(active["session_id"])
            working = self.sessions.working_path(session_id)
            active = {
                **active,
                "working_path": str(working),
                "working_sha256": sha256_bytes(working.read_bytes()),
            }
        return {
            "server": "diptrace-mcp",
            "version": __version__,
            "configuration": self.settings.as_dict(),
            "active_session": active,
            "capabilities": self.get_capabilities(),
        }

    def get_capabilities(self, path: str | None = None) -> dict[str, Any]:
        if path is None:
            active = self.sessions.active_metadata()
            if active is None:
                report = build_capabilities(None).model_dump()
                probe = self.external_jobs.freerouting.probe()
                report["external_adapters"]["freerouting"] = probe.as_dict()
                report["limits"]["max_document_bytes"] = self.settings.max_document_bytes
                report["limits"]["max_external_log_bytes"] = (
                    self.settings.max_external_log_bytes
                )
                report["policy"].update(self.policy.capability_payload())
                if probe.available:
                    report["reasons_unavailable"] = [
                        item
                        for item in report["reasons_unavailable"]
                        if item.get("feature") != "external_autorouting"
                    ]
                return report
        document, target = self.load(path)
        report = build_capabilities(document, live_session=target.is_live).model_dump()
        probe = self.external_jobs.freerouting.probe()
        report["external_adapters"]["freerouting"] = probe.as_dict()
        report["limits"]["max_document_bytes"] = self.settings.max_document_bytes
        report["limits"]["max_external_log_bytes"] = self.settings.max_external_log_bytes
        report["policy"].update(self.policy.capability_payload())
        if probe.available:
            report["reasons_unavailable"] = [
                item
                for item in report["reasons_unavailable"]
                if item.get("feature") != "external_autorouting"
            ]
        snapshot = self.models.get(document, live_session=target.is_live)
        dsn_reasons = dsn_export_limitations(snapshot)
        report["write_capabilities"]["autorouter_dsn_export"] = not dsn_reasons
        report["read_capabilities"]["autorouter_ses_inspection"] = document.kind == "pcb"
        report["write_capabilities"]["autorouter_ses_import"] = document.kind == "pcb"
        if dsn_reasons:
            report["reasons_unavailable"].append(
                {
                    "feature": "autorouter_dsn_export",
                    "code": "capability_unavailable",
                    "message": (
                        "Current document lacks geometry required by the bounded DSN serializer."
                    ),
                    "details": {"reasons": dsn_reasons},
                }
            )
        return report

    def document_info(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        info = self.models.get(document, live_session=target.is_live).info
        return self._read_success(info, info.model_dump())

    def board_model(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        info = snapshot.info
        model = snapshot.board
        if model is None:
            raise DocumentError("PCB model is only available for PCB documents")
        return self._read_success(
            info,
            model.model_dump(),
            resources=[f"diptrace://document/{info.document_id}/board-model"],
            warnings=model.warnings,
        )

    def schematic_model(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        info = snapshot.info
        model = snapshot.schematic
        if model is None:
            raise DocumentError("Schematic model is only available for schematic documents")
        return self._read_success(
            info,
            model.model_dump(),
            resources=[f"diptrace://document/{info.document_id}/schematic-model"],
            warnings=model.warnings,
        )

    def library_model(self, path: str) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        model = get_library_model(document)
        return self._read_success(
            snapshot.info,
            model.model_dump(),
            warnings=model.warnings,
        )

    def scan_component_libraries(
        self, root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        return self._scan_libraries("DipTrace-ComponentLibrary", root, recursive)

    def scan_pattern_libraries(
        self, root: str | None = None, recursive: bool = True
    ) -> dict[str, Any]:
        return self._scan_libraries("DipTrace-PatternLibrary", root, recursive)

    def query_library_items(
        self,
        path: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        model = get_library_model(document)
        items = query_library_items(model, query)
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(items),
                "offset": offset,
                "limit": limit,
                "items": items[offset : offset + limit],
            },
            warnings=model.warnings,
        )

    def get_library_component(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._get_library_item(path, "component", stable_id_value, name)

    def get_library_pattern(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._get_library_item(path, "pattern", stable_id_value, name)

    def validate_library_component(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._validate_library_item(path, "component", stable_id_value, name)

    def validate_library_pattern(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        return self._validate_library_item(path, "pattern", stable_id_value, name)

    def validate_pin_pad_mapping(
        self,
        path: str,
        stable_id_value: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        result = self._validate_library_item(path, "component", stable_id_value, name)
        mapping_codes = {
            "attached_pattern_not_found",
            "duplicate_pin_number",
            "missing_pin_number",
            "pin_pad_mapping_missing",
        }
        findings = [
            item for item in result["result"]["findings"] if item["code"] in mapping_codes
        ]
        result["result"]["findings"] = findings
        result["result"]["finding_count"] = len(findings)
        result["result"]["valid"] = not any(
            item["severity"] == "error" for item in findings
        )
        return result

    def get_bom(
        self,
        path: str | None = None,
        *,
        grouped: bool = False,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        records = extract_bom(snapshot)
        if grouped:
            records = group_bom(records, include_dnp=include_dnp)
        elif not include_dnp:
            records = [record for record in records if not record.dnp]
        return self._read_success(
            snapshot.info,
            {
                "record_count": len(records),
                "grouped": grouped,
                "include_dnp": include_dnp,
                "items": [record.model_dump(mode="json") for record in records],
            },
        )

    def export_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        record = create_bom_export(self.exports, snapshot, include_dnp=include_dnp)
        return self._read_success(
            snapshot.info,
            {"export": record.model_dump(mode="json")},
            resources=export_resources(record),
            limitations=record.limitations,
        )

    def export_fabrication_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        if request_native_outputs:
            raise CapabilityUnavailableError(
                "Authoritative Gerber/NC drill export is unavailable from confirmed XML semantics. "
                "Call with request_native_outputs=false to create a review manifest bundle.",
                details={"not_generated": ["gerber", "nc_drill", "odb++", "ipc-2581"]},
            )
        return self._export_release_manifest(
            path,
            export_type="fabrication_manifest",
            include_dnp=include_dnp,
        )

    def export_assembly_outputs(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = False,
        request_native_outputs: bool = False,
    ) -> dict[str, Any]:
        if request_native_outputs:
            raise CapabilityUnavailableError(
                "Authoritative vendor-specific assembly output is unavailable. "
                "Call with request_native_outputs=false for generic placement and BOM artifacts.",
                details={"not_generated": ["vendor_cpl", "assembly_drawing"]},
            )
        return self._export_release_manifest(
            path,
            export_type="assembly_manifest",
            include_dnp=include_dnp,
        )

    def _export_release_manifest(
        self,
        path: str | None,
        *,
        export_type: Literal["fabrication_manifest", "assembly_manifest"],
        include_dnp: bool,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        record = create_release_manifest(
            self.exports,
            snapshot,
            export_type=export_type,
            include_dnp=include_dnp,
        )
        return self._read_success(
            snapshot.info,
            {"export": record.model_dump(mode="json")},
            resources=export_resources(record),
            limitations=record.limitations,
        )

    def review_bom(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        records = extract_bom(snapshot)
        result = review_bom(records)
        result["items"] = [record.model_dump(mode="json") for record in records]
        return self._read_success(snapshot.info, result)

    def compare_bom_to_design(
        self,
        external_records: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        if len(external_records) > 100_000:
            raise DocumentError("At most 100000 external BOM rows are accepted")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = compare_bom_records(extract_bom(snapshot), external_records)
        return self._read_success(snapshot.info, result)

    def find_missing_component_fields(
        self,
        required_fields: list[str],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        if not required_fields or len(required_fields) > 100:
            raise DocumentError("required_fields must contain between 1 and 100 names")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        records = extract_bom(snapshot)
        missing: list[dict[str, Any]] = []
        for record in records:
            standard = {
                "value": record.value,
                "pattern": record.pattern,
                "manufacturer": record.manufacturer,
                "mpn": record.mpn,
                "variant": record.variant,
            }
            available = {
                **{key.casefold(): value for key, value in record.fields.items()},
                **standard,
            }
            absent = [field for field in required_fields if not available.get(field.casefold())]
            if absent:
                missing.append({"refdes": record.refdes, "missing_fields": absent})
        return self._read_success(
            snapshot.info,
            {"record_count": len(records), "missing_count": len(missing), "items": missing},
        )

    def group_bom(
        self,
        path: str | None = None,
        *,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        return self.get_bom(path, grouped=True, include_dnp=include_dnp)

    def detect_duplicate_bom_items(self, path: str | None = None) -> dict[str, Any]:
        response = self.get_bom(path, grouped=True, include_dnp=True)
        duplicates = [
            item for item in response["result"]["items"] if int(item["quantity"]) > 1
        ]
        response["result"] = {
            "duplicate_group_count": len(duplicates),
            "items": duplicates,
            "definition": "Same MPN/manufacturer/value/pattern/DNP/variant identity.",
        }
        return response

    def validate_mpn_consistency(self, path: str | None = None) -> dict[str, Any]:
        response = self.review_bom(path)
        response["result"]["findings"] = [
            item
            for item in response["result"]["findings"]
            if item["code"] == "bom.mpn_inconsistent"
        ]
        response["result"]["valid"] = not response["result"]["findings"]
        return response

    def validate_value_pattern_consistency(
        self, path: str | None = None
    ) -> dict[str, Any]:
        response = self.review_bom(path)
        response["result"]["findings"] = [
            item
            for item in response["result"]["findings"]
            if item["code"] in {"bom.mpn_inconsistent", "bom.multipart_inconsistent"}
        ]
        response["result"]["valid"] = not response["result"]["findings"]
        return response

    def compare_schematic_to_pcb(
        self, schematic_path: str, pcb_path: str
    ) -> dict[str, Any]:
        schematic_document, schematic_target = self.load(schematic_path)
        pcb_document, pcb_target = self.load(pcb_path)
        schematic = self.models.get(
            schematic_document, live_session=schematic_target.is_live
        )
        pcb = self.models.get(pcb_document, live_session=pcb_target.is_live)
        result = compare_design_snapshots(schematic, pcb)
        return self._read_success(
            schematic.info,
            {
                **result,
                "pcb_document": pcb.info.model_dump(mode="json"),
            },
            limitations=result["limitations"],
        )

    def query_objects(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "stable_id",
    ) -> dict[str, Any]:
        document, target = self.load(path)
        request = QueryRequest.model_validate(
            {
                "selector": selector or {},
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
            }
        )
        snapshot = self.models.get(document, live_session=target.is_live)
        info = snapshot.info
        result = snapshot.query(request)
        return self._read_success(info, result.model_dump())

    def get_object(self, stable_id_value: str, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        info = snapshot.info
        record = snapshot.get_object(stable_id_value)
        result = record.model_dump()
        element = snapshot.elements.get(stable_id_value)
        result["source_xml"] = (
            ET.tostring(element, encoding="unicode") if element is not None else None
        )
        return self._read_success(info, result)

    def get_connectivity_graph(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        graph = build_connectivity_graph(snapshot)
        return self._read_success(
            snapshot.info,
            graph.model_dump(mode="json"),
            warnings=graph.warnings,
            resources=[f"diptrace://document/{snapshot.info.document_id}/connectivity"],
        )

    def document_resource(self, document_id: str, resource: str) -> str:
        document, target = self.load_document_id(document_id)
        if resource == "summary":
            payload = inspector.summarize(document, live_session=target.is_live)
        elif resource == "board-model":
            payload = get_board_model(document, live_session=target.is_live).model_dump()
        elif resource == "schematic-model":
            payload = get_schematic_model(document, live_session=target.is_live).model_dump()
        elif resource == "stackup":
            model = get_board_model(document, live_session=target.is_live)
            payload = model.stackup.model_dump(mode="json")
        elif resource == "connectivity":
            snapshot = self.models.get(document, live_session=target.is_live)
            payload = build_connectivity_graph(snapshot).model_dump(mode="json")
        elif resource == "library-model":
            payload = get_library_model(document).model_dump()
        else:
            raise DocumentError(
                f"Unknown document resource: {resource}",
                code="object_not_found",
            )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def summarize(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        return inspector.summarize(document, live_session=target.is_live)

    def components(
        self,
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        return {
            **inspector.components(document, query, offset, limit, live_session=target.is_live),
            "live_session": target.is_live,
        }

    def component(self, refdes: str, path: str | None = None) -> dict[str, Any]:
        if not refdes.strip():
            raise DocumentError("refdes cannot be empty")
        document, target = self.load(path)
        return {
            **inspector.component(document, refdes, live_session=target.is_live),
            "live_session": target.is_live,
        }

    def nets(
        self,
        path: str | None = None,
        query: str | None = None,
        include_endpoints: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        return {
            **inspector.nets(
                document,
                query,
                include_endpoints,
                offset,
                limit,
                live_session=target.is_live,
            ),
            "live_session": target.is_live,
        }

    def rules(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        return {
            **inspector.design_rules(document, live_session=target.is_live),
            "live_session": target.is_live,
        }

    def read_xml(
        self,
        path: str | None = None,
        xpath: str = ".",
        max_matches: int = 25,
        max_characters: int = 20_000,
    ) -> dict[str, Any]:
        if not 1 <= max_matches <= 100:
            raise DocumentError("max_matches must be between 1 and 100")
        if not 1 <= max_characters <= 100_000:
            raise DocumentError("max_characters must be between 1 and 100000")
        document, target = self.load(path)
        fragments = document.xml_fragments(xpath, max_matches)
        rendered = "\n\n".join(fragments)
        truncated = len(rendered) > max_characters
        if truncated:
            rendered = rendered[:max_characters] + "\n... XML output truncated ..."
        return {
            "path": str(document.path),
            "live_session": target.is_live,
            "xpath": xpath,
            "match_count": len(fragments),
            "truncated": truncated,
            "xml": rendered,
        }

    def apply_edits(
        self,
        edits: list[XmlEdit],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=dry_run, operation="apply_xml_edits")
        if len(edits) > 50:
            raise EditError("A single call can contain at most 50 edits")
        if not dry_run and not expected_sha256:
            raise EditError("expected_sha256 from a dry-run is required when dry_run=false")
        document, target = self.load(path)
        before = document.raw_bytes
        before_sha256 = sha256_bytes(before)
        if expected_sha256 and before_sha256 != expected_sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {before_sha256}",
                details={"expected_sha256": expected_sha256, "current_sha256": before_sha256},
            )
        after, previews = document.apply_edits(edits)
        after_sha256 = sha256_bytes(after)
        changed = before != after
        result: dict[str, Any] = {
            "path": str(target.path),
            "live_session": target.is_live,
            "session_id": target.live_session_id,
            "dry_run": dry_run,
            "changed": changed,
            "before_sha256": before_sha256,
            "after_sha256": after_sha256,
            "operations": previews,
            "diff": unified_xml_diff(before, after),
        }
        if dry_run or not changed:
            result["written"] = False
            return result

        if target.live_session_id:
            backup_dir = self.sessions.backups_dir(target.live_session_id)
        else:
            backup_dir = target.path.parent / ".diptrace-mcp-backups"
        backup = write_with_backup(target.path, after, backup_dir)
        DipTraceDocument.load(target.path, self.settings.max_document_bytes)
        if target.live_session_id:
            self.sessions.record_edit(target.live_session_id, after_sha256, backup)
        result.update(
            {
                "written": True,
                "backup": str(backup),
                "written_at": utc_now(),
            }
        )
        return result

    def begin_transaction(
        self,
        path: str | None = None,
        expected_sha256: str | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=True, operation="begin_transaction")
        document, target = self.load(path)
        snapshot = build_snapshot(document, live_session=target.is_live)
        if expected_sha256 is not None and expected_sha256 != snapshot.info.sha256:
            raise Sha256MismatchError(
                f"Document changed: expected {expected_sha256}, current {snapshot.info.sha256}",
                details={
                    "expected_sha256": expected_sha256,
                    "current_sha256": snapshot.info.sha256,
                },
            )
        record = self.transactions.create(
            snapshot.info,
            target.path,
            source_sha256=snapshot.info.sha256,
            expected_sha256=expected_sha256 or snapshot.info.sha256,
            notes=notes,
        )
        self.transactions.store_snapshot(record.txid, document.raw_bytes)
        updated = self.transactions.update(
            record.txid,
            status="staged",
            snapshot_path=str(self.transactions.snapshot_path(record.txid)),
        )
        return {
            "ok": True,
            "document": snapshot.info.model_dump(),
            "transaction": updated.model_dump(),
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def stage_operations(self, txid: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        self.policy.require_write(dry_run=True, operation="stage_operations")
        record = self.transactions.read(txid)
        if record.status not in {"staged", "validated"}:
            raise TransactionConflictError(
                f"Transaction cannot accept operations in state {record.status}: {txid}",
                txid=txid,
            )
        parsed = parse_semantic_operations(operations)
        if not parsed:
            raise EditError("At least one semantic operation is required")
        staged = [*record.operations, *(operation.model_dump() for operation in parsed)]
        updated = self.transactions.update(
            txid,
            status="staged",
            operations=staged,
            compiled_patch_count=len(staged),
            changed_ids=[],
            validation_after_preview={},
            preview_resources=[],
        )
        return {
            "ok": True,
            "transaction": updated.model_dump(),
            "result": {"staged_count": len(staged)},
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def preview_transaction(self, txid: str) -> dict[str, Any]:
        self.policy.require_write(dry_run=True, operation="preview_transaction")
        record = self.transactions.read(txid)
        if record.status not in {"staged", "validated"}:
            raise TransactionConflictError(
                f"Transaction cannot be previewed in state {record.status}: {txid}",
                txid=txid,
            )
        if not record.operations:
            raise TransactionConflictError("Transaction contains no operations", txid=txid)
        source = self._load_snapshot_record(record)
        operations = parse_semantic_operations(record.operations)
        preview = self._preview_semantic_operations(source, operations)
        resources = tx_preview_resources(txid)
        self.transactions.store_preview(
            txid,
            preview["svg"],
            preview["json"],
            preview["diff"],
        )
        updated = self.transactions.update(
            txid,
            status="validated",
            changed_ids=preview["changed_ids"],
            validation_before=preview["validation_before"],
            validation_after_preview=preview["validation_after_preview"],
            preview_resources=resources,
            risk=default_risk("limited_write", "semantic operation preview generated"),
            compiled_patch_count=preview["patch_count"],
        )
        return {
            "ok": True,
            "transaction": updated.model_dump(),
            "result": {
                "changed_ids": preview["changed_ids"],
                "validation_before": preview["validation_before"],
                "validation_after_preview": preview["validation_after_preview"],
            },
            "warnings": preview["warnings"],
            "limitations": preview["limitations"],
            "resources": resources,
            "preview": {
                "svg": preview["svg"],
                "json": preview["json"],
                "diff": preview["diff"],
            },
        }

    def validate_transaction(self, txid: str) -> dict[str, Any]:
        return self.preview_transaction(txid)

    def commit_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        self.policy.require_write(dry_run=False, operation="commit_transaction")
        record = self.transactions.read(txid)
        if record.status != "validated":
            raise TransactionConflictError(
                f"Transaction must be validated before commit: {txid}",
                details={"current_status": record.status},
                txid=txid,
            )
        if not record.operations:
            raise TransactionConflictError("Transaction contains no operations", txid=txid)
        if expected_sha256 is None:
            raise ConfirmationRequiredError(
                "expected_sha256 is required when committing a transaction",
                txid=txid,
            )
        source = self._load_snapshot_record(record)
        operations = parse_semantic_operations(record.operations)
        preview = self._preview_semantic_operations(source, operations)
        target_path = self.settings.resolve_allowed_path(record.target_path)
        current = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
        current_sha256 = current.sha256
        expected = record.expected_sha256 or record.source_sha256
        if expected_sha256 != expected or current_sha256 != expected:
            raise Sha256MismatchError(
                f"Document changed: expected {expected}, current {current_sha256}",
                details={
                    "transaction_expected_sha256": expected,
                    "provided_sha256": expected_sha256,
                    "current_sha256": current_sha256,
                },
                txid=txid,
            )
        is_live = self._session_id_from_working(target_path) is not None
        applied = apply_semantic_operations(current, operations, live_session=is_live)
        backup = self.transactions.store_backup(txid, current.raw_bytes)
        try:
            atomic_write_bytes(target_path, applied.raw_bytes)
            reparsed = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
            committed_sha256 = reparsed.sha256
            if committed_sha256 != sha256_bytes(applied.raw_bytes):
                raise RoundtripValidationError(
                    "Committed XML SHA does not match compiled transaction output",
                    txid=txid,
                )
        except Exception as exc:
            atomic_write_bytes(target_path, backup.read_bytes())
            self.transactions.mark_failed(
                txid,
                {
                    "code": getattr(exc, "code", "schema_write_error"),
                    "message": str(exc),
                },
            )
            raise
        session_id = self._session_id_from_working(target_path)
        if session_id is not None:
            self.sessions.record_edit(session_id, committed_sha256, backup)
        updated = self.transactions.mark_committed(
            txid,
            committed_sha256=committed_sha256,
            changed_ids=applied.changed_ids,
            compiled_patch_count=applied.patch_count,
            preview_resources=tx_preview_resources(txid),
            backup_path=backup,
        )
        return {
            "ok": True,
            "transaction": updated.model_dump(),
            "result": {
                "changed_ids": applied.changed_ids,
                "compiled_patch_count": applied.patch_count,
            },
            "warnings": applied.warnings,
            "limitations": preview["limitations"],
            "resources": tx_preview_resources(txid),
        }

    def rollback_transaction(
        self,
        txid: str,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        record = self.transactions.read(txid)
        if record.status == "rolled_back":
            raise TransactionConflictError("Transaction is already rolled back", txid=txid)
        restored_sha256: str | None = None
        if record.status == "committed":
            if expected_sha256 is None:
                raise ConfirmationRequiredError(
                    "expected_sha256 is required to roll back a committed transaction",
                    txid=txid,
                )
            target_path = self.settings.resolve_allowed_path(record.target_path)
            current = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
            if expected_sha256 != record.committed_sha256 or current.sha256 != expected_sha256:
                raise Sha256MismatchError(
                    "The committed document changed after this transaction",
                    details={
                        "transaction_commit_sha256": record.committed_sha256,
                        "provided_sha256": expected_sha256,
                        "current_sha256": current.sha256,
                    },
                    txid=txid,
                )
            if not record.backup_path:
                raise TransactionConflictError("Transaction backup is missing", txid=txid)
            backup_path = Path(record.backup_path)
            if not backup_path.is_file():
                raise TransactionConflictError(
                    f"Transaction backup is missing: {backup_path}",
                    txid=txid,
                )
            backup_bytes = backup_path.read_bytes()
            DipTraceDocument.from_bytes(target_path, backup_bytes)
            atomic_write_bytes(target_path, backup_bytes)
            restored_sha256 = sha256_bytes(backup_bytes)
        updated = self.transactions.mark_rolled_back(
            txid,
            rolled_back_sha256=restored_sha256,
            reason="explicit rollback",
        )
        return {
            "ok": True,
            "transaction": updated.model_dump(),
            "result": {
                "rolled_back": True,
                "document_restored": restored_sha256 is not None,
                "restored_sha256": restored_sha256,
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
        }

    def list_transactions(self) -> dict[str, Any]:
        return {
            "ok": True,
            "transactions": [item.model_dump() for item in self.transactions.list()],
        }

    def move_components(
        self,
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
        op = MoveComponentsOperation.model_validate(
            {
                "selector": selector or {},
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "grid_snap": grid_snap,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(op, path, dry_run, expected_sha256, txid)

    def set_component_value(
        self,
        selector: dict[str, Any] | None,
        value: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        op = SetComponentValueOperation.model_validate(
            {"selector": selector or {}, "value": value}
        )
        return self._run_semantic_write(op, path, dry_run, expected_sha256, txid)

    def rotate_components(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allowed_angles: list[float] | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = RotateComponentsOperation.model_validate(
            {
                "selector": selector or {},
                "angle_deg": angle_deg,
                "mode": mode,
                "allowed_angles": allowed_angles or [],
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_side(
        self,
        selector: dict[str, Any] | None,
        side: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetComponentSideOperation.model_validate(
            {"selector": selector or {}, "side": side, "allow_locked": allow_locked}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_lock(
        self,
        selector: dict[str, Any] | None,
        locked: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetComponentLockOperation.model_validate(
            {"selector": selector or {}, "locked": locked}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_properties(
        self,
        selector: dict[str, Any] | None,
        *,
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
        operation = SetComponentPropertiesOperation.model_validate(
            {
                "selector": selector or {},
                "name": name,
                "value": value,
                "refdes": refdes,
                "fields": fields or {},
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_component_pattern(
        self,
        selector: dict[str, Any],
        pattern_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetComponentPatternOperation.model_validate(
            {
                "selector": selector,
                "pattern_style": pattern_style,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def align_components(
        self,
        selector: dict[str, Any],
        alignment: str,
        *,
        target_value: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        valid = {"left", "center_x", "right", "top", "center_y", "bottom"}
        if alignment not in valid:
            raise DocumentError(
                f"alignment must be one of {sorted(valid)}", code="geometry_invalid"
            )
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Component alignment requires a PCB document")
        query = QuerySelector.model_validate(selector)
        records = snapshot.select(query, kinds={"component"})
        if len(records) < 2:
            raise DocumentError(
                "Component alignment requires at least two matched components",
                code="scope_required",
            )
        if any(record.position is None or record.bbox is None for record in records):
            raise DocumentError(
                "All aligned components require position and bbox geometry",
                code="geometry_invalid",
            )
        records.sort(key=lambda item: item.stable_id)

        def coordinate(record: ObjectRecord) -> float:
            box = record.bbox
            assert box is not None
            return {
                "left": box["min_x"],
                "center_x": (box["min_x"] + box["max_x"]) / 2.0,
                "right": box["max_x"],
                "top": box["min_y"],
                "center_y": (box["min_y"] + box["max_y"]) / 2.0,
                "bottom": box["max_y"],
            }[alignment]

        aligned_value = target_value if target_value is not None else coordinate(records[0])
        x_axis = alignment in {"left", "center_x", "right"}
        operations: list[SemanticOperation] = []
        for record in records:
            assert record.position is not None
            delta = aligned_value - coordinate(record)
            operations.append(
                MoveComponentsOperation(
                    selector=QuerySelector(ids=[record.stable_id]),
                    absolute_x=record.position["x"] + delta if x_axis else None,
                    absolute_y=record.position["y"] + delta if not x_axis else None,
                    allow_locked=allow_locked,
                )
            )
        return self._run_semantic_operations(
            operations,
            path,
            dry_run,
            expected_sha256 or snapshot.info.sha256,
            txid,
        )

    def distribute_components(
        self,
        selector: dict[str, Any],
        axis: str,
        *,
        mode: str = "centers",
        spacing: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        if axis not in {"x", "y"} or mode not in {"centers", "gaps"}:
            raise DocumentError(
                "axis must be x/y and mode must be centers/gaps", code="geometry_invalid"
            )
        if spacing is not None and spacing < 0:
            raise DocumentError("spacing cannot be negative", code="geometry_invalid")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Component distribution requires a PCB document")
        records = snapshot.select(QuerySelector.model_validate(selector), kinds={"component"})
        if len(records) < 3:
            raise DocumentError(
                "Component distribution requires at least three matched components",
                code="scope_required",
            )
        if any(record.position is None or record.bbox is None for record in records):
            raise DocumentError(
                "All distributed components require position and bbox geometry",
                code="geometry_invalid",
            )
        center_key = "x" if axis == "x" else "y"
        minimum_key = "min_x" if axis == "x" else "min_y"
        maximum_key = "max_x" if axis == "x" else "max_y"
        records.sort(
            key=lambda record: (
                record.position[center_key] if record.position is not None else 0.0,
                record.stable_id,
            )
        )

        def position(record: ObjectRecord) -> dict[str, float]:
            assert record.position is not None
            return record.position

        def box(record: ObjectRecord) -> dict[str, float]:
            assert record.bbox is not None
            return record.bbox

        targets: list[float] = []
        if mode == "centers":
            first = position(records[0])[center_key]
            step = (
                spacing
                if spacing is not None
                else (position(records[-1])[center_key] - first) / (len(records) - 1)
            )
            targets = [first + index * step for index in range(len(records))]
        else:
            boxes = [box(record) for record in records]
            first_edge = boxes[0][minimum_key]
            total_size = sum(
                item[maximum_key] - item[minimum_key] for item in boxes
            )
            gap = (
                spacing
                if spacing is not None
                else (boxes[-1][maximum_key] - first_edge - total_size)
                / (len(records) - 1)
            )
            cursor = first_edge
            for item in boxes:
                size = item[maximum_key] - item[minimum_key]
                targets.append(cursor + size / 2.0)
                cursor += size + gap
        operations = []
        for record, target_coordinate in zip(records, targets, strict=True):
            operations.append(
                MoveComponentsOperation(
                    selector=QuerySelector(ids=[record.stable_id]),
                    absolute_x=target_coordinate if axis == "x" else None,
                    absolute_y=target_coordinate if axis == "y" else None,
                    allow_locked=allow_locked,
                )
            )
        return self._run_semantic_operations(
            operations,
            path,
            dry_run,
            expected_sha256 or snapshot.info.sha256,
            txid,
        )

    def group_components(
        self,
        selector: dict[str, Any],
        *,
        group_id: int | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = GroupComponentsOperation.model_validate(
            {
                "selector": selector,
                "group_id": group_id,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def ungroup_components(
        self,
        selector: dict[str, Any],
        *,
        remove_empty_groups: bool = True,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = UngroupComponentsOperation.model_validate(
            {
                "selector": selector,
                "remove_empty_groups": remove_empty_groups,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def list_board_texts(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        query = QuerySelector.model_validate(selector or {})
        records = snapshot.select(query, kinds={"component_text", "board_text"})
        return self._read_success(
            snapshot.info,
            {"matched_count": len(records), "items": [item.model_dump() for item in records]},
        )

    def move_board_texts(
        self,
        selector: dict[str, Any] | None,
        *,
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
        operation = MoveBoardTextsOperation.model_validate(
            {
                "selector": selector or {},
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def rotate_board_texts(
        self,
        selector: dict[str, Any] | None,
        angle_deg: float,
        mode: str = "relative",
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = RotateBoardTextsOperation.model_validate(
            {
                "selector": selector or {},
                "angle_deg": angle_deg,
                "mode": mode,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_text_visibility(
        self,
        selector: dict[str, Any] | None,
        visibility: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetTextVisibilityOperation.model_validate(
            {
                "selector": selector or {},
                "visibility": visibility,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_text_style(
        self,
        selector: dict[str, Any] | None,
        *,
        font_size: int | None = None,
        font_width: float | None = None,
        horizontal_align: str | None = None,
        vertical_align: str | None = None,
        mirrored: bool | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = SetTextStyleOperation.model_validate(
            {
                "selector": selector or {},
                "font_size": font_size,
                "font_width": font_width,
                "horizontal_align": horizontal_align,
                "vertical_align": vertical_align,
                "mirrored": mirrored,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_pin_no_connect(
        self,
        selector: dict[str, Any] | None,
        no_connect: bool,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetPinNoConnectOperation.model_validate(
            {"selector": selector or {}, "no_connect": no_connect}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def rename_net(
        self,
        selector: dict[str, Any] | None,
        new_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = RenameNetOperation.model_validate(
            {"selector": selector or {}, "new_name": new_name}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def update_net_class_rules(
        self,
        class_name: str,
        *,
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
        operation = UpdateNetClassRulesOperation.model_validate(
            {
                "class_name": class_name,
                "layer": layer,
                "width": width,
                "min_width": min_width,
                "max_width": max_width,
                "clearance": clearance,
                "neck_width": neck_width,
                "differential_gap": differential_gap,
                "max_uncoupled_length": max_uncoupled_length,
                "tolerance": tolerance,
                "check_length": check_length,
                "fixed_length": fixed_length,
                "length_delta": length_delta,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def assign_nets_to_class(
        self,
        selector: dict[str, Any] | None,
        class_name: str,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AssignNetsToClassOperation.model_validate(
            {"selector": selector or {}, "class_name": class_name}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def list_testpoints(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        query = QuerySelector.model_validate(selector or {})
        records = snapshot.select(query, kinds={"testpoint"})
        net_names = {
            record.xml_id: record.name
            for record in snapshot.objects.values()
            if record.kind == "net" and record.xml_id is not None
        }
        items = []
        for record in records:
            payload = record.model_dump()
            payload["net_name"] = (
                net_names.get(record.net_id) if record.net_id is not None else None
            )
            items.append(payload)
        return self._read_success(
            snapshot.info,
            {"matched_count": len(items), "items": items},
        )

    def find_testpoint_candidates(
        self,
        target_nets: list[str],
        *,
        path: str | None = None,
        side: str = "Top",
        probe_diameter: float = 1.0,
        clearance: float = 0.5,
        grid: float = 2.54,
        candidates_per_net: int = 10,
    ) -> dict[str, Any]:
        if not target_nets:
            raise DocumentError("target_nets cannot be empty", code="scope_required")
        if side not in {"Top", "Bottom"}:
            raise DocumentError("side must be Top or Bottom", code="geometry_invalid")
        if probe_diameter <= 0 or clearance < 0 or grid <= 0:
            raise DocumentError("probe_diameter and grid must be positive")
        if not 1 <= candidates_per_net <= 100:
            raise DocumentError("candidates_per_net must be between 1 and 100")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None or snapshot.board.outline is None:
            raise DocumentError("A PCB board outline is required", code="geometry_invalid")
        outline = [Point(**item) for item in snapshot.board.outline.get("points", [])]
        board_box = BBox(**snapshot.board.outline["bbox"])
        obstacles = [
            BBox(**record.bbox).expand(clearance + probe_diameter / 2.0)
            for record in snapshot.objects.values()
            if record.kind in {"component", "testpoint", "keepout"}
            and record.bbox is not None
            and (record.side in {None, side} or record.kind == "keepout")
        ]
        free_points: list[Point] = []
        x = math.ceil(board_box.min_x / grid) * grid
        while x <= board_box.max_x and len(free_points) < 5_000:
            y = math.ceil(board_box.min_y / grid) * grid
            while y <= board_box.max_y and len(free_points) < 5_000:
                point = Point(x, y)
                if point_in_polygon(point, outline) and not any(
                    obstacle.contains_point(point) for obstacle in obstacles
                ):
                    free_points.append(point)
                y += grid
            x += grid
        net_records = [
            record
            for record in snapshot.objects.values()
            if record.kind == "net"
            and any(
                candidate.casefold()
                in {(record.name or "").casefold(), record.stable_id.casefold()}
                for candidate in target_nets
            )
        ]
        missing = [
            candidate
            for candidate in target_nets
            if not any(
                candidate.casefold()
                in {(record.name or "").casefold(), record.stable_id.casefold()}
                for record in net_records
            )
        ]
        if missing:
            raise DocumentError(
                "Some target nets were not found",
                code="object_not_found",
                details={"missing_nets": missing},
            )
        candidates: list[dict[str, Any]] = []
        for net in net_records:
            endpoints = [
                snapshot.objects[object_id]
                for object_id in net.relationships.get("endpoints", [])
                if object_id in snapshot.objects
                and snapshot.objects[object_id].position is not None
            ]
            ranked = sorted(
                free_points,
                key=lambda point: min(
                    (
                        distance(point, Point(**endpoint.position))
                        for endpoint in endpoints
                        if endpoint.position is not None
                    ),
                    default=0.0,
                ),
            )[:candidates_per_net]
            for rank, point in enumerate(ranked, start=1):
                candidates.append(
                    {
                        "candidate_id": f"tpc_{net.stable_id}_{rank}",
                        "net_id": net.stable_id,
                        "net_name": net.name,
                        "position": point.as_dict(),
                        "side": side,
                        "probe_diameter": probe_diameter,
                        "clearance": clearance,
                    }
                )
        return self._read_success(
            snapshot.info,
            {
                "matched_net_count": len(net_records),
                "candidate_count": len(candidates),
                "candidates": candidates,
            },
            limitations=[
                "Candidates use exported bbox geometry; enclosure and fixture shadowing "
                "are not modeled."
            ],
        )

    def add_testpoints(
        self,
        testpoints: list[dict[str, Any]],
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        if not testpoints:
            raise DocumentError("testpoints cannot be empty", code="scope_required")
        operations = [AddTestpointOperation.model_validate(item) for item in testpoints]
        return self._run_semantic_operations(
            operations, path, dry_run, expected_sha256, txid
        )

    def move_testpoints(
        self,
        selector: dict[str, Any] | None,
        *,
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
        operation = MoveTestpointsOperation.model_validate(
            {
                "selector": selector or {},
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "grid_snap": grid_snap,
                "allow_locked": allow_locked,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def remove_testpoints(
        self,
        selector: dict[str, Any] | None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
        allow_locked: bool = False,
    ) -> dict[str, Any]:
        operation = RemoveTestpointsOperation.model_validate(
            {"selector": selector or {}, "allow_locked": allow_locked}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def review_testpoint_coverage(
        self,
        target_nets: list[str] | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        nets = [record for record in snapshot.objects.values() if record.kind == "net"]
        if target_nets:
            requested = {name.casefold() for name in target_nets}
            nets = [record for record in nets if (record.name or "").casefold() in requested]
        testpoint_net_ids = {
            record.net_id
            for record in snapshot.objects.values()
            if record.kind == "testpoint" and record.net_id is not None
        }
        covered = [record for record in nets if record.xml_id in testpoint_net_ids]
        uncovered = [record for record in nets if record.xml_id not in testpoint_net_ids]
        coverage = len(covered) / len(nets) if nets else 1.0
        return self._read_success(
            snapshot.info,
            {
                "target_net_count": len(nets),
                "covered_count": len(covered),
                "coverage": coverage,
                "covered_nets": [record.name for record in covered],
                "uncovered_nets": [record.name for record in uncovered],
            },
            limitations=[
                "Coverage counts explicit MCP/DipTrace standalone pad testpoints only."
            ],
        )

    def add_trace(
        self,
        *,
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
        operation = AddTraceOperation.model_validate(
            {
                "net": net,
                "start_object_id": start_object_id,
                "end_object_id": end_object_id,
                "points": points,
                "layer": layer,
                "width": width,
                "clearance": clearance,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def replace_trace(
        self,
        trace_id: str,
        points: list[dict[str, Any]],
        *,
        layer: str,
        width: float,
        clearance: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = ReplaceTraceOperation.model_validate(
            {
                "trace_id": trace_id,
                "points": points,
                "layer": layer,
                "width": width,
                "clearance": clearance,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def delete_trace(
        self,
        selector: dict[str, Any],
        *,
        allow_connectivity_regression: bool = False,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = DeleteTraceOperation.model_validate(
            {
                "selector": selector,
                "allow_connectivity_regression": allow_connectivity_regression,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_trace_width(
        self,
        selector: dict[str, Any],
        width: float,
        *,
        segment_indices: list[int] | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetTraceWidthOperation.model_validate(
            {
                "selector": selector,
                "width": width,
                "segment_indices": segment_indices or [],
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def add_via(
        self,
        trace_id: str,
        x: float,
        y: float,
        via_style: str,
        *,
        layer_before: str | None = None,
        layer_after: str | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = AddViaOperation.model_validate(
            {
                "trace_id": trace_id,
                "x": x,
                "y": y,
                "via_style": via_style,
                "layer_before": layer_before,
                "layer_after": layer_after,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def move_via(
        self,
        selector: dict[str, Any],
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        absolute_x: float | None = None,
        absolute_y: float | None = None,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = MoveViaOperation.model_validate(
            {
                "selector": selector,
                "dx": dx,
                "dy": dy,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
            }
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def delete_via(
        self,
        selector: dict[str, Any],
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = DeleteViaOperation.model_validate({"selector": selector})
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def set_via_style(
        self,
        selector: dict[str, Any],
        via_style: str,
        *,
        path: str | None = None,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        operation = SetViaStyleOperation.model_validate(
            {"selector": selector, "via_style": via_style}
        )
        return self._run_semantic_write(operation, path, dry_run, expected_sha256, txid)

    def list_unrouted_connections(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Unrouted connections require a PCB document")
        requested = {item.casefold() for item in nets or []}
        items: list[dict[str, Any]] = []
        for index, ratline in enumerate(snapshot.board.ratlines):
            endpoints = ratline.get("endpoints", [])
            if len(endpoints) != 2:
                continue
            pad_ids = [endpoint.get("pad_id") for endpoint in endpoints]
            if any(pad_id is None for pad_id in pad_ids):
                continue
            first = snapshot.get_object(str(pad_ids[0]))
            second = snapshot.get_object(str(pad_ids[1]))
            if first.net_id is None or first.net_id != second.net_id:
                continue
            net = next(
                (
                    item
                    for item in snapshot.board.nets
                    if item.xml_id == first.net_id
                ),
                None,
            )
            if net is None or (
                requested
                and (net.name or "").casefold() not in requested
                and net.stable_id.casefold() not in requested
            ):
                continue
            positions = [endpoint.get("position") for endpoint in endpoints]
            ratline_length = (
                distance(Point(**positions[0]), Point(**positions[1]))
                if positions[0] is not None and positions[1] is not None
                else None
            )
            items.append(
                {
                    "connection_id": f"ratline:{index}",
                    "net_id": net.stable_id,
                    "net": net.name,
                    "net_class": net.attributes.get("net_class"),
                    "endpoints": endpoints,
                    "ratline_length_mm": ratline_length,
                    "priority": 0,
                    "differential_pair": None,
                }
            )
        return self._read_success(
            snapshot.info,
            {"matched_count": len(items), "items": items},
            limitations=[
                "Unrouted connections are derived from exported Ratlines.",
                "Priority and differential-pair enrichment are not implemented yet.",
            ],
        )

    def get_route_details(
        self,
        *,
        trace_id: str | None = None,
        net: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        if (trace_id is None) == (net is None):
            raise DocumentError(
                "Specify exactly one of trace_id or net", code="scope_required"
            )
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Route details require a PCB document")
        if trace_id is not None:
            traces = [snapshot.get_object(trace_id)]
            if traces[0].kind != "trace":
                raise DocumentError(f"Object is not a trace: {trace_id}")
        else:
            assert net is not None
            net_matches = [
                item
                for item in snapshot.board.nets
                if item.stable_id == net
                or item.xml_id == net
                or (item.name or "").casefold() == net.casefold()
            ]
            if len(net_matches) != 1:
                raise DocumentError(f"Unique net was not found: {net}")
            traces = [
                item
                for item in snapshot.board.traces
                if item.parent_id == net_matches[0].stable_id
            ]
        per_layer: dict[str, float] = {}
        total_length = 0.0
        via_ids: list[str] = []
        items: list[dict[str, Any]] = []
        for trace in traces:
            points = [Point(**item) for item in trace.attributes.get("points", [])]
            layers = trace.attributes.get("segment_layers", [])
            segment_lengths: list[float] = []
            for segment_index, (start, end) in enumerate(
                zip(points, points[1:], strict=False)
            ):
                length = distance(start, end)
                segment_lengths.append(length)
                layer = (
                    str(layers[segment_index])
                    if segment_index < len(layers)
                    else trace.layer or ""
                )
                per_layer[layer] = per_layer.get(layer, 0.0) + length
                total_length += length
            via_ids.extend(trace.relationships.get("vias", []))
            items.append(
                {
                    **trace.model_dump(mode="json"),
                    "segment_lengths_mm": segment_lengths,
                    "bend_count": max(0, len(points) - 2),
                }
            )
        return self._read_success(
            snapshot.info,
            {
                "trace_count": len(traces),
                "traces": items,
                "total_length_mm": total_length,
                "per_layer_length_mm": per_layer,
                "via_count": len(set(via_ids)),
                "via_ids": sorted(set(via_ids)),
                "layer_transition_count": len(set(via_ids)),
            },
            limitations=[
                "Length is geometric centerline length; arc and electrical delay are not included."
            ],
        )

    def get_stackup(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Stackup is only available for PCB documents")
        return self._read_success(
            snapshot.info,
            snapshot.board.stackup.model_dump(mode="json"),
            warnings=snapshot.board.stackup.warnings,
            limitations=(
                ["Physical LayerStackItems are absent from this XML export."]
                if snapshot.board.stackup.source == "missing"
                else []
            ),
            resources=[f"diptrace://document/{snapshot.info.document_id}/stackup"],
        )

    def measure_net_lengths(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
        effective_dielectric_constant: float | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Net-length measurement requires a PCB document")
        references = nets or [net.stable_id for net in snapshot.board.nets]
        measurements = [
            measure_net_length(
                snapshot,
                reference,
                effective_dielectric_constant=effective_dielectric_constant,
            )
            for reference in references
        ]
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(measurements),
                "measurements": [item.model_dump(mode="json") for item in measurements],
                "units": {"length": "mm", "delay": "ps"},
            },
            limitations=[
                "Geometric length follows exported trace centerlines; package and pin delay "
                "are not included."
            ],
        )

    def analyze_length_group(
        self,
        nets: list[str],
        *,
        tolerance_mm: float | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        if len(nets) < 2:
            raise DocumentError("Length-group analysis requires at least two nets")
        if tolerance_mm is not None and tolerance_mm < 0:
            raise DocumentError("tolerance_mm cannot be negative")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        measurements = [measure_net_length(snapshot, net) for net in nets]
        lengths = [item.geometric_length_mm for item in measurements]
        minimum = min(lengths)
        maximum = max(lengths)
        delta = maximum - minimum
        return self._read_success(
            snapshot.info,
            {
                "measurements": [item.model_dump(mode="json") for item in measurements],
                "minimum_length_mm": minimum,
                "maximum_length_mm": maximum,
                "delta_mm": delta,
                "tolerance_mm": tolerance_mm,
                "within_tolerance": tolerance_mm is None or delta <= tolerance_mm,
            },
        )

    def list_differential_pairs(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Differential pairs require a PCB document")
        pairs = snapshot.board.differential_pairs
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(pairs),
                "offset": offset,
                "limit": limit,
                "items": [
                    item.model_dump(mode="json") for item in pairs[offset : offset + limit]
                ],
            },
        )

    def get_differential_pair(
        self, pair: str, path: str | None = None
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = resolve_differential_pair(snapshot, pair)
        return self._read_success(snapshot.info, result.model_dump(mode="json"))

    def analyze_differential_pair(
        self, pair: str, path: str | None = None
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = analyze_pair_geometry(snapshot, pair)
        return self._read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            warnings=result.warnings,
            limitations=[
                "Coupling and gap are geometry heuristics; this is not a field-solver result."
            ],
        )

    def analyze_differential_pairs(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Differential pairs require a PCB document")
        analyses = [
            analyze_pair_geometry(snapshot, pair.stable_id)
            for pair in snapshot.board.differential_pairs
        ]
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(analyses),
                "items": [item.model_dump(mode="json") for item in analyses],
                "failed_check_count": sum(
                    1
                    for item in analyses
                    for check in item.checks
                    if not bool(check["passed"])
                ),
            },
            limitations=[
                "Coupling and gap are geometry heuristics; this is not a field-solver result."
            ],
        )

    def validate_differential_pair(
        self, pair: str, path: str | None = None
    ) -> dict[str, Any]:
        response = self.analyze_differential_pair(pair, path)
        checks = response["result"]["checks"]
        response["result"]["valid"] = all(bool(check["passed"]) for check in checks)
        response["result"]["evaluated_check_count"] = len(checks)
        return response

    def calculate_impedance(
        self,
        *,
        structure: str,
        width_mm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        gap_mm: float | None = None,
        frequency_hz: float | None = None,
        target_ohm: float | None = None,
        tolerance_ohm: float | None = None,
    ) -> dict[str, Any]:
        values = ImpedanceInput.model_validate(
            {
                "structure": structure,
                "width_mm": width_mm,
                "copper_thickness_mm": copper_thickness_mm,
                "dielectric_height_mm": dielectric_height_mm,
                "dielectric_constant": dielectric_constant,
                "gap_mm": gap_mm,
                "frequency_hz": frequency_hz,
                "target_ohm": target_ohm,
                "tolerance_ohm": tolerance_ohm,
            }
        )
        result = calculate_impedance_estimate(values)
        return {
            "ok": True,
            "document": None,
            "result": result.model_dump(mode="json"),
            "warnings": result.warnings,
            "limitations": [
                "Analytical preliminary estimate only; not a full-wave or fabrication-coupon "
                "result."
            ],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def suggest_trace_geometry_for_impedance(
        self,
        *,
        target_ohm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        minimum_width_mm: float,
        maximum_width_mm: float,
        tolerance_ohm: float = 0.01,
    ) -> dict[str, Any]:
        result = synthesize_microstrip_width(
            target_ohm=target_ohm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            minimum_width_mm=minimum_width_mm,
            maximum_width_mm=maximum_width_mm,
            tolerance_ohm=tolerance_ohm,
        )
        return {
            "ok": True,
            "document": None,
            "result": result,
            "warnings": result["result"]["warnings"],
            "limitations": [
                "Width synthesis uses the same preliminary Hammerstad-Jensen microstrip model."
            ],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def analyze_stackup_for_impedance(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Stackup analysis requires a PCB document")
        result = analyze_stackup(snapshot.board.stackup)
        return self._read_success(
            snapshot.info,
            result,
            warnings=snapshot.board.stackup.warnings,
            limitations=result["limitations"],
        )

    def validate_impedance_constraints(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        if not constraints:
            raise DocumentError("At least one explicit impedance constraint is required")
        if len(constraints) > 1_000:
            raise DocumentError("At most 1000 impedance constraints are accepted")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Impedance validation requires a PCB document")
        stackup_analysis = analyze_stackup(snapshot.board.stackup)
        candidates = stackup_analysis["microstrip_candidates"]
        layer_names = {
            str(layer.get("id", "")): str(layer.get("name", ""))
            for layer in snapshot.board.layers
        }
        results: list[dict[str, Any]] = []
        for index, raw_constraint in enumerate(constraints):
            net_ref = str(raw_constraint.get("net", "")).strip()
            layer_ref = str(raw_constraint.get("layer", "")).strip()
            if not net_ref or not layer_ref:
                raise DocumentError(
                    f"Constraint {index} requires net and layer",
                    details={"constraint_index": index},
                )
            net = resolve_net(snapshot, net_ref)
            target_ohm = float(raw_constraint.get("target_ohm", 0.0))
            tolerance_ohm = float(raw_constraint.get("tolerance_ohm", 0.0))
            if target_ohm <= 0 or tolerance_ohm < 0:
                raise DocumentError(
                    f"Constraint {index} has invalid target/tolerance",
                    details={"constraint_index": index},
                )
            canonical_layer = layer_names.get(layer_ref, layer_ref)
            stack_candidates = [
                item for item in candidates if item["signal_layer"] == canonical_layer
            ]
            if len(stack_candidates) != 1:
                results.append(
                    {
                        "net_id": net.stable_id,
                        "net": net.name,
                        "layer": layer_ref,
                        "status": "skipped",
                        "reason": "No unique complete microstrip geometry exists for this layer.",
                    }
                )
                continue
            widths = {
                float(width)
                for trace in snapshot.board.traces
                if trace.parent_id == net.stable_id
                for segment_index, width in enumerate(
                    trace.attributes.get("segment_widths_mm", [])
                )
                if width is not None
                and (
                    segment_index
                    >= len(trace.attributes.get("segment_layers", []))
                    or str(trace.attributes["segment_layers"][segment_index]) == layer_ref
                    or layer_names.get(
                        str(trace.attributes["segment_layers"][segment_index]), ""
                    )
                    == canonical_layer
                )
            }
            if raw_constraint.get("width_mm") is not None:
                widths = {float(raw_constraint["width_mm"])}
            if not widths:
                results.append(
                    {
                        "net_id": net.stable_id,
                        "net": net.name,
                        "layer": layer_ref,
                        "status": "skipped",
                        "reason": "No routed width exists on the requested layer.",
                    }
                )
                continue
            stack_candidate = stack_candidates[0]
            estimates = [
                calculate_impedance_estimate(
                    ImpedanceInput(
                        structure="microstrip",
                        width_mm=width,
                        copper_thickness_mm=float(
                            stack_candidate.get("copper_thickness_mm") or 0.0
                        ),
                        dielectric_height_mm=float(stack_candidate["dielectric_height_mm"]),
                        dielectric_constant=float(stack_candidate["dielectric_constant"]),
                        target_ohm=target_ohm,
                        tolerance_ohm=tolerance_ohm,
                        source=f"stackup:{snapshot.info.document_id}:{canonical_layer}",
                    )
                )
                for width in sorted(widths)
            ]
            results.append(
                {
                    "net_id": net.stable_id,
                    "net": net.name,
                    "layer": layer_ref,
                    "status": "evaluated",
                    "valid": all(item.within_tolerance is True for item in estimates),
                    "estimates": [item.model_dump(mode="json") for item in estimates],
                    "stackup_geometry": stack_candidate,
                }
            )
        evaluated = [item for item in results if item["status"] == "evaluated"]
        return self._read_success(
            snapshot.info,
            {
                "constraint_count": len(constraints),
                "evaluated_count": len(evaluated),
                "skipped_count": len(results) - len(evaluated),
                "valid": bool(evaluated)
                and len(evaluated) == len(results)
                and all(bool(item["valid"]) for item in evaluated),
                "items": results,
            },
            limitations=[
                "Only explicit single-ended outer-layer microstrip constraints are evaluated.",
                "Reference-plane net continuity and solder mask are not inferred by this tool.",
            ],
        )

    def analyze_controlled_impedance_nets(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self.validate_impedance_constraints(constraints, path=path)

    def list_copper_pours(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._validate_page(offset, limit)
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Copper pours require a PCB document")
        items = snapshot.board.copper_pours
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(items),
                "offset": offset,
                "limit": limit,
                "items": [
                    item.model_dump(mode="json") for item in items[offset : offset + limit]
                ],
            },
            limitations=[
                "Exported polygons are pour boundaries, not authoritative refilled copper."
            ],
        )

    def analyze_plane_continuity(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = analyze_plane_geometry(snapshot)
        return self._read_success(
            snapshot.info,
            result,
            limitations=result["limitations"],
        )

    def analyze_return_path(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
        stitching_radius_mm: float = 2.0,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = analyze_return_geometry(
            snapshot,
            nets=nets,
            reference_nets=reference_nets,
            stitching_radius_mm=stitching_radius_mm,
        )
        return self._read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            limitations=[
                "Geometry-based heuristic only; exported pour boundaries are not final refill."
            ],
        )

    def route_connection(
        self,
        *,
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
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = RouteConnectionConfig(
            net=net,
            start_object_id=start_object_id,
            end_object_id=end_object_id,
            layer=layer,
            width=width,
            clearance=clearance,
            grid=grid,
            bend_cost=bend_cost,
            preferred_layers=preferred_layers or [],
            start_layer=start_layer,
            end_layer=end_layer,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
            max_nodes=max_nodes,
            time_budget_ms=time_budget_ms,
            avoid_component_bodies=avoid_component_bodies,
        )
        route = synthesize_route(snapshot, config)
        response = self._run_semantic_write(
            route.operation, path, dry_run, expected_sha256, txid
        )
        response["routing"] = {
            "points": [point.as_dict() for point in route.points],
            "path": [point.model_dump(mode="json") for point in route.operation.points],
            "metrics": route.metrics,
            "assumptions": route.assumptions,
        }
        response["warnings"] = [*response.get("warnings", []), *route.warnings]
        response["limitations"] = [
            *response.get("limitations", []),
            *route.limitations,
        ]
        return response

    def route_net(
        self,
        net: str,
        *,
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
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        pairs = self._unrouted_pairs(snapshot, [net])
        if not pairs:
            raise DocumentError(f"No exported unrouted connection was found for net: {net}")
        operations: list[SemanticOperation] = []
        metrics: list[dict[str, Any]] = []
        working = document
        working_snapshot = snapshot
        for pair in pairs:
            route = synthesize_route(
                working_snapshot,
                RouteConnectionConfig(
                    net=pair["net_id"],
                    start_object_id=pair["start_object_id"],
                    end_object_id=pair["end_object_id"],
                    layer=layer,
                    width=width,
                    clearance=clearance,
                    grid=grid,
                    preferred_layers=preferred_layers or [],
                    via_style=via_style,
                    max_vias=max_vias,
                    via_cost=via_cost,
                ),
            )
            operations.append(route.operation)
            metrics.append(route.metrics)
            applied = apply_semantic_operations(
                working, [route.operation], live_session=target.is_live
            )
            working = applied.document
            working_snapshot = build_snapshot(working, live_session=target.is_live)
        response = self._run_semantic_operations(
            operations, path, dry_run, expected_sha256, txid
        )
        response["routing"] = {"connection_count": len(operations), "routes": metrics}
        return response

    def route_diff_pair(
        self,
        pair: str,
        *,
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
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        route = synthesize_differential_pair_route(
            snapshot,
            DifferentialPairRouteConfig(
                pair=pair,
                start_pad_point_id=start_pad_point_id,
                end_pad_point_id=end_pad_point_id,
                layer=layer,
                preferred_layers=preferred_layers or [],
                width=width,
                gap=gap,
                clearance=clearance,
                grid=grid,
                via_style=via_style,
                max_vias=max_vias,
                via_cost=via_cost,
                max_detour=max_detour,
            ),
        )
        response = self._run_semantic_write(
            route.operation, path, dry_run, expected_sha256, txid
        )
        response["routing"] = {
            "center_points": [point.as_dict() for point in route.center_points],
            "positive_points": [point.as_dict() for point in route.positive_points],
            "negative_points": [point.as_dict() for point in route.negative_points],
            "metrics": route.metrics,
            "assumptions": route.assumptions,
        }
        response["warnings"] = [*response.get("warnings", []), *route.warnings]
        response["limitations"] = [
            *response.get("limitations", []),
            *route.limitations,
        ]
        return response

    def plan_diff_pair_route(
        self,
        pair: str,
        *,
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
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = DifferentialPairRouteConfig(
            pair=pair,
            start_pad_point_id=start_pad_point_id,
            end_pad_point_id=end_pad_point_id,
            layer=layer,
            preferred_layers=preferred_layers or [],
            width=width,
            gap=gap,
            clearance=clearance,
            grid=grid,
            via_style=via_style,
            max_vias=max_vias,
            via_cost=via_cost,
            max_detour=max_detour,
        )
        route = synthesize_differential_pair_route(snapshot, config)
        preview = self._preview_semantic_operations(document, [route.operation])
        record = self.plans.create(
            plan_type="diff_pair_route",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[route.operation.model_dump(mode="json")],
            changed_ids=[
                route.operation.pair,
                route.operation.positive_net,
                route.operation.negative_net,
            ],
            unresolved=[],
            candidates=[{"metrics": route.metrics}],
            score={"absolute_skew_mm": float(route.metrics["absolute_skew_mm"])},
            metrics=route.metrics,
            assumptions=route.assumptions,
            warnings=route.warnings,
            limitations=route.limitations,
        )
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "center_points": [point.as_dict() for point in route.center_points],
                "positive_points": [point.as_dict() for point in route.positive_points],
                "negative_points": [point.as_dict() for point in route.negative_points],
                "metrics": route.metrics,
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        return self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            limitations=record.limitations,
            resources=resources,
        )

    def plan_route_nets(
        self,
        nets: list[str],
        *,
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
        if not nets:
            raise DocumentError("At least one net is required", code="scope_required")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        pairs = self._unrouted_pairs(snapshot, nets)
        if not pairs:
            raise DocumentError("No matching exported unrouted connections were found")
        if len(pairs) > 20:
            raise DocumentError("A local route plan is limited to 20 connections")
        operations: list[SemanticOperation] = []
        candidates: list[dict[str, Any]] = []
        working = document
        working_snapshot = snapshot
        for pair in pairs:
            route = synthesize_route(
                working_snapshot,
                RouteConnectionConfig(
                    net=pair["net_id"],
                    start_object_id=pair["start_object_id"],
                    end_object_id=pair["end_object_id"],
                    layer=layer,
                    width=width,
                    clearance=clearance,
                    grid=grid,
                    preferred_layers=preferred_layers or [],
                    via_style=via_style,
                    max_vias=max_vias,
                    via_cost=via_cost,
                ),
            )
            operations.append(route.operation)
            candidates.append(
                {
                    "net_id": pair["net_id"],
                    "points": [point.as_dict() for point in route.points],
                    "metrics": route.metrics,
                }
            )
            applied = apply_semantic_operations(
                working, [route.operation], live_session=target.is_live
            )
            working = applied.document
            working_snapshot = build_snapshot(working, live_session=target.is_live)
        preview = self._preview_semantic_operations(document, operations)
        total_length = sum(float(item["metrics"]["length_mm"]) for item in candidates)
        record = self.plans.create(
            plan_type="route_nets",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config={
                "nets": nets,
                "layer": layer,
                "width": width,
                "clearance": clearance,
                "grid": grid,
                "preferred_layers": preferred_layers or [],
                "via_style": via_style,
                "max_vias": max_vias,
                "via_cost": via_cost,
            },
            operations=[operation.model_dump(mode="json") for operation in operations],
            changed_ids=sorted({pair["net_id"] for pair in pairs}),
            unresolved=[],
            candidates=candidates,
            score={"total_length_mm": total_length},
            metrics={"connection_count": len(operations), "total_length_mm": total_length},
            assumptions=["Connections are routed sequentially with bounded 45-degree A*."],
            warnings=[],
            limitations=["No push-and-shove or rip-up/retry is implemented."],
        )
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "routes": candidates,
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        return self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            limitations=record.limitations,
            resources=resources,
        )

    def apply_route_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        plan = self.plans.read(plan_id)
        if plan.plan_type not in {"route_nets", "diff_pair_route"}:
            raise DocumentError(
                f"Unexpected route plan type for {plan_id}: {plan.plan_type}",
                code="transaction_conflict",
            )
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type=plan.plan_type,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def export_autorouter_dsn(
        self,
        path: str | None = None,
        *,
        design_name: str | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        dsn = export_dsn(snapshot, design_name=design_name)
        record = self.external_jobs.create_export_job(
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
                ],
            },
        )
        response = self._read_success(
            snapshot.info,
            {"job": record.model_dump(mode="json")},
            resources=job_resources(record.jobid),
            limitations=[
                "The bounded serializer rejects cutouts, keepouts, pours and unsupported "
                "pad shapes."
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
        self.policy.require_external_execution(operation="run_external_autorouter")
        if dsn_job_id is not None and dsn_path is not None:
            raise DocumentError("Pass either dsn_job_id or dsn_path, not both")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if dsn_job_id is not None:
            export_job = self.jobs.read(dsn_job_id)
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
            dsn = self.jobs.artifact_path(dsn_job_id, "input.dsn").read_bytes()
        elif dsn_path is not None:
            source = self.settings.resolve_allowed_path(dsn_path)
            if source.stat().st_size > self.settings.max_document_bytes:
                raise DocumentError("DSN input exceeds the document size limit")
            dsn = source.read_bytes()
        else:
            dsn = export_dsn(snapshot)
        record = self.external_jobs.start_freerouting(
            snapshot.info,
            target.path,
            dsn,
            max_passes=max_passes,
            threads=threads,
            timeout_seconds=timeout_seconds,
            ignore_net_classes=list(ignore_net_classes or []),
        )
        response = self._read_success(
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
        job = self.jobs.read(jobid)
        if job.job_type != "freerouting" or job.status != "completed":
            raise DocumentError(
                "Autorouter result inspection requires a completed Freerouting job",
                details={"jobid": jobid, "status": job.status, "job_type": job.job_type},
            )
        target_path = path or job.target_path
        if target_path is None:
            raise DocumentError("Autorouter job has no associated DipTrace target")
        document, target = self.load(target_path)
        snapshot = self.models.get(document, live_session=target.is_live)
        if snapshot.info.sha256 != job.source_sha256:
            raise Sha256MismatchError(
                "DipTrace document changed after the autorouter job was created",
                details={
                    "job_source_sha256": job.source_sha256,
                    "current_sha256": snapshot.info.sha256,
                },
            )
        ses_path = self.jobs.artifact_path(jobid, "output.ses")
        session = parse_ses(
            ses_path.read_bytes(), max_bytes=self.settings.max_document_bytes
        )
        operation_plan = session_to_operations(snapshot, session, via_style=via_style)
        plan_record = None
        resources = job_resources(jobid)
        if operation_plan.operations:
            preview = self._preview_semantic_operations(
                document, cast(list[SemanticOperation], operation_plan.operations)
            )
            plan_record = self.plans.create(
                plan_type="autorouter_ses_import",
                document_id=snapshot.info.document_id,
                source_sha256=snapshot.info.sha256,
                target_path=target.path,
                config={"jobid": jobid, "via_style": via_style},
                operations=[
                    operation.model_dump(mode="json")
                    for operation in operation_plan.operations
                ],
                changed_ids=sorted(
                    {operation.net for operation in operation_plan.operations}
                ),
                unresolved=operation_plan.skipped,
                candidates=[item.model_dump(mode="json") for item in session.routes],
                score={
                    "imported_length_mm": float(
                        operation_plan.metrics["imported_length_mm"]
                    )
                },
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
            plan_resources = self.plans.store_preview(
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
            plan_record = self.plans.read(plan_record.plan_id)
        return self._read_success(
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
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type="autorouter_ses_import",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def get_job_status(self, jobid: str) -> dict[str, Any]:
        record = self.jobs.read(jobid)
        return {
            "ok": True,
            "document": None,
            "result": {"job": record.model_dump(mode="json")},
            "warnings": record.warnings,
            "limitations": [],
            "resources": job_resources(jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def get_job_result(self, jobid: str) -> dict[str, Any]:
        record = self.jobs.read(jobid)
        return {
            "ok": True,
            "document": None,
            "result": {
                "status": record.status,
                "result": record.result,
                "partial_result": record.partial_result,
                "error": record.error,
                "artifacts": record.artifacts,
            },
            "warnings": record.warnings,
            "limitations": [],
            "resources": job_resources(jobid),
            "transaction": None,
            "job": record.model_dump(mode="json"),
        }

    def cancel_job(self, jobid: str) -> dict[str, Any]:
        record = self.external_jobs.cancel(jobid)
        return self.get_job_status(record.jobid)

    def list_jobs(self, status: str | None = None) -> dict[str, Any]:
        allowed = {None, "queued", "running", "completed", "failed", "cancelled"}
        if status not in allowed:
            raise DocumentError(f"Unknown job status: {status}")
        records = self.jobs.list(status=cast(JobStatus | None, status))
        return {
            "ok": True,
            "document": None,
            "result": {
                "matched_count": len(records),
                "jobs": [record.model_dump(mode="json") for record in records],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def list_exports(self) -> dict[str, Any]:
        records = self.exports.list()
        return {
            "ok": True,
            "document": None,
            "result": {
                "matched_count": len(records),
                "exports": [record.model_dump(mode="json") for record in records],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def export_resource(self, export_id: str, artifact: str) -> str:
        return self.exports.artifact(export_id, artifact).decode("utf-8", errors="strict")

    def job_resource(self, jobid: str, artifact: str) -> str:
        record = self.jobs.read(jobid)
        if artifact == "status":
            return json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if artifact == "result":
            return json.dumps(
                {"status": record.status, "result": record.result, "error": record.error},
                ensure_ascii=False,
                indent=2,
            )
        name = {
            "log": "log.txt",
            "input.dsn": "input.dsn",
            "output.ses": "output.ses",
            "manifest.json": "manifest.json",
        }.get(artifact)
        if name is None:
            raise CapabilityUnavailableError(f"Unknown job resource: {artifact}")
        artifact_path = self.jobs.artifact_path(jobid, name)
        if not artifact_path.exists():
            return ""
        data = artifact_path.read_bytes()
        if artifact == "log" and len(data) > self.settings.max_external_log_bytes:
            data = data[-self.settings.max_external_log_bytes :]
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _unrouted_pairs(
        snapshot: DocumentSnapshot,
        nets: list[str],
    ) -> list[dict[str, str]]:
        if snapshot.board is None:
            raise DocumentError("Routing requires a PCB document")
        requested = {item.casefold() for item in nets}
        pairs: list[dict[str, str]] = []
        for ratline in snapshot.board.ratlines:
            endpoints = ratline.get("endpoints", [])
            if len(endpoints) != 2 or any(item.get("pad_id") is None for item in endpoints):
                continue
            first = snapshot.get_object(str(endpoints[0]["pad_id"]))
            second = snapshot.get_object(str(endpoints[1]["pad_id"]))
            if first.net_id is None or first.net_id != second.net_id:
                continue
            net = next(
                (item for item in snapshot.board.nets if item.xml_id == first.net_id), None
            )
            if net is None or not (
                (net.name or "").casefold() in requested
                or net.stable_id.casefold() in requested
                or (net.xml_id or "").casefold() in requested
            ):
                continue
            pairs.append(
                {
                    "net_id": net.stable_id,
                    "start_object_id": first.stable_id,
                    "end_object_id": second.stable_id,
                }
            )
        return pairs

    def plan_silkscreen(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        clearance: float = 0.2,
        board_edge_clearance: float = 0.2,
        grid: float = 0.25,
        search_steps: int = 4,
        include_board_texts: bool = False,
        avoid_component_bodies: bool = False,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = SilkscreenPlanConfig.model_validate(
            {
                "selector": selector or {},
                "clearance": clearance,
                "board_edge_clearance": board_edge_clearance,
                "grid": grid,
                "search_steps": search_steps,
                "include_board_texts": include_board_texts,
                "avoid_component_bodies": avoid_component_bodies,
            }
        )
        planned = plan_silkscreen(snapshot, config)
        record = self.plans.create(
            plan_type="silkscreen",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[operation.model_dump(mode="json") for operation in planned.operations],
            changed_ids=planned.changed_ids,
            unresolved=planned.unresolved,
            candidates=planned.candidates,
            score=planned.score,
            metrics=planned.metrics,
            assumptions=planned.assumptions,
            warnings=planned.warnings,
            limitations=planned.limitations,
        )
        if planned.operations:
            preview = self._preview_semantic_operations(document, planned.operations)
        else:
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "candidates": planned.candidates,
                "unresolved": planned.unresolved,
                "score": planned.score,
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        return self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            warnings=planned.warnings,
            limitations=planned.limitations,
            resources=resources,
        )

    def analyze_placement(
        self,
        path: str | None = None,
        *,
        selector: dict[str, Any] | None = None,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        result = analyze_placement(
            snapshot,
            QuerySelector.model_validate(selector or {}),
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
        )
        return self._read_success(
            snapshot.info,
            result,
            limitations=[
                "Component bounds are estimated when body/courtyard geometry is absent."
            ],
        )

    def generate_placement_candidates(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = self._placement_config(selector, options)
        candidates = generate_placement_candidates(snapshot, config)
        return self._read_success(
            snapshot.info,
            {
                "matched_count": len(candidates),
                "config": config.model_dump(mode="json"),
                "items": candidates,
            },
            limitations=["Candidate geometry uses normalized component bounds."],
        )

    def score_placement(
        self,
        placements: list[dict[str, Any]],
        path: str | None = None,
        *,
        spacing: float = 0.2,
        board_edge_clearance: float = 0.5,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = PlacementConfig(
            spacing=spacing,
            board_edge_clearance=board_edge_clearance,
            weights=PlacementWeights.model_validate(weights or {}),
        )
        proposals = [PlacementProposal.model_validate(item) for item in placements]
        score, violations = score_placement_proposal(snapshot, proposals, config)
        return self._read_success(
            snapshot.info,
            {"score": score, "violations": violations},
            limitations=["Ratsnest cost uses component anchors, not exact pad anchors."],
        )

    def plan_component_placement(
        self,
        selector: dict[str, Any],
        path: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        config = self._placement_config(selector, options)
        planned = plan_component_placement(snapshot, config)
        before_findings, _, _, _ = run_checks(snapshot, categories={"placement"})
        if planned.operations:
            applied = apply_semantic_operations(
                document, planned.operations, live_session=target.is_live
            )
            after_snapshot = build_snapshot(applied.document, live_session=target.is_live)
            after_findings, _, _, _ = run_checks(
                after_snapshot, categories={"placement"}
            )
            preview = self._preview_semantic_operations(document, planned.operations)
        else:
            after_findings = before_findings
            preview = {
                "svg": render_preview_svg(snapshot, snapshot, []),
                "json": render_preview_json(snapshot, snapshot, []),
                "diff": "",
            }
        before_errors = sum(item.severity == "error" for item in before_findings)
        after_errors = sum(item.severity == "error" for item in after_findings)
        if after_errors > before_errors:
            raise DrcRegressionError(
                "Placement plan introduces new placement DRC errors",
                details={
                    "errors_before": before_errors,
                    "errors_after": after_errors,
                },
                object_ids=planned.changed_ids,
            )
        metrics = {
            **planned.metrics,
            "validation": {
                "placement_errors_before": before_errors,
                "placement_errors_after": after_errors,
                "no_new_placement_errors": after_errors <= before_errors,
            },
        }
        record = self.plans.create(
            plan_type="component_placement",
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            target_path=target.path,
            config=config.model_dump(mode="json"),
            operations=[operation.model_dump(mode="json") for operation in planned.operations],
            changed_ids=planned.changed_ids,
            unresolved=planned.unresolved,
            candidates=planned.candidates,
            score=planned.score,
            metrics=metrics,
            assumptions=planned.assumptions,
            warnings=planned.warnings,
            limitations=planned.limitations,
        )
        resources = self.plans.store_preview(
            record.plan_id,
            svg=preview["svg"],
            geometry={
                **preview["json"],
                "plan_id": record.plan_id,
                "candidates": planned.candidates,
                "unresolved": planned.unresolved,
                "score": planned.score,
                "validation": metrics["validation"],
            },
            diff=preview["diff"],
        )
        record = self.plans.read(record.plan_id)
        return self._read_success(
            snapshot.info,
            {"plan": record.model_dump(mode="json")},
            warnings=planned.warnings,
            limitations=planned.limitations,
            resources=resources,
        )

    def apply_component_placement_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type="component_placement",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def apply_silkscreen_plan(
        self,
        plan_id: str,
        *,
        dry_run: bool = True,
        expected_sha256: str | None = None,
        txid: str | None = None,
    ) -> dict[str, Any]:
        return self._apply_stored_plan(
            plan_id,
            expected_plan_type="silkscreen",
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            txid=txid,
        )

    def _apply_stored_plan(
        self,
        plan_id: str,
        *,
        expected_plan_type: str,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        plan = self.plans.read(plan_id)
        if plan.plan_type != expected_plan_type:
            raise DocumentError(
                f"Unexpected plan type for {plan_id}: {plan.plan_type}",
                code="transaction_conflict",
                details={
                    "expected_plan_type": expected_plan_type,
                    "actual_plan_type": plan.plan_type,
                },
            )
        target_path = self.settings.resolve_allowed_path(plan.target_path)
        document = DipTraceDocument.load(target_path, self.settings.max_document_bytes)
        if document.sha256 != plan.source_sha256:
            self.plans.update(plan_id, status="obsolete", transaction_id=plan.transaction_id)
            raise Sha256MismatchError(
                "Document changed after the silkscreen plan was generated",
                details={
                    "plan_sha256": plan.source_sha256,
                    "current_sha256": document.sha256,
                },
            )
        if expected_sha256 is not None and expected_sha256 != plan.source_sha256:
            raise Sha256MismatchError(
                "Provided SHA does not match the silkscreen plan source",
                details={
                    "plan_sha256": plan.source_sha256,
                    "provided_sha256": expected_sha256,
                },
            )
        operations = parse_semantic_operations(plan.operations)
        if not operations:
            raise EditError("Silkscreen plan contains no changes")
        response = self._run_semantic_operations(
            operations,
            str(target_path),
            dry_run,
            expected_sha256 or plan.source_sha256,
            txid,
        )
        transaction = response.get("transaction") or {}
        transaction_id = transaction.get("txid")
        status: PlanStatus = (
            "committed" if transaction.get("status") == "committed" else "staged"
        )
        updated = self.plans.update(
            plan_id,
            status=status,
            transaction_id=transaction_id,
        )
        response["plan"] = updated.model_dump(mode="json")
        return response

    @staticmethod
    def _placement_config(
        selector: dict[str, Any], options: dict[str, Any]
    ) -> PlacementConfig:
        payload = {"selector": selector, **options}
        if "weights" in payload:
            payload["weights"] = PlacementWeights.model_validate(payload["weights"] or {})
        return PlacementConfig.model_validate(payload)

    def plan_resource(self, plan_id: str, resource: str) -> str:
        if resource == "summary":
            return json.dumps(
                self.plans.read(plan_id).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        paths = {
            "preview.svg": self.plans.preview_svg_path(plan_id),
            "preview.json": self.plans.preview_json_path(plan_id),
            "diff": self.plans.diff_path(plan_id),
        }
        try:
            resource_path = paths[resource]
        except KeyError as exc:
            raise DocumentError(
                f"Unknown plan resource: {resource}", code="object_not_found"
            ) from exc
        if not resource_path.is_file():
            raise DocumentError(
                f"Plan resource is unavailable: {resource}", code="object_not_found"
            )
        return resource_path.read_text(encoding="utf-8")

    def run_review(
        self,
        path: str | None = None,
        *,
        profile: str,
        categories: set[str] | None = None,
    ) -> dict[str, Any]:
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        findings, metrics, skipped, check_count = run_checks(
            snapshot, categories=categories
        )
        assumptions = [
            "All coordinates are normalized to millimetres.",
            "Checks use exported XML geometry only and do not invoke DipTrace DRC/ERC.",
        ]
        if snapshot.board is not None:
            assumptions.append(
                "Component bboxes are estimated when footprint courtyard/body geometry is absent."
            )
            if not any(pad.bbox for pad in snapshot.board.pads):
                skipped.append(
                    {
                        "check_id": "pcb.silk_to_pad",
                        "reason": "pad_geometry_unavailable",
                    }
                )
                check_count += 1
        report = self.findings.create_report(
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            profile=profile,
            findings=findings,
            metrics=metrics,
            assumptions=assumptions,
            skipped_checks=skipped,
            registered_check_count=check_count,
        )
        resources = [
            f"diptrace://document/{snapshot.info.document_id}/review/{report.report_id}",
            f"diptrace://document/{snapshot.info.document_id}/findings",
        ]
        return self._read_success(
            snapshot.info,
            {
                "summary": report.summary(),
                "findings": [finding.model_dump() for finding in report.findings],
                "metrics": report.metrics,
                "assumptions": report.assumptions,
                "skipped_checks": report.skipped_checks,
            },
            resources=resources,
        )

    def get_findings(self, report_id: str) -> dict[str, Any]:
        report = self.findings.read(report_id)
        return {
            "ok": True,
            "report": report.summary(),
            "findings": [finding.model_dump() for finding in report.findings],
        }

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        return {"ok": True, "finding": self.findings.get_finding(finding_id).model_dump()}

    def review_resource(self, report_id: str) -> str:
        report = self.findings.read(report_id)
        return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)

    def findings_resource(self, document_id: str) -> str:
        reports = []
        for path in sorted(self.findings.reports_dir.glob("report_*.json")):
            report = self.findings.read(path.stem)
            if report.document_id == document_id:
                reports.append(report.model_dump())
        return json.dumps({"document_id": document_id, "reports": reports}, indent=2)

    def finish_live_session(self, action: SessionAction) -> dict[str, Any]:
        if action == "apply":
            self.policy.require_write(dry_run=False, operation="finish_live_session")
        return self.sessions.request_finish(action)

    def scan_documents(self, root: str | None = None, recursive: bool = True) -> dict[str, Any]:
        scan_root = self.settings.resolve_allowed_path(root or str(self.settings.workspace))
        if not scan_root.is_dir():
            raise DocumentError(f"Scan root is not a directory: {scan_root}")
        iterator = scan_root.rglob("*") if recursive else scan_root.glob("*")
        results: list[dict[str, Any]] = []
        examined = 0
        truncated = False
        for candidate in iterator:
            if not candidate.is_file() or candidate.suffix.lower() not in _CANDIDATE_SUFFIXES:
                continue
            try:
                candidate = self.settings.resolve_allowed_path(candidate)
            except PathAccessError:
                continue
            examined += 1
            if examined > self.settings.max_scan_files:
                truncated = True
                break
            header = self._read_source_header(candidate)
            if header is None:
                continue
            try:
                relative = candidate.relative_to(self.settings.workspace)
                relative_path = str(relative)
            except ValueError:
                relative_path = None
            results.append(
                {
                    "path": str(candidate),
                    "relative_path": relative_path,
                    "size_bytes": candidate.stat().st_size,
                    **header,
                }
            )
        return {
            "root": str(scan_root),
            "recursive": recursive,
            "examined_candidates": min(examined, self.settings.max_scan_files),
            "truncated": truncated,
            "documents": results,
        }

    def _scan_libraries(
        self,
        source_type: str,
        root: str | None,
        recursive: bool,
    ) -> dict[str, Any]:
        scanned = self.scan_documents(root, recursive)
        items = [
            item for item in scanned["documents"] if item.get("type") == source_type
        ]
        return {
            "ok": True,
            "document": None,
            "result": {
                "source_type": source_type,
                "matched_count": len(items),
                "items": items,
                "truncated": scanned["truncated"],
            },
            "warnings": [],
            "limitations": [],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def _get_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        if stable_id_value is None and name is None:
            raise DocumentError("A stable_id or name is required", code="scope_required")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        model = get_library_model(document)
        item = get_library_item(
            model,
            stable_id_value=stable_id_value,
            name=name,
            kind=kind,
        )
        return self._read_success(snapshot.info, item.model_dump(), warnings=model.warnings)

    def _validate_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        if stable_id_value is None and name is None:
            raise DocumentError("A stable_id or name is required", code="scope_required")
        document, target = self.load(path)
        snapshot = self.models.get(document, live_session=target.is_live)
        model = get_library_model(document)
        item = get_library_item(
            model,
            stable_id_value=stable_id_value,
            name=name,
            kind=kind,
        )
        related_ids = {item.stable_id}
        if isinstance(item, LibraryComponent):
            related_ids.update(pin.stable_id for pin in item.pins)
        elif isinstance(item, LibraryPattern):
            related_ids.update(pad.stable_id for pad in item.pads)
        findings = [
            finding
            for finding in validate_library(model)
            if finding.object_id is None or finding.object_id in related_ids
        ]
        return self._read_success(
            snapshot.info,
            {
                "item": item.model_dump(),
                "valid": not any(finding.severity == "error" for finding in findings),
                "finding_count": len(findings),
                "findings": [finding.model_dump() for finding in findings],
            },
            warnings=model.warnings,
        )

    def _run_semantic_write(
        self,
        operation: SemanticOperation,
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        return self._run_semantic_operations(
            [operation], path, dry_run, expected_sha256, txid
        )

    def _run_semantic_operations(
        self,
        operations: Sequence[SemanticOperation],
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        if not operations:
            raise EditError("At least one semantic operation is required")
        self.policy.require_write(
            dry_run=dry_run,
            operation=operations[0].kind if len(operations) == 1 else "semantic_operations",
        )
        if txid is None:
            document, target = self.load(path)
            snapshot = build_snapshot(document, live_session=target.is_live)
            if expected_sha256 is not None and expected_sha256 != snapshot.info.sha256:
                raise Sha256MismatchError(
                    "Document changed before the semantic operation was planned",
                    details={
                        "expected_sha256": expected_sha256,
                        "current_sha256": snapshot.info.sha256,
                    },
                )
            tx_record = self.transactions.create(
                snapshot.info,
                target.path,
                source_sha256=snapshot.info.sha256,
                expected_sha256=expected_sha256 or snapshot.info.sha256,
                notes=[operation.kind for operation in operations],
            )
            txid = tx_record.txid
            self.transactions.store_snapshot(txid, document.raw_bytes)
            self.transactions.update(
                txid,
                status="staged",
                operations=[operation.model_dump() for operation in operations],
                compiled_patch_count=len(operations),
                snapshot_path=str(self.transactions.snapshot_path(txid)),
            )
        else:
            existing = self.transactions.read(txid)
            if existing.status not in {"staged", "validated"}:
                raise TransactionConflictError(
                    f"Transaction cannot be edited in state {existing.status}: {txid}",
                    txid=txid,
                )
            if path is not None:
                supplied_target = self.resolve_target(path)
                if supplied_target.path != Path(existing.target_path):
                    raise TransactionConflictError(
                        "The supplied path does not match the transaction target",
                        details={
                            "transaction_path": existing.target_path,
                            "supplied_path": str(supplied_target.path),
                        },
                        txid=txid,
                    )
            incoming_operations = [operation.model_dump() for operation in operations]
            if existing.operations != incoming_operations:
                combined_operations = [*existing.operations, *incoming_operations]
                self.transactions.update(
                    txid,
                    status="staged",
                    operations=combined_operations,
                    compiled_patch_count=len(combined_operations),
                    snapshot_path=existing.snapshot_path
                    or str(self.transactions.snapshot_path(txid)),
                )
        preview = self.preview_transaction(txid)
        if dry_run:
            return preview
        record = self.transactions.read(txid)
        return self.commit_transaction(
            txid,
            expected_sha256=expected_sha256 or record.source_sha256,
        )

    def _preview_semantic_operations(
        self,
        document: DipTraceDocument,
        operations: list[SemanticOperation],
    ) -> dict[str, Any]:
        before = build_snapshot(document)
        result: SemanticApplyResult = apply_semantic_operations(document, operations)
        after = build_snapshot(result.document)
        before_findings, _, _, _ = run_checks(before)
        after_findings, _, _, _ = run_checks(after)
        before_errors: dict[str, int] = {}
        after_errors: dict[str, int] = {}
        for finding in before_findings:
            if finding.severity == "error":
                before_errors[finding.category] = before_errors.get(finding.category, 0) + 1
        for finding in after_findings:
            if finding.severity == "error":
                after_errors[finding.category] = after_errors.get(finding.category, 0) + 1
        allow_connectivity_regression = any(
            isinstance(operation, DeleteTraceOperation)
            and operation.allow_connectivity_regression
            for operation in operations
        )
        if (
            after_errors.get("connectivity", 0) > before_errors.get("connectivity", 0)
            and not allow_connectivity_regression
        ):
            raise ConnectivityRegressionError(
                "Semantic preview introduces new connectivity errors",
                details={"before": before_errors, "after": after_errors},
                object_ids=result.changed_ids,
            )
        non_connectivity_categories = (
            set(before_errors) | set(after_errors)
        ) - {"connectivity"}
        regressions = {
            category: {
                "before": before_errors.get(category, 0),
                "after": after_errors.get(category, 0),
            }
            for category in sorted(non_connectivity_categories)
            if after_errors.get(category, 0) > before_errors.get(category, 0)
        }
        if regressions:
            raise DrcRegressionError(
                "Semantic preview introduces new deterministic review errors",
                details={"regressions": regressions},
                object_ids=result.changed_ids,
            )
        svg = render_preview_svg(before, after, result.changed_ids)
        preview_json = render_preview_json(before, after, result.changed_ids)
        preview_json["review_validation"] = {
            "errors_before": before_errors,
            "errors_after": after_errors,
            "allow_connectivity_regression": allow_connectivity_regression,
        }
        diff = unified_xml_diff(before.document.raw_bytes, result.raw_bytes)
        return {
            "svg": svg,
            "json": preview_json,
            "diff": diff,
            "patch_count": result.patch_count,
            "changed_ids": result.changed_ids,
            "validation_before": {
                **before.info.model_dump(),
                "review_errors": before_errors,
            },
            "validation_after_preview": {
                **after.info.model_dump(),
                "review_errors": after_errors,
            },
            "warnings": result.warnings,
            "limitations": (
                ["geometry for components without footprint dimensions is estimated"]
                if before.info.kind == "pcb"
                else []
            ),
        }

    def _load_snapshot_record(self, record: TransactionRecord) -> DipTraceDocument:
        if not record.snapshot_path:
            raise EditError(f"Transaction does not contain a snapshot: {record.txid}")
        snapshot_path = Path(record.snapshot_path)
        if not snapshot_path.exists():
            raise EditError(f"Transaction snapshot is missing: {snapshot_path}")
        return DipTraceDocument.load(snapshot_path, self.settings.max_document_bytes)

    def _session_id_from_working(self, path: Path) -> str | None:
        active = self.sessions.active_metadata()
        if active is None:
            return None
        session_id = str(active["session_id"])
        if self.sessions.working_path(session_id) == path:
            return session_id
        return None

    def _read_source_header(self, path: Path) -> dict[str, str] | None:
        try:
            with path.open("rb") as stream:
                prefix = stream.read(16 * 1024)
        except OSError:
            return None
        match = _SOURCE_TAG.search(prefix)
        if not match:
            return None
        attributes = {
            key.decode("ascii", errors="ignore"): value.decode("utf-8", errors="replace")
            for key, value in _SOURCE_ATTRIBUTE.findall(match.group(1))
        }
        source_type = attributes.get("Type", "")
        if not source_type.startswith("DipTrace-"):
            return None
        return {
            "type": source_type,
            "source_type": source_type,
            "version": attributes.get("Version", ""),
            "units": attributes.get("Units", ""),
        }

    @staticmethod
    def _read_success(
        info: DocumentInfo,
        result: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        limitations: list[str] | None = None,
        resources: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "document": info.model_dump(),
            "result": result,
            "warnings": list(warnings or []),
            "limitations": list(limitations or info.compatibility.get("limitations", [])),
            "resources": list(resources or []),
            "transaction": None,
            "job": None,
        }

    @staticmethod
    def _validate_page(offset: int, limit: int) -> None:
        if offset < 0:
            raise DocumentError("offset cannot be negative")
        if not 1 <= limit <= 500:
            raise DocumentError("limit must be between 1 and 500")
