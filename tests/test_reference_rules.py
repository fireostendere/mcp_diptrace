from __future__ import annotations

import hashlib
import json

import pytest

from diptrace_mcp.reference_rules import ingest_engineering_rule_pack


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
