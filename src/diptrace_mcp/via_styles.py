from __future__ import annotations

from .domain import BoardModel, ViaStyleModel
from .errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    GeometryError,
    ObjectNotFoundError,
)


def select_via_style(board: BoardModel, value: str) -> ViaStyleModel:
    matches = [
        style
        for style in board.via_styles
        if style.id == value or style.name.casefold() == value.casefold()
    ]
    if not matches:
        raise ObjectNotFoundError(f"Via style was not found: {value}")
    if len(matches) > 1:
        raise AmbiguousSelectorError(f"Via style is ambiguous: {value}")
    return matches[0]


def validate_via_geometry(style: ViaStyleModel) -> tuple[float, float]:
    diameter = style.diameter_mm or 0.0
    hole = style.hole_mm or 0.0
    if diameter <= 0.0 or hole <= 0.0 or diameter <= hole:
        raise GeometryError(
            "Via style lacks valid exported diameter and hole geometry",
            details={
                "via_style": style.id,
                "diameter_mm": diameter,
                "hole_mm": hole,
            },
        )
    return diameter, hole


def resolve_via_span(board: BoardModel, style: ViaStyleModel) -> tuple[str, ...]:
    board_layers = tuple(str(item.get("id", "")) for item in board.layers)
    if style.span_source == "explicit":
        span = tuple(style.span_layer_ids)
        if len(span) >= 2 and all(layer in board_layers for layer in span):
            return span
        raise GeometryError(
            "Via style references an invalid copper-layer span",
            details={
                "via_style": style.id,
                "layer_start_id": style.layer_start_id,
                "layer_end_id": style.layer_end_id,
                "board_layer_ids": list(board_layers),
            },
        )
    if style.span_source == "invalid":
        raise GeometryError(
            "Via style has incomplete or invalid Lay1/Lay2 references",
            details={
                "via_style": style.id,
                "layer_start_id": style.layer_start_id,
                "layer_end_id": style.layer_end_id,
                "board_layer_ids": list(board_layers),
            },
        )
    if len(board_layers) == 2:
        return board_layers
    raise CapabilityUnavailableError(
        "Via style span is omitted on a board with more than two copper layers",
        details={
            "via_style": style.id,
            "board_layer_ids": list(board_layers),
            "required_fields": ["Lay1", "Lay2"],
        },
    )


def validate_via_transition(
    board: BoardModel,
    style: ViaStyleModel,
    before_layer_id: str,
    after_layer_id: str,
) -> tuple[str, ...]:
    span = resolve_via_span(board, style)
    if before_layer_id not in span or after_layer_id not in span:
        raise GeometryError(
            "Via style does not span the requested layer transition",
            details={
                "via_style": style.id,
                "before_layer_id": before_layer_id,
                "after_layer_id": after_layer_id,
                "span_layer_ids": list(span),
            },
        )
    return span
