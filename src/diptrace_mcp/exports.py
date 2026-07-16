from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Literal

from .adapters import DocumentSnapshot
from .bom import extract_bom, group_bom
from .domain import ExportRecord
from .errors import ObjectNotFoundError
from .xml_document import atomic_write_bytes, utc_now

ExportType = Literal["bom", "fabrication_manifest", "assembly_manifest", "si_geometry"]


def _safe_csv(value: object) -> str:
    rendered = str(value)
    if rendered.startswith(("=", "+", "-", "@")):
        return f"'{rendered}"
    return rendered


def _csv_bytes(rows: list[dict[str, object]], fields: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _safe_csv(row.get(field, "")) for field in fields})
    return output.getvalue().encode("utf-8")


class ExportStore:
    def __init__(self, state_dir: Path, max_artifact_bytes: int):
        self.root = state_dir / "exports"
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_artifact_bytes = max_artifact_bytes

    def _directory(self, export_id: str) -> Path:
        if not export_id.startswith("export_") or len(export_id) != 39:
            raise ObjectNotFoundError(f"Invalid export id: {export_id}")
        return self.root / export_id

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
        export_id = f"export_{uuid.uuid4().hex}"
        directory = self._directory(export_id)
        directory.mkdir(parents=True, exist_ok=False)
        artifact_resources: dict[str, str] = {}
        for name, payload in artifacts.items():
            if Path(name).name != name or not name:
                raise ValueError(f"Invalid export artifact name: {name!r}")
            if len(payload) > self.max_artifact_bytes:
                raise ValueError(f"Export artifact exceeds size limit: {name}")
            path = directory / name
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
        atomic_write_bytes(
            self._record_path(export_id),
            json.dumps(record.model_dump(mode="json"), indent=2).encode("utf-8"),
        )
        return record

    def read(self, export_id: str) -> ExportRecord:
        path = self._record_path(export_id)
        if not path.is_file():
            raise ObjectNotFoundError(f"Export was not found: {export_id}")
        return ExportRecord.model_validate_json(path.read_bytes())

    def artifact(self, export_id: str, name: str) -> bytes:
        record = self.read(export_id)
        if name not in record.artifacts or Path(name).name != name:
            raise ObjectNotFoundError(
                f"Export artifact was not found: {export_id}/{name}"
            )
        path = self._directory(export_id) / name
        payload = path.read_bytes()
        if len(payload) > self.max_artifact_bytes:
            raise ValueError(f"Export artifact exceeds read limit: {name}")
        return payload

    def list(self) -> list[ExportRecord]:
        records: list[ExportRecord] = []
        for path in sorted(self.root.glob("export_*/record.json"), reverse=True):
            records.append(ExportRecord.model_validate_json(path.read_bytes()))
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


def placement_csv(snapshot: DocumentSnapshot) -> bytes:
    if snapshot.board is None:
        return b""
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
    manifest: dict[str, object] = {
        "kind": export_type,
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
            "unrouted_net_count": sum(
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
        ],
        "not_generated": ["gerber", "nc_drill", "odb++", "ipc-2581", "final_pours"],
        "limitations": limitations,
    }
    artifacts = {
        "manifest.json": json.dumps(manifest, indent=2).encode("utf-8"),
        "bom.csv": bom_csv(snapshot, include_dnp=include_dnp),
        "placement.csv": placement_csv(snapshot),
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
    return store.create(snapshot, export_type, artifacts, manifest, limitations)


def export_resources(record: ExportRecord) -> list[str]:
    return [
        f"diptrace://export/{record.export_id}/{name}"
        for name in sorted(record.artifacts)
    ]
