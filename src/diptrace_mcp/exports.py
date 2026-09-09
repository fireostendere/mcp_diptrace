from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from .adapters import DocumentSnapshot
from .bom import extract_bom, group_bom
from .connectivity import build_connectivity_graph
from .domain import ExportRecord
from .errors import ObjectNotFoundError
from .record_ids import (
    InvalidRecordId,
    InvalidRecordPath,
    is_link_like,
    iter_valid_record_files,
    require_confined_record_artifact,
    require_confined_record_directory,
    require_confined_record_file,
    require_record_id,
)
from .record_store import RecordStore
from .release_readiness import run_release_readiness
from .retention import (
    RetentionCandidate,
    RetentionPolicy,
    RetentionReport,
    parse_retention_timestamp,
    prune_terminal_records,
    system_clock,
)
from .xml_document import atomic_write_bytes, utc_now

ExportType = Literal["bom", "fabrication_manifest", "assembly_manifest", "si_geometry"]


def _safe_csv(value: object) -> str:
    # Coordinates are numbers, not untrusted spreadsheet expressions. Escaping a
    # negative float corrupts machine-readable placement data.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("CSV numeric values must be finite")
        return str(value)
    rendered = str(value)
    if rendered.lstrip().startswith(("=", "+", "-", "@")) or rendered.startswith(
        ("\t", "\r", "\n")
    ):
        return f"'{rendered}"
    return rendered


def _csv_bytes(rows: list[dict[str, object]], fields: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _safe_csv(row.get(field, "")) for field in fields})
    return output.getvalue().encode("utf-8")


class ExportStore(RecordStore):
    def __init__(
        self,
        state_dir: Path,
        max_artifact_bytes: int,
        *,
        retention: RetentionPolicy | None = None,
        clock: Callable[[], datetime] = system_clock,
    ):
        self.state_dir = state_dir
        self.root = state_dir / "exports"
        self.max_artifact_bytes = max_artifact_bytes
        self.retention = retention or RetentionPolicy()
        self.clock = clock
        self._initialize_record_store(
            state_dir=state_dir,
            store_root=self.root,
        )
        self.last_retention_report = self._initial_retention_report()

    def _prune_retention(self) -> RetentionReport:
        candidates: list[RetentionCandidate] = []
        paths = sorted(self.root.glob("export_*/record.json"))
        for path_export_id, path in iter_valid_record_files(
            self.root,
            paths,
            kind="export",
            record_filename="record.json",
        ):
            try:
                record = ExportRecord.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                continue
            timestamp = parse_retention_timestamp(record.created_at)
            if (
                record.export_id != path_export_id
                or timestamp is None
                or not self._artifacts_complete(record)
            ):
                continue
            candidates.append(
                RetentionCandidate(
                    identifier=record.export_id,
                    path=path.parent,
                    timestamp=timestamp,
                )
            )
        return prune_terminal_records(
            state_root=self.state_dir,
            store_root=self.root,
            candidates=candidates,
            policy=self.retention,
            clock=self.clock,
        )

    def _artifacts_complete(self, record: ExportRecord) -> bool:
        for name, resource in record.artifacts.items():
            if (
                Path(name).name != name
                or resource != f"diptrace://export/{record.export_id}/{name}"
            ):
                return False
            try:
                require_confined_record_artifact(
                    self.root,
                    record.export_id,
                    name,
                    kind="export",
                )
            except (
                InvalidRecordId,
                InvalidRecordPath,
                FileNotFoundError,
            ):
                return False
        return True

    def _directory(self, export_id: str) -> Path:
        try:
            validated = require_record_id(export_id, "export")
        except InvalidRecordId:
            raise ObjectNotFoundError("Invalid export id") from None
        return self.root / validated

    def _record_path(self, export_id: str) -> Path:
        return self._directory(export_id) / "record.json"

    def create(
        self,
        snapshot: DocumentSnapshot,
        export_type: ExportType,
        artifacts: dict[str, bytes],
        manifest: dict[str, object],
        limitations: list[str],
    ) -> ExportRecord:
        self._require_safe_root()
        export_id = f"export_{uuid.uuid4().hex}"
        directory = self._directory(export_id)
        directory.mkdir(parents=True, exist_ok=False)
        try:
            require_confined_record_directory(
                self.root,
                export_id,
                kind="export",
            )
        except (InvalidRecordId, InvalidRecordPath) as exc:
            raise ValueError("Export directory is redirected or outside its store") from exc
        artifact_resources: dict[str, str] = {}
        for name, payload in artifacts.items():
            self._require_safe_root()
            if Path(name).name != name or not name:
                raise ValueError(f"Invalid export artifact name: {name!r}")
            if len(payload) > self.max_artifact_bytes:
                raise ValueError(f"Export artifact exceeds size limit: {name}")
            try:
                directory = require_confined_record_directory(
                    self.root,
                    export_id,
                    kind="export",
                )
            except (InvalidRecordId, InvalidRecordPath) as exc:
                raise ValueError(
                    "Export directory is redirected or outside its store"
                ) from exc
            path = directory / name
            if is_link_like(path):
                raise ValueError(f"Export artifact path is redirected: {name}")
            atomic_write_bytes(path, payload)
            artifact_resources[name] = f"diptrace://export/{export_id}/{name}"
        record = ExportRecord(
            export_id=export_id,
            export_type=export_type,
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            created_at=utc_now(),
            artifacts=artifact_resources,
            manifest=dict(manifest),
            limitations=limitations,
        )
        self._require_safe_root()
        try:
            directory = require_confined_record_directory(
                self.root,
                export_id,
                kind="export",
            )
        except (InvalidRecordId, InvalidRecordPath) as exc:
            raise ValueError("Export directory is redirected or outside its store") from exc
        record_path = directory / "record.json"
        if is_link_like(record_path):
            raise ValueError("Export record path is redirected")
        self._write_store_json(
            record_path,
            record.model_dump(mode="json"),
            ensure_ascii=True,
        )
        return record

    def read(self, export_id: str) -> ExportRecord:
        try:
            path = require_confined_record_file(
                self.root,
                export_id,
                kind="export",
                record_filename="record.json",
            )
            record = ExportRecord.model_validate_json(path.read_bytes())
        except InvalidRecordId:
            raise ObjectNotFoundError("Invalid export id") from None
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(f"Export was not found: {export_id}") from exc
        except InvalidRecordPath as exc:
            raise ObjectNotFoundError(
                "Export state path is redirected or outside its store"
            ) from exc
        except (OSError, ValueError) as exc:
            raise ObjectNotFoundError("Export state is corrupt") from exc
        if record.export_id != export_id:
            raise ObjectNotFoundError(
                "Export state id does not match the requested export"
            )
        return record

    def artifact(self, export_id: str, name: str) -> bytes:
        record = self.read(export_id)
        if name not in record.artifacts or Path(name).name != name:
            raise ObjectNotFoundError(
                f"Export artifact was not found: {export_id}/{name}"
            )
        try:
            path = require_confined_record_artifact(
                self.root,
                export_id,
                name,
                kind="export",
            )
            with path.open("rb") as stream:
                payload = stream.read(self.max_artifact_bytes + 1)
        except (
            InvalidRecordId,
            InvalidRecordPath,
            OSError,
        ) as exc:
            raise ObjectNotFoundError(
                f"Export artifact was not found: {export_id}/{name}"
            ) from exc
        if len(payload) > self.max_artifact_bytes:
            raise ValueError(f"Export artifact exceeds read limit: {name}")
        if record.manifest.get("schema_version") == 2:
            if name == "manifest.json":
                if json.loads(payload) != record.manifest:
                    raise ValueError("Export manifest integrity check failed")
            else:
                inventory = record.manifest.get("artifact_integrity", {})
                expected = inventory.get(name) if isinstance(inventory, dict) else None
                actual = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
                if expected != actual:
                    raise ValueError(f"Export artifact integrity check failed: {name}")
        return payload

    def list(self) -> list[ExportRecord]:
        records: list[ExportRecord] = []
        paths = sorted(self.root.glob("export_*/record.json"), reverse=True)
        for path_export_id, path in iter_valid_record_files(
            self.root,
            paths,
            kind="export",
            record_filename="record.json",
        ):
            try:
                record = ExportRecord.model_validate_json(path.read_bytes())
            except (OSError, ValueError):
                continue
            if record.export_id != path_export_id:
                continue
            records.append(record)
        return records


def bom_csv(snapshot: DocumentSnapshot, *, include_dnp: bool = True) -> bytes:
    records = group_bom(extract_bom(snapshot), include_dnp=include_dnp)
    rows: list[dict[str, object]] = [
        {
            "Quantity": record.quantity,
            "RefDes": ",".join(record.refdes),
            "Value": record.value,
            "Pattern": record.pattern,
            "Manufacturer": record.manufacturer,
            "MPN": record.mpn,
            "DNP": "Y" if record.dnp else "N",
            "Variant": record.variant,
        }
        for record in records
    ]
    return _csv_bytes(
        rows,
        [
            "Quantity",
            "RefDes",
            "Value",
            "Pattern",
            "Manufacturer",
            "MPN",
            "DNP",
            "Variant",
        ],
    )


def placement_csv(snapshot: DocumentSnapshot, *, include_dnp: bool = True) -> bytes:
    if snapshot.board is None:
        return b""
    excluded = {
        object_id
        for record in extract_bom(snapshot)
        if record.dnp and not include_dnp
        for object_id in record.source_object_ids
    }
    rows = [
        {
            "RefDes": item.refdes or "",
            "Value": item.value or "",
            "Pattern": item.attributes.get("pattern_style", ""),
            "X_mm": item.position["x"] if item.position else "",
            "Y_mm": item.position["y"] if item.position else "",
            "Rotation_deg": item.rotation_deg,
            "Side": item.side or "",
            "Locked": "Y" if item.locked else "N",
            "GeometryConfidence": item.confidence,
        }
        for item in snapshot.board.components
        if item.stable_id not in excluded
    ]
    return _csv_bytes(
        rows,
        [
            "RefDes",
            "Value",
            "Pattern",
            "X_mm",
            "Y_mm",
            "Rotation_deg",
            "Side",
            "Locked",
            "GeometryConfidence",
        ],
    )


def create_bom_export(
    store: ExportStore, snapshot: DocumentSnapshot, *, include_dnp: bool
) -> ExportRecord:
    limitations = [
        "This is a generic UTF-8 CSV, not a vendor-specific procurement format.",
        "No internet sourcing or lifecycle lookup was performed.",
    ]
    manifest = {
        "kind": "bom",
        "document_id": snapshot.info.document_id,
        "source_sha256": snapshot.info.sha256,
        "include_dnp": include_dnp,
    }
    return store.create(
        snapshot,
        "bom",
        {
            "bom.csv": bom_csv(snapshot, include_dnp=include_dnp),
            "manifest.json": json.dumps(manifest, indent=2).encode("utf-8"),
        },
        manifest,
        limitations,
    )


def create_release_manifest(
    store: ExportStore,
    snapshot: DocumentSnapshot,
    *,
    export_type: Literal["fabrication_manifest", "assembly_manifest"],
    include_dnp: bool,
) -> ExportRecord:
    if snapshot.board is None:
        raise ValueError("Release manifests require a PCB document")
    limitations = [
        "Gerber, NC drill, ODB++, IPC-2581 and authoritative copper refill are not generated.",
        "Placement CSV is generic and must be mapped to the assembler's coordinate convention.",
        "The bundle is a release-review manifest, not fabrication-ready artwork.",
    ]
    bom = extract_bom(snapshot)
    included = [record for record in bom if include_dnp or not record.dnp]
    readiness = run_release_readiness(snapshot)
    graph = build_connectivity_graph(snapshot)
    preflight = {
        "source_sha256": snapshot.info.sha256,
        "status": (
            "blocked"
            if readiness["status"] == "blocked" or graph.unrouted_connections
            else "manual_review_required"
        ),
        "native_acceptance": "not_run",
        "offline_drc": "not_run",
        "readiness": readiness,
        "explicit_unrouted_connections": graph.unrouted_connections,
        "manual_gates": readiness["manual_gates"],
        "limitations": [
            *graph.warnings,
            "No ratlines does not prove copper continuity or native DRC acceptance.",
            "Run the registered PCB review separately for geometric/clearance checks.",
        ],
    }
    manifest: dict[str, object] = {
        "schema_version": 2,
        "kind": export_type,
        "include_dnp": include_dnp,
        "population": {
            "total_components": len(bom),
            "included_components": len(included),
            "excluded_refdes": sorted(
                refdes for record in bom if record.dnp and not include_dnp
                for refdes in record.refdes
            ),
        },
        "placement_convention": {
            "units": "mm",
            "origin": "exported_document_origin",
            "rotation_units": "degrees",
            "bottom_side_transform": "none; assembler convention requires review",
        },
        "preflight_status": preflight["status"],
        "document_id": snapshot.info.document_id,
        "source_type": snapshot.info.source_type,
        "source_version": snapshot.info.version,
        "source_sha256": snapshot.info.sha256,
        "created_at": utc_now(),
        "board": {
            "outline": snapshot.board.outline,
            "layer_count": len(snapshot.board.layers),
            "component_count": len(snapshot.board.components),
            "net_count": len(snapshot.board.nets),
            "nets_without_traces_count": sum(
                int(net.attributes.get("endpoint_count", 0)) > 1
                and int(net.attributes.get("trace_count", 0)) == 0
                for net in snapshot.board.nets
            ),
        },
        "stackup": {
            "name": snapshot.board.stackup.name,
            "completeness": snapshot.board.stackup.completeness,
            "missing_fields": snapshot.board.stackup.missing_fields,
        },
        "generated_artifacts": [
            "manifest.json",
            "bom.csv",
            "placement.csv",
            "stackup.json",
            "board-geometry.json",
            "preflight.json",
        ],
        "not_generated": ["gerber", "nc_drill", "odb++", "ipc-2581", "final_pours"],
        "limitations": limitations,
    }
    artifacts = {
        "bom.csv": bom_csv(snapshot, include_dnp=include_dnp),
        "placement.csv": placement_csv(snapshot, include_dnp=include_dnp),
        "preflight.json": json.dumps(preflight, indent=2).encode("utf-8"),
        "stackup.json": json.dumps(
            snapshot.board.stackup.model_dump(mode="json"), indent=2
        ).encode("utf-8"),
        "board-geometry.json": json.dumps(
            {
                "coordinate_units": "mm",
                "outline": snapshot.board.outline,
                "layers": snapshot.board.layers,
                "copper_pours": [
                    item.model_dump(mode="json") for item in snapshot.board.copper_pours
                ],
            },
            indent=2,
        ).encode("utf-8"),
    }
    # The manifest cannot hash itself; record.json stores the same manifest.
    # These digests establish byte identity, not a signature or engineering approval.
    manifest["artifact_integrity"] = {
        name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        for name, payload in sorted(artifacts.items())
    }
    artifacts["manifest.json"] = json.dumps(manifest, indent=2).encode("utf-8")
    return store.create(snapshot, export_type, artifacts, manifest, limitations)


def export_resources(record: ExportRecord) -> list[str]:
    return [
        f"diptrace://export/{record.export_id}/{name}"
        for name in sorted(record.artifacts)
    ]
