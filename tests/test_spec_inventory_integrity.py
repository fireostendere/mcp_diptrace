"""Focused tests for the specification-inventory integrity boundary."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest

from scripts.extract_spec_inventory import build_inventory
from scripts.spec_inventory_integrity import (
    MIN_ATTRIBUTE_COUNT,
    validate_inventory,
)

_REPOSITORY_ROOT = Path(__file__).parents[1]
_EXTRACTED_TEXT = _REPOSITORY_ROOT / "reference/diptrace-xml/extracted_text"


@pytest.fixture(scope="module")
def generated_inventory() -> dict[str, Any]:
    """Build from the same committed, offline intermediates used by CI."""
    return build_inventory(_EXTRACTED_TEXT)


def test_generated_inventory_passes_integrity(
    generated_inventory: dict[str, Any],
) -> None:
    validate_inventory(generated_inventory, _REPOSITORY_ROOT)


def test_truncated_attribute_inventory_is_rejected(
    generated_inventory: dict[str, Any],
) -> None:
    truncated = copy.deepcopy(generated_inventory)
    for element_name, element in truncated["elements"].items():
        if element_name not in {"Source", "Library", "Component", "Shape", "Table"}:
            element["attributes"].clear()

    remaining = sum(
        len(element["attributes"])
        for element in truncated["elements"].values()
    )
    assert remaining < MIN_ATTRIBUTE_COUNT
    with pytest.raises(ValueError, match="expected at least 500 attributes"):
        validate_inventory(truncated, _REPOSITORY_ROOT)


def test_substituted_source_digest_is_rejected(
    generated_inventory: dict[str, Any],
) -> None:
    substituted = copy.deepcopy(generated_inventory)
    substituted["sources"][0]["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="does not match the reviewed manifest"):
        validate_inventory(substituted, _REPOSITORY_ROOT)


def test_tampered_extracted_text_bundle_is_rejected(
    generated_inventory: dict[str, Any],
    tmp_path: Path,
) -> None:
    destination = tmp_path / "reference/diptrace-xml/extracted_text"
    shutil.copytree(_EXTRACTED_TEXT, destination)
    tampered_path = destination / "DipTraceXML_Pcb_En.pages.json"
    tampered_path.write_bytes(tampered_path.read_bytes() + b" ")

    with pytest.raises(ValueError, match="bundle SHA-256"):
        validate_inventory(generated_inventory, tmp_path)
