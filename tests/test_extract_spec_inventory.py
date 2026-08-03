"""Tests for the clean-room factual inventory generator."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from scripts.extract_spec_inventory import _canonical_json, build_inventory
from scripts.report_format_coverage import main as coverage_main

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures"


def test_inventory_generation_is_deterministic_and_factual() -> None:
    first = build_inventory(FIXTURES)
    second = build_inventory(FIXTURES)

    assert _canonical_json(first) == _canonical_json(second)
    assert first["schema_version"] == "diptrace-factual-inventory-v1"
    assert first["facts"]
    assert all(fact["source_kind"] == "synthetic_fixture" for fact in first["facts"])
    assert all("description" not in fact for fact in first["facts"])
    assert all("text" not in fact for fact in first["facts"])


def test_pdf_or_page_text_inputs_are_rejected(tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"not a source")

    with pytest.raises(ValueError, match="XML files only"):
        build_inventory(pdf)


def test_controlled_export_metadata_is_projected_without_prose(tmp_path: Path) -> None:
    source = tmp_path / "controlled.xml"
    source.write_text(
        '<Source Type="DipTrace-PCB" Version="5.3.0.2" Units="mm">'
        '<Board><Item Angle="90" /></Board></Source>',
        encoding="utf-8",
    )

    inventory = build_inventory(
        source,
        repository_root=tmp_path,
        provenance={
            "controlled.xml": {
                "source_kind": "controlled_real_export",
                "diptrace_version": "5.3.0.2",
                "diptrace_build": "test-build",
                "evidence_id": "controlled-test-export",
                "confidence": "observed",
                "redistribution_basis": "project-authored disposable test design",
                "contains_third_party_design": False,
            }
        },
    )

    assert inventory["sources"][0]["source_kind"] == "controlled_real_export"
    assert inventory["sources"][0]["diptrace_build"] == "test-build"
    assert inventory["facts"][0]["confidence"] == "observed"
    assert all("description" not in fact for fact in inventory["facts"])


def test_mixed_synthetic_and_controlled_sources_are_not_silently_merged(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.xml"
    second = tmp_path / "second.xml"
    xml = '<Source Type="DipTrace-PCB" Version="5.3.0.2"><Board /></Source>'
    first.write_text(xml, encoding="utf-8")
    second.write_text(xml.replace("Board", "Board2"), encoding="utf-8")

    with pytest.raises(ValueError, match="one source_kind"):
        build_inventory(
            [first, second],
            repository_root=tmp_path,
            provenance={
                "second.xml": {
                    "source_kind": "controlled_real_export",
                    "diptrace_build": "test-build",
                    "evidence_id": "controlled-test-export",
                    "confidence": "observed",
                    "redistribution_basis": "project-authored disposable test design",
                }
            },
        )


def test_coverage_cli_rejects_truncated_factual_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inventory = build_inventory(FIXTURES)
    truncated = copy.deepcopy(inventory)
    truncated["facts"] = truncated["facts"][:1]
    truncated["elements"] = {
        truncated["facts"][0]["element"]: truncated["elements"][
            truncated["facts"][0]["element"]
        ]
    }
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(truncated, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report_format_coverage.py",
            "--inventory",
            str(inventory_path),
            "--src",
            str(ROOT / "src/diptrace_mcp"),
            "--out",
            str(tmp_path / "coverage.md"),
            "--check",
        ],
    )

    assert coverage_main() == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.err or "differs" in captured.err
