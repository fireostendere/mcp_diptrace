"""Repository-owned allowlist for independently reviewed provenance evidence.

The production registry is a package file, not workspace or state-directory
data.  Consequently an MCP client cannot add an entry through a document write.
Every entry binds one exact document hash to one exact evidence-manifest hash
and the independently reviewed metadata used to interpret those bytes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .domain import (
    DocumentProvenance,
    EvidenceAuthority,
    FixtureValidationLevel,
    ProvenanceAuthority,
    SourceType,
    StrictModel,
    TrustedRoundtripEvidence,
)

_REGISTRY_RESOURCE = "trusted_provenance_registry.json"
_HIGH_TRUST_LEVELS = frozenset(
    {
        FixtureValidationLevel.diptrace_exported,
        FixtureValidationLevel.diptrace_open_save_verified,
        FixtureValidationLevel.diptrace_roundtrip_verified,
        FixtureValidationLevel.external_tool_roundtrip_verified,
    }
)


class RegistryAuthorizationError(ValueError):
    """An exact registry binding could not be established."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TrustedProvenanceRegistryEntry(StrictModel):
    """One code-reviewed, exact-hash trust assertion."""

    entry_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_manifest_source: str = Field(min_length=1, max_length=512)
    source_type: SourceType
    validation_level: FixtureValidationLevel

    @field_validator("evidence_manifest_source")
    @classmethod
    def _safe_repository_source(cls, value: str) -> str:
        """Require a canonical repository-relative provenance reference."""

        if "\\" in value or "\x00" in value or ":" in value:
            raise ValueError(
                "evidence_manifest_source must be a canonical repository-relative POSIX path"
            )
        source = PurePosixPath(value)
        if (
            source.is_absolute()
            or source.as_posix() != value
            or any(part in {"", ".", ".."} for part in source.parts)
        ):
            raise ValueError(
                "evidence_manifest_source must be a canonical repository-relative POSIX path"
            )
        return value

    @model_validator(mode="after")
    def _require_high_trust_level(self) -> TrustedProvenanceRegistryEntry:
        if self.validation_level not in _HIGH_TRUST_LEVELS:
            raise ValueError("trusted registry entries must grant a high-trust validation level")
        return self


class TrustedProvenanceRegistryFile(StrictModel):
    """Canonical on-disk registry schema."""

    schema_version: Literal["diptrace-trusted-provenance-registry-v1"] = (
        "diptrace-trusted-provenance-registry-v1"
    )
    entries: list[TrustedProvenanceRegistryEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_deterministic_unique_entries(self) -> TrustedProvenanceRegistryFile:
        ids = [entry.entry_id for entry in self.entries]
        if ids != sorted(ids):
            raise ValueError("trusted registry entries must be sorted by entry_id")
        if len(ids) != len(set(ids)):
            raise ValueError("trusted registry entry_id values must be unique")
        bindings = [
            (entry.document_sha256, entry.evidence_manifest_sha256)
            for entry in self.entries
        ]
        if len(bindings) != len(set(bindings)):
            raise ValueError("trusted registry document/evidence bindings must be unique")
        return self


def canonical_registry_bytes(registry: TrustedProvenanceRegistryFile) -> bytes:
    """Serialize the registry deterministically for code review and CI."""

    payload = registry.model_dump(mode="json")
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


class TrustedProvenanceRegistry:
    """Validated immutable view of the embedded trust allowlist."""

    def __init__(
        self,
        registry: TrustedProvenanceRegistryFile,
        *,
        source_label: str,
    ) -> None:
        self._registry = registry
        self._source_label = source_label
        self._entries = {entry.entry_id: entry for entry in registry.entries}

    @classmethod
    def from_bytes(
        cls,
        raw: bytes,
        *,
        source_label: str,
        evidence_source_reader: Callable[[str], bytes] | None = None,
    ) -> TrustedProvenanceRegistry:
        try:
            text = raw.decode("utf-8", errors="strict")
            data = json.loads(text)
            registry = TrustedProvenanceRegistryFile.model_validate(data)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid trusted provenance registry: {exc}") from exc
        if canonical_registry_bytes(registry) != raw:
            raise ValueError("Trusted provenance registry is not canonical deterministic JSON")
        if registry.entries and evidence_source_reader is None:
            raise ValueError(
                "Non-empty trusted provenance registry requires a package-owned "
                "evidence source reader"
            )
        for entry in registry.entries:
            assert evidence_source_reader is not None
            try:
                evidence_bytes = evidence_source_reader(entry.evidence_manifest_source)
            except OSError as exc:
                raise ValueError(
                    f"Cannot read registry evidence source for {entry.entry_id}: {exc}"
                ) from exc
            source_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
            if not hmac.compare_digest(source_sha256, entry.evidence_manifest_sha256):
                raise ValueError(
                    f"Registry evidence source SHA mismatch for {entry.entry_id}"
                )
            try:
                evidence = TrustedRoundtripEvidence.model_validate_json(evidence_bytes)
            except ValueError as exc:
                raise ValueError(
                    f"Registry evidence source schema is invalid for {entry.entry_id}: {exc}"
                ) from exc
            evidence_types = {
                evidence.source.source_type,
                evidence.saved.source_type,
            }
            if evidence.reexport is not None:
                evidence_types.add(evidence.reexport.source_type)
            binding_matches = (
                evidence.authority == EvidenceAuthority.trusted_registry
                and evidence.status == "passed"
                and hmac.compare_digest(evidence.document_sha256, entry.document_sha256)
                and evidence.validation_level == entry.validation_level
                and evidence_types == {entry.source_type}
            )
            if not binding_matches:
                raise ValueError(
                    f"Registry evidence metadata mismatch for {entry.entry_id}"
                )
        return cls(registry, source_label=source_label)

    @classmethod
    def from_path(cls, path: Path) -> TrustedProvenanceRegistry:
        """Load a registry file; primarily useful for isolated verifier tests."""

        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"Cannot read trusted provenance registry: {exc}") from exc
        source_root = path.parent.resolve()

        def read_evidence_source(relative_path: str) -> bytes:
            source_path = source_root.joinpath(*PurePosixPath(relative_path).parts)
            if source_path.is_symlink():
                raise OSError("registry evidence source must not be a symlink")
            resolved = source_path.resolve(strict=True)
            try:
                resolved.relative_to(source_root)
            except ValueError as exc:
                raise OSError("registry evidence source escaped its package root") from exc
            if not resolved.is_file():
                raise OSError("registry evidence source is not a regular file")
            return resolved.read_bytes()

        return cls.from_bytes(
            raw,
            source_label=str(path),
            evidence_source_reader=read_evidence_source,
        )

    @classmethod
    def load_embedded(cls) -> TrustedProvenanceRegistry:
        """Load the sole production authority from package-owned bytes."""

        data_root = resources.files("diptrace_mcp").joinpath("data")
        try:
            raw = data_root.joinpath(_REGISTRY_RESOURCE).read_bytes()
        except OSError as exc:
            raise ValueError(f"Cannot read embedded trusted provenance registry: {exc}") from exc

        def read_evidence_source(relative_path: str) -> bytes:
            source = data_root
            for part in PurePosixPath(relative_path).parts:
                source = source.joinpath(part)
            return source.read_bytes()

        return cls.from_bytes(
            raw,
            source_label="diptrace_mcp/data/trusted_provenance_registry.json",
            evidence_source_reader=read_evidence_source,
        )

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def report(self) -> dict[str, object]:
        """Return a public, deterministic disclosure of registry contents."""

        return {
            "schema_version": self._registry.schema_version,
            "authority": "repository_owned_committed_sha256_allowlist",
            "source": self._source_label,
            "trusted_entry_count": self.entry_count,
            "high_trust_currently_available": self.entry_count > 0,
            "entries": [
                {
                    "entry_id": entry.entry_id,
                    "document_sha256": entry.document_sha256,
                    "evidence_manifest_sha256": entry.evidence_manifest_sha256,
                    "evidence_manifest_source": entry.evidence_manifest_source,
                    "source_type": entry.source_type,
                    "validation_level": entry.validation_level.value,
                }
                for entry in self._registry.entries
            ],
            "every_entry_requires_human_review": True,
        }

    def authorize(
        self,
        *,
        entry_id: str,
        document_sha256: str,
        evidence_manifest_sha256: str,
        source_type: str,
        validation_level: FixtureValidationLevel,
    ) -> TrustedProvenanceRegistryEntry:
        """Require every registry-bound field to match an embedded entry."""

        entry = self._entries.get(entry_id)
        if entry is None:
            raise RegistryAuthorizationError("trusted_registry_entry_unregistered")
        bindings_match = (
            hmac.compare_digest(entry.document_sha256, document_sha256)
            and hmac.compare_digest(
                entry.evidence_manifest_sha256,
                evidence_manifest_sha256,
            )
            and entry.source_type == source_type
            and entry.validation_level == validation_level
        )
        if not bindings_match:
            raise RegistryAuthorizationError("trusted_registry_binding_mismatch")
        return entry

    def create_provenance(
        self,
        *,
        entry_id: str,
        document_sha256: str,
        evidence_manifest_path: str,
        evidence_manifest_sha256: str,
        source_type: str,
        validation_level: FixtureValidationLevel,
        provenance: str = "repository_reviewed_evidence",
    ) -> DocumentProvenance:
        """Construct a sidecar only after exact registry authorization."""

        self.authorize(
            entry_id=entry_id,
            document_sha256=document_sha256,
            evidence_manifest_sha256=evidence_manifest_sha256,
            source_type=source_type,
            validation_level=validation_level,
        )
        return DocumentProvenance(
            provenance=provenance,
            validation_level=validation_level,
            current_document_sha256=document_sha256,
            authority=ProvenanceAuthority.trusted_registry,
            evidence_manifest_path=evidence_manifest_path,
            evidence_manifest_sha256=evidence_manifest_sha256,
            trusted_registry_entry_id=entry_id,
        )
