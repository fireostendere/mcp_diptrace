from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Literal

from pydantic import Field

from .adapters import DocumentSnapshot
from .domain import ObjectRecord, StrictModel
from .errors import CapabilityUnavailableError

ComponentRole = Literal[
    "controller",
    "power_converter",
    "connector",
    "interface",
    "sensor",
    "timing",
    "protection",
    "power_support",
    "support",
    "mechanical_anchor",
    "other",
]
NetRole = Literal[
    "ground",
    "shield",
    "power",
    "high_current_power",
    "switching_node",
    "clock",
    "differential",
    "reset",
    "control",
    "digital",
    "analog",
    "precision_analog",
    "reference",
    "feedback",
    "current_sense",
    "rf",
    "unknown",
]
ThermalRole = Literal["normal", "potential_heat_source", "temperature_sensitive"]
ReturnStrategy = Literal[
    "continuous_plane_preferred",
    "local_plane_or_pour_candidate",
    "local_copper_minimized",
    "kelvin_candidate",
    "chassis_or_shield",
    "explicit_star",
    "unknown",
]
BlockRole = Literal["controller", "power", "connector", "interface", "sensor", "generic"]

_POWER_RE = re.compile(
    r"^(?:\+)?(?:VCC|VDD|AVDD|DVDD|PVDD|VBAT|BAT|VIN|VOUT|VSYS|VUSB|"
    r"\d+(?:V\d+|V)?)(?:[_-].*)?$",
    re.IGNORECASE,
)
_GROUND_RE = re.compile(r"^(?:GND|AGND|DGND|PGND|0V|VSS)(?:[_-].*)?$", re.IGNORECASE)
_SHIELD_RE = re.compile(r"^(?:CHASSIS|SHIELD|EARTH|PE)(?:[_-].*)?$", re.IGNORECASE)
_SWITCH_NODE_RE = re.compile(r"^(?:SW|PHASE|LX)(?:[_-].*)?$", re.IGNORECASE)


class PCBElectricalConstraints(StrictModel):
    signal_frequency_hz: float | None = Field(default=None, gt=0.0)
    edge_rate_ns: float | None = Field(default=None, gt=0.0)
    current_a: float | None = Field(default=None, ge=0.0)
    trace_width_mm: float | None = Field(default=None, gt=0.0)
    target_impedance_ohm: float | None = Field(default=None, gt=0.0)
    impedance_tolerance_percent: float | None = Field(default=None, gt=0.0, le=100.0)
    max_length_mm: float | None = Field(default=None, gt=0.0)
    max_skew_mm: float | None = Field(default=None, ge=0.0)
    max_vias: int | None = Field(default=None, ge=0, le=128)
    preferred_layers: list[str] = Field(default_factory=list)
    forbidden_layers: list[str] = Field(default_factory=list)
    reference_net: str | None = None
    minimum_spacing_mm: float | None = Field(default=None, ge=0.0)
    stub_sensitive: bool = False
    shielding_preferred: bool = False


class PCBComponentOverride(StrictModel):
    selector: str = Field(min_length=1, max_length=256)
    role: ComponentRole | None = None
    block_id: str | None = Field(default=None, min_length=1, max_length=256)
    anchor_component: str | None = Field(default=None, min_length=1, max_length=256)
    mechanical_anchor: bool | None = None
    noise_emission: int | None = Field(default=None, ge=0, le=100)
    noise_sensitivity: int | None = Field(default=None, ge=0, le=100)
    thermal_role: ThermalRole | None = None
    placement_priority: int | None = Field(default=None, ge=0, le=100)


class PCBNetOverride(StrictModel):
    selector: str = Field(min_length=1, max_length=256)
    roles: list[NetRole] = Field(default_factory=list)
    constraints: PCBElectricalConstraints = Field(default_factory=PCBElectricalConstraints)
    return_strategy: ReturnStrategy | None = None


class PCBIntentOverrides(StrictModel):
    components: list[PCBComponentOverride] = Field(default_factory=list)
    nets: list[PCBNetOverride] = Field(default_factory=list)


class PCBComponentIntent(StrictModel):
    component_id: str
    refdes: str | None = None
    role: ComponentRole
    block_id: str
    anchor_component_id: str | None = None
    mechanical_anchor: bool = False
    noise_emission: int = Field(ge=0, le=100)
    noise_sensitivity: int = Field(ge=0, le=100)
    thermal_role: ThermalRole = "normal"
    placement_priority: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class PCBNetIntent(StrictModel):
    net_id: str
    name: str | None = None
    roles: list[NetRole] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)
    criticality: int = Field(ge=0, le=100)
    noise_emission: int = Field(ge=0, le=100)
    noise_sensitivity: int = Field(ge=0, le=100)
    via_penalty: int = Field(ge=0, le=100)
    reference_plane_required: bool = False
    constraints: PCBElectricalConstraints = Field(default_factory=PCBElectricalConstraints)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class PCBFunctionalBlock(StrictModel):
    block_id: str
    role: BlockRole
    anchor_component_id: str
    member_component_ids: list[str] = Field(default_factory=list)
    support_component_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class PCBPowerGroundStrategy(StrictModel):
    net_id: str
    name: str | None = None
    strategy: ReturnStrategy
    explicit: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class PCBDesignIntent(StrictModel):
    document_id: str
    components: list[PCBComponentIntent] = Field(default_factory=list)
    nets: list[PCBNetIntent] = Field(default_factory=list)
    blocks: list[PCBFunctionalBlock] = Field(default_factory=list)
    power_ground: list[PCBPowerGroundStrategy] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


_ROLE_BASE_CRITICALITY: dict[NetRole, int] = {
    "ground": 80,
    "shield": 65,
    "power": 55,
    "high_current_power": 80,
    "switching_node": 100,
    "clock": 90,
    "differential": 90,
    "reset": 45,
    "control": 30,
    "digital": 35,
    "analog": 65,
    "precision_analog": 90,
    "reference": 90,
    "feedback": 85,
    "current_sense": 90,
    "rf": 100,
    "unknown": 20,
}


def _require_board(snapshot: DocumentSnapshot) -> None:
    if snapshot.board is None:
        raise CapabilityUnavailableError("PCB design intent requires a PCB document")


def _component_text(component: ObjectRecord) -> str:
    return " ".join(
        value
        for value in (
            component.refdes,
            component.name,
            component.value,
            str(component.attributes.get("pattern_name", "")),
        )
        if value
    ).upper()


def _component_role(component: ObjectRecord) -> tuple[ComponentRole, float, list[str]]:
    refdes = (component.refdes or "").upper()
    match = re.match(r"[A-Z]+", refdes)
    prefix = match.group(0) if match else ""
    text = _component_text(component)
    if prefix in {"J", "P", "CN", "CON"} or any(
        token in text for token in ("CONNECTOR", "HEADER", "USB-C", "TYPE-C")
    ):
        return "connector", 0.9, ["connector-like RefDes/name"]
    if prefix in {"SW", "S", "BTN"} or "BUTTON" in text or "SWITCH" in text:
        return (
            "mechanical_anchor",
            0.8,
            ["board-interface control is mechanically constrained"],
        )
    if prefix in {"U", "IC"}:
        if any(
            token in text
            for token in (
                "LDO",
                "BUCK",
                "BOOST",
                "PMIC",
                "REGULATOR",
                "CONVERTER",
                "DCDC",
            )
        ):
            return "power_converter", 0.85, ["active device has power-conversion keyword"]
        if any(token in text for token in ("PHY", "TRANSCEIVER", "DRIVER", "RECEIVER")):
            return "interface", 0.8, ["active device has interface keyword"]
        if any(token in text for token in ("SENSOR", "ADC", "AFE", "IMU", "ACCEL", "GYRO")):
            return "sensor", 0.75, ["active device has sensor/analog-front-end keyword"]
        return "controller", 0.8, ["IC-style RefDes"]
    if prefix in {"Y", "X"} or any(
        token in text for token in ("XTAL", "CRYSTAL", "OSCILLATOR")
    ):
        return "timing", 0.9, ["timing-source RefDes/name"]
    if prefix in {"F", "TVS"} or any(token in text for token in ("ESD", "TVS", "FUSE")):
        return "protection", 0.8, ["protection-device RefDes/name"]
    if prefix in {"C", "L", "FB"}:
        return (
            "power_support",
            0.7,
            ["passive commonly participates in local power/support networks"],
        )
    if prefix in {"R", "D", "LED", "NTC", "RT"}:
        return "support", 0.7, ["passive/support RefDes"]
    if prefix in {"Q", "T", "K"}:
        return "interface", 0.55, ["discrete active-device RefDes"]
    return "other", 0.35, ["no stronger deterministic component-role signal"]


def _component_defaults(role: ComponentRole) -> tuple[int, int, ThermalRole, int, bool]:
    if role == "power_converter":
        return 90, 35, "potential_heat_source", 95, False
    if role == "timing":
        return 75, 70, "normal", 90, False
    if role == "sensor":
        return 20, 85, "temperature_sensitive", 85, False
    if role == "controller":
        return 55, 45, "normal", 80, False
    if role == "interface":
        return 60, 45, "normal", 75, False
    if role in {"connector", "mechanical_anchor"}:
        return 20, 20, "normal", 100, True
    if role == "protection":
        return 15, 20, "normal", 80, False
    if role in {"support", "power_support"}:
        return 10, 35, "normal", 65, False
    return 20, 30, "normal", 40, False


def _net_members(snapshot: DocumentSnapshot) -> dict[str, list[str]]:
    assert snapshot.board is not None
    components = {
        item.xml_id: item.stable_id
        for item in snapshot.board.components
        if item.xml_id
    }
    nets = {item.xml_id: item.stable_id for item in snapshot.board.nets if item.xml_id}
    result: dict[str, list[str]] = defaultdict(list)
    for net in snapshot.document.container.findall("./Nets/Net"):
        net_id = nets.get(net.get("Id", ""))
        if net_id is None:
            continue
        seen: set[str] = set()
        for pad in net.findall("./Pads/Item"):
            component_id = components.get(pad.get("Comp", ""))
            if component_id is not None and component_id not in seen:
                result[net_id].append(component_id)
                seen.add(component_id)
    return result


def _normalized_name(name: str | None) -> str:
    return (name or "").strip().upper().replace(" ", "")


def _name_tokens(folded: str) -> set[str]:
    return {token for token in re.split(r"[^A-Z0-9]+", folded) if token}


def _roles_for_net(
    name: str | None,
    *,
    differential: bool,
) -> tuple[list[NetRole], float, list[str]]:
    folded = _normalized_name(name)
    roles: list[NetRole] = []
    reasons: list[str] = []
    confidence = 0.4
    if not folded:
        return ["unknown"], 0.2, ["net has no usable name"]
    tokens = _name_tokens(folded)
    if _GROUND_RE.match(folded):
        roles.append("ground")
        confidence = 0.98
        reasons.append("ground-like net name")
    if _SHIELD_RE.match(folded):
        roles.append("shield")
        confidence = max(confidence, 0.95)
        reasons.append("chassis/shield-like net name")
    if _POWER_RE.match(folded):
        roles.append("power")
        confidence = max(confidence, 0.85)
        reasons.append("power-rail-like net name")
    if _SWITCH_NODE_RE.match(folded):
        roles.append("switching_node")
        confidence = max(confidence, 0.75)
        reasons.append("switch-node-like net name")
    if any(token in folded for token in ("CLK", "CLOCK", "XTAL", "OSC")):
        roles.append("clock")
        confidence = max(confidence, 0.8)
        reasons.append("clock/timing-like net name")
    if differential:
        roles.append("differential")
        confidence = max(confidence, 0.98)
        reasons.append("net belongs to an exported differential-pair model")
    elif folded in {
        "USB_D+",
        "USB_D-",
        "USB_DP",
        "USB_DM",
        "CANH",
        "CANL",
        "LVDS_P",
        "LVDS_N",
    }:
        roles.append("differential")
        confidence = max(confidence, 0.7)
        reasons.append("differential-protocol naming heuristic")
    reference_name = any(
        token in folded for token in ("VREF", "AREF", "REFOUT", "REFIN")
    ) or (
        "REF" in tokens
        and bool({"ADC", "DAC", "ANALOG"}.intersection(tokens))
    )
    if reference_name:
        roles.extend(["analog", "precision_analog", "reference"])
        confidence = max(confidence, 0.9)
        reasons.append("precision-reference-like net name")
    if any(token in folded for token in ("SENSE", "ISNS", "CSENSE", "SHUNT")):
        roles.extend(["analog", "precision_analog", "current_sense"])
        confidence = max(confidence, 0.85)
        reasons.append("current/voltage-sense-like net name")
    if {"FB", "FEEDBACK"}.intersection(tokens):
        roles.extend(["analog", "feedback"])
        confidence = max(confidence, 0.8)
        reasons.append("feedback-like net name")
    analog_tokens = {"ADC", "AIN", "ANALOG", "DAC", "AOUT", "MIC", "AUDIO"}
    if analog_tokens.intersection(tokens) or folded.startswith(("ADC", "AIN", "DAC", "AOUT")):
        roles.append("analog")
        confidence = max(confidence, 0.75)
        reasons.append("analog-function-like net name")
    if any(
        token.startswith(("RF", "ANT", "MATCH"))
        for token in tokens
    ):
        roles.append("rf")
        confidence = max(confidence, 0.75)
        reasons.append("RF/antenna-like net name")
    if any(token in folded for token in ("RESET", "RST", "NRST")):
        roles.append("reset")
        confidence = max(confidence, 0.8)
        reasons.append("reset-like net name")
    control_tokens = {"EN", "ENABLE", "BOOT", "INT", "IRQ", "CS"}
    if control_tokens.intersection(tokens) or any(
        token.startswith("GPIO") for token in tokens
    ):
        roles.append("control")
        confidence = max(confidence, 0.65)
        reasons.append("control-like net name")
    if not roles:
        roles.append("digital")
        reasons.append("named net with no stronger deterministic role signal")
    return list(dict.fromkeys(roles)), confidence, reasons


def _criticality(roles: list[NetRole], constraints: PCBElectricalConstraints) -> int:
    value = max((_ROLE_BASE_CRITICALITY[role] for role in roles), default=20)
    if constraints.target_impedance_ohm is not None:
        value = max(value, 90)
    if constraints.edge_rate_ns is not None:
        if constraints.edge_rate_ns <= 1.0:
            value = max(value, 100)
        elif constraints.edge_rate_ns <= 5.0:
            value = max(value, 90)
        elif constraints.edge_rate_ns <= 20.0:
            value = max(value, 70)
    if constraints.signal_frequency_hz is not None:
        if constraints.signal_frequency_hz >= 100_000_000:
            value = max(value, 90)
        elif constraints.signal_frequency_hz >= 10_000_000:
            value = max(value, 70)
    if constraints.current_a is not None:
        if constraints.current_a >= 2.0:
            value = max(value, 90)
        elif constraints.current_a >= 0.5:
            value = max(value, 70)
    if constraints.max_skew_mm is not None or constraints.max_length_mm is not None:
        value = max(value, 80)
    return min(value, 100)


def _net_risk(roles: list[NetRole]) -> tuple[int, int]:
    emission = 15
    sensitivity = 20
    if "switching_node" in roles:
        emission = 100
    elif "clock" in roles or "rf" in roles:
        emission = 90
    elif "differential" in roles:
        emission = 65
    if any(
        role in roles
        for role in ("precision_analog", "reference", "current_sense")
    ):
        sensitivity = 100
    elif any(role in roles for role in ("analog", "feedback", "rf")):
        sensitivity = 80
    elif "clock" in roles or "differential" in roles:
        sensitivity = 60
    return emission, sensitivity


def _resolve_component(snapshot: DocumentSnapshot, selector: str) -> ObjectRecord | None:
    assert snapshot.board is not None
    folded = selector.casefold()
    matches = [
        item
        for item in snapshot.board.components
        if item.stable_id == selector or (item.refdes or "").casefold() == folded
    ]
    return matches[0] if len(matches) == 1 else None


def _resolve_net(snapshot: DocumentSnapshot, selector: str) -> ObjectRecord | None:
    assert snapshot.board is not None
    folded = selector.casefold()
    matches = [
        item
        for item in snapshot.board.nets
        if item.stable_id == selector
        or (item.name or item.net_name or "").casefold() == folded
    ]
    return matches[0] if len(matches) == 1 else None


def _differential_net_ids(snapshot: DocumentSnapshot) -> set[str]:
    assert snapshot.board is not None
    result: set[str] = set()
    for pair in snapshot.board.differential_pairs:
        if pair.positive_net_id:
            result.add(pair.positive_net_id)
        if pair.negative_net_id:
            result.add(pair.negative_net_id)
    return result


def _constraints_from_pair(
    snapshot: DocumentSnapshot,
    net_id: str,
) -> PCBElectricalConstraints:
    assert snapshot.board is not None
    for pair in snapshot.board.differential_pairs:
        if net_id not in {pair.positive_net_id, pair.negative_net_id}:
            continue
        rules = pair.rules
        return PCBElectricalConstraints(
            target_impedance_ohm=rules.target_impedance_ohm,
            max_length_mm=rules.fixed_length_mm,
            max_skew_mm=rules.length_tolerance_mm,
        )
    return PCBElectricalConstraints()


def _return_strategy(
    net: PCBNetIntent,
    explicit: ReturnStrategy | None,
) -> PCBPowerGroundStrategy | None:
    if explicit is not None:
        return PCBPowerGroundStrategy(
            net_id=net.net_id,
            name=net.name,
            strategy=explicit,
            explicit=True,
            confidence=1.0,
            reasons=["operator-supplied return/power topology strategy"],
        )
    roles = set(net.roles)
    if "shield" in roles:
        return PCBPowerGroundStrategy(
            net_id=net.net_id,
            name=net.name,
            strategy="chassis_or_shield",
            confidence=0.95,
            reasons=["shield/chassis net remains a distinct return domain"],
        )
    if "ground" in roles:
        return PCBPowerGroundStrategy(
            net_id=net.net_id,
            name=net.name,
            strategy="continuous_plane_preferred",
            confidence=0.9,
            reasons=[
                "continuous reference is the conservative default; ground is not auto-split"
            ],
        )
    if "switching_node" in roles:
        return PCBPowerGroundStrategy(
            net_id=net.net_id,
            name=net.name,
            strategy="local_copper_minimized",
            confidence=0.8,
            reasons=[
                "switch-node copper is kept local rather than promoted to a broad pour"
            ],
        )
    if "current_sense" in roles:
        return PCBPowerGroundStrategy(
            net_id=net.net_id,
            name=net.name,
            strategy="kelvin_candidate",
            confidence=0.75,
            reasons=["sense-net naming suggests a Kelvin connection when topology confirms it"],
        )
    if "power" in roles or "high_current_power" in roles:
        return PCBPowerGroundStrategy(
            net_id=net.net_id,
            name=net.name,
            strategy="local_plane_or_pour_candidate",
            confidence=0.65,
            reasons=[
                "power rail is a plane/pour candidate; current and stackup decide implementation"
            ],
        )
    return None


def _block_role(role: ComponentRole) -> BlockRole:
    if role == "power_converter":
        return "power"
    if role in {"connector", "mechanical_anchor"}:
        return "connector"
    if role == "controller":
        return "controller"
    if role == "interface":
        return "interface"
    if role == "sensor":
        return "sensor"
    return "generic"


def _assign_blocks(
    components: list[PCBComponentIntent],
    nets: list[PCBNetIntent],
    explicit_blocks: dict[str, str],
    explicit_anchors: dict[str, str],
) -> tuple[list[PCBComponentIntent], list[PCBFunctionalBlock]]:
    net_by_component: dict[str, list[PCBNetIntent]] = defaultdict(list)
    for net in nets:
        for component_id in net.component_ids:
            net_by_component[component_id].append(net)
    support_roles = {"support", "power_support", "timing", "protection"}
    anchors = [item for item in components if item.role not in support_roles]
    if not anchors and components:
        anchors = [
            max(
                components,
                key=lambda item: (item.placement_priority, item.component_id),
            )
        ]

    chosen_anchor: dict[str, str | None] = {}
    for component in components:
        explicit_anchor = explicit_anchors.get(component.component_id)
        if explicit_anchor is not None:
            chosen_anchor[component.component_id] = explicit_anchor
            continue
        if component.role not in support_roles:
            chosen_anchor[component.component_id] = component.component_id
            continue
        best: tuple[float, str] | None = None
        for anchor in anchors:
            score = 0.0
            for net in net_by_component.get(component.component_id, []):
                if anchor.component_id not in net.component_ids:
                    continue
                is_common_supply = any(
                    role in net.roles for role in ("ground", "power")
                )
                score += (0.2 if is_common_supply else 1.0) * (
                    1.0 + net.criticality / 100.0
                )
            candidate = (score, anchor.component_id)
            if score > 0.0 and (best is None or candidate > best):
                best = candidate
        chosen_anchor[component.component_id] = best[1] if best is not None else None

    updated: list[PCBComponentIntent] = []
    for component in components:
        anchor_id = chosen_anchor.get(component.component_id)
        block_id = explicit_blocks.get(
            component.component_id,
            f"block:{anchor_id or component.component_id}",
        )
        updated.append(
            component.model_copy(
                update={
                    "block_id": block_id,
                    "anchor_component_id": (
                        anchor_id
                        if anchor_id and anchor_id != component.component_id
                        else None
                    ),
                }
            )
        )

    by_block: dict[str, list[PCBComponentIntent]] = defaultdict(list)
    for component in updated:
        by_block[component.block_id].append(component)
    blocks: list[PCBFunctionalBlock] = []
    for block_id, members in sorted(by_block.items()):
        anchor = next(
            (
                item
                for item in members
                if chosen_anchor.get(item.component_id) == item.component_id
            ),
            max(
                members,
                key=lambda item: (item.placement_priority, item.component_id),
            ),
        )
        support_ids = [
            item.component_id
            for item in members
            if item.component_id != anchor.component_id
        ]
        blocks.append(
            PCBFunctionalBlock(
                block_id=block_id,
                role=_block_role(anchor.role),
                anchor_component_id=anchor.component_id,
                member_component_ids=[item.component_id for item in members],
                support_component_ids=support_ids,
                confidence=min((item.confidence for item in members), default=0.0),
                reasons=[
                    "deterministic anchor/support grouping from roles and shared nets"
                ],
            )
        )
    return updated, blocks


def build_pcb_design_intent(
    snapshot: DocumentSnapshot,
    overrides: PCBIntentOverrides | None = None,
) -> PCBDesignIntent:
    _require_board(snapshot)
    assert snapshot.board is not None
    overrides = overrides or PCBIntentOverrides()
    component_override_by_id: dict[str, PCBComponentOverride] = {}
    net_override_by_id: dict[str, PCBNetOverride] = {}
    warnings: list[str] = []

    for component_override_input in overrides.components:
        component_record = _resolve_component(
            snapshot,
            component_override_input.selector,
        )
        if component_record is None:
            warnings.append(
                "component override did not resolve uniquely: "
                f"{component_override_input.selector}"
            )
        else:
            component_override_by_id[component_record.stable_id] = component_override_input
    for net_override_input in overrides.nets:
        net_record = _resolve_net(snapshot, net_override_input.selector)
        if net_record is None:
            warnings.append(
                f"net override did not resolve uniquely: {net_override_input.selector}"
            )
        else:
            net_override_by_id[net_record.stable_id] = net_override_input

    members = _net_members(snapshot)
    differential_ids = _differential_net_ids(snapshot)
    nets: list[PCBNetIntent] = []
    for net_record in snapshot.board.nets:
        net_override = net_override_by_id.get(net_record.stable_id)
        constraints = _constraints_from_pair(snapshot, net_record.stable_id)
        if net_override is not None:
            supplied = net_override.constraints.model_dump(exclude_defaults=True)
            constraints = constraints.model_copy(update=supplied)
        inferred_roles, confidence, reasons = _roles_for_net(
            net_record.name or net_record.net_name,
            differential=net_record.stable_id in differential_ids,
        )
        roles = (
            list(dict.fromkeys(net_override.roles))
            if net_override is not None and net_override.roles
            else inferred_roles
        )
        if (
            constraints.current_a is not None
            and constraints.current_a >= 0.5
            and "power" in roles
        ):
            roles = list(dict.fromkeys([*roles, "high_current_power"]))
        criticality = _criticality(roles, constraints)
        emission, sensitivity = _net_risk(roles)
        nets.append(
            PCBNetIntent(
                net_id=net_record.stable_id,
                name=net_record.name or net_record.net_name,
                roles=roles,
                component_ids=sorted(members.get(net_record.stable_id, [])),
                criticality=criticality,
                noise_emission=emission,
                noise_sensitivity=sensitivity,
                via_penalty=min(100, max(10, criticality - 10)),
                reference_plane_required=bool(
                    {"clock", "differential", "rf"}.intersection(roles)
                    or constraints.target_impedance_ohm is not None
                ),
                constraints=constraints,
                confidence=(
                    1.0
                    if net_override is not None and net_override.roles
                    else confidence
                ),
                reasons=(
                    [*reasons, "operator-supplied net role/constraint override"]
                    if net_override is not None
                    else reasons
                ),
            )
        )

    components: list[PCBComponentIntent] = []
    explicit_blocks: dict[str, str] = {}
    explicit_anchors: dict[str, str] = {}
    for component_record in snapshot.board.components:
        role, confidence, reasons = _component_role(component_record)
        component_override = component_override_by_id.get(component_record.stable_id)
        if component_override is not None and component_override.role is not None:
            role = component_override.role
            confidence = 1.0
            reasons.append("operator-supplied component role")
        emission, sensitivity, thermal_role, priority, mechanical = _component_defaults(
            role
        )
        if component_override is not None:
            if component_override.noise_emission is not None:
                emission = component_override.noise_emission
            if component_override.noise_sensitivity is not None:
                sensitivity = component_override.noise_sensitivity
            thermal_role = component_override.thermal_role or thermal_role
            if component_override.placement_priority is not None:
                priority = component_override.placement_priority
            if component_override.mechanical_anchor is not None:
                mechanical = component_override.mechanical_anchor
            if component_override.block_id:
                explicit_blocks[component_record.stable_id] = component_override.block_id
            if component_override.anchor_component:
                anchor_record = _resolve_component(
                    snapshot,
                    component_override.anchor_component,
                )
                if anchor_record is None:
                    warnings.append(
                        "component anchor override did not resolve uniquely: "
                        f"{component_override.anchor_component}"
                    )
                else:
                    explicit_anchors[component_record.stable_id] = anchor_record.stable_id
        components.append(
            PCBComponentIntent(
                component_id=component_record.stable_id,
                refdes=component_record.refdes,
                role=role,
                block_id=f"block:{component_record.stable_id}",
                mechanical_anchor=mechanical or component_record.locked,
                noise_emission=emission,
                noise_sensitivity=sensitivity,
                thermal_role=thermal_role,
                placement_priority=priority,
                confidence=confidence,
                reasons=reasons,
            )
        )

    components, blocks = _assign_blocks(
        components,
        nets,
        explicit_blocks,
        explicit_anchors,
    )
    power_ground: list[PCBPowerGroundStrategy] = []
    for net_intent in nets:
        net_override = net_override_by_id.get(net_intent.net_id)
        strategy = _return_strategy(
            net_intent,
            net_override.return_strategy if net_override is not None else None,
        )
        if strategy is not None:
            power_ground.append(strategy)

    return PCBDesignIntent(
        document_id=snapshot.board.document_id,
        components=sorted(components, key=lambda item: item.component_id),
        nets=sorted(nets, key=lambda item: item.net_id),
        blocks=blocks,
        power_ground=sorted(power_ground, key=lambda item: item.net_id),
        assumptions=[
            (
                "Automatic intent uses only exported connectivity and deterministic "
                "naming/RefDes heuristics."
            ),
            (
                "Missing edge rate, current, impedance and datasheet facts remain "
                "unknown unless supplied explicitly."
            ),
            (
                "Ground defaults to a continuous reference preference; the engine "
                "never infers a split/star ground merely from analog/digital naming."
            ),
        ],
        warnings=warnings,
    )


def intent_confidence(intent: PCBDesignIntent) -> float:
    values = [item.confidence for item in intent.components]
    values.extend(item.confidence for item in intent.nets)
    return math.fsum(values) / len(values) if values else 0.0
