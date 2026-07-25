from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from pydantic import ValidationError

from .errors import DocumentError
from .geometry import to_mm
from .xml_document import DipTraceDocument

P = ParamSpec("P")
R = TypeVar("R")


def require_finite_number(
    value: float,
    *,
    context: str,
    offset: int | None = None,
    offset_unit: str = "byte",
    details: dict[str, Any] | None = None,
) -> float:
    """Reject NaN and infinities before they can reach geometry or comparisons."""

    if math.isfinite(value):
        return value
    location = f" at {offset_unit} offset {offset}" if offset is not None else ""
    error_details = dict(details or {})
    if offset is not None:
        error_details[f"{offset_unit}_offset"] = offset
    raise DocumentError(
        f"Non-finite numeric value in {context}{location}",
        details=error_details,
    )


def xml_number(
    document: DipTraceDocument,
    element: ET.Element,
    attribute: str,
    default: float = 0.0,
) -> float:
    """Parse one numeric XML attribute with element identity and byte location."""

    raw = element.get(attribute)
    if raw is None or raw == "":
        return default
    offset = document.element_byte_offset(element)
    details = {
        "element": str(element.tag),
        "attribute": attribute,
        "byte_offset": offset,
    }
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise DocumentError(
            f"Invalid numeric attribute {attribute}={raw!r} on <{element.tag}> "
            f"at byte offset {offset}",
            details=details,
        ) from exc
    return require_finite_number(
        parsed,
        context=f"attribute {attribute}={raw!r} on <{element.tag}>",
        offset=offset,
        details=details,
    )


def xml_number_mm(
    document: DipTraceDocument,
    element: ET.Element,
    attribute: str,
    default: float = 0.0,
) -> float:
    """Parse and normalize one XML dimension without allowing overflow."""

    offset = document.element_byte_offset(element)
    return require_finite_number(
        to_mm(xml_number(document, element, attribute, default), document.units),
        context=f"converted attribute {attribute} on <{element.tag}>",
        offset=offset,
        details={
            "element": str(element.tag),
            "attribute": attribute,
            "byte_offset": offset,
        },
    )


def xml_integer(
    document: DipTraceDocument,
    element: ET.Element,
    attribute: str,
    default: int = 0,
) -> int:
    """Parse one integer XML attribute without leaking a bare ValueError."""

    raw = element.get(attribute)
    if raw is None or raw == "":
        return default
    offset = document.element_byte_offset(element)
    try:
        return int(raw)
    except ValueError as exc:
        raise DocumentError(
            f"Invalid integer attribute {attribute}={raw!r} on <{element.tag}> "
            f"at byte offset {offset}",
            details={
                "element": str(element.tag),
                "attribute": attribute,
                "byte_offset": offset,
            },
        ) from exc


def translate_validation_errors(function: Callable[P, R]) -> Callable[P, R]:
    """Keep Pydantic implementation errors behind the document error contract."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except ValidationError as exc:
            first = exc.errors(include_url=False)[0]
            location = ".".join(str(item) for item in first.get("loc", ())) or "<root>"
            message = str(first.get("msg", "validation failed"))
            raise DocumentError(
                f"Invalid normalized document data at {location}: {message}"
            ) from exc

    return cast(Callable[P, R], wrapped)
