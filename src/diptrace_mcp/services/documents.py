"""Read-only document models, queries, resources, and XML fragments."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from .. import inspector
from ..adapters import get_board_model, get_schematic_model
from ..connectivity import build_connectivity_graph
from ..domain import BOARD_MODEL_COLLECTION_SECTIONS, BoardModelSection, QueryRequest
from ..errors import DocumentError
from ..library_adapters import get_library_model
from .context import (
    DocumentGateway,
    ServiceContext,
    bounded_text,
    json_size,
    read_success,
    validate_page,
)

BOARD_MODEL_RESPONSE_BYTE_LIMIT = 256 * 1024
BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT = 32 * 1024


def _bounded_board_item(
    item: Any,
    *,
    item_index: int,
    full_model_resource: str,
) -> tuple[Any, bool]:
    rendered = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
    full_item_bytes = json_size(rendered)
    if full_item_bytes <= BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT:
        return rendered, False

    summary: dict[str, Any] = {}
    if isinstance(rendered, dict):
        for key in (
            "stable_id",
            "kind",
            "id",
            "xml_id",
            "index",
            "name",
            "label",
            "refdes",
            "value",
            "layer",
            "side",
        ):
            scalar = rendered.get(key)
            if isinstance(scalar, str):
                summary[key], _ = bounded_text(scalar, 512)
            elif key in rendered and (
                scalar is None or isinstance(scalar, (bool, int, float))
            ):
                summary[key] = scalar
    elif isinstance(rendered, str):
        summary["value_prefix"], _ = bounded_text(rendered, 1_000)

    payload_metadata: dict[str, Any] = {
        "detail": "summary",
        "item_index": item_index,
        "full_item_bytes": full_item_bytes,
        "detail_byte_limit": BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT,
        "full_model_resource": full_model_resource,
        "reason": "nested_item_exceeds_computational_payload_cap",
    }
    if isinstance(rendered, dict):
        omitted_fields = [key for key in rendered if key not in summary]
        payload_metadata["omitted_field_count"] = len(omitted_fields)
        payload_metadata["omitted_fields"] = [
            bounded_text(str(key), 128)[0] for key in omitted_fields[:32]
        ]
        payload_metadata["omitted_fields_truncated"] = len(omitted_fields) > 32
    elif isinstance(rendered, str):
        payload_metadata["omitted_character_count"] = max(
            0,
            len(rendered) - len(summary.get("value_prefix", "")),
        )
    summary["_payload"] = payload_metadata
    return summary, True


class DocumentService:
    """Implementation for the Facade's read-only document methods."""

    def __init__(self, context: ServiceContext, gateway: DocumentGateway):
        self.context = context
        self.gateway = gateway

    def board_model(
        self,
        path: str | None = None,
        *,
        section: BoardModelSection = "summary",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        validate_page(offset, limit)
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        info = snapshot.info
        model = snapshot.board
        if model is None:
            raise DocumentError("PCB model is only available for PCB documents")
        resource_uri = f"diptrace://document/{info.document_id}/board-model"
        section_counts = {
            name: len(getattr(model, name)) for name in BOARD_MODEL_COLLECTION_SECTIONS
        }
        limitations = list(info.compatibility.get("limitations", []))
        if model.warnings and section != "warnings":
            limitations.append(
                "Board-model warnings are not duplicated inline; page section='warnings' "
                "or read the full-model resource."
            )
        if section == "summary":
            result: dict[str, Any] = {
                "contract_version": 1,
                "section": "summary",
                "available_sections": ["summary", *BOARD_MODEL_COLLECTION_SECTIONS],
                "section_counts": section_counts,
                "outline_available": model.outline is not None,
                "rules_available": bool(model.rules),
                "stackup_completeness": model.stackup.completeness,
                "response_byte_limit": BOARD_MODEL_RESPONSE_BYTE_LIMIT,
                "item_detail_byte_limit": BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT,
                "full_model_resource": resource_uri,
            }
            response = read_success(
                info,
                result,
                resources=[resource_uri],
                limitations=limitations,
            )
            for _ in range(4):
                serialized_size = json_size(response)
                if result.get("serialized_response_bytes") == serialized_size:
                    break
                result["serialized_response_bytes"] = serialized_size
            if json_size(response) > BOARD_MODEL_RESPONSE_BYTE_LIMIT:
                raise DocumentError("Board-model summary exceeds its payload cap")
            return response
        if section not in BOARD_MODEL_COLLECTION_SECTIONS:
            raise DocumentError(f"Unknown board-model section: {section}")

        section_items = getattr(model, section)
        total_count = len(section_items)
        requested_items = section_items[offset : offset + limit]
        rendered_items: list[Any] = []
        summarized_flags: list[bool] = []
        summarized_count = 0
        consumed_count = 0

        def build_response(*, byte_limited: bool) -> dict[str, Any]:
            next_offset = offset + consumed_count
            has_more = next_offset < total_count
            result = {
                "contract_version": 1,
                "section": section,
                "page": {
                    "offset": offset,
                    "limit": limit,
                    "returned_count": consumed_count,
                    "total_count": total_count,
                    "has_more": has_more,
                    "next_offset": next_offset if has_more else None,
                    "byte_limited": byte_limited,
                    "detail_limited": summarized_count > 0,
                    "summarized_item_count": summarized_count,
                    "response_byte_limit": BOARD_MODEL_RESPONSE_BYTE_LIMIT,
                    "item_detail_byte_limit": BOARD_MODEL_ITEM_DETAIL_BYTE_LIMIT,
                    "serialized_response_bytes": 0,
                },
                "items": rendered_items,
                "full_model_resource": resource_uri,
            }
            response = read_success(
                info,
                result,
                resources=[resource_uri],
                limitations=limitations,
            )
            page = response["result"]["page"]
            for _ in range(4):
                serialized_size = json_size(response)
                if page["serialized_response_bytes"] == serialized_size:
                    break
                page["serialized_response_bytes"] = serialized_size
            return response

        response = build_response(byte_limited=False)
        for relative_index, item in enumerate(requested_items):
            rendered, summarized = _bounded_board_item(
                item,
                item_index=offset + relative_index,
                full_model_resource=resource_uri,
            )
            rendered_items.append(rendered)
            summarized_flags.append(summarized)
            consumed_count += 1
            summarized_count += int(summarized)
            candidate = build_response(byte_limited=False)
            if json_size(candidate) > BOARD_MODEL_RESPONSE_BYTE_LIMIT:
                rendered_items.pop()
                summarized_flags.pop()
                consumed_count -= 1
                summarized_count -= int(summarized)
                response = build_response(byte_limited=True)
                break
            response = candidate
        else:
            response = build_response(byte_limited=False)

        while json_size(response) > BOARD_MODEL_RESPONSE_BYTE_LIMIT and rendered_items:
            rendered_items.pop()
            removed_was_summarized = summarized_flags.pop()
            consumed_count -= 1
            if removed_was_summarized:
                summarized_count -= 1
            response = build_response(byte_limited=True)
        if json_size(response) > BOARD_MODEL_RESPONSE_BYTE_LIMIT:
            raise DocumentError("Board-model response metadata exceeds its payload cap")
        return response

    def schematic_model(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        info = snapshot.info
        model = snapshot.schematic
        if model is None:
            raise DocumentError("Schematic model is only available for schematic documents")
        return read_success(
            info,
            model.model_dump(),
            resources=[f"diptrace://document/{info.document_id}/schematic-model"],
            warnings=model.warnings,
        )

    def query_objects(
        self,
        path: str | None = None,
        selector: dict[str, Any] | None = None,
        offset: int = 0,
        limit: int = 100,
        sort_by: str = "stable_id",
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        request = QueryRequest.model_validate(
            {
                "selector": selector or {},
                "offset": offset,
                "limit": limit,
                "sort_by": sort_by,
            }
        )
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        info = snapshot.info
        result = snapshot.query(request)
        return read_success(info, result.model_dump())

    def get_object(self, stable_id_value: str, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        info = snapshot.info
        record = snapshot.get_object(stable_id_value)
        result = record.model_dump()
        element = snapshot.elements.get(stable_id_value)
        result["source_xml"] = (
            ET.tostring(element, encoding="unicode") if element is not None else None
        )
        return read_success(info, result)

    def get_connectivity_graph(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        graph = build_connectivity_graph(snapshot)
        return read_success(
            snapshot.info,
            graph.model_dump(mode="json"),
            warnings=graph.warnings,
            resources=[f"diptrace://document/{snapshot.info.document_id}/connectivity"],
        )

    def document_resource(self, document_id: str, resource: str) -> str:
        document, target = self.gateway.load_document_id(document_id)
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
            snapshot = self.context.model_cache.get(document, live_session=target.is_live)
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
        document, target = self.gateway.load(path)
        return inspector.summarize(document, live_session=target.is_live)

    def components(
        self,
        path: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        validate_page(offset, limit)
        document, target = self.gateway.load(path)
        return {
            **inspector.components(document, query, offset, limit, live_session=target.is_live),
            "live_session": target.is_live,
        }

    def component(self, refdes: str, path: str | None = None) -> dict[str, Any]:
        if not refdes.strip():
            raise DocumentError("refdes cannot be empty")
        document, target = self.gateway.load(path)
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
        validate_page(offset, limit)
        document, target = self.gateway.load(path)
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
        document, target = self.gateway.load(path)
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
        document, target = self.gateway.load(path)
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

