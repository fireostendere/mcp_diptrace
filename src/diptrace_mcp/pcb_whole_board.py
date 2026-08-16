from __future__ import annotations

import difflib
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import Field

from .adapters import build_snapshot
from .backups import BackupStore
from .config import Settings
from .copper_pours import CopperPourResult, add_copper_pours
from .domain import StrictModel
from .errors import CapabilityUnavailableError, EditError, Sha256MismatchError
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
from .plans import PlanStore
from .policy import Policy
from .preview import render_preview_json, render_preview_svg
from .semantic_compiler import apply_semantic_operations
from .silkscreen import SilkscreenPlanConfig, SilkscreenPlanningResult, plan_silkscreen
from .xml_analysis import compare_xml_semantics
from .xml_document import (
    DipTraceDocument,
    RawTreeSnapshot,
    atomic_write_bytes,
)


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


def _whole_board_connectivity_sha256(document: DipTraceDocument) -> str:
    snapshot = build_snapshot(document)
    if snapshot.board is None:
        raise CapabilityUnavailableError("Whole-board planning requires a PCB document")
    payload = [
        (
            net.name or net.net_name or net.stable_id,
            tuple(sorted(str(item) for item in net.relationships.get("endpoints", []))),
        )
        for net in snapshot.board.nets
    ]
    raw = json.dumps(sorted(payload), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _whole_board_identity_payload(
    *,
    source_sha256: str,
    candidate_sha256: str,
    config: PCBWholeBoardConfig,
    stage_operation_kinds: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "diptrace-pcb-whole-board-plan-v1",
        "source_sha256": source_sha256,
        "candidate_sha256": candidate_sha256,
        "config": config.model_dump(mode="json"),
        "stages": list(stage_operation_kinds),
    }


def _whole_board_plan_identity(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _whole_board_candidate_path(plan_store: PlanStore, plan_id: str) -> Path:
    plan_dir = plan_store.plan_dir(plan_id)
    resolved = plan_dir.resolve(strict=True)
    candidate = resolved / "candidate.xml"
    if candidate.parent != resolved:
        raise EditError("Whole-board candidate escaped its plan directory")
    return candidate


def plan_pcb_whole_board_guarded(
    document: DipTraceDocument,
    plan_store: PlanStore,
    *,
    target_path: Path | None = None,
    overrides: PCBIntentOverrides | None = None,
    config: PCBWholeBoardConfig | None = None,
) -> dict[str, Any]:
    """Create an immutable SHA-bound whole-board candidate and preview.

    This intentionally stays below the public MCP surface.  It reuses the
    existing plan store and records native refill/DRC as unresolved rather
    than treating exported pour boundaries as authoritative copper.
    """

    if document.kind != "pcb":
        raise CapabilityUnavailableError("Whole-board planning requires a PCB document")
    config = config or PCBWholeBoardConfig()
    result = optimize_pcb_whole_board(document, overrides=overrides, config=config)
    candidate = result.document
    source_snapshot = build_snapshot(document)
    candidate_snapshot = build_snapshot(candidate)
    semantic_delta = compare_xml_semantics(document, candidate)
    source_connectivity = _whole_board_connectivity_sha256(document)
    candidate_connectivity = _whole_board_connectivity_sha256(candidate)
    identity_payload = _whole_board_identity_payload(
        source_sha256=document.sha256,
        candidate_sha256=candidate.sha256,
        config=config,
        stage_operation_kinds=result.stage_operation_kinds,
    )
    identity = _whole_board_plan_identity(identity_payload)
    no_changes = candidate.sha256 == document.sha256
    unresolved = [
        {
            "code": "native_refill_and_drc_required",
            "message": (
                "Authoritative DipTrace copper refill, plane connectivity, thermal "
                "geometry and native DRC remain a manual M1 gate."
            ),
        }
    ]
    record = plan_store.create(
        plan_type="pcb_whole_board",
        document_id=source_snapshot.info.document_id,
        source_sha256=document.sha256,
        target_path=target_path or document.path,
        config=config.model_dump(mode="json"),
        operations=[],
        changed_ids=[],
        unresolved=unresolved,
        candidates=[
            {
                "candidate_sha256": candidate.sha256,
                "plan_identity_sha256": identity,
                "stage_operation_kinds": result.stage_operation_kinds,
            }
        ],
        score={"hard_error_count": float(result.quality.hard_error_count)},
        metrics={
            "schema_version": "diptrace-pcb-whole-board-plan-v1",
            "candidate_sha256": candidate.sha256,
            "plan_identity_sha256": identity,
            "source_connectivity_sha256": source_connectivity,
            "candidate_connectivity_sha256": candidate_connectivity,
            "connectivity_preserved": source_connectivity == candidate_connectivity,
            "semantic_delta": semantic_delta.model_dump(mode="json"),
            "quality": result.quality.model_dump(mode="json"),
            "stage_operation_kinds": result.stage_operation_kinds,
            "native_refill_required": True,
            "native_drc_required": True,
        },
        assumptions=result.quality.assumptions,
        warnings=result.warnings,
        limitations=result.limitations,
    )
    candidate_path = _whole_board_candidate_path(plan_store, record.plan_id)
    atomic_write_bytes(candidate_path, candidate.raw_bytes)
    changed_ids = sorted(
        set(source_snapshot.objects).symmetric_difference(candidate_snapshot.objects)
        | {
            key
            for key in set(source_snapshot.objects) & set(candidate_snapshot.objects)
            if source_snapshot.objects[key] != candidate_snapshot.objects[key]
        }
    )
    diff = "".join(
        difflib.unified_diff(
            document.raw_bytes.decode(document.encoding, errors="replace").splitlines(True),
            candidate.raw_bytes.decode(candidate.encoding, errors="replace").splitlines(True),
            fromfile="source.xml",
            tofile="candidate.xml",
        )
    )
    resources = plan_store.store_preview(
        record.plan_id,
        svg=render_preview_svg(source_snapshot, candidate_snapshot, changed_ids),
        geometry={
            **render_preview_json(source_snapshot, candidate_snapshot, changed_ids),
            "plan_id": record.plan_id,
            "candidate_sha256": candidate.sha256,
            "plan_identity_sha256": identity,
            "quality": result.quality.model_dump(mode="json"),
            "native_refill_required": True,
        },
        diff=diff,
    )
    if no_changes:
        record = plan_store.update(record.plan_id, status="noop", transaction_id=None)
    else:
        record = plan_store.read(record.plan_id)
    return {
        "ok": True,
        "plan": record.model_dump(mode="json"),
        "candidate_sha256": candidate.sha256,
        "plan_identity_sha256": identity,
        "no_changes": no_changes,
        "hard_error_count": result.quality.hard_error_count,
        "connectivity_preserved": source_connectivity == candidate_connectivity,
        "resources": resources,
        "limitations": result.limitations,
    }


def apply_pcb_whole_board_plan_guarded(
    plan_store: PlanStore,
    backups: BackupStore,
    policy: Policy,
    settings: Settings,
    plan_id: str,
    *,
    dry_run: bool = True,
    expected_sha256: str | None = None,
    invalidate_trust: Callable[[Path, str], None] | None = None,
) -> dict[str, Any]:
    """Preview or atomically commit a stored whole-board candidate.

    Commit is fail-closed: source SHA, candidate SHA, deterministic plan
    identity, hard review findings and post-write parsing are revalidated.
    Any post-write/trust-invalidation failure restores the exact backup.
    """

    policy.require_write(dry_run=dry_run, operation="pcb_whole_board_plan")
    plan = plan_store.read(plan_id)
    if plan.plan_type != "pcb_whole_board":
        raise EditError("Unexpected plan type for whole-board apply")
    target = settings.resolve_allowed_path(plan.target_path)
    current = DipTraceDocument.load(target, settings.max_document_bytes)
    if current.sha256 != plan.source_sha256:
        plan_store.update(plan_id, status="obsolete", transaction_id=plan.transaction_id)
        raise Sha256MismatchError(
            "Document changed after the whole-board plan was generated",
            details={
                "plan_sha256": plan.source_sha256,
                "current_sha256": current.sha256,
            },
        )
    if expected_sha256 is not None and expected_sha256 != plan.source_sha256:
        raise Sha256MismatchError(
            "Provided SHA does not match the whole-board plan source",
            details={
                "plan_sha256": plan.source_sha256,
                "provided_sha256": expected_sha256,
            },
        )
    if plan.status == "noop":
        return {
            "ok": True,
            "changed": False,
            "plan": plan.model_dump(mode="json"),
            "candidate_sha256": plan.source_sha256,
        }
    candidate_path = _whole_board_candidate_path(plan_store, plan_id)
    try:
        candidate_bytes = candidate_path.read_bytes()
    except OSError as exc:
        raise EditError("Whole-board candidate artifact is unavailable") from exc
    candidate = DipTraceDocument.from_bytes(target, candidate_bytes)
    recorded_candidate_sha = str(plan.metrics.get("candidate_sha256") or "")
    if not recorded_candidate_sha or candidate.sha256 != recorded_candidate_sha:
        raise Sha256MismatchError(
            "Stored whole-board candidate no longer matches its plan",
            details={
                "recorded_candidate_sha256": recorded_candidate_sha,
                "actual_candidate_sha256": candidate.sha256,
            },
        )
    identity_payload = _whole_board_identity_payload(
        source_sha256=plan.source_sha256,
        candidate_sha256=candidate.sha256,
        config=PCBWholeBoardConfig.model_validate(plan.config),
        stage_operation_kinds=[str(item) for item in plan.metrics.get("stage_operation_kinds", [])],
    )
    identity = _whole_board_plan_identity(identity_payload)
    if identity != plan.metrics.get("plan_identity_sha256"):
        raise Sha256MismatchError("Whole-board plan identity no longer matches")
    quality = plan.metrics.get("quality")
    hard_error_count = int(quality.get("hard_error_count", 0)) if isinstance(quality, dict) else 0
    if hard_error_count:
        raise EditError(
            "Whole-board candidate contains hard quality findings and cannot be committed",
            code="drc_regression",
            details={"hard_error_count": hard_error_count},
        )
    if dry_run:
        return {
            "ok": True,
            "changed": True,
            "dry_run": True,
            "source_sha256": plan.source_sha256,
            "candidate_sha256": candidate.sha256,
            "plan_identity_sha256": identity,
            "native_refill_required": True,
            "plan": plan.model_dump(mode="json"),
        }
    backup = backups.write_with_backup(
        target,
        candidate_bytes,
        expected_sha256=plan.source_sha256,
    )
    try:
        written = DipTraceDocument.load(target, settings.max_document_bytes)
        if written.sha256 != candidate.sha256:
            raise Sha256MismatchError("Post-write whole-board SHA validation failed")
        if invalidate_trust is not None:
            invalidate_trust(target, written.sha256)
    except Exception as exc:
        try:
            atomic_write_bytes(target, backup.read_bytes())
            restored = DipTraceDocument.load(target, settings.max_document_bytes)
            if restored.sha256 != plan.source_sha256:
                raise EditError("Rollback restored unexpected document bytes")
        except Exception as rollback_exc:
            raise EditError(
                "Whole-board commit failed and rollback could not restore source bytes",
                code="rollback_failed",
                details={"target": str(target)},
            ) from rollback_exc
        raise EditError(
            "Whole-board commit failed validation; exact source bytes were restored",
            code="write_validation_failed",
            details={"target": str(target)},
        ) from exc
    updated = plan_store.update(plan_id, status="committed", transaction_id=None)
    return {
        "ok": True,
        "changed": True,
        "dry_run": False,
        "source_sha256": plan.source_sha256,
        "candidate_sha256": candidate.sha256,
        "plan_identity_sha256": identity,
        "backup_path": str(backup),
        "native_refill_required": True,
        "plan": updated.model_dump(mode="json"),
    }
