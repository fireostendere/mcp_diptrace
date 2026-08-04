"""Controlled DipTrace document scaffolding and seed-copy writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..adapters import build_snapshot
from ..backups import BackupStore
from ..domain import (
    _HIGH_TRUST_LEVELS,
    DocumentProvenance,
    FixtureValidationLevel,
    ProvenanceAuthority,
    ValidatedEvidence,
    requires_diptrace_verification,
)
from ..errors import EditError
from ..scaffolding import (
    DEFAULT_FORMAT_VERSION,
    PcbScaffold,
    SchematicScaffold,
    build_pcb_document,
    build_schematic_document,
    validate_format_version,
)
from ..services.context import ServiceContext, read_success
from ..write_limits import WriteImpact, write_impact
from ..xml_document import (
    DipTraceDocument,
    atomic_write_bytes,
    sha256_bytes,
    write_with_backup,
)


class LoadOverwriteTarget(Protocol):
    def __call__(
        self,
        target: Path,
        *,
        overwrite: bool,
        expected_sha256: str | None,
    ) -> DipTraceDocument | None: ...


class RequireCurrentTargetSha256(Protocol):
    def __call__(self, target: Path, expected_sha256: str) -> None: ...


class RequireTargetStillAbsent(Protocol):
    def __call__(self, target: Path) -> None: ...


class LoadSeedProvenance(Protocol):
    def __call__(self, seed_path: Path) -> DocumentProvenance | None: ...


class LoadAndValidateEvidenceManifest(Protocol):
    def __call__(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> ValidatedEvidence: ...


class LoadAndAuthorizeTrustedRegistryEvidence(Protocol):
    def __call__(
        self,
        document_path: Path,
        provenance: DocumentProvenance,
    ) -> ValidatedEvidence: ...


class WriteProvenanceSidecar(Protocol):
    def __call__(self, document_path: Path, provenance: DocumentProvenance) -> None: ...


class RequireWriteImpact(Protocol):
    def __call__(self, impact: WriteImpact, *, operation: str) -> None: ...


class ScaffoldingService:
    """Implementation for synthetic document creation and exact seed copies."""

    def __init__(
        self,
        context: ServiceContext,
        backups: BackupStore,
        load_overwrite_target: LoadOverwriteTarget,
        require_current_target_sha256: RequireCurrentTargetSha256,
        require_target_still_absent: RequireTargetStillAbsent,
        load_seed_provenance: LoadSeedProvenance,
        load_and_validate_evidence_manifest: LoadAndValidateEvidenceManifest,
        load_and_authorize_trusted_registry_evidence: (LoadAndAuthorizeTrustedRegistryEvidence),
        write_provenance_sidecar: WriteProvenanceSidecar,
        require_write_impact: RequireWriteImpact,
    ) -> None:
        self.context = context
        self.backups = backups
        self.load_overwrite_target = load_overwrite_target
        self.require_current_target_sha256 = require_current_target_sha256
        self.require_target_still_absent = require_target_still_absent
        self.load_seed_provenance = load_seed_provenance
        self.load_and_validate_evidence_manifest = load_and_validate_evidence_manifest
        self.load_and_authorize_trusted_registry_evidence = (
            load_and_authorize_trusted_registry_evidence
        )
        self.write_provenance_sidecar = write_provenance_sidecar
        self.require_write_impact = require_write_impact

    def create_document(
        self,
        kind: str,
        path: str,
        *,
        sheets: list[str] | None = None,
        pcb: dict[str, Any] | None = None,
        units: str = "mm",
        format_version: str = DEFAULT_FORMAT_VERSION,
        overwrite: bool = False,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a brand-new synthetic DipTrace-shaped XML document."""

        self.context.policy.require_write(dry_run=False, operation="create_document")
        if units not in {"mm", "inch", "mil"}:
            raise EditError(f"Unsupported document units: {units!r}", code="invalid_request")
        format_version = validate_format_version(format_version)
        target = self.context.settings.resolve_allowed_path(path, must_exist=False)
        if target.exists() and not overwrite:
            raise EditError(
                f"Target already exists (pass overwrite=true to replace): {target}",
                code="path_exists",
                details={"path": str(target)},
            )
        if kind == "schematic":
            scaffold = SchematicScaffold(sheet_names=sheets) if sheets else None
            raw = build_schematic_document(scaffold, units=units, version=format_version)
        elif kind == "pcb":
            scaffold_pcb = PcbScaffold.model_validate(pcb or {})
            raw = build_pcb_document(scaffold_pcb, units=units, version=format_version)
        else:
            raise EditError(
                f"Unsupported document kind for creation: {kind!r}",
                code="invalid_request",
            )
        # Validate the generated bytes before they ever reach the filesystem.
        candidate = DipTraceDocument.from_bytes(target, raw)
        snapshot = build_snapshot(candidate)
        previous = self.load_overwrite_target(
            target,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )
        impact = write_impact(previous, candidate)
        self.require_write_impact(impact, operation="create_document")
        if previous is not None:
            assert expected_sha256 is not None
            self.require_current_target_sha256(target, expected_sha256)
            written = write_with_backup(
                target,
                raw,
                self.backups,
                expected_sha256=expected_sha256,
            )
            backup: str | None = str(written)
        else:
            self.require_target_still_absent(target)
            atomic_write_bytes(target, raw)
            backup = None
        loaded = DipTraceDocument.load(target, self.context.settings.max_document_bytes)
        if loaded.sha256 != sha256_bytes(raw):
            raise EditError(
                "Created document failed the post-write checksum verification",
                details={"path": str(target)},
            )
        info = build_snapshot(loaded).info
        # Write provenance sidecar for synthetic documents
        sidecar = DocumentProvenance(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.synthetic_parser_only,
            current_document_sha256=loaded.sha256,
        )
        self.write_provenance_sidecar(target, sidecar)
        return read_success(
            info,
            {
                "created": True,
                "kind": kind,
                "path": str(target),
                "size_bytes": len(raw),
                "sha256": loaded.sha256,
                "backup": backup,
                "write_object_count": impact.object_count,
                "summary": {
                    "sheets": len(snapshot.schematic.sheets) if snapshot.schematic else None,
                    "layers": len(snapshot.board.layers) if snapshot.board else None,
                },
                "provenance": "mcp_generated",
                "validation_level": "synthetic_parser_only",
                "requires_diptrace_verification": True,
                "format_version": loaded.version,
            },
            warnings=snapshot.warnings,
        )

    def create_document_from_seed(
        self,
        seed_path: str,
        target_path: str,
        *,
        expected_seed_sha256: str | None = None,
        overwrite: bool = False,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Create a new document by copying an existing DipTrace-shaped XML seed.

        The seed file must be valid DipTrace XML (PCB, Schematic, ComponentLibrary,
        or PatternLibrary). The copy preserves all unknown XML, line endings, and
        unsupported sections.

        **Trust model:** The client cannot assign a validation level.  Trust is
        derived exclusively from verifiable metadata (provenance sidecar or
        fixture manifest) found alongside the seed.  If no metadata is present,
        the copy defaults to ``synthetic_parser_only``.
        """
        self.context.policy.require_write(dry_run=False, operation="create_document_from_seed")
        seed = self.context.settings.resolve_allowed_path(seed_path, must_exist=True)
        seed_bytes = seed.read_bytes()
        if len(seed_bytes) > self.context.settings.max_document_bytes:
            raise EditError(
                f"Seed file exceeds max document size: {len(seed_bytes)} bytes",
                code="document_too_large",
            )
        # Pre-copy SHA check
        seed_sha256 = sha256_bytes(seed_bytes)
        if expected_seed_sha256 is not None and expected_seed_sha256 != seed_sha256:
            raise EditError(
                f"Seed SHA-256 mismatch: expected {expected_seed_sha256}, got {seed_sha256}",
                code="sha256_mismatch",
            )
        # Validate seed through the parser
        seed_doc = DipTraceDocument.from_bytes(seed, seed_bytes)
        source_type = seed_doc.source_type
        if source_type not in {
            "DipTrace-PCB",
            "DipTrace-Schematic",
            "DipTrace-ComponentLibrary",
            "DipTrace-PatternLibrary",
        }:
            raise EditError(
                f"Unsupported seed source type: {source_type!r}",
                code="invalid_request",
            )
        target = self.context.settings.resolve_allowed_path(target_path, must_exist=False)
        previous = self.load_overwrite_target(
            target,
            overwrite=overwrite,
            expected_sha256=expected_sha256,
        )
        impact = write_impact(previous, seed_doc)
        self.require_write_impact(impact, operation="create_document_from_seed")
        # Copy seed bytes verbatim — do not modify unknown XML
        if previous is not None:
            assert expected_sha256 is not None
            self.require_current_target_sha256(target, expected_sha256)
            written = write_with_backup(
                target,
                seed_bytes,
                self.backups,
                expected_sha256=expected_sha256,
            )
            backup: str | None = str(written)
        else:
            self.require_target_still_absent(target)
            atomic_write_bytes(target, seed_bytes)
            backup = None
        loaded = DipTraceDocument.load(target, self.context.settings.max_document_bytes)
        if loaded.sha256 != seed_sha256:
            raise EditError(
                "Seed copy failed the post-write checksum verification",
                details={"path": str(target)},
            )
        # Determine trust from verifiable seed metadata only
        seed_sidecar = self.load_seed_provenance(seed)
        # Default: unknown origin → synthetic
        trust_level = FixtureValidationLevel.synthetic_parser_only
        trust_provenance = "seed_copy_unknown_origin"
        parent_level: FixtureValidationLevel | None = None
        copy_authority = ProvenanceAuthority.runtime
        evidence_path: str | None = None
        evidence_sha: str | None = None
        if seed_sidecar is not None:
            # Validate the sidecar: SHA must match
            if seed_sidecar.current_document_sha256 != seed_sha256:
                # Stale sidecar — do not trust at all
                trust_provenance = "seed_copy_stale_sidecar"
            elif seed_sidecar.authority == ProvenanceAuthority.runtime:
                # Runtime sidecar: even if it claims a high level, we downgrade.
                # A runtime sidecar can never grant high trust.
                trust_level = FixtureValidationLevel.synthetic_parser_only
                trust_provenance = "seed_copy_runtime_sidecar_downgraded"
                parent_level = seed_sidecar.validation_level
            elif seed_sidecar.authority == ProvenanceAuthority.user_supplied_evidence:
                # User-supplied evidence: revalidate but cannot grant high trust
                try:
                    evidence = self.load_and_validate_evidence_manifest(seed, seed_sidecar)
                    # User-supplied evidence can never grant high trust
                    if evidence.validation_level in _HIGH_TRUST_LEVELS:
                        trust_level = FixtureValidationLevel.synthetic_parser_only
                        trust_provenance = "seed_copy_user_supplied_no_high_trust"
                        parent_level = evidence.validation_level
                    else:
                        trust_level = evidence.validation_level
                        trust_provenance = "seed_copy_user_supplied_evidence"
                        parent_level = evidence.validation_level
                    copy_authority = ProvenanceAuthority.user_supplied_evidence
                    evidence_path = str(evidence.manifest_path)
                    evidence_sha = evidence.manifest_sha256
                except EditError:
                    trust_level = FixtureValidationLevel.synthetic_parser_only
                    trust_provenance = "seed_copy_evidence_validation_failed"
                    parent_level = seed_sidecar.validation_level
            elif seed_sidecar.authority == ProvenanceAuthority.fixture_manifest:
                # Fixture manifest: MUST validate the actual manifest file
                try:
                    evidence = self.load_and_validate_evidence_manifest(seed, seed_sidecar)
                    trust_level = evidence.validation_level
                    trust_provenance = "seed_copy_of_verified_fixture"
                    parent_level = evidence.validation_level
                    copy_authority = seed_sidecar.authority
                    evidence_path = str(evidence.manifest_path)
                    evidence_sha = evidence.manifest_sha256
                except EditError:
                    trust_level = FixtureValidationLevel.synthetic_parser_only
                    trust_provenance = "seed_copy_evidence_validation_failed"
                    parent_level = seed_sidecar.validation_level
            elif seed_sidecar.authority == ProvenanceAuthority.trusted_registry:
                try:
                    evidence = self.load_and_authorize_trusted_registry_evidence(
                        seed,
                        seed_sidecar,
                    )
                    # An exact byte copy does not preserve the manifest's
                    # path-role binding. A new reviewed evidence entry for the
                    # target is required before the copy may regain authority.
                    trust_provenance = "seed_copy_trusted_registry_requires_target_evidence"
                    parent_level = evidence.validation_level
                except EditError:
                    trust_provenance = "seed_copy_trusted_registry_validation_failed"
                    parent_level = None
        # Write provenance sidecar for the new copy
        sidecar = DocumentProvenance(
            provenance=trust_provenance,
            validation_level=trust_level,
            current_document_sha256=loaded.sha256,
            seed_sha256=seed_sha256,
            parent_validation_level=parent_level,
            authority=copy_authority,
            evidence_manifest_path=evidence_path,
            evidence_manifest_sha256=evidence_sha,
            last_modified_by="mcp_create_document_from_seed",
        )
        sidecar_path = target.with_suffix(target.suffix + ".provenance.json")
        atomic_write_bytes(sidecar_path, sidecar.model_dump_json(indent=2).encode())
        snapshot = build_snapshot(loaded)
        return read_success(
            snapshot.info,
            {
                "created": True,
                "kind": source_type.split("-", 1)[-1].lower(),
                "path": str(target),
                "size_bytes": len(seed_bytes),
                "sha256": loaded.sha256,
                "backup": backup,
                "write_object_count": impact.object_count,
                "seed_path": str(seed),
                "seed_sha256": seed_sha256,
                "format_version": loaded.version,
                "provenance": trust_provenance,
                "validation_level": trust_level.value,
                "requires_diptrace_verification": requires_diptrace_verification(trust_level),
                "summary": {
                    "sheets": len(snapshot.schematic.sheets) if snapshot.schematic else None,
                    "layers": len(snapshot.board.layers) if snapshot.board else None,
                },
            },
            warnings=snapshot.warnings,
        )
