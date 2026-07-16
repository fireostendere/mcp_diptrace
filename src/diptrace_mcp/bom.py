from __future__ import annotations

from collections import defaultdict
from typing import Any

from .adapters import DocumentSnapshot, stable_id
from .domain import BomRecord, ObjectRecord
from .errors import DocumentError

_MPN_KEYS = ("mpn", "manufacturer part number", "manufacturer_part_number")
_MANUFACTURER_KEYS = ("manufacturer", "mfr")
_VARIANT_KEYS = ("variant", "assembly variant", "build variant")


def _fields(item: ObjectRecord) -> dict[str, str]:
    raw = item.attributes.get("additional_fields", {})
    return {str(key): str(value).strip() for key, value in raw.items()}


def _lookup(fields: dict[str, str], keys: tuple[str, ...]) -> str:
    folded = {key.casefold(): value for key, value in fields.items()}
    return next((folded[key] for key in keys if folded.get(key)), "")


def _dnp(fields: dict[str, str]) -> bool:
    folded = {key.casefold(): value.casefold() for key, value in fields.items()}
    return folded.get("dnp", "") in {"y", "yes", "true", "1", "dnp"} or folded.get(
        "populate", ""
    ) in {"n", "no", "false", "0"}


def _item_record(item: ObjectRecord, source_type: str) -> BomRecord:
    fields = _fields(item)
    pattern = str(
        item.attributes.get("pattern_style")
        or item.attributes.get("component_style")
        or ""
    )
    manufacturer = _lookup(fields, _MANUFACTURER_KEYS) or str(
        item.attributes.get("manufacturer", "")
    )
    mpn = _lookup(fields, _MPN_KEYS)
    variant = _lookup(fields, _VARIANT_KEYS)
    refdes = item.refdes or item.label or item.stable_id
    return BomRecord(
        stable_id=stable_id("bom-record", source_type, refdes),
        refdes=[refdes],
        quantity=1,
        value=item.value or "",
        pattern=pattern,
        manufacturer=manufacturer,
        mpn=mpn,
        dnp=_dnp(fields),
        variant=variant,
        source_object_ids=[item.stable_id],
        fields=fields,
    )


def extract_bom(snapshot: DocumentSnapshot) -> list[BomRecord]:
    if snapshot.board is not None:
        return [
            _item_record(item, snapshot.info.source_type)
            for item in snapshot.board.components
        ]
    if snapshot.schematic is None:
        raise DocumentError("BOM extraction requires a PCB or schematic document")
    by_refdes: dict[str, list[ObjectRecord]] = defaultdict(list)
    for part in snapshot.schematic.parts:
        by_refdes[(part.refdes or part.stable_id).casefold()].append(part)
    records: list[BomRecord] = []
    for parts in by_refdes.values():
        record = _item_record(parts[0], snapshot.info.source_type)
        record.source_object_ids = [part.stable_id for part in parts]
        values = {part.value or "" for part in parts}
        patterns = {
            str(part.attributes.get("component_style", "")) for part in parts
        }
        if len(values) > 1:
            record.warnings.append("Multi-part schematic units have inconsistent values.")
        if len(patterns) > 1:
            record.warnings.append("Multi-part schematic units have inconsistent patterns.")
        records.append(record)
    return records


def group_bom(records: list[BomRecord], *, include_dnp: bool = True) -> list[BomRecord]:
    groups: dict[tuple[str, ...], list[BomRecord]] = defaultdict(list)
    for record in records:
        if record.dnp and not include_dnp:
            continue
        key = (
            record.mpn.casefold(),
            record.manufacturer.casefold(),
            record.value.casefold(),
            record.pattern.casefold(),
            str(record.dnp),
            record.variant.casefold(),
        )
        groups[key].append(record)
    result: list[BomRecord] = []
    for group_key, items in sorted(groups.items()):
        first = items[0]
        refs = sorted(
            (refdes for item in items for refdes in item.refdes),
            key=lambda value: value.casefold(),
        )
        result.append(
            BomRecord(
                stable_id=stable_id("bom-group", *group_key),
                refdes=refs,
                quantity=len(refs),
                value=first.value,
                pattern=first.pattern,
                manufacturer=first.manufacturer,
                mpn=first.mpn,
                dnp=first.dnp,
                variant=first.variant,
                source_object_ids=[
                    object_id for item in items for object_id in item.source_object_ids
                ],
                fields=first.fields,
                warnings=[warning for item in items for warning in item.warnings],
            )
        )
    return result


def review_bom(records: list[BomRecord]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for record in records:
        if record.dnp:
            continue
        missing = [
            field
            for field, value in (
                ("value", record.value),
                ("pattern", record.pattern),
                ("manufacturer", record.manufacturer),
                ("mpn", record.mpn),
            )
            if not value
        ]
        if missing:
            findings.append(
                {
                    "code": "bom.missing_fields",
                    "severity": "warning",
                    "refdes": record.refdes,
                    "message": f"Missing fields: {', '.join(missing)}.",
                    "fields": missing,
                }
            )
        for warning in record.warnings:
            findings.append(
                {
                    "code": "bom.multipart_inconsistent",
                    "severity": "error",
                    "refdes": record.refdes,
                    "message": warning,
                }
            )
    by_mpn: dict[str, list[BomRecord]] = defaultdict(list)
    for record in records:
        if record.mpn:
            by_mpn[record.mpn.casefold()].append(record)
    for mpn, items in by_mpn.items():
        identities = {
            (item.manufacturer.casefold(), item.value.casefold(), item.pattern.casefold())
            for item in items
        }
        if len(identities) > 1:
            findings.append(
                {
                    "code": "bom.mpn_inconsistent",
                    "severity": "error",
                    "refdes": [ref for item in items for ref in item.refdes],
                    "message": f"MPN {mpn!r} maps to inconsistent value/pattern metadata.",
                }
            )
    severity_counts = {
        severity: sum(item["severity"] == severity for item in findings)
        for severity in ("error", "warning", "info")
    }
    return {
        "valid": severity_counts["error"] == 0,
        "record_count": len(records),
        "finding_count": len(findings),
        "by_severity": severity_counts,
        "findings": findings,
    }


def compare_bom_records(
    design: list[BomRecord], external: list[dict[str, Any]]
) -> dict[str, Any]:
    design_by_ref = {
        refdes.casefold(): record for record in design for refdes in record.refdes
    }
    external_by_ref: dict[str, dict[str, Any]] = {}
    for row in external:
        refs = row.get("refdes", [])
        if isinstance(refs, str):
            refs = [item.strip() for item in refs.split(",") if item.strip()]
        for refdes in refs:
            external_by_ref[str(refdes).casefold()] = row
    missing_external = sorted(set(design_by_ref) - set(external_by_ref))
    extra_external = sorted(set(external_by_ref) - set(design_by_ref))
    mismatches: list[dict[str, Any]] = []
    for refdes in sorted(set(design_by_ref) & set(external_by_ref)):
        design_item = design_by_ref[refdes]
        row = external_by_ref[refdes]
        for field in ("value", "pattern", "manufacturer", "mpn"):
            external_value = str(row.get(field, "")).strip()
            design_value = str(getattr(design_item, field)).strip()
            if external_value and external_value.casefold() != design_value.casefold():
                mismatches.append(
                    {
                        "refdes": refdes,
                        "field": field,
                        "design": design_value,
                        "external": external_value,
                    }
                )
    return {
        "matches": not missing_external and not extra_external and not mismatches,
        "missing_external": missing_external,
        "extra_external": extra_external,
        "mismatches": mismatches,
    }
