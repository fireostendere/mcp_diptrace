from __future__ import annotations

from typing import Any

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
from .xml_document import DipTraceDocument


def summarize(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    return _summarize(document, live_session=live_session)


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
    return _design_rules(document, live_session=live_session)


def get_document_info(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    return _get_document_info(document, live_session=live_session).model_dump()


def get_board_model(document: DipTraceDocument, *, live_session: bool = False) -> dict[str, Any]:
    return _get_board_model(document, live_session=live_session).model_dump()


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
