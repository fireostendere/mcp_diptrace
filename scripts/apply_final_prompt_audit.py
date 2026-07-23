from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    if old not in text:
        raise RuntimeError(f"expected source block not found in {path}")
    target.write_text(text.replace(old, new, 1))


replace(
    "src/diptrace_mcp/domain.py",
    '''        # Semantic comparison fields
        if self.semantic_comparison is not None:
            if not self.semantic_comparison.comparison_complete:
                errors.append("semantic comparison must be complete for recorded evidence")
            if not self.semantic_comparison.passed:
                errors.append("semantic comparison must pass for recorded evidence")
            if self.semantic_comparison.differences:
                errors.append("semantic comparison with differences cannot be recorded as passed")
            # Critical unsupported categories
            critical = [
                cat
                for cat in self.semantic_comparison.unsupported_categories
                if cat.severity == "critical"
            ]
            if critical:
                errors.append("critical unsupported categories prevent recording as passed")
''',
    '''        # Successful recorded evidence must be complete and difference-free.
        # Failed evidence intentionally preserves incomplete/different results.
        if self.semantic_comparison is not None and self.status == "recorded":
            if not self.semantic_comparison.comparison_complete:
                errors.append("semantic comparison must be complete for recorded evidence")
            if not self.semantic_comparison.passed:
                errors.append("semantic comparison must pass for recorded evidence")
            if self.semantic_comparison.differences:
                errors.append("semantic comparison with differences cannot be recorded as passed")
            critical = [
                cat
                for cat in self.semantic_comparison.unsupported_categories
                if cat.severity == "critical"
            ]
            if critical:
                errors.append("critical unsupported categories prevent recording as passed")
''',
)
replace(
    "src/diptrace_mcp/domain.py",
    '''    A runtime sidecar (authority=runtime) can never grant a high-trust level.
    High-trust levels require either a fixture_manifest or trusted_registry
    authority with verifiable SHA binding.
''',
    '''    A runtime sidecar (authority=runtime) can never grant a high-trust level.
    High-trust promotion is unavailable until an authenticated server-owned
    registry, trusted bridge, or signed/allowlisted fixture authority exists.
''',
)
replace(
    "src/diptrace_mcp/domain.py",
    '''        Runtime authority can only grant synthetic_parser_only or
        synthetic_operation_fixture.  Higher levels require either
        fixture_manifest or trusted_registry authority.
''',
    '''        Runtime authority can only grant synthetic_parser_only or
        synthetic_operation_fixture. High-trust promotion remains unavailable
        until an authenticated authority is implemented.
''',
)
replace(
    "src/diptrace_mcp/domain.py",
    '''        fixture_manifest authority with high trust requires
        evidence_manifest_path and evidence_manifest_sha256.
''',
    '''        fixture_manifest is only a provenance label until a committed
        allowlist or signature verifier is implemented; it cannot grant high
        trust from workspace-controlled JSON and SHA values.
''',
)
replace(
    "src/diptrace_mcp/domain.py",
    '"requires fixture_manifest or trusted_registry authority"',
    '"an authenticated high-trust authority is unavailable"',
)
replace(
    "src/diptrace_mcp/domain.py",
    '"only trusted_registry or fixture_manifest can"',
    '"an authenticated high-trust authority is unavailable"',
)
replace(
    "src/diptrace_mcp/domain.py",
    '''        if (
            self.authority == ProvenanceAuthority.fixture_manifest
            and self.validation_level in _HIGH_TRUST_LEVELS
        ):
            if not self.evidence_manifest_path:
                raise ValueError(
                    "fixture_manifest authority with high trust requires evidence_manifest_path"
                )
            if not self.evidence_manifest_sha256:
                raise ValueError(
                    "fixture_manifest authority with high trust requires evidence_manifest_sha256"
                )
''',
    '''        if (
            self.authority == ProvenanceAuthority.fixture_manifest
            and self.validation_level in _HIGH_TRUST_LEVELS
        ):
            raise ValueError(
                "fixture_manifest high trust is unavailable without an authenticated "
                "committed allowlist or signature verifier"
            )
''',
)

replace(
    "src/diptrace_mcp/service.py",
    '''        # 5. Find document SHA from manifest
        doc_sha_from_manifest = record_data["document_sha256"]
        doc_path_from_manifest = record_data["document_path"]

        # 6. Document SHA binding
''',
    '''        # 5. Bind the manifest to this exact target document, not merely bytes
        # with the same hash elsewhere in the workspace.
        doc_sha_from_manifest = record_data["document_sha256"]
        doc_path_from_manifest = record_data["document_path"]
        try:
            manifest_document_path = self.settings.resolve_allowed_path(
                doc_path_from_manifest, must_exist=True
            )
        except (EditError, PathAccessError, OSError) as exc:
            raise EditError(
                f"Evidence document path is unavailable or outside allowed roots: {exc}",
                code="evidence_document_path_invalid",
            ) from exc
        if not same_file_role(manifest_document_path, document_path):
            raise EditError(
                "Evidence manifest is bound to a different document path",
                code="evidence_document_path_mismatch",
            )

        # 6. Document SHA binding
''',
)
replace(
    "src/diptrace_mcp/service.py",
    '''        # 7. Source type validation
        saved_info = record_data.get("saved", {})
        source_type_from_manifest = ""
        if isinstance(saved_info, dict):
            source_type_from_manifest = saved_info.get("source_type", "")

        # 8. Validation level must match
''',
    '''        # 7. Source type validation against the actual current document.
        saved_info = record_data.get("saved", {})
        source_type_from_manifest = ""
        if isinstance(saved_info, dict):
            source_type_from_manifest = saved_info.get("source_type", "")
        actual_document = DipTraceDocument.load(
            document_path, self.settings.max_document_bytes
        )
        if source_type_from_manifest != actual_document.source_type:
            raise EditError(
                f"Evidence source type {source_type_from_manifest!r} does not match "
                f"document source type {actual_document.source_type!r}",
                code="evidence_source_type_mismatch",
            )

        # 8. Validation level must match
''',
)
replace(
    "src/diptrace_mcp/service.py",
    '''        # 6. Fixture manifest authority: revalidate evidence for high trust
        if provenance.authority == ProvenanceAuthority.fixture_manifest:
            if provenance.validation_level in _HIGH_TRUST_LEVELS:
                if not provenance.evidence_manifest_path:
                    return _fail_closed_trust(
                        reason="fixture_manifest_high_trust_missing_evidence",
                        warning_code="evidence_manifest_missing",
                    )
                try:
                    evidence = self._load_and_validate_evidence_manifest(document_path, provenance)
                    return EffectiveTrust(
                        validation_level=provenance.validation_level,
                        authority=provenance.authority.value,
                        requires_diptrace_verification=requires_diptrace_verification(
                            provenance.validation_level
                        ),
                        evidence_manifest_path=str(evidence.manifest_path),
                        evidence_manifest_sha256=evidence.manifest_sha256,
                    )
                except EditError as exc:
                    return _fail_closed_trust(
                        reason=str(exc),
                        warning_code=getattr(exc, "code", "evidence_validation_failed"),
                    )
            # Non-high-trust fixture manifest: accept as-is
            return EffectiveTrust(
                validation_level=provenance.validation_level,
                authority=provenance.authority.value,
                requires_diptrace_verification=requires_diptrace_verification(
                    provenance.validation_level
                ),
            )
''',
    '''        # 6. Fixture-manifest is not an authenticated root of trust yet.
        # Workspace-controlled JSON + matching SHA cannot self-mint high trust.
        if provenance.authority == ProvenanceAuthority.fixture_manifest:
            if provenance.validation_level in _HIGH_TRUST_LEVELS:
                return _fail_closed_trust(
                    reason="fixture_manifest_high_trust_authority_unavailable",
                    warning_code="trusted_fixture_authority_unavailable",
                )
            return EffectiveTrust(
                validation_level=provenance.validation_level,
                authority=provenance.authority.value,
                requires_diptrace_verification=requires_diptrace_verification(
                    provenance.validation_level
                ),
            )
''',
)
replace(
    "src/diptrace_mcp/service.py",
    '''                        # Verify the restored sidecar SHA matches restored doc
                        restored_sidecar = json.loads(prov_bytes)
                        if restored_sidecar.get("current_document_sha256") == restored_sha256:
                            atomic_write_bytes(sidecar_path, prov_bytes)
                        else:
                            # Sidecar SHA stale → create synthetic fallback
                            sidecar = DocumentProvenance(
                                provenance="mcp_rollback_synthetic",
                                validation_level=FixtureValidationLevel.synthetic_operation_fixture,
                                current_document_sha256=restored_sha256,
                                last_modified_by="mcp_rollback_transaction",
                            )
                            self._write_provenance_sidecar(target_path, sidecar)
                    except (OSError, json.JSONDecodeError, ValueError):
                        # Corrupt backup → create synthetic fallback
''',
    '''                        # Validate schema, document binding, and any referenced
                        # evidence before restoring provenance atomically.
                        restored_sidecar = DocumentProvenance.model_validate_json(prov_bytes)
                        if restored_sidecar.current_document_sha256 != restored_sha256:
                            raise ValueError("restored provenance document SHA mismatch")
                        if restored_sidecar.authority == ProvenanceAuthority.user_supplied_evidence:
                            self._load_and_validate_evidence_manifest(
                                target_path, restored_sidecar
                            )
                        if (
                            restored_sidecar.authority == ProvenanceAuthority.fixture_manifest
                            and restored_sidecar.validation_level in _HIGH_TRUST_LEVELS
                        ):
                            raise ValueError("unauthenticated fixture high trust cannot be restored")
                        atomic_write_bytes(sidecar_path, prov_bytes)
                    except (OSError, json.JSONDecodeError, ValueError, EditError):
                        # Corrupt or unauthenticated backup → create synthetic fallback
''',
)

replace(
    "tests/test_trust_model.py",
    '''    def test_fixture_manifest_can_grant_high_trust(self) -> None:
        """fixture_manifest authority can grant high trust with evidence manifest."""
        sidecar = DocumentProvenance(
            provenance="fixture_validated",
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
            current_document_sha256="a" * 64,
            authority=ProvenanceAuthority.fixture_manifest,
            evidence_manifest_path="/tmp/evidence.json",
            evidence_manifest_sha256="b" * 64,
        )
        assert sidecar.validation_level == FixtureValidationLevel.diptrace_roundtrip_verified

    def test_fixture_manifest_high_trust_requires_manifest(self) -> None:
        """fixture_manifest authority with high trust without evidence fields is rejected."""
        with pytest.raises(ValueError, match="requires evidence_manifest_path"):
            DocumentProvenance(
                provenance="fixture_validated",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.fixture_manifest,
            )
''',
    '''    def test_fixture_manifest_cannot_grant_high_trust_without_authenticated_allowlist(
        self,
    ) -> None:
        """A workspace-controlled fixture manifest is not a root of trust."""
        with pytest.raises(ValueError, match="fixture_manifest high trust is unavailable"):
            DocumentProvenance(
                provenance="fixture_validated",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.fixture_manifest,
                evidence_manifest_path="/tmp/evidence.json",
                evidence_manifest_sha256="b" * 64,
            )

    def test_fixture_manifest_high_trust_without_manifest_is_rejected(self) -> None:
        """Missing evidence cannot bypass the unavailable authority boundary."""
        with pytest.raises(ValueError, match="fixture_manifest high trust is unavailable"):
            DocumentProvenance(
                provenance="fixture_validated",
                validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.fixture_manifest,
            )
''',
)
replace(
    "tests/test_trust_model.py",
    '''        for level in {
            FixtureValidationLevel.diptrace_roundtrip_verified,
            FixtureValidationLevel.external_tool_roundtrip_verified,
        }:
            sidecar = DocumentProvenance(
                provenance="test",
                validation_level=level,
                current_document_sha256="a" * 64,
                authority=ProvenanceAuthority.fixture_manifest,
                evidence_manifest_path="/tmp/m.json",
                evidence_manifest_sha256="b" * 64,
            )
            assert sidecar.requires_diptrace_verification is False
''',
    '''        for level in {
            FixtureValidationLevel.diptrace_roundtrip_verified,
            FixtureValidationLevel.external_tool_roundtrip_verified,
        }:
            with pytest.raises(ValueError, match="fixture_manifest high trust is unavailable"):
                DocumentProvenance(
                    provenance="test",
                    validation_level=level,
                    current_document_sha256="a" * 64,
                    authority=ProvenanceAuthority.fixture_manifest,
                    evidence_manifest_path="/tmp/m.json",
                    evidence_manifest_sha256="b" * 64,
                )
''',
)
replace(
    "tests/test_trust_model.py",
    '''        sidecar = DocumentProvenance(
            provenance="fake_fixture",
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
            current_document_sha256=seed_sha,
            authority=ProvenanceAuthority.fixture_manifest,
            evidence_manifest_path=str(manifest_path),
            evidence_manifest_sha256=manifest_sha,
        )
        sidecar_path = seed_path.with_suffix(seed_path.suffix + ".provenance.json")
        sidecar_path.write_text(sidecar.model_dump_json())

        # document_info should resolve to fail-closed because manifest is missing
''',
    '''        sidecar_path = seed_path.with_suffix(seed_path.suffix + ".provenance.json")
        sidecar_path.write_text(
            json.dumps(
                {
                    "schema_version": "diptrace-document-provenance-v1",
                    "provenance": "fake_fixture",
                    "validation_level": "diptrace_roundtrip_verified",
                    "current_document_sha256": seed_sha,
                    "authority": "fixture_manifest",
                    "evidence_manifest_path": str(manifest_path),
                    "evidence_manifest_sha256": manifest_sha,
                }
            )
        )

''',
)

trust_tests = Path("tests/test_trust_model.py")
text = trust_tests.read_text()
start = text.index("    def test_trace_coordinate_change_is_detected")
end = text.index("\n\n# ── Evidence authority boundary", start)
trust_tests.write_text(text[:start] + text[end:])

patch = Path("scripts/final_prompt_audit.patch").read_text()
marker = "--- /dev/null\n+++ b/tests/test_prompt_acceptance.py\n"
section = patch.split(marker, 1)[1]
lines: list[str] = []
for line in section.splitlines():
    if line.startswith("@@"):
        continue
    if line.startswith("+"):
        lines.append(line[1:])
    elif line.startswith("\\ No newline"):
        continue
    else:
        raise RuntimeError(f"unexpected line in new-file patch: {line!r}")
Path("tests/test_prompt_acceptance.py").write_text("\n".join(lines) + "\n")
