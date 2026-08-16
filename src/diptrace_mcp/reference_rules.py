from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic_core import CoreSchema

from .domain import StrictModel
from .pcb_design_intent import (
    PCBComponentOverride,
    PCBIntentOverrides,
    PCBNetOverride,
)
from .schematic_layout import (
    BoundReferenceMotif,
    ReferenceMotif,
    ReferenceMotifConstraint,
)


class EngineeringRuleSource(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    kind: Literal["datasheet", "reference_design", "project"]
    title: str = Field(min_length=1, max_length=512)
    locator: str = Field(min_length=1, max_length=2_048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    redistribution_allowed: bool = False


class SchematicMotifRule(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    constraints: list[ReferenceMotifConstraint] = Field(
        default_factory=list,
        min_length=1,
        max_length=128,
    )
    bindings: dict[str, str] = Field(default_factory=dict)


class PCBComponentRule(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    override: PCBComponentOverride


class PCBNetRule(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    override: PCBNetOverride


class EngineeringRulePack(StrictModel):
    schema_version: Literal["diptrace-engineering-rules-v1"] = "diptrace-engineering-rules-v1"
    sources: list[EngineeringRuleSource] = Field(
        min_length=1,
        max_length=64,
    )
    schematic_motifs: list[SchematicMotifRule] = Field(
        default_factory=list,
        max_length=256,
    )
    pcb_components: list[PCBComponentRule] = Field(
        default_factory=list,
        max_length=256,
    )
    pcb_nets: list[PCBNetRule] = Field(default_factory=list, max_length=256)

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: CoreSchema,
        _handler: GetJsonSchemaHandler,
    ) -> dict[str, Any]:
        # FastMCP embeds this schema in every tool that accepts a rule pack. The
        # complete nested schema duplicates large PCB-intent and schematic-motif
        # definitions and can dominate tools/list. Runtime validation still uses
        # the full Pydantic core schema; only discovery metadata is compacted.
        return {
            "type": "object",
            "description": (
                "Strict diptrace-engineering-rules-v1 object with sources, "
                "schematic_motifs, pcb_components, and pcb_nets; validated fully at runtime."
            ),
        }

    @model_validator(mode="after")
    def validate_sources(self) -> EngineeringRulePack:
        source_ids = [item.source_id for item in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("engineering rule source_id values must be unique")
        known = set(source_ids)
        referenced = {item.source_id for item in self.schematic_motifs}
        referenced.update(item.source_id for item in self.pcb_components)
        referenced.update(item.source_id for item in self.pcb_nets)
        missing = sorted(referenced - known)
        if missing:
            raise ValueError(f"engineering rules reference unknown sources: {', '.join(missing)}")
        return self


class EngineeringRuleProvenance(StrictModel):
    rule_kind: Literal["schematic_motif", "pcb_component", "pcb_net"]
    rule_index: int = Field(ge=0)
    source_id: str
    source_kind: Literal["datasheet", "reference_design", "project"]
    source_locator: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EngineeringRuleIngestion(StrictModel):
    pack_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    motifs: list[BoundReferenceMotif] = Field(default_factory=list)
    pcb_overrides: PCBIntentOverrides = Field(default_factory=PCBIntentOverrides)
    provenance: list[EngineeringRuleProvenance] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _payload_bytes(payload: bytes | str | Mapping[str, Any]) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def ingest_engineering_rule_pack(
    payload: bytes | str | Mapping[str, Any],
    *,
    expected_sha256: str | None = None,
) -> EngineeringRuleIngestion:
    """Validate a reviewer-extracted rule pack and retain per-rule provenance."""

    raw = _payload_bytes(payload)
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError(
            "engineering rule pack SHA-256 mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"invalid engineering rule pack JSON: {exc}") from exc
    pack = EngineeringRulePack.model_validate(decoded)
    sources = {item.source_id: item for item in pack.sources}
    motifs: list[BoundReferenceMotif] = []
    provenance: list[EngineeringRuleProvenance] = []

    for index, rule in enumerate(pack.schematic_motifs):
        source = sources[rule.source_id]
        motifs.append(
            BoundReferenceMotif(
                motif=ReferenceMotif(
                    name=rule.name,
                    source=(f"{source.title}; {source.locator}; sha256={source.sha256}"),
                    source_kind=source.kind,
                    confidence=rule.confidence,
                    constraints=rule.constraints,
                ),
                bindings=rule.bindings,
            )
        )
        provenance.append(
            EngineeringRuleProvenance(
                rule_kind="schematic_motif",
                rule_index=index,
                source_id=source.source_id,
                source_kind=source.kind,
                source_locator=source.locator,
                source_sha256=source.sha256,
            )
        )
    for index, component_rule in enumerate(pack.pcb_components):
        source = sources[component_rule.source_id]
        provenance.append(
            EngineeringRuleProvenance(
                rule_kind="pcb_component",
                rule_index=index,
                source_id=source.source_id,
                source_kind=source.kind,
                source_locator=source.locator,
                source_sha256=source.sha256,
            )
        )
    for index, net_rule in enumerate(pack.pcb_nets):
        source = sources[net_rule.source_id]
        provenance.append(
            EngineeringRuleProvenance(
                rule_kind="pcb_net",
                rule_index=index,
                source_id=source.source_id,
                source_kind=source.kind,
                source_locator=source.locator,
                source_sha256=source.sha256,
            )
        )

    nonredistributable = sorted(
        item.source_id for item in pack.sources if not item.redistribution_allowed
    )
    warnings = (
        [
            "Source bytes are not redistributable for: "
            + ", ".join(nonredistributable)
            + "; only extracted facts and hashes may be retained."
        ]
        if nonredistributable
        else []
    )
    return EngineeringRuleIngestion(
        pack_sha256=actual_sha256,
        motifs=motifs,
        pcb_overrides=PCBIntentOverrides(
            components=[item.override for item in pack.pcb_components],
            nets=[item.override for item in pack.pcb_nets],
        ),
        provenance=provenance,
        warnings=warnings,
        limitations=[
            (
                "The pack validates reviewer-extracted facts and provenance; it does "
                "not parse arbitrary PDFs or prove that an extraction is correct."
            ),
            (
                "Conflicting rules remain visible to the normal strict intent and "
                "selector resolution paths; ingestion does not silently merge them."
            ),
        ],
    )


class SourcedRuleDocument(StrictModel):
    source_id: str = Field(min_length=1, max_length=128)
    kind: Literal["datasheet", "reference_design", "project"]
    title: str = Field(min_length=1, max_length=512)
    revision: str = Field(min_length=1, max_length=256)
    locator: str = Field(min_length=1, max_length=2_048)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    redistribution_allowed: bool = False


class SourcedRuleFact(StrictModel):
    fact_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    source_revision: str = Field(min_length=1, max_length=256)
    source_locator: str = Field(min_length=1, max_length=2_048)
    rule_kind: Literal["schematic_motif", "pcb_component", "pcb_net"]
    units: str = Field(min_length=1, max_length=64)
    limit_type: Literal["min", "typ", "max", "exact", "range", "qualitative"]
    conditions: str = Field(min_length=1, max_length=2_048)
    applicability: str = Field(min_length=1, max_length=2_048)
    payload: dict[str, Any]


class SourceToRulePackResult(StrictModel):
    schema_version: Literal["diptrace-source-to-rule-pack-v1"] = "diptrace-source-to-rule-pack-v1"
    pack: EngineeringRulePack
    fact_metadata: list[SourcedRuleFact]
    source_bytes_retained: Literal[False] = False
    claim_eligible: Literal[False] = False
    required_manual_gate: Literal["M3"] = "M3"
    warnings: list[str] = Field(default_factory=list)


def build_engineering_rule_pack_from_sourced_facts(
    source_bytes: Mapping[str, bytes],
    documents: list[SourcedRuleDocument],
    facts: list[SourcedRuleFact],
) -> SourceToRulePackResult:
    """Build a strict draft rule pack from hash-bound, caller-supplied facts.

    This is deliberately not a PDF/LLM extractor.  It accepts only structured
    proposed facts whose source bytes, revision and locator are explicit, and
    it never promotes them to an engineering claim without manual gate M3.
    """

    by_id = {item.source_id: item for item in documents}
    if len(by_id) != len(documents):
        raise ValueError("sourced rule document source_id values must be unique")
    fact_ids = [item.fact_id for item in facts]
    if len(fact_ids) != len(set(fact_ids)):
        raise ValueError("sourced rule fact_id values must be unique")
    for source_id, document in by_id.items():
        try:
            raw = source_bytes[source_id]
        except KeyError as exc:
            raise ValueError(f"missing source bytes for {source_id}") from exc
        actual = hashlib.sha256(raw).hexdigest()
        if actual != document.sha256:
            raise ValueError(
                f"source SHA-256 mismatch for {source_id}: expected {document.sha256}, got {actual}"
            )
    motif_rules: list[SchematicMotifRule] = []
    component_rules: list[PCBComponentRule] = []
    net_rules: list[PCBNetRule] = []
    for fact in facts:
        try:
            document = by_id[fact.source_id]
        except KeyError as exc:
            raise ValueError(
                f"sourced rule fact references unknown source: {fact.source_id}"
            ) from exc
        if fact.source_revision != document.revision:
            raise ValueError(
                f"source revision mismatch for fact {fact.fact_id}: "
                f"{fact.source_revision!r} != {document.revision!r}"
            )
        if fact.source_locator != document.locator:
            raise ValueError(f"source locator mismatch for fact {fact.fact_id}")
        payload = {"source_id": fact.source_id, **fact.payload}
        if fact.rule_kind == "schematic_motif":
            motif_rules.append(SchematicMotifRule.model_validate(payload))
        elif fact.rule_kind == "pcb_component":
            component_rules.append(PCBComponentRule.model_validate(payload))
        else:
            net_rules.append(PCBNetRule.model_validate(payload))
    pack = EngineeringRulePack(
        sources=[
            EngineeringRuleSource(
                source_id=item.source_id,
                kind=item.kind,
                title=f"{item.title} [revision {item.revision}]",
                locator=item.locator,
                sha256=item.sha256,
                redistribution_allowed=item.redistribution_allowed,
            )
            for item in documents
        ],
        schematic_motifs=motif_rules,
        pcb_components=component_rules,
        pcb_nets=net_rules,
    )
    warnings = [
        "Draft pack is hash-bound but not engineering-claim eligible until manual M3 review."
    ]
    nonredistributable = sorted(
        item.source_id for item in documents if not item.redistribution_allowed
    )
    if nonredistributable:
        warnings.append(
            "Source bytes must remain outside the repository for: " + ", ".join(nonredistributable)
        )
    return SourceToRulePackResult(
        pack=pack,
        fact_metadata=facts,
        warnings=warnings,
    )
