from __future__ import annotations

from typing import Literal

from pydantic import Field

from .domain import StrictModel


class PCBPhysicsPrinciple(StrictModel):
    principle_id: str
    domain: Literal[
        "return_path",
        "power_integrity",
        "signal_integrity",
        "emi",
        "thermal",
    ]
    statement: str
    optimizer_terms: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    source_title: str
    source_url: str
    source_revision: str | None = None
    source_locator: str | None = None
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provenance_status: Literal["complete", "incomplete"] = "incomplete"
    claim_eligible: bool = False


_PRINCIPLES = (
    PCBPhysicsPrinciple(
        principle_id="continuous_reference_plane",
        domain="return_path",
        statement=(
            "Keep the reference plane continuous so high-frequency return current "
            "can remain close to the signal path and avoid enlarged loop area."
        ),
        optimizer_terms=["ground_pour_layer_count", "return_path", "stitching_coverage"],
        required_evidence=["exported stackup", "reference-net copper boundary"],
        source_title="Practical PCB Design Rules (TI SCAA082A)",
        source_url="https://www.ti.com/lit/an/scaa082a/scaa082a.pdf",
        source_revision="SCAA082A",
    ),
    PCBPhysicsPrinciple(
        principle_id="minimize_high_didt_loop",
        domain="emi",
        statement=(
            "Minimize the enclosed area and trace length of high-di/dt switching loops; "
            "keep high-dV/dt switching-node copper local."
        ),
        optimizer_terms=["hot_loop_span", "switch_node_broad_copper"],
        required_evidence=["switching-node role", "converter/support topology"],
        source_title="TPS55288 Layout Guideline (TI SLVAER0B)",
        source_url="https://www.ti.com/lit/an/slvaer0/slvaer0.pdf",
        source_revision="SLVAER0B",
    ),
    PCBPhysicsPrinciple(
        principle_id="short_decoupling_loop",
        domain="power_integrity",
        statement=(
            "Place decoupling capacitors and their plane vias close to the supplied "
            "device to reduce loop inductance and resistance."
        ),
        optimizer_terms=["decoupling_span", "support_adjacency"],
        required_evidence=["power source/load direction", "decoupling membership"],
        source_title="EVMK2GX Power Distribution Network Analysis (TI SPRACE6)",
        source_url="https://www.ti.com/lit/an/sprace6/sprace6.pdf",
        source_revision="SPRACE6",
    ),
)


def pcb_physics_principles() -> list[PCBPhysicsPrinciple]:
    """Return source-linked principles; incomplete provenance is never claim-eligible."""

    return [item.model_copy(deep=True) for item in _PRINCIPLES]
