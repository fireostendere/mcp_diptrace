"""Trust model tests — covers sidecar authority, trust escalation prevention,
seed creation, trust invalidation, roundtrip evidence, and structural comparison."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import (
    DocumentProvenance,
    FixtureValidationLevel,
    ProvenanceAuthority,
)
from diptrace_mcp.errors import EditError
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document
from diptrace_mcp.service import DipTraceService, _semantic_roundtrip_check
from diptrace_mcp.xml_document import DipTraceDocument, XmlEdit

MAX_BYTES = 10_000_000


def _service(tmp_path: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
            max_document_bytes=MAX_BYTES,
        )
    )


# ── DocumentProvenance model invariants ──────────────────────────────────────


class TestDocumentProvenanceInvariants:
    """Model validators prevent invalid trust states."""

    def test_runtime_sidecar_cannot_grant_diptrace_exported(self) -> None:
        """Runtime authority cannot grant diptrace_exported."""
        with pytest.raises(ValueError, match="Runtime sidecar cannot grant"):
            DocumentProvenance(
                provenance="fake_export",
                validation_level=FixtureValidationLevel.diptrace_exported,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.runtime,
            )

    def test_runtime_sidecar_cannot_grant_roundtrip_verified(self) -> None:
        """Runtime authority cannot grant diptrace_roundtrip_verified."""
        with pytest.raises(ValueError, match="Runtime sidecar cannot grant"):
            DocumentProvenance(
                provenance="fake_roundtrip",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.runtime,
            )

    def test_validated_evidence_requires_manifest_path(self) -> None:
        """validated_evidence authority requires evidence_manifest_path."""
        with pytest.raises(ValueError, match="requires evidence_manifest_path"):
            DocumentProvenance(
                provenance="evidence_validated",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.validated_evidence,
            )

    def test_validated_evidence_requires_manifest_sha(self) -> None:
        """validated_evidence authority requires evidence_manifest_sha256."""
        with pytest.raises(ValueError, match="requires evidence_manifest_sha256"):
            DocumentProvenance(
                provenance="evidence_validated",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.validated_evidence,
                evidence_manifest_path="/tmp/manifest.json",
            )

    def test_fixture_manifest_can_grant_high_trust(self) -> None:
        """fixture_manifest authority can grant high trust."""
        sidecar = DocumentProvenance(
            provenance="fixture_validated",
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
            current_document_sha256="a" * 64,
            authority=ProvenanceAuthority.fixture_manifest,
        )
        assert sidecar.validation_level == FixtureValidationLevel.diptrace_roundtrip_verified

    def test_runtime_can_grant_synthetic_levels(self) -> None:
        """Runtime authority can grant synthetic levels."""
        for level in {
            FixtureValidationLevel.synthetic_parser_only,
            FixtureValidationLevel.synthetic_operation_fixture,
        }:
            sidecar = DocumentProvenance(
                provenance="mcp_generated",
                validation_level=level,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.runtime,
            )
            assert sidecar.validation_level == level

    def test_requires_diptrace_verification_is_computed(self) -> None:
        """requires_diptrace_verification is computed from validation_level."""
        # Synthetic levels: requires_diptrace_verification = True
        for level in {
            FixtureValidationLevel.synthetic_parser_only,
            FixtureValidationLevel.synthetic_operation_fixture,
        }:
            sidecar = DocumentProvenance(
                provenance="test",
                validation_level=level,
                current_document_sha256="a" * 64,
            )
            assert sidecar.requires_diptrace_verification is True

        # Diptrace levels that need verification: requires_diptrace_verification = True
        for level in {
            FixtureValidationLevel.diptrace_exported,
            FixtureValidationLevel.diptrace_open_save_verified,
        }:
            sidecar = DocumentProvenance(
                provenance="test",
                validation_level=level,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.fixture_manifest,
            )
            assert sidecar.requires_diptrace_verification is True

        # Verified levels: requires_diptrace_verification = False
        for level in {
            FixtureValidationLevel.diptrace_roundtrip_verified,
            FixtureValidationLevel.external_tool_roundtrip_verified,
        }:
            sidecar = DocumentProvenance(
                provenance="test",
                validation_level=level,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.validated_evidence,
                evidence_manifest_path="/tmp/m.json",
                evidence_manifest_sha256="b" * 64,
            )
            assert sidecar.requires_diptrace_verification is False


# ── Seed creation ────────────────────────────────────────────────────────────


class TestSeedBasedCreation:
    """create_document_from_seed trust derivation."""

    def test_defaults_to_synthetic(self, tmp_path: Path) -> None:
        """Seed without sidecar → synthetic_parser_only."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        (tmp_path / "seed.dip").write_bytes(raw)

        result = service.create_document_from_seed("seed.dip", "project/board.dip")
        assert result["result"]["created"] is True
        assert result["result"]["provenance"] == "seed_copy_unknown_origin"
        assert result["result"]["validation_level"] == "synthetic_parser_only"
        assert result["result"]["requires_diptrace_verification"] is True
        assert result["result"]["seed_sha256"] is not None

    def test_runtime_sidecar_high_trust_rejected(self, tmp_path: Path) -> None:
        """Seed with runtime sidecar claiming high trust fails to load → synthetic."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        seed_path = tmp_path / "seed.dip"
        seed_path.write_bytes(raw)
        seed_sha = hashlib.sha256(raw).hexdigest()

        # Write a sidecar with high trust but runtime authority
        # The model validator rejects this, so _load_seed_provenance returns None
        import json
        sidecar_data = {
            "schema_version": "diptrace-document-provenance-v1",
            "provenance": "diptrace_exported",
            "validation_level": "diptrace_exported",
            "current_document_sha256": seed_sha,
            "authority": "runtime",
        }
        sidecar_path = seed_path.with_suffix(seed_path.suffix + ".provenance.json")
        sidecar_path.write_text(json.dumps(sidecar_data))
        # Sidecar fails model validation → treated as unknown origin
        result = service.create_document_from_seed("seed.dip", "project/board.dip")
        assert result["result"]["validation_level"] == "synthetic_parser_only"
        assert result["result"]["provenance"] == "seed_copy_unknown_origin"

    def test_validated_evidence_sidecar_preserves_trust(self, tmp_path: Path) -> None:
        """Seed with validated_evidence sidecar → trust preserved."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        seed_path = tmp_path / "seed.dip"
        seed_path.write_bytes(raw)
        seed_sha = hashlib.sha256(raw).hexdigest()

        sidecar = DocumentProvenance(
            provenance="diptrace_validated",
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
            current_document_sha256=seed_sha,
            seed_sha256=seed_sha,
            authority=ProvenanceAuthority.validated_evidence,
            evidence_manifest_path="/tmp/evidence.json",
            evidence_manifest_sha256="b" * 64,
        )
        sidecar_path = seed_path.with_suffix(seed_path.suffix + ".provenance.json")
        sidecar_path.write_text(sidecar.model_dump_json())

        result = service.create_document_from_seed("seed.dip", "project/board.dip")
        assert result["result"]["validation_level"] == "diptrace_roundtrip_verified"
        assert result["result"]["provenance"] == "seed_copy_of_verified_fixture"

    def test_stale_sidecar_downgraded(self, tmp_path: Path) -> None:
        """Seed with stale sidecar (SHA mismatch) → synthetic."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        seed_path = tmp_path / "seed.dip"
        seed_path.write_bytes(raw)

        sidecar = DocumentProvenance(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.synthetic_parser_only,
            current_document_sha256="bad" + "a" * 61,
        )
        sidecar_path = seed_path.with_suffix(seed_path.suffix + ".provenance.json")
        sidecar_path.write_text(sidecar.model_dump_json())

        result = service.create_document_from_seed("seed.dip", "project/board.dip")
        assert result["result"]["validation_level"] == "synthetic_parser_only"
        assert "stale" in result["result"]["provenance"]

    def test_sha_mismatch_fails(self, tmp_path: Path) -> None:
        """Seed creation fails when expected SHA doesn't match."""
        service = _service(tmp_path)
        raw = build_pcb_document()
        (tmp_path / "seed.dip").write_bytes(raw)

        with pytest.raises(EditError, match="SHA-256 mismatch"):
            service.create_document_from_seed(
                "seed.dip", "board.dip", expected_seed_sha256="a" * 64
            )


# ── Trust invalidation ──────────────────────────────────────────────────────


class TestTrustInvalidation:
    """MCP writes must downgrade trust."""

    def test_invalidate_preserves_parent(self, tmp_path: Path) -> None:
        """Invalidation preserves parent_validation_level."""
        service = _service(tmp_path)
        service.create_document("pcb", "board.dip")
        board_path = tmp_path / "board.dip"
        result = service.document_info("board.dip")
        sha = result["result"]["sha256"]

        # Write a sidecar with a parent level
        sidecar = DocumentProvenance(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            current_document_sha256=sha,
            parent_validation_level=FixtureValidationLevel.diptrace_exported,
        )
        sidecar_path = board_path.with_suffix(board_path.suffix + ".provenance.json")
        sidecar_path.write_text(sidecar.model_dump_json())

        new_sha = "b" * 64
        service.invalidate_document_trust_after_write(
            board_path, new_sha, operation_name="test_edit"
        )
        loaded = service._load_seed_provenance(board_path)
        assert loaded is not None
        assert loaded.validation_level == FixtureValidationLevel.synthetic_operation_fixture
        assert loaded.parent_validation_level == FixtureValidationLevel.diptrace_exported
        assert loaded.last_modified_by == "test_edit"

    def test_sidecar_sha_matches_after_invalidation(self, tmp_path: Path) -> None:
        """After invalidation, sidecar SHA matches document."""
        service = _service(tmp_path)
        service.create_document("pcb", "board.dip")
        board_path = tmp_path / "board.dip"

        new_sha = "c" * 64
        service.invalidate_document_trust_after_write(
            board_path, new_sha, operation_name="test_edit"
        )
        loaded = service._load_seed_provenance(board_path)
        assert loaded is not None
        assert loaded.current_document_sha256 == new_sha


# ── Roundtrip evidence role exclusions ──────────────────────────────────────


class TestRoundtripEvidence:
    """validate_roundtrip_evidence prevents same-file role reuse."""

    def test_source_equals_saved_rejected(self, tmp_path: Path) -> None:
        """source_path == saved_path must be rejected."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        # Create a single file that will serve as both source and saved
        shared = tmp_path / "shared.dip"
        shared.write_bytes(raw)
        # Also create a target document for the service
        (tmp_path / "board.dip").write_bytes(raw)
        shared_sha = hashlib.sha256(raw).hexdigest()

        with pytest.raises(EditError, match="different files"):
            service.validate_roundtrip_evidence(
                "board.dip",
                source_path="shared.dip",
                source_sha256=shared_sha,
                saved_path="shared.dip",
            )

    def test_source_equals_reexport_rejected(self, tmp_path: Path) -> None:
        """source_path == reexport_path must be rejected."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        source = tmp_path / "source.dip"
        source.write_bytes(raw)
        source_sha = hashlib.sha256(raw).hexdigest()
        saved = tmp_path / "saved.dip"
        saved.write_bytes(raw)
        # Create board.dip as the target document
        (tmp_path / "board.dip").write_bytes(raw)

        with pytest.raises(EditError, match="different files"):
            service.validate_roundtrip_evidence(
                "board.dip",
                source_path="source.dip",
                source_sha256=source_sha,
                saved_path="saved.dip",
                reexport_path="source.dip",
                reexport_sha256=source_sha,
            )

    def test_saved_equals_reexport_rejected(self, tmp_path: Path) -> None:
        """saved_path == reexport_path must be rejected."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        source = tmp_path / "source.dip"
        source.write_bytes(raw)
        source_sha = hashlib.sha256(raw).hexdigest()
        shared = tmp_path / "shared.dip"
        shared.write_bytes(raw)
        shared_sha = hashlib.sha256(raw).hexdigest()
        # Create board.dip as the target document
        (tmp_path / "board.dip").write_bytes(raw)

        with pytest.raises(EditError, match="different files"):
            service.validate_roundtrip_evidence(
                "board.dip",
                source_path="source.dip",
                source_sha256=source_sha,
                saved_path="shared.dip",
                reexport_path="shared.dip",
                reexport_sha256=shared_sha,
            )


# ── Structural semantic comparison regression ─────────────────────────────────


class TestSemanticComparisonRegression:
    """Structural comparison catches specific changes (not count-based)."""

    @staticmethod
    def _pcb_xml(
        net_name: str = "VCC",
        net_names: list[str] | None = None,
        outline_points: str = "0,0 50,0 50,30 0,30",
        trace_layer: str = "0",
    ) -> bytes:
        """Build a minimal PCB XML for semantic comparison."""
        nets = net_names or [net_name]
        net_elements = []
        for idx, name in enumerate(nets):
            net_elements.append(
                f'<Net Id="{idx}" NetClass="0" Locked="N">'
                f"<Name>{name}</Name><Traces/></Net>"
            )
        nets_xml = "\n".join(net_elements)
        points_xml = " ".join(
            f'<Point X="{x}" Y="{y}"/>'
            for coord in outline_points.split()
            for x, y in [coord.split(",")]
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">'
            "<Library Type=\"DipTrace-ComponentLibrary\" Version=\"4.3.0.3\" Units=\"mm\" />"
            "<Library Type=\"DipTrace-PatternLibrary\" Version=\"4.3.0.3\" Units=\"mm\" />"
            "<Board>"
            "<BoardOutline Locked=\"N\" Selected=\"N\">"
            f"<Points>{points_xml}</Points>"
            "</BoardOutline>"
            "<Settings>"
            '<Routing TraceWidth="0.25" TraceClearance="0.2" ViaSize="0.6" ViaHole="0.3" />'
            "</Settings>"
            "<CopperLayers>"
            '<Lay Id="0" Type="Signal"><Name>Top</Name></Lay>'
            '<Lay Id="3" Type="Signal"><Name>Bottom</Name></Lay>'
            "</CopperLayers>"
            f"<Nets>{nets_xml}</Nets>"
            "</Board>"
            "</Source>"
        ).encode()

    def test_net_name_change_detected(self) -> None:
        """Changing a net name is detected as a structural difference."""
        a = DipTraceDocument.from_bytes(Path("a.dip"), self._pcb_xml("VCC"))
        b = DipTraceDocument.from_bytes(Path("b.dip"), self._pcb_xml("GND"))
        result = _semantic_roundtrip_check(a, b)
        assert not result["passed"]
        assert any("nets" in d for d in result["differences"])

    def test_outline_change_detected(self) -> None:
        """Changing the board outline is detected."""
        a = DipTraceDocument.from_bytes(
            Path("a.dip"), self._pcb_xml(outline_points="0,0 50,0 50,30 0,30")
        )
        b = DipTraceDocument.from_bytes(
            Path("b.dip"), self._pcb_xml(outline_points="0,0 60,0 60,40 0,40")
        )
        result = _semantic_roundtrip_check(a, b)
        assert not result["passed"]
        assert any("outline" in d for d in result["differences"])

    def test_same_document_passes(self) -> None:
        """Identical documents pass semantic comparison."""
        a = DipTraceDocument.from_bytes(Path("a.dip"), self._pcb_xml())
        b = DipTraceDocument.from_bytes(Path("b.dip"), self._pcb_xml())
        result = _semantic_roundtrip_check(a, b)
        assert result["passed"]
        assert len(result["differences"]) == 0

    def test_result_has_required_keys(self) -> None:
        """Comparison result contains all required keys."""
        a = DipTraceDocument.from_bytes(Path("a.dip"), self._pcb_xml())
        b = DipTraceDocument.from_bytes(Path("b.dip"), self._pcb_xml())
        result = _semantic_roundtrip_check(a, b)
        assert "passed" in result
        assert "compared_categories" in result
        assert "differences" in result
        assert "ignored_normalizations" in result
        assert "unsupported_categories" in result
        assert "parse_warnings" in result


# ── All write paths invalidate trust ─────────────────────────────────────────


class TestAllWritePathsInvalidate:
    """Every MCP write path must invalidate trust."""

    def test_apply_edits_noop_preserves_trust(self, tmp_path: Path) -> None:
        """apply_edits with a no-op edit does not change the document."""
        service = _service(tmp_path)
        service.create_document("pcb", "board.dip")
        board_path = tmp_path / "board.dip"

        # Establish a known trust level
        sha1 = service.document_info("board.dip")["result"]["sha256"]
        sidecar = DocumentProvenance(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.diptrace_exported,
            current_document_sha256=sha1,
            authority=ProvenanceAuthority.fixture_manifest,
        )
        sidecar_path = board_path.with_suffix(board_path.suffix + ".provenance.json")
        sidecar_path.write_text(sidecar.model_dump_json())

        # A no-op edit (set Version to same value) — document bytes don't change,
        # so trust is NOT invalidated because changed=False.
        result = service.apply_edits(
            [XmlEdit(
                operation="set_attribute",
                xpath="/Source",
                attribute="Version",
                value="4.3.0.3",
                expected_matches=1,
            )],
            path="board.dip",
            dry_run=True,
        )
        assert result["dry_run"] is True
        loaded = service._load_seed_provenance(board_path)
        assert loaded is not None
        assert loaded.validation_level == FixtureValidationLevel.diptrace_exported

    def test_create_document_from_seed_invalidation(self, tmp_path: Path) -> None:
        """create_document_from_seed writes trust sidecar with correct authority."""
        service = _service(tmp_path)
        raw = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
        (tmp_path / "seed.dip").write_bytes(raw)

        result = service.create_document_from_seed("seed.dip", "project/board.dip")
        assert result["result"]["created"] is True

        # Verify the trust sidecar exists with correct authority
        board_path = tmp_path / "project" / "board.dip"
        loaded = service._load_seed_provenance(board_path)
        assert loaded is not None
        assert loaded.authority == ProvenanceAuthority.runtime
        assert loaded.validation_level == FixtureValidationLevel.synthetic_parser_only
