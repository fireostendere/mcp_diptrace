from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from pydantic import BaseModel, ConfigDict

from .adapters import component as _component
from .adapters import components as _components
from .adapters import design_rules as _design_rules
from .adapters import get_board_model as _get_board_model
from .adapters import get_document_info as _get_document_info
from .adapters import get_object as _get_object
from .adapters import get_schematic_model as _get_schematic_model
from .adapters import nets as _nets
from .adapters import query_objects as _query_objects
from .adapters import summarize as _summarize
from .capabilities import get_capabilities as build_capabilities
from .domain import QueryRequest
from .errors import DocumentError
from .geometry import to_mm
from .numeric_inputs import require_finite_number
from .xml_document import DipTraceDocument


class BoardProjectSettings(BaseModel):
    """Board-wide defaults normalized to millimetres without inventing omissions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    courtyard_line_width_mm: float | None = None
    solder_mask_swell_mm: float | None = None
    paste_mask_shrink_mm: float | None = None


def _optional_length_text_mm(
    document: DipTraceDocument,
    element: ET.Element | None,
    *,
    field_name: str,
) -> float | None:
    if element is None:
        return None
    raw = (element.text or "").strip()
    if not raw:
        return None

    offset = document.element_byte_offset(element)
    details = {
        "element": str(element.tag),
        "field": field_name,
        "byte_offset": offset,
    }
    try:
        value = float(raw)
    except ValueError as exc:
        raise DocumentError(
            f"Invalid numeric field {field_name}={raw!r} on <{element.tag}> "
            f"at byte offset {offset}",
            details=details,
        ) from exc

    value = require_finite_number(
        value,
        context=f"numeric field {field_name} on <{element.tag}>",
        offset=offset,
        details=details,
    )
    return require_finite_number(
        to_mm(value, document.units),
        context=f"converted field {field_name} on <{element.tag}>",
        offset=offset,
        details=details,
    )


def get_board_project_settings(document: DipTraceDocument) -> BoardProjectSettings:
    """Read supported board defaults while leaving missing DipTrace values as ``None``."""

    if document.kind != "pcb":
        raise DocumentError("Project board settings are only available for PCB documents")

    settings = document.container.find("./Settings")
    if settings is None:
        return BoardProjectSettings()

    return BoardProjectSettings(
        courtyard_line_width_mm=_optional_length_text_mm(
            document,
            settings.find("./LineWidth/Courtyard"),
            field_name="LineWidth/Courtyard",
        ),
        solder_mask_swell_mm=_optional_length_text_mm(
            document,
            settings.find("./SolderMaskSwell"),
            field_name="SolderMaskSwell",
        ),
        paste_mask_shrink_mm=_optional_length_text_mm(
            document,
            settings.find("./PasteMaskShrink"),
            field_name="PasteMaskShrink",
        ),
    )


def _project_settings_payload(document: DipTraceDocument) -> dict[str, Any]:
    return get_board_project_settings(document).model_dump(mode="json")


def summarize(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    result = _summarize(document, live_session=live_session)
    if document.kind == "pcb":
        result["project_settings"] = _project_settings_payload(document)
    return result


def components(
    document: DipTraceDocument,
    query: str | None = None,
    offset: int = 0,
    limit: int = 100,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    return _components(document, query, offset, limit, live_session=live_session)


def component(
    document: DipTraceDocument,
    refdes: str,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    return _component(document, refdes, live_session=live_session)


def nets(
    document: DipTraceDocument,
    query: str | None = None,
    include_endpoints: bool = True,
    offset: int = 0,
    limit: int = 100,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    return _nets(
        document,
        query,
        include_endpoints,
        offset,
        limit,
        live_session=live_session,
    )


def design_rules(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    result = _design_rules(document, live_session=live_session)
    if document.kind == "pcb":
        result["project_settings"] = _project_settings_payload(document)
    return result


def get_document_info(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    return _get_document_info(document, live_session=live_session).model_dump()


def get_board_model(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    result = _get_board_model(document, live_session=live_session).model_dump()
    result.setdefault("rules", {})["project_settings"] = _project_settings_payload(document)
    return result


def get_schematic_model(
    document: DipTraceDocument, *, live_session: bool = False
) -> dict[str, Any]:
    return _get_schematic_model(document, live_session=live_session).model_dump()


def query_objects(
    document: DipTraceDocument,
    request: QueryRequest,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    return _query_objects(document, request, live_session=live_session).model_dump()


def get_object(
    document: DipTraceDocument,
    stable_id: str,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    return _get_object(document, stable_id, live_session=live_session)


def get_capabilities(
    document: DipTraceDocument | None = None,
    *,
    live_session: bool = False,
) -> dict[str, Any]:
    report = build_capabilities(document, live_session=live_session)
    return report.model_dump()
