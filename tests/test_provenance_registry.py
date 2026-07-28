from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import (
    DocumentProvenance,
    EvidenceAuthority,
    EvidenceFileRecord,
    FixtureValidationLevel,
    ProvenanceAuthority,
    SemanticComparisonEvidence,
    TrustedRoundtripEvidence,
)
from diptrace_mcp.provenance_registry import (
    RegistryAuthorizationError,
    TrustedProvenanceRegistry,
    TrustedProvenanceRegistryEntry,
    TrustedProvenanceRegistryFile,
    canonical_registry_bytes,
)
from diptrace_mcp.scaffolding import PcbScaffold, build_pcb_document
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import utc_now


def _write_registry(
    path: Path,
    *,
    document_sha256: str,
    evidence_manifest_sha256: str,
    evidence_manifest_source: str = "reviewed/synthetic-evidence.json",
    source_type: str = "DipTrace-PCB",
    validation_level: FixtureValidationLevel = FixtureValidationLevel.diptrace_exported,
) -> TrustedProvenanceRegistry:
    registry = TrustedProvenanceRegistryFile(
        entries=[
            TrustedProvenanceRegistryEntry(
                entry_id="synthetic-test-entry",
                document_sha256=document_sha256,
                evidence_manifest_sha256=evidence_manifest_sha256,
                evidence_manifest_source=evidence_manifest_source,
                source_type=source_type,
                validation_level=validation_level,
            )
        ]
    )
    path.write_bytes(canonical_registry_bytes(registry))
    return TrustedProvenanceRegistry.from_path(path)


def _trusted_evidence(
    *,
    document_path: Path,
    document_sha256: str,
) -> TrustedRoundtripEvidence:
    source = EvidenceFileRecord(
        path=str(document_path.with_name("source.dip")),
        sha256=document_sha256,
        source_type="DipTrace-PCB",
    )
    saved = EvidenceFileRecord(
        path=str(document_path),
        sha256=document_sha256,
        source_type="DipTrace-PCB",
    )
    return TrustedRoundtripEvidence(
        authority=EvidenceAuthority.trusted_registry,
        document_path=str(document_path),
        document_sha256=document_sha256,
        source=source,
        saved=saved,
        semantic_comparison=SemanticComparisonEvidence(
            passed=True,
            comparison_complete=True,
            compared_categories=["source_type"],
        ),
        validation_level=FixtureValidationLevel.diptrace_exported,
        status="passed",
        created_at=utc_now(),
        created_by="synthetic_registry_unit_test",
    )


def test_embedded_registry_is_packaged_canonical_and_empty() -> None:
    raw = (
        resources.files("diptrace_mcp")
        .joinpath("data")
        .joinpath("trusted_provenance_registry.json")
        .read_bytes()
    )
    registry = TrustedProvenanceRegistry.load_embedded()

    assert registry.entry_count == 0
    assert registry.report()["high_trust_currently_available"] is False
    assert registry.report()["every_entry_requires_human_review"] is True
    assert TrustedProvenanceRegistry.from_bytes(
        raw,
        source_label="packaged-test",
    ).entry_count == 0


@pytest.mark.parametrize(
    "source",
    [
        "../evidence.json",
        "/absolute/evidence.json",
        "C:/evidence.json",
        r"reviewed\evidence.json",
        "reviewed/./evidence.json",
    ],
)
def test_registry_rejects_evidence_source_path_injection(source: str) -> None:
    with pytest.raises(ValueError, match="repository-relative POSIX path"):
        TrustedProvenanceRegistryEntry(
            entry_id="synthetic-test-entry",
            document_sha256="a" * 64,
            evidence_manifest_sha256="b" * 64,
            evidence_manifest_source=source,
            source_type="DipTrace-PCB",
            validation_level=FixtureValidationLevel.diptrace_exported,
        )


def test_registry_requires_canonical_json() -> None:
    noncanonical = json.dumps(
        {
            "schema_version": "diptrace-trusted-provenance-registry-v1",
            "entries": [],
        }
    ).encode()
    with pytest.raises(ValueError, match="canonical deterministic JSON"):
        TrustedProvenanceRegistry.from_bytes(
            noncanonical,
            source_label="noncanonical-test",
        )


def test_registry_source_bytes_are_hash_bound(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    evidence_path = tmp_path / "reviewed" / "synthetic-evidence.json"
    evidence_path.parent.mkdir()
    evidence_path.write_bytes(b"reviewed evidence")
    wrong_sha = hashlib.sha256(b"different evidence").hexdigest()
    registry = TrustedProvenanceRegistryFile(
        entries=[
            TrustedProvenanceRegistryEntry(
                entry_id="synthetic-test-entry",
                document_sha256="a" * 64,
                evidence_manifest_sha256=wrong_sha,
                evidence_manifest_source="reviewed/synthetic-evidence.json",
                source_type="DipTrace-PCB",
                validation_level=FixtureValidationLevel.diptrace_exported,
            )
        ]
    )
    registry_path.write_bytes(canonical_registry_bytes(registry))

    with pytest.raises(ValueError, match="evidence source SHA mismatch"):
        TrustedProvenanceRegistry.from_path(registry_path)


def test_registry_source_metadata_must_match_entry(tmp_path: Path) -> None:
    document_path = tmp_path / "board.dip"
    document_bytes = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    document_path.write_bytes(document_bytes)
    document_sha256 = hashlib.sha256(document_bytes).hexdigest()
    evidence_path = tmp_path / "reviewed" / "synthetic-evidence.json"
    evidence_path.parent.mkdir()
    evidence_path.write_text(
        _trusted_evidence(
            document_path=document_path,
            document_sha256=document_sha256,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    registry_path = tmp_path / "registry.json"
    registry_file = TrustedProvenanceRegistryFile(
        entries=[
            TrustedProvenanceRegistryEntry(
                entry_id="synthetic-test-entry",
                document_sha256="b" * 64,
                evidence_manifest_sha256=evidence_sha256,
                evidence_manifest_source="reviewed/synthetic-evidence.json",
                source_type="DipTrace-PCB",
                validation_level=FixtureValidationLevel.diptrace_exported,
            )
        ]
    )
    registry_path.write_bytes(canonical_registry_bytes(registry_file))

    with pytest.raises(ValueError, match="evidence metadata mismatch"):
        TrustedProvenanceRegistry.from_path(registry_path)


def test_registered_exact_binding_constructs_and_resolves_trust(tmp_path: Path) -> None:
    document_path = tmp_path / "board.dip"
    document_bytes = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    document_path.write_bytes(document_bytes)
    document_sha256 = hashlib.sha256(document_bytes).hexdigest()

    evidence = _trusted_evidence(
        document_path=document_path,
        document_sha256=document_sha256,
    )
    evidence_path = tmp_path / "reviewed" / "synthetic-evidence.json"
    evidence_path.parent.mkdir()
    evidence_path.write_text(evidence.model_dump_json(indent=2), encoding="utf-8")
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()

    registry = _write_registry(
        tmp_path / "registry.json",
        document_sha256=document_sha256,
        evidence_manifest_sha256=evidence_sha256,
    )
    sidecar = registry.create_provenance(
        entry_id="synthetic-test-entry",
        document_sha256=document_sha256,
        evidence_manifest_path=str(evidence_path),
        evidence_manifest_sha256=evidence_sha256,
        source_type="DipTrace-PCB",
        validation_level=FixtureValidationLevel.diptrace_exported,
    )
    document_path.with_suffix(".dip.provenance.json").write_text(
        sidecar.model_dump_json(indent=2),
        encoding="utf-8",
    )

    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
        )
    )
    # Production always loads the embedded registry. This isolated synthetic
    # verifier test substitutes a temporary registry without editing or
    # promoting any repository fixture.
    service._trusted_provenance_registry = registry

    result = service.document_info("board.dip")["result"]
    assert result["validation_level"] == "diptrace_exported"
    assert result["trust_authority"] == "trusted_registry"
    assert result["requires_diptrace_verification"] is True

    copied = service.create_document_from_seed("board.dip", "copy.dip")["result"]
    assert copied["validation_level"] == "synthetic_parser_only"
    assert (
        copied["provenance"]
        == "seed_copy_trusted_registry_requires_target_evidence"
    )


def test_unregistered_and_mismatched_bindings_fail_closed(tmp_path: Path) -> None:
    document_path = tmp_path / "board.dip"
    document_bytes = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    document_path.write_bytes(document_bytes)
    document_sha256 = hashlib.sha256(document_bytes).hexdigest()
    evidence_path = tmp_path / "reviewed" / "synthetic-evidence.json"
    evidence_path.parent.mkdir()
    evidence_path.write_text(
        _trusted_evidence(
            document_path=document_path,
            document_sha256=document_sha256,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    registry = _write_registry(
        tmp_path / "registry.json",
        document_sha256=document_sha256,
        evidence_manifest_sha256=evidence_sha256,
    )

    with pytest.raises(
        RegistryAuthorizationError,
        match="trusted_registry_entry_unregistered",
    ):
        registry.create_provenance(
            entry_id="not-registered",
            document_sha256=document_sha256,
            evidence_manifest_path=str(evidence_path),
            evidence_manifest_sha256=evidence_sha256,
            source_type="DipTrace-PCB",
            validation_level=FixtureValidationLevel.diptrace_exported,
        )
    mismatched_bindings = [
        {
            "document_sha256": "b" * 64,
            "evidence_manifest_sha256": evidence_sha256,
            "source_type": "DipTrace-PCB",
            "validation_level": FixtureValidationLevel.diptrace_exported,
        },
        {
            "document_sha256": document_sha256,
            "evidence_manifest_sha256": "c" * 64,
            "source_type": "DipTrace-PCB",
            "validation_level": FixtureValidationLevel.diptrace_exported,
        },
        {
            "document_sha256": document_sha256,
            "evidence_manifest_sha256": evidence_sha256,
            "source_type": "DipTrace-Schematic",
            "validation_level": FixtureValidationLevel.diptrace_exported,
        },
        {
            "document_sha256": document_sha256,
            "evidence_manifest_sha256": evidence_sha256,
            "source_type": "DipTrace-PCB",
            "validation_level": FixtureValidationLevel.diptrace_open_save_verified,
        },
    ]
    for binding in mismatched_bindings:
        with pytest.raises(
            RegistryAuthorizationError,
            match="trusted_registry_binding_mismatch",
        ):
            registry.create_provenance(
                entry_id="synthetic-test-entry",
                evidence_manifest_path=str(evidence_path),
                **binding,
            )


def test_manual_unregistered_sidecar_resolves_fail_closed(tmp_path: Path) -> None:
    document_path = tmp_path / "board.dip"
    document_bytes = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    document_path.write_bytes(document_bytes)
    document_sha256 = hashlib.sha256(document_bytes).hexdigest()
    evidence_path = tmp_path / "unreviewed-evidence.json"
    evidence_path.write_text(
        _trusted_evidence(
            document_path=document_path,
            document_sha256=document_sha256,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    sidecar = DocumentProvenance(
        provenance="manually_self_minted",
        validation_level=FixtureValidationLevel.diptrace_exported,
        current_document_sha256=document_sha256,
        authority=ProvenanceAuthority.trusted_registry,
        evidence_manifest_path=str(evidence_path),
        evidence_manifest_sha256=evidence_sha256,
        trusted_registry_entry_id="not-registered",
    )
    document_path.with_suffix(".dip.provenance.json").write_text(
        sidecar.model_dump_json(),
        encoding="utf-8",
    )
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
        )
    )

    result = service.document_info("board.dip")["result"]
    assert result["validation_level"] == "synthetic_parser_only"
    assert result["requires_diptrace_verification"] is True
    assert result["trust_warnings"][0]["code"] == "trusted_registry_entry_unregistered"


def test_tampered_workspace_manifest_loses_registry_trust(tmp_path: Path) -> None:
    document_path = tmp_path / "board.dip"
    document_bytes = build_pcb_document(PcbScaffold(width_mm=50.0, height_mm=30.0))
    document_path.write_bytes(document_bytes)
    document_sha256 = hashlib.sha256(document_bytes).hexdigest()
    evidence_path = tmp_path / "reviewed" / "synthetic-evidence.json"
    evidence_path.parent.mkdir()
    evidence_path.write_text(
        _trusted_evidence(
            document_path=document_path,
            document_sha256=document_sha256,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    registry = _write_registry(
        tmp_path / "registry.json",
        document_sha256=document_sha256,
        evidence_manifest_sha256=evidence_sha256,
    )
    sidecar = registry.create_provenance(
        entry_id="synthetic-test-entry",
        document_sha256=document_sha256,
        evidence_manifest_path=str(evidence_path),
        evidence_manifest_sha256=evidence_sha256,
        source_type="DipTrace-PCB",
        validation_level=FixtureValidationLevel.diptrace_exported,
    )
    document_path.with_suffix(".dip.provenance.json").write_text(
        sidecar.model_dump_json(),
        encoding="utf-8",
    )
    service = DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
        )
    )
    service._trusted_provenance_registry = registry

    evidence_path.write_text('{"tampered":true}', encoding="utf-8")
    result = service.document_info("board.dip")["result"]
    assert result["validation_level"] == "synthetic_parser_only"
    assert result["requires_diptrace_verification"] is True
    assert result["trust_warnings"][0]["code"] == "evidence_manifest_sha_mismatch"
