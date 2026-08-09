"""Typed parsing for project-level PCB settings stored under Board/Settings."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pydantic import BaseModel, ConfigDict

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
