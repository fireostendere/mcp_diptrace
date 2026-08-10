from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, StrictModel
from .errors import CapabilityUnavailableError
from .geometry import Point, distance
from .impedance import analyze_stackup
from .lengths import record_belongs_to_net
from .pcb_design_intent import (
    PCBDesignIntent,
    PCBIntentOverrides,
    PCBNetIntent,
    build_pcb_design_intent,
)
from .return_path import analyze_return_path


class PCBReferenceCandidate(StrictModel):
    signal_layer: str
    reference_layers: list[str] = Field(default_factory=list)
    structure: Literal["microstrip", "symmetric_stripline"]
    dielectric_constant: float | None = None
    copper_thickness_mm: float | None = None
    dielectric_height_mm: float | None = None
    plane_to_plane_separation_mm: float | None = None
    reference_plane_confidence: Literal["low", "high"] = "low"
    evidence: Literal["exported_stackup"] = "exported_stackup"
    preliminary_only: bool = True


class PCBPDNRailAssessment(StrictModel):
    net_id: str
    name: str | None = None
    current_a: float | None = None
    source_component_ids: list[str] = Field(default_factory=list)
    load_component_ids: list[str] = Field(default_factory=list)
    decoupling_component_ids: list[str] = Field(default_factory=list)
    distribution_strategy: str
    power_via_capacity_required: bool = False
    current_density_known: bool = False
    voltage_drop_known: bool = False
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PCBHotLoopCandidate(StrictModel):
    switching_net_id: str
    switching_net_name: str | None = None
    converter_component_ids: list[str] = Field(default_factory=list)
    support_component_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class PCBNoisePairAssessment(StrictModel):
    aggressor_net_id: str
    victim_net_id: str
    aggressor_name: str | None = None
    victim_name: str | None = None
    separation_mm: float = Field(gt=0.0)
    risk_score: float = Field(ge=0.0)
    timing_evidence: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium"] = "low"


ViaRole = Literal[
    "signal_via",
    "power_via",
    "ground_stitching_via",
    "return_transition_candidate",
    "differential_transition_member",
    "thermal_via",
]


class PCBViaRoleAssessment(StrictModel):
    via_id: str
    net_id: str | None = None
    net_name: str | None = None
    roles: list[ViaRole] = Field(default_factory=list)
    representation: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class PCBPhysicalAnalysis(StrictModel):
    intent: PCBDesignIntent
    reference_candidates: list[PCBReferenceCandidate] = Field(default_factory=list)
    stackup_limitations: list[str] = Field(default_factory=list)
    pdn_rails: list[PCBPDNRailAssessment] = Field(default_factory=list)
    hot_loop_candidates: list[PCBHotLoopCandidate] = Field(default_factory=list)
    return_path: dict[str, Any] = Field(default_factory=dict)
    noise_pairs: list[PCBNoisePairAssessment] = Field(default_factory=list)
    via_roles: list[PCBViaRoleAssessment] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _require_board(snapshot: DocumentSnapshot) -> None:
    if snapshot.board is None:
        raise CapabilityUnavailableError(
            "PCB physical analysis requires a PCB document"
        )


def _reference_candidates(
    snapshot: DocumentSnapshot,
) -> tuple[list[PCBReferenceCandidate], list[str]]:
    assert snapshot.board is not None
    analysis = analyze_stackup(snapshot.board.stackup)
    candidates: list[PCBReferenceCandidate] = []
    for item in analysis["microstrip_candidates"]:
        candidates.append(
            PCBReferenceCandidate(
                signal_layer=str(item["signal_layer"]),
                reference_layers=[str(item["reference_layer"])],
                structure="microstrip",
                dielectric_constant=item.get("dielectric_constant"),
                copper_thickness_mm=item.get("copper_thickness_mm"),
                dielectric_height_mm=item.get("dielectric_height_mm"),
                reference_plane_confidence=item.get(
                    "reference_plane_confidence", "low"
                ),
            )
        )
    for item in analysis["stripline_candidates"]:
        candidates.append(
            PCBReferenceCandidate(
                signal_layer=str(item["signal_layer"]),
                reference_layers=[
                    str(value) for value in item["reference_layers"]
                ],
                structure="symmetric_stripline",
                dielectric_constant=item.get("dielectric_constant"),
                copper_thickness_mm=item.get("copper_thickness_mm"),
                plane_to_plane_separation_mm=item.get(
                    "plane_to_plane_separation_mm"
                ),
                reference_plane_confidence=item.get(
                    "reference_plane_confidence", "low"
                ),
            )
        )
    return candidates, [str(item) for item in analysis["limitations"]]


def _component_records(snapshot: DocumentSnapshot) -> dict[str, ObjectRecord]:
    assert snapshot.board is not None
    return {item.stable_id: item for item in snapshot.board.components}


def _power_strategy(intent: PCBDesignIntent, net_id: str) -> str:
    match = next(
        (item for item in intent.power_ground if item.net_id == net_id),
        None,
    )
    return match.strategy if match is not None else "unknown"


def _pdn_rails(
    snapshot: DocumentSnapshot,
    intent: PCBDesignIntent,
) -> list[PCBPDNRailAssessment]:
    components = {item.component_id: item for item in intent.components}
    records = _component_records(snapshot)
    rails: list[PCBPDNRailAssessment] = []
    for net in intent.nets:
        if not {"power", "high_current_power"}.intersection(net.roles):
            continue
        connected = [
            components[item]
            for item in net.component_ids
            if item in components
        ]
        sources = sorted(
            item.component_id
            for item in connected
            if item.role == "power_converter"
        )
        loads = sorted(
            item.component_id
            for item in connected
            if item.component_id not in sources
        )
        decoupling = sorted(
            item.component_id
            for item in connected
            if records.get(item.component_id) is not None
            and (records[item.component_id].refdes or "")
            .upper()
            .startswith("C")
        )
        current_known = net.constraints.current_a is not None
        warnings: list[str] = []
        if not current_known:
            warnings.append(
                "Rail current is unknown; current density, voltage drop and "
                "numeric via capacity are not inferred."
            )
        if not sources:
            warnings.append(
                "No power-converter source is proven by exported connectivity/"
                "intent; source direction remains unresolved."
            )
        rails.append(
            PCBPDNRailAssessment(
                net_id=net.net_id,
                name=net.name,
                current_a=net.constraints.current_a,
                source_component_ids=sources,
                load_component_ids=loads,
                decoupling_component_ids=decoupling,
                distribution_strategy=_power_strategy(intent, net.net_id),
                power_via_capacity_required=bool(
                    current_known and (net.constraints.current_a or 0.0) >= 0.5
                ),
                reasons=[
                    "Distribution strategy is inherited from Generation A intent.",
                    "Decoupling candidates are capacitor RefDes rail members; "
                    "pad-level loop proof is not invented.",
                ],
                warnings=warnings,
            )
        )
    return rails


def _hot_loops(intent: PCBDesignIntent) -> list[PCBHotLoopCandidate]:
    components = {item.component_id: item for item in intent.components}
    result: list[PCBHotLoopCandidate] = []
    support_roles = {"power_support", "support", "protection"}
    for net in intent.nets:
        if "switching_node" not in net.roles:
            continue
        connected = [
            components[item]
            for item in net.component_ids
            if item in components
        ]
        converters = sorted(
            item.component_id
            for item in connected
            if item.role == "power_converter"
        )
        supports = sorted(
            item.component_id
            for item in connected
            if item.role in support_roles
        )
        if converters:
            result.append(
                PCBHotLoopCandidate(
                    switching_net_id=net.net_id,
                    switching_net_name=net.name,
                    converter_component_ids=converters,
                    support_component_ids=supports,
                    confidence=0.65 if supports else 0.45,
                    reasons=[
                        "Topology-only candidate: switching-node membership plus "
                        "a power-converter endpoint.",
                        "Actual current loop requires pad-level source/load and "
                        "return-path evidence.",
                    ],
                )
            )
    return result


def _net_center(
    net: PCBNetIntent,
    records: dict[str, ObjectRecord],
) -> Point | None:
    points: list[Point] = []
    for component_id in net.component_ids:
        record = records.get(component_id)
        if record is None or record.position is None:
            continue
        points.append(Point(**record.position))
    if not points:
        return None
    return Point(
        math.fsum(item.x for item in points) / len(points),
        math.fsum(item.y for item in points) / len(points),
    )


def _timing_evidence(net: PCBNetIntent) -> list[str]:
    evidence: list[str] = []
    if net.constraints.edge_rate_ns is not None:
        evidence.append(f"edge_rate_ns={net.constraints.edge_rate_ns:g}")
    if net.constraints.signal_frequency_hz is not None:
        evidence.append(
            f"signal_frequency_hz={net.constraints.signal_frequency_hz:g}"
        )
    return evidence


def _noise_pairs(
    snapshot: DocumentSnapshot,
    intent: PCBDesignIntent,
) -> list[PCBNoisePairAssessment]:
    records = _component_records(snapshot)
    centers = {
        net.net_id: center
        for net in intent.nets
        if (center := _net_center(net, records)) is not None
    }
    result: list[PCBNoisePairAssessment] = []
    for aggressor in intent.nets:
        timing = _timing_evidence(aggressor)
        if (
            not timing
            or aggressor.noise_emission < 50
            or aggressor.net_id not in centers
        ):
            continue
        for victim in intent.nets:
            if victim.net_id == aggressor.net_id:
                continue
            if victim.noise_sensitivity < 50 or victim.net_id not in centers:
                continue
            separation = max(
                distance(
                    centers[aggressor.net_id],
                    centers[victim.net_id],
                ),
                0.1,
            )
            risk = (
                aggressor.noise_emission
                * victim.noise_sensitivity
                * (1.0 + aggressor.criticality / 100.0)
                / 10_000.0
                / separation
            )
            victim_has_timing = (
                victim.constraints.edge_rate_ns is not None
                or victim.constraints.signal_frequency_hz is not None
            )
            result.append(
                PCBNoisePairAssessment(
                    aggressor_net_id=aggressor.net_id,
                    victim_net_id=victim.net_id,
                    aggressor_name=aggressor.name,
                    victim_name=victim.name,
                    separation_mm=separation,
                    risk_score=risk,
                    timing_evidence=timing,
                    reasons=[
                        "Risk combines explicit timing evidence, intent emission/"
                        "sensitivity and component-centroid separation.",
                        "Trace parallelism, field coupling and spectral overlap "
                        "are not asserted by this score.",
                    ],
                    confidence="medium" if victim_has_timing else "low",
                )
            )
    result.sort(
        key=lambda item: (
            -item.risk_score,
            item.aggressor_net_id,
            item.victim_net_id,
        )
    )
    return result


def _via_roles(
    snapshot: DocumentSnapshot,
    intent: PCBDesignIntent,
) -> list[PCBViaRoleAssessment]:
    assert snapshot.board is not None
    net_records = {item.stable_id: item for item in snapshot.board.nets}
    net_intents = {item.net_id: item for item in intent.nets}
    result: list[PCBViaRoleAssessment] = []
    for via in snapshot.board.vias:
        matches = [
            net_id
            for net_id, net_record in net_records.items()
            if record_belongs_to_net(via, net_record)
        ]
        net_id = matches[0] if len(matches) == 1 else None
        net = net_intents.get(net_id or "")
        roles: list[ViaRole] = []
        reasons: list[str] = []
        if net is not None:
            if "ground" in net.roles:
                roles.append("ground_stitching_via")
                reasons.append("Via belongs to an identified ground net.")
            elif {"power", "high_current_power"}.intersection(net.roles):
                roles.append("power_via")
                reasons.append("Via belongs to an identified power rail.")
            else:
                roles.append("signal_via")
                reasons.append("Via belongs to a non-power signal net.")
            if "differential" in net.roles:
                roles.append("differential_transition_member")
                reasons.append(
                    "Via belongs to an exported/inferred differential net."
                )
            is_transition = (
                via.attributes.get("representation")
                == "trace_layer_transition"
            )
            if net.reference_plane_required and is_transition:
                roles.append("return_transition_candidate")
                reasons.append(
                    "Reference-sensitive signal changes layers at this "
                    "normalized transition."
                )
        if bool(via.attributes.get("thermal")):
            roles.append("thermal_via")
            reasons.append("Thermal role is explicit in normalized via attributes.")
        representation = via.attributes.get("representation")
        result.append(
            PCBViaRoleAssessment(
                via_id=via.stable_id,
                net_id=net_id,
                net_name=net.name if net is not None else via.net_name,
                roles=list(dict.fromkeys(roles)),
                representation=(
                    str(representation) if representation is not None else None
                ),
                confidence=0.9 if net is not None else 0.25,
                reasons=reasons
                or [
                    "No unique electrical role can be proven from normalized "
                    "via/net evidence."
                ],
            )
        )
    return result


def _return_path(
    snapshot: DocumentSnapshot,
    intent: PCBDesignIntent,
    stitching_radius_mm: float,
) -> dict[str, Any]:
    precision_roles = {
        "precision_analog",
        "reference",
        "feedback",
        "current_sense",
    }
    targets = [
        item.net_id
        for item in intent.nets
        if item.reference_plane_required
        or precision_roles.intersection(item.roles)
    ]
    if not targets:
        return {
            "target_net_ids": [],
            "analysis": None,
            "reason": "No reference-sensitive nets were identified.",
        }
    analysis = analyze_return_path(
        snapshot,
        stitching_radius_mm=stitching_radius_mm,
        nets=targets,
    )
    return {
        "target_net_ids": targets,
        "analysis": analysis.model_dump(mode="json"),
    }


def analyze_pcb_physics(
    snapshot: DocumentSnapshot,
    *,
    overrides: PCBIntentOverrides | None = None,
    intent: PCBDesignIntent | None = None,
    stitching_radius_mm: float = 2.0,
) -> PCBPhysicalAnalysis:
    """Build Generation B physical-context analysis without mutating the board."""

    _require_board(snapshot)
    if not math.isfinite(stitching_radius_mm) or stitching_radius_mm <= 0.0:
        raise ValueError("stitching_radius_mm must be finite and positive")
    intent = intent or build_pcb_design_intent(snapshot, overrides)
    references, stackup_limitations = _reference_candidates(snapshot)
    pdn = _pdn_rails(snapshot, intent)
    warnings = list(intent.warnings)
    warnings.extend(warning for rail in pdn for warning in rail.warnings)
    return PCBPhysicalAnalysis(
        intent=intent,
        reference_candidates=references,
        stackup_limitations=stackup_limitations,
        pdn_rails=pdn,
        hot_loop_candidates=_hot_loops(intent),
        return_path=_return_path(snapshot, intent, stitching_radius_mm),
        noise_pairs=_noise_pairs(snapshot, intent),
        via_roles=_via_roles(snapshot, intent),
        assumptions=[
            "Generation B consumes exported stackup, normalized connectivity/"
            "geometry and explicit operator facts only.",
            "Analytic impedance candidates remain preliminary and are not "
            "promoted to manufacturer or field-solver evidence.",
            "Ground remains continuous by default; current-domain analysis "
            "never invents a split or star ground.",
        ],
        warnings=sorted(set(warnings)),
        limitations=[
            "Current density and voltage drop stay unknown until copper geometry, "
            "material and current paths are sufficient.",
            "Decoupling and regulator hot-loop identification are topology "
            "candidates until pad-level current direction is proven.",
            "Aggressor/victim scoring is bounded geometry/timing triage, not an "
            "EMC or full-wave result.",
            "Via roles do not imply current capacity; existing via geometry/span "
            "validation remains authoritative.",
        ],
    )
