"""Tests for the clean-room factual inventory integrity boundary."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.extract_spec_inventory import build_inventory
from scripts.spec_inventory_integrity import validate_inventory

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def generated_inventory() -> dict:
    return build_inventory(ROOT / "tests/fixtures")


def test_generated_inventory_passes_integrity(generated_inventory: dict) -> None:
    validate_inventory(generated_inventory, ROOT)


def test_substituted_source_digest_is_rejected(generated_inventory: dict) -> None:
    substituted = copy.deepcopy(generated_inventory)
    substituted["sources"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256 does not match"):
        validate_inventory(substituted, ROOT)


def test_verbatim_or_source_derived_fact_fields_are_rejected(
    generated_inventory: dict,
) -> None:
    invalid = copy.deepcopy(generated_inventory)
    invalid["facts"][0]["description"] = "copied paragraph"

    with pytest.raises(ValueError, match="unexpected or missing fields"):
        validate_inventory(invalid, ROOT)
