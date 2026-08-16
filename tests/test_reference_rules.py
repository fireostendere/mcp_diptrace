from __future__ import annotations

import hashlib
import json

import pytest

from diptrace_mcp.reference_rules import EngineeringRulePack, ingest_engineering_rule_pack


def _payload() -> bytes:
    value = {
        "schema_version": "diptrace-engineering-rules-v1",
        "sources": [
            {
                "source_id": "device-ds",
                "kind": "datasheet",
                "title": "Device datasheet",
                "locator": "https://example.invalid/device.pdf#page=12",
                "sha256": "a" * 64,
                "redistribution_allowed": False,
            }
        ],
        "schematic_motifs": [
            {
                "source_id": "device-ds",
                "name": "decoupler-near-device",
                "confidence": 0.95,
                "constraints": [
                    {
                        "first_key": "device",
                        "second_key": "decoupler",
                        "relation": "near",
                        "max_distance_mm": 10.0,
                    }
                ],
                "bindings": {
                    "device": "part_0000000000000001",
                    "decoupler": "part_0000000000000002",
                },
            }
        ],
        "pcb_components": [
            {
                "source_id": "device-ds",
                "override": {
                    "selector": "U1",
                    "role": "controller",
                    "noise_sensitivity": 80,
                },
            }
        ],
        "pcb_nets": [
            {
                "source_id": "device-ds",
                "override": {
                    "selector": "CLK",
                    "roles": ["clock"],
                    "constraints": {"edge_rate_ns": 1.5},
                },
            }
        ],
    }
    return json.dumps(value, sort_keys=True).encode("utf-8")


def test_rule_pack_retains_per_rule_source_hashes_and_builds_typed_inputs() -> None:
    raw = _payload()
    result = ingest_engineering_rule_pack(
        raw,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
    )

    assert result.motifs[0].motif.source_kind == "datasheet"
    assert "sha256=" in result.motifs[0].motif.source
    assert result.pcb_overrides.components[0].selector == "U1"
    assert result.pcb_overrides.nets[0].constraints.edge_rate_ns == 1.5
    assert len(result.provenance) == 3
    assert result.warnings


def test_rule_pack_fails_closed_on_hash_or_unknown_source() -> None:
    raw = _payload()
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ingest_engineering_rule_pack(raw, expected_sha256="0" * 64)

    value = json.loads(raw)
    value["pcb_nets"][0]["source_id"] = "missing"
    with pytest.raises(ValueError, match="unknown sources"):
        ingest_engineering_rule_pack(value)


def test_rule_pack_keeps_discovery_schema_compact_without_weakening_validation() -> None:
    schema = EngineeringRulePack.model_json_schema()

    assert schema["type"] == "object"
    assert "$defs" not in schema
    assert "diptrace-engineering-rules-v1" in schema["description"]

    validated = EngineeringRulePack.model_validate(json.loads(_payload()))
    assert validated.sources[0].source_id == "device-ds"
    with pytest.raises(ValueError):
        EngineeringRulePack.model_validate({"sources": []})


def test_source_to_rule_pack_requires_exact_source_revision_locator_and_sha() -> None:
    from diptrace_mcp.reference_rules import (
        SourcedRuleDocument,
        SourcedRuleFact,
        build_engineering_rule_pack_from_sourced_facts,
    )

    source = b"authoritative bytes supplied out of repository"
    digest = hashlib.sha256(source).hexdigest()
    document = SourcedRuleDocument(
        source_id="ds",
        kind="datasheet",
        title="Device datasheet",
        revision="rev-c",
        locator="page 12, table 4",
        sha256=digest,
        redistribution_allowed=False,
    )
    fact = SourcedRuleFact(
        fact_id="clk-role",
        source_id="ds",
        source_revision="rev-c",
        source_locator="page 12, table 4",
        rule_kind="pcb_net",
        units="ns",
        limit_type="max",
        conditions="3.3 V, nominal temperature",
        applicability="CLK net for exact device revision",
        payload={
            "override": {
                "selector": "CLK",
                "roles": ["clock"],
                "constraints": {"edge_rate_ns": 1.5},
            }
        },
    )
    result = build_engineering_rule_pack_from_sourced_facts({"ds": source}, [document], [fact])
    assert result.pack.pcb_nets[0].override.constraints.edge_rate_ns == 1.5
    assert result.claim_eligible is False
    assert result.required_manual_gate == "M3"
    assert result.source_bytes_retained is False
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_engineering_rule_pack_from_sourced_facts(
            {"ds": source + b"tampered"}, [document], [fact]
        )
    with pytest.raises(ValueError, match="revision mismatch"):
        build_engineering_rule_pack_from_sourced_facts(
            {"ds": source},
            [document],
            [fact.model_copy(update={"source_revision": "rev-b"})],
        )


def test_builtin_physics_principles_are_not_claim_eligible_without_exact_locator_hash() -> None:
    from diptrace_mcp.pcb_physics_knowledge import pcb_physics_principles

    principles = pcb_physics_principles()
    assert principles
    assert all(item.source_revision for item in principles)
    assert all(item.provenance_status == "incomplete" for item in principles)
    assert all(item.source_locator is None for item in principles)
    assert all(item.source_sha256 is None for item in principles)
    assert all(item.claim_eligible is False for item in principles)
