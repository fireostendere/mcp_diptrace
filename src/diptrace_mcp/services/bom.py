"""BOM and component/library metadata read services."""

from __future__ import annotations

from typing import Any

from ..bom import compare_bom_records, extract_bom, group_bom, review_bom
from ..domain import LibraryComponent, LibraryPattern
from ..errors import DocumentError
from ..library_adapters import (
    get_library_item,
    get_library_model,
    query_library_items,
    validate_library,
)
from .context import DocumentGateway, ServiceContext, read_success, validate_page


class BomService:
    """Implementation for BOM, component metadata, and library reads."""

    def __init__(self, context: ServiceContext, gateway: DocumentGateway):
        self.context = context
        self.gateway = gateway

    def library_model(self, path: str) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        model = get_library_model(document)
        return read_success(snapshot.info, model.model_dump(), warnings=model.warnings)

    def query_library_items(
        self,
        path: str,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        validate_page(offset, limit)
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        model = get_library_model(document)
        items = query_library_items(model, query)
        return read_success(
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

    def _get_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        if stable_id_value is None and name is None:
            raise DocumentError("A stable_id or name is required", code="scope_required")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        model = get_library_model(document)
        item = get_library_item(
            model,
            stable_id_value=stable_id_value,
            name=name,
            kind=kind,
        )
        return read_success(snapshot.info, item.model_dump(), warnings=model.warnings)

    def _validate_library_item(
        self,
        path: str,
        kind: str,
        stable_id_value: str | None,
        name: str | None,
    ) -> dict[str, Any]:
        if stable_id_value is None and name is None:
            raise DocumentError("A stable_id or name is required", code="scope_required")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
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
        return read_success(
            snapshot.info,
            {
                "item": item.model_dump(),
                "valid": not any(finding.severity == "error" for finding in findings),
                "finding_count": len(findings),
                "findings": [finding.model_dump() for finding in findings],
            },
            warnings=model.warnings,
        )

    def get_bom(
        self,
        path: str | None = None,
        *,
        grouped: bool = False,
        include_dnp: bool = True,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        records = extract_bom(snapshot)
        if grouped:
            records = group_bom(records, include_dnp=include_dnp)
        elif not include_dnp:
            records = [record for record in records if not record.dnp]
        return read_success(
            snapshot.info,
            {
                "record_count": len(records),
                "grouped": grouped,
                "include_dnp": include_dnp,
                "items": [record.model_dump(mode="json") for record in records],
            },
        )

    def review_bom(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        records = extract_bom(snapshot)
        result = review_bom(records)
        result["items"] = [record.model_dump(mode="json") for record in records]
        return read_success(snapshot.info, result)

    def compare_bom_to_design(
        self,
        external_records: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        if len(external_records) > 100_000:
            raise DocumentError("At most 100000 external BOM rows are accepted")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = compare_bom_records(extract_bom(snapshot), external_records)
        return read_success(snapshot.info, result)

    def find_missing_component_fields(
        self,
        required_fields: list[str],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        if not required_fields or len(required_fields) > 100:
            raise DocumentError("required_fields must contain between 1 and 100 names")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
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
        return read_success(
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

    def validate_value_pattern_consistency(self, path: str | None = None) -> dict[str, Any]:
        response = self.review_bom(path)
        response["result"]["findings"] = [
            item
            for item in response["result"]["findings"]
            if item["code"] in {"bom.mpn_inconsistent", "bom.multipart_inconsistent"}
        ]
        response["result"]["valid"] = not response["result"]["findings"]
        return response

