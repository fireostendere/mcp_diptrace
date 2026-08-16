from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import cast

from pydantic import Field

from .adapters import build_snapshot
from .copper_pours import CopperPourResult, add_copper_pours
from .domain import StrictModel
from .errors import CapabilityUnavailableError, EditError
from .geometry import BBox, Point, from_mm, to_mm
from .pcb_autorouter import PCBRoutePlan, PCBRouterConfig, plan_pcb_routes
from .pcb_candidate_ensemble import (
    PCBEnsembleConfig,
    PCBEnsembleProfile,
    PCBEnsembleResult,
    build_pcb_candidate_ensemble,
    pcb_placement_profile_config,
)
from .pcb_design_intent import PCBIntentOverrides, build_pcb_design_intent
from .pcb_placement import plan_pcb_placement_v2
from .pcb_quality import PCBQualityConfig, PCBQualityReview, review_pcb_quality
from .semantic_compiler import apply_semantic_operations
from .silkscreen import SilkscreenPlanConfig, SilkscreenPlanningResult, plan_silkscreen
from .xml_document import DipTraceDocument, RawTreeSnapshot


class PCBWholeBoardConfig(StrictModel):
    ensemble: PCBEnsembleConfig = Field(default_factory=PCBEnsembleConfig)
    routing: PCBRouterConfig = Field(default_factory=PCBRouterConfig)
    quality: PCBQualityConfig = Field(default_factory=PCBQualityConfig)
    silkscreen: SilkscreenPlanConfig = Field(default_factory=SilkscreenPlanConfig)
    compact_outline: bool = True
    outline_margin_mm: float = Field(default=0.5, ge=0.0, le=25.0)
    minimum_board_width_mm: float = Field(default=2.0, gt=0.0, le=1_000.0)
    minimum_board_height_mm: float = Field(default=2.0, gt=0.0, le=1_000.0)
    add_two_layer_ground: bool = True
    ground_net: str | None = Field(default=None, min_length=1, max_length=256)
    stitch_pitch_mm: float = Field(default=2.0, gt=0.0, le=25.0)
    stitch_edge_mm: float = Field(default=0.8, ge=0.0, le=25.0)


@dataclass(frozen=True, slots=True)
class PCBWholeBoardResult:
    document: DipTraceDocument
    ensemble: PCBEnsembleResult
    routing: PCBRoutePlan
    silkscreen: SilkscreenPlanningResult
    quality: PCBQualityReview
    outline_before: dict[str, float] | None
    outline_after: dict[str, float] | None
    outline_changed: bool
    ground_net: str | None
    pour_count: int
    stitch_via_count: int
    stage_operation_kinds: list[str]
    warnings: list[str]
    limitations: list[str]


def _rectangular_outline_box(document: DipTraceDocument) -> BBox | None:
    points = document.container.findall("./BoardOutline/Points/Point")
    if len(points) != 4:
        return None
    coordinates = [
        Point(
            to_mm(float(point.get("X", "nan")), document.units),
            to_mm(float(point.get("Y", "nan")), document.units),
        )
        for point in points
    ]
    if not all(math.isfinite(value) for point in coordinates for value in (point.x, point.y)):
        return None
    xs = sorted(set(point.x for point in coordinates))
    ys = sorted(set(point.y for point in coordinates))
    if len(xs) != 2 or len(ys) != 2:
        return None
    return BBox(xs[0], ys[0], xs[1], ys[1])


def compact_rectangular_board_outline(
    document: DipTraceDocument,
    *,
    margin_mm: float = 0.5,
    minimum_width_mm: float = 2.0,
    minimum_height_mm: float = 2.0,
) -> tuple[DipTraceDocument, bool, dict[str, float] | None, dict[str, float] | None]:
    """Shrink an unlocked rectangular outline around proven occupied geometry."""

    if document.kind != "pcb":
        raise EditError("Board-outline compaction requires a PCB document")
    if margin_mm < 0.0 or minimum_width_mm <= 0.0 or minimum_height_mm <= 0.0:
        raise EditError("Board-outline compaction dimensions are invalid")
    outline = document.container.find("./BoardOutline")
    before = _rectangular_outline_box(document)
    if outline is None or before is None or outline.get("Locked", "N") == "Y":
        return document, False, before.as_dict() if before else None, None
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    records = (
        snapshot.board.components
        + snapshot.board.holes
        + snapshot.board.keepouts
        + snapshot.board.testpoints
        + snapshot.board.traces
    )
    boxes = [BBox(**item.bbox) for item in records if item.bbox is not None]
    if not boxes:
        return document, False, before.as_dict(), before.as_dict()
    occupied = BBox(
        min(item.min_x for item in boxes),
        min(item.min_y for item in boxes),
        max(item.max_x for item in boxes),
        max(item.max_y for item in boxes),
    ).expand(margin_mm)
    width = max(occupied.width, minimum_width_mm)
    height = max(occupied.height, minimum_height_mm)
    center = occupied.center
    after = BBox(
        center.x - width / 2.0,
        center.y - height / 2.0,
        center.x + width / 2.0,
        center.y + height / 2.0,
    )
    if all(
        math.isclose(first, second, abs_tol=1e-9)
        for first, second in zip(
            (before.min_x, before.min_y, before.max_x, before.max_y),
            (after.min_x, after.min_y, after.max_x, after.max_y),
            strict=True,
        )
    ):
        return document, False, before.as_dict(), after.as_dict()

    working = DipTraceDocument.from_bytes(document.path, document.raw_bytes)
    raw_tree = RawTreeSnapshot.capture(working)
    points = working.container.find("./BoardOutline/Points")
    assert points is not None
    points.clear()
    def unit(value: float) -> str:
        return f"{from_mm(value, working.units):.9g}"
    for point in (
        Point(after.min_x, after.min_y),
        Point(after.max_x, after.min_y),
        Point(after.max_x, after.max_y),
        Point(after.min_x, after.max_y),
    ):
        ET.SubElement(points, "Point", {"X": unit(point.x), "Y": unit(point.y)})
    compiled = raw_tree.compile(working.root, working.path)
    return (
        DipTraceDocument.from_bytes(working.path, compiled),
        True,
        before.as_dict(),
        after.as_dict(),
    )


def _ground_name(document: DipTraceDocument, requested: str | None) -> str | None:
    snapshot = build_snapshot(document)
    intent = build_pcb_design_intent(snapshot)
    names = sorted({item.name for item in intent.nets if "ground" in item.roles and item.name})
    if requested is not None:
        matches = [name for name in names if name.casefold() == requested.casefold()]
        if len(matches) != 1:
            raise CapabilityUnavailableError(
                f"Requested unique ground net was not identified: {requested}"
            )
        return matches[0]
    return names[0] if len(names) == 1 else None


def _two_copper_layers(document: DipTraceDocument) -> tuple[str, str] | None:
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    names = [str(item.get("name", "")) for item in snapshot.board.layers]
    top = next((item for item in names if item.casefold() == "top"), None)
    bottom = next((item for item in names if item.casefold() == "bottom"), None)
    return (top, bottom) if top is not None and bottom is not None else None


def optimize_pcb_whole_board(
    document: DipTraceDocument,
    *,
    overrides: PCBIntentOverrides | None = None,
    config: PCBWholeBoardConfig | None = None,
) -> PCBWholeBoardResult:
    """Build one bounded whole-board candidate without committing workspace bytes."""

    if document.kind != "pcb":
        raise CapabilityUnavailableError("Whole-board optimization requires a PCB document")
    config = config or PCBWholeBoardConfig()
    source_snapshot = build_snapshot(document)
    ensemble = build_pcb_candidate_ensemble(
        source_snapshot,
        overrides=overrides,
        config=config.ensemble,
    )
    placement_operations = []
    working = document
    if ensemble.selected_profile != "existing_board":
        selected_placement = plan_pcb_placement_v2(
            source_snapshot,
            overrides=overrides,
            config=pcb_placement_profile_config(
                cast(PCBEnsembleProfile, ensemble.selected_profile),
                config.ensemble.placement,
            ),
        )
        placement_operations = selected_placement.operations
        working = apply_semantic_operations(document, placement_operations).document
    routing_config = config.routing.model_copy(update={"allow_component_moves": False})
    route_plan = plan_pcb_routes(
        working,
        overrides=overrides,
        config=routing_config,
    )
    working = apply_semantic_operations(working, route_plan.operations).document
    outline_before: dict[str, float] | None = None
    outline_after: dict[str, float] | None = None
    outline_changed = False
    warnings = list(route_plan.warnings)
    if config.compact_outline:
        working, outline_changed, outline_before, outline_after = compact_rectangular_board_outline(
            working,
            margin_mm=config.outline_margin_mm,
            minimum_width_mm=config.minimum_board_width_mm,
            minimum_height_mm=config.minimum_board_height_mm,
        )
        if outline_after is None:
            warnings.append(
                "Outline compaction was skipped because the outline is locked or "
                "not a simple rectangle."
            )

    ground = _ground_name(working, config.ground_net)
    pour_result = CopperPourResult(document=working, pour_count=0, stitch_via_count=0)
    layers = _two_copper_layers(working)
    if config.add_two_layer_ground and ground is not None and layers is not None:
        pour_result = add_copper_pours(
            working,
            net=ground,
            layers=layers,
            stitch_pitch_mm=config.stitch_pitch_mm,
            stitch_edge_mm=config.stitch_edge_mm,
        )
        working = pour_result.document
    elif config.add_two_layer_ground:
        warnings.append(
            "Automatic two-layer GND pours were skipped because one unique ground "
            "net or Top/Bottom layers were unavailable."
        )

    silk_plan = plan_silkscreen(build_snapshot(working), config.silkscreen)
    if silk_plan.operations:
        working = apply_semantic_operations(working, silk_plan.operations).document
    final_snapshot = build_snapshot(working)
    final_intent = build_pcb_design_intent(final_snapshot, overrides)
    quality = review_pcb_quality(
        final_snapshot,
        intent=final_intent,
        config=config.quality,
    )
    stage_kinds = [
        *[item.kind for item in placement_operations],
        *[item.kind for item in route_plan.operations],
        *(["compact_board_outline"] if outline_changed else []),
        *(["add_ground_pours", "add_ground_stitching_vias"] if pour_result.pour_count else []),
        *[item.kind for item in silk_plan.operations],
    ]
    return PCBWholeBoardResult(
        document=working,
        ensemble=ensemble,
        routing=route_plan,
        silkscreen=silk_plan,
        quality=quality,
        outline_before=outline_before,
        outline_after=outline_after,
        outline_changed=outline_changed,
        ground_net=ground,
        pour_count=pour_result.pour_count,
        stitch_via_count=pour_result.stitch_via_count,
        stage_operation_kinds=stage_kinds,
        warnings=sorted(set(warnings)),
        limitations=[
            (
                "The returned document is a candidate; normal SHA-bound preview/"
                "transaction and native DipTrace DRC/refill remain required."
            ),
            "Outline compaction only rewrites an unlocked four-corner rectangular outline.",
            (
                "Physics review uses explicit facts and bounded proxies; unknown "
                "current, stackup and material data stay unknown."
            ),
        ],
    )
