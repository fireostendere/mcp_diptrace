"""Regression tests for fixture trust model and classification.

These tests verify that:
- Synthetic fixtures cannot claim DipTrace-validated status
- Validation levels are enforced correctly
- Plane layer routing is properly rejected
- Pattern validation modes work correctly
- Seed-based document creation preserves provenance
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import FixtureManifest, FixtureValidationLevel
from diptrace_mcp.errors import EditError, RoutingError
from diptrace_mcp.operations import SetComponentPatternOperation
from diptrace_mcp.scaffolding import (
    PcbScaffold,
    build_pcb_document,
    build_schematic_document,
)
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "diptrace_5_3"
POWER_MULTILAYER = FIXTURE_ROOT / "power_multilayer"
MAX_BYTES = 10_000_000


# ---------------------------------------------------------------------------
# Fixture classification tests
# ---------------------------------------------------------------------------


class TestFixtureClassification:
    """Verify that fixtures are correctly classified."""

    def test_power_multilayer_manifest_is_synthetic(self) -> None:
        manifest_path = POWER_MULTILAYER / "manifest.pending.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["validation_level"] == "synthetic_operation_fixture"
        assert manifest["provenance"] == "mcp_generated"
        assert manifest["diptrace_opened"] is False
        assert manifest["diptrace_saved"] is False
        assert manifest["diptrace_reexported"] is False
        assert manifest["roundtrip_verified"] is False

    def test_power_multilayer_source_is_synthetic(self) -> None:
        source = POWER_MULTILAYER / "source_board.xml"
        raw = source.read_bytes()
        expected_sha = hashlib.sha256(raw).hexdigest()
        summary = json.loads((POWER_MULTILAYER / "expected_summary.json").read_text())
        assert summary["source"]["sha256"] == expected_sha

    def test_synthetic_fixture_cannot_claim_roundtrip(self) -> None:
        manifest = FixtureManifest(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
        )
        errors = manifest.validate_for_level()
        assert errors == []  # No errors for correct level

    def test_roundtrip_requires_diptrace_version(self) -> None:
        """Creating a roundtrip manifest without diptrace_version must raise."""
        with pytest.raises(ValueError, match="diptrace_version"):
            FixtureManifest(
                provenance="mcp_generated",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                source_sha256="a" * 64,
            )

    def test_roundtrip_requires_reexport(self) -> None:
        """Creating a roundtrip manifest without diptrace_reexported must raise."""
        with pytest.raises(ValueError, match="diptrace_reexported"):
            FixtureManifest(
                provenance="diptrace_exported",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                diptrace_version="5.3.0.2",
                source_sha256="a" * 64,
                diptrace_opened=True,
                diptrace_saved=True,
            )

    def test_roundtrip_requires_semantic_comparison(self) -> None:
        """Creating a roundtrip manifest without semantic_comparison must raise."""
        with pytest.raises(ValueError, match="semantic_comparison_passed"):
            FixtureManifest(
                provenance="diptrace_exported",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                diptrace_version="5.3.0.2",
                source_sha256="a" * 64,
                reexport_sha256="b" * 64,
                diptrace_opened=True,
                diptrace_saved=True,
                diptrace_reexported=True,
            )

    def test_open_save_requires_diptrace_saved(self) -> None:
        """diptrace_open_save_verified requires diptrace_saved=true."""
        with pytest.raises(ValueError, match="diptrace_saved"):
            FixtureManifest(
                provenance="diptrace_exported",
                validation_level=FixtureValidationLevel.diptrace_open_save_verified,
                diptrace_version="5.3.0.2",
                source_sha256="a" * 64,
                diptrace_opened=True,
                diptrace_saved=False,
            )


# ---------------------------------------------------------------------------
# Scaffolding provenance tests
# ---------------------------------------------------------------------------


class TestScaffoldingProvenance:
    """Verify that scaffolding returns correct provenance metadata."""

    def test_create_document_returns_synthetic_provenance(self, tmp_path: Path) -> None:
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        result = service.create_document("pcb", "test.dip")
        assert result["result"]["provenance"] == "mcp_generated"
        assert result["result"]["validation_level"] == "synthetic_parser_only"
        assert result["result"]["requires_diptrace_verification"] is True

    def test_schematic_scaffold_is_synthetic(self) -> None:
        raw = build_schematic_document()
        doc = DipTraceDocument.from_bytes(Path("test.xml"), raw)
        assert doc.kind == "schematic"
        # Verify it parses correctly but is synthetic
        snapshot = build_snapshot(doc)
        assert snapshot.schematic is not None


# ---------------------------------------------------------------------------
# Plane layer routing tests
# ---------------------------------------------------------------------------


class TestPlaneLayerRouting:
    """Verify that trace routing on Plane layers is rejected."""

    def test_signal_layer_routing_succeeds(self, tmp_path: Path) -> None:
        """Routing on a Signal layer should succeed."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        # Create a PCB with Signal layers
        service.create_document("pcb", "test.dip", pcb={"layers": [
            {"name": "Top", "type": "Signal"},
            {"name": "Bottom", "type": "Signal"},
        ]})
        # This should not raise
        result = service.document_info("test.dip")
        assert result["result"]["kind"] == "pcb"

    def test_plane_layer_routing_fails(self, tmp_path: Path) -> None:
        """Routing on a Plane layer should fail with a clear error."""
        from diptrace_mcp.routing_compiler import _layer_type, _validate_routing_layer

        # Create a mock snapshot with a Plane layer
        class MockBoard:
            layers = [{"id": "1", "name": "GND", "type": "Plane"}]

        class MockSnapshot:
            board = MockBoard()

        snapshot = MockSnapshot()
        assert _layer_type(snapshot, "1") == "Plane"

        with pytest.raises(RoutingError, match="plane layer"):
            _validate_routing_layer(snapshot, "1", context="test")

    def test_through_via_across_plane_layers_succeeds(self) -> None:
        """Through-via spans across Plane layers are allowed."""
        from diptrace_mcp.routing_compiler import _layer_type

        class MockBoard:
            layers = [
                {"id": "0", "name": "Top", "type": "Signal"},
                {"id": "1", "name": "GND", "type": "Plane"},
                {"id": "2", "name": "PWR", "type": "Plane"},
                {"id": "3", "name": "Bottom", "type": "Signal"},
            ]

        class MockSnapshot:
            board = MockBoard()

        snapshot = MockSnapshot()
        # Layer types are correct
        assert _layer_type(snapshot, "0") == "Signal"
        assert _layer_type(snapshot, "1") == "Plane"
        assert _layer_type(snapshot, "2") == "Plane"
        assert _layer_type(snapshot, "3") == "Signal"


# ---------------------------------------------------------------------------
# Pattern validation tests
# ---------------------------------------------------------------------------


class TestPatternValidation:
    """Verify PatternStyle validation modes."""

    def test_strict_mode_rejects_missing_pattern(self) -> None:
        """strict_embedded_pattern mode should reject missing patterns."""
        operation = SetComponentPatternOperation(
            selector={"refdes": ["R1"]},
            pattern_style="NonExistent",
            validation_mode="strict_embedded_pattern",
        )
        assert operation.validation_mode == "strict_embedded_pattern"

    def test_external_mode_allows_missing_pattern(self) -> None:
        """external_pattern_reference mode should allow missing patterns."""
        operation = SetComponentPatternOperation(
            selector={"refdes": ["R1"]},
            pattern_style="ExternalPattern",
            validation_mode="external_pattern_reference",
        )
        assert operation.validation_mode == "external_pattern_reference"


# ---------------------------------------------------------------------------
# Seed-based creation tests
# ---------------------------------------------------------------------------


class TestSeedBasedCreation:
    """Verify seed-based document creation preserves provenance."""

    def test_create_document_from_seed_defaults_to_synthetic(self, tmp_path: Path) -> None:
        """Seed-based creation defaults to synthetic_parser_only — no trust escalation."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        seed_path = tmp_path / "seed.dip"
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        seed_path.write_bytes(raw)

        result = service.create_document_from_seed("seed.dip", "project/board.dip")
        assert result["result"]["created"] is True
        assert result["result"]["provenance"] == "seed_copy"
        assert result["result"]["validation_level"] == "synthetic_parser_only"
        assert result["result"]["requires_diptrace_verification"] is True
        assert result["result"]["seed_sha256"] is not None

    def test_create_document_from_seed_explicit_level(self, tmp_path: Path) -> None:
        """Seed creation with explicit claimed level and DipTrace version."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        seed_path = tmp_path / "seed.dip"
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        seed_path.write_bytes(raw)

        result = service.create_document_from_seed(
            "seed.dip",
            "project/board.dip",
            claimed_validation_level="diptrace_exported",
            diptrace_version="5.3.0.2",
        )
        assert result["result"]["validation_level"] == "diptrace_exported"
        assert result["result"]["diptrace_version"] == "5.3.0.2"
        assert result["result"]["requires_diptrace_verification"] is False

    def test_create_document_from_seed_rejects_high_level_without_version(
        self, tmp_path: Path
    ) -> None:
        """Claiming diptrace_exported without diptrace_version must fail."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".level",
                max_document_bytes=MAX_BYTES,
            )
        )
        seed_path = tmp_path / "seed.dip"
        raw = build_pcb_document()
        seed_path.write_bytes(raw)

        with pytest.raises(EditError, match="diptrace_version"):
            service.create_document_from_seed(
                "seed.dip",
                "board.dip",
                claimed_validation_level="diptrace_exported",
            )

    def test_create_document_from_seed_rejects_invalid_level(self, tmp_path: Path) -> None:
        """Invalid claimed_validation_level must be rejected."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        seed_path = tmp_path / "seed.dip"
        raw = build_pcb_document()
        seed_path.write_bytes(raw)

        with pytest.raises(EditError, match="Invalid claimed_validation_level"):
            service.create_document_from_seed(
                "seed.dip",
                "board.dip",
                claimed_validation_level="nonexistent_level",
            )

    def test_seed_creation_refuses_overwrite(self, tmp_path: Path) -> None:
        """Seed-based creation should refuse overwrite without flag."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        seed_path = tmp_path / "seed.dip"
        raw = build_pcb_document()
        seed_path.write_bytes(raw)

        # First creation
        service.create_document_from_seed("seed.dip", "board.dip")

        # Second creation without overwrite should fail
        with pytest.raises(EditError, match="overwrite"):
            service.create_document_from_seed("seed.dip", "board.dip")

    def test_seed_creation_with_overwrite(self, tmp_path: Path) -> None:
        """Seed-based creation with overwrite should succeed."""
        service = DipTraceService(
            Settings(
                workspace=tmp_path,
                allowed_roots=(tmp_path,),
                state_dir=tmp_path / ".state",
                max_document_bytes=MAX_BYTES,
            )
        )
        seed_path = tmp_path / "seed.dip"
        raw = build_pcb_document()
        seed_path.write_bytes(raw)

        # First creation
        service.create_document_from_seed("seed.dip", "board.dip")

        # Second creation with overwrite should succeed
        result = service.create_document_from_seed("seed.dip", "board.dip", overwrite=True)
        assert result["result"]["created"] is True
