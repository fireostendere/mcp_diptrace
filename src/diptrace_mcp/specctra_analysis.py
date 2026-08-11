from __future__ import annotations

import math
from collections import Counter
from typing import Any

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import SpecctraSession, StrictModel
from .errors import DocumentError
from .geometry import Point, distance
from .specctra import _SExprParser, parse_ses, session_to_operations


class SpecctraStructureInventory(StrictModel):
    root_scope: str
    token_count: int = Field(ge=0)
    scope_count: int = Field(ge=0)
    max_depth: int = Field(ge=0)
    scope_histogram: dict[str, int] = Field(default_factory=dict)


class SpecctraRouteStatistics(StrictModel):
    net_count: int = Field(ge=0)
    wire_count: int = Field(ge=0)
    via_count: int = Field(ge=0)
    segment_count: int = Field(ge=0)
    total_length_mm: float = Field(ge=0.0)
    min_width_mm: float | None = Field(default=None, ge=0.0)
    max_width_mm: float | None = Field(default=None, ge=0.0)
    layers: list[str] = Field(default_factory=list)
    duplicate_net_names: list[str] = Field(default_factory=list)


class SpecctraCompatibilityAnalysis(StrictModel):
    structure: SpecctraStructureInventory
    session: SpecctraSession
    routes: SpecctraRouteStatistics
    importable_nets: list[str] = Field(default_factory=list)
    skipped_nets: list[dict[str, Any]] = Field(default_factory=list)
    unknown_board_nets: list[str] = Field(default_factory=list)
    unknown_board_layers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _structure_metrics(
    value: Any,
    *,
    depth: int = 0,
) -> tuple[int, int, Counter[str]]:
    if not isinstance(value, list):
        return 0, depth, Counter()
    scopes = 1
    max_depth = depth
    histogram: Counter[str] = Counter()
    if value and isinstance(value[0], str):
        histogram[str(value[0])] += 1
    for child in value[1:]:
        child_scopes, child_depth, child_histogram = _structure_metrics(
            child,
            depth=depth + 1,
        )
        scopes += child_scopes
        max_depth = max(max_depth, child_depth)
        histogram.update(child_histogram)
    return scopes, max_depth, histogram


def analyze_specctra_structure(
    data: bytes,
    *,
    expected_root: str | None = None,
    max_bytes: int = 128 * 1024 * 1024,
    max_tokens: int = 2_000_000,
    max_depth: int = 128,
) -> SpecctraStructureInventory:
    if len(data) > max_bytes:
        raise DocumentError(f"Specctra file exceeds {max_bytes} bytes")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentError("Specctra file must be UTF-8 text") from exc
    parser = _SExprParser(text, max_tokens=max_tokens, max_depth=max_depth)
    roots = parser.parse()
    if len(roots) != 1 or not isinstance(roots[0], list) or not roots[0]:
        raise DocumentError("Specctra file must contain exactly one root scope")
    root = roots[0]
    root_name = str(root[0])
    if expected_root is not None and root_name != expected_root:
        raise DocumentError(
            f"Expected Specctra root {expected_root!r}, got {root_name!r}"
        )
    scope_count, observed_depth, histogram = _structure_metrics(root)
    return SpecctraStructureInventory(
        root_scope=root_name,
        token_count=parser.tokens,
        scope_count=scope_count,
        max_depth=observed_depth,
        scope_histogram=dict(sorted(histogram.items())),
    )


def analyze_session_routes(session: SpecctraSession) -> SpecctraRouteStatistics:
    widths: list[float] = []
    layers: set[str] = set()
    total_length = 0.0
    segment_count = 0
    names = [route.name for route in session.routes]
    duplicates = sorted(
        name
        for name, count in Counter(item.casefold() for item in names).items()
        if count > 1
    )
    canonical_name = {item.casefold(): item for item in names}
    duplicate_names = [canonical_name[item] for item in duplicates]

    for route in session.routes:
        for wire in route.wires:
            widths.append(wire.width_mm)
            layers.add(wire.layer)
            for first, second in zip(wire.points, wire.points[1:], strict=False):
                total_length += distance(Point(**first), Point(**second))
                segment_count += 1
    if not math.isfinite(total_length):
        raise DocumentError("SES route analysis produced a non-finite length")
    return SpecctraRouteStatistics(
        net_count=len(session.routes),
        wire_count=sum(len(item.wires) for item in session.routes),
        via_count=sum(len(item.vias) for item in session.routes),
        segment_count=segment_count,
        total_length_mm=total_length,
        min_width_mm=min(widths) if widths else None,
        max_width_mm=max(widths) if widths else None,
        layers=sorted(layers),
        duplicate_net_names=duplicate_names,
    )


def analyze_ses_compatibility(
    snapshot: DocumentSnapshot,
    data: bytes,
    *,
    via_style: str | None = None,
    max_bytes: int = 128 * 1024 * 1024,
) -> SpecctraCompatibilityAnalysis:
    structure = analyze_specctra_structure(
        data,
        expected_root="session",
        max_bytes=max_bytes,
    )
    session = parse_ses(data, max_bytes=max_bytes)
    route_stats = analyze_session_routes(session)
    plan = session_to_operations(snapshot, session, via_style=via_style)

    board_net_names: set[str] = set()
    board_layer_names: set[str] = set()
    if snapshot.board is not None:
        board_net_names = {
            (item.name or "").casefold()
            for item in snapshot.board.nets
            if item.name
        }
        board_layer_names = {
            str(item.get("name", "")).casefold()
            for item in snapshot.board.layers
            if item.get("name")
        }
    unknown_nets = sorted(
        route.name
        for route in session.routes
        if route.name.casefold() not in board_net_names
    )
    unknown_layers = sorted(
        layer for layer in route_stats.layers if layer.casefold() not in board_layer_names
    )
    warnings: list[str] = []
    if route_stats.duplicate_net_names:
        warnings.append(
            "SES contains duplicate net scopes under case-insensitive matching."
        )
    if unknown_nets:
        warnings.append("SES contains nets that do not resolve on the target PCB.")
    if unknown_layers:
        warnings.append("SES contains route layers that do not resolve on the target PCB.")
    if plan.skipped:
        warnings.append(
            "One or more SES nets are not importable by the bounded semantic importer."
        )

    return SpecctraCompatibilityAnalysis(
        structure=structure,
        session=session,
        routes=route_stats,
        importable_nets=list(plan.imported_nets),
        skipped_nets=list(plan.skipped),
        unknown_board_nets=unknown_nets,
        unknown_board_layers=unknown_layers,
        warnings=warnings,
        limitations=[
            (
                "Structural inventory validates the bounded S-expression subset; it "
                "does not prove compatibility with every Specctra producer or "
                "DipTrace build."
            ),
            (
                "Importability is evaluated without mutating the target PCB and "
                "remains limited to the existing conservative SES semantic importer."
            ),
            (
                "A clean analysis does not replace post-import DRC, connectivity "
                "review, native DipTrace round-trip, or copper-refill acceptance "
                "where applicable."
            ),
        ],
    )
