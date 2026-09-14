from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import (
    DocumentProvenance,
    EvidenceAuthority,
    EvidenceFileRecord,
    FieldSolverRequest,
    FixtureManifest,
    FixtureValidationLevel,
    GeometryShape,
    ImpedanceInput,
    ObjectRecord,
    ProvenanceAuthority,
    QuerySelector,
    SemanticComparisonEvidence,
    TrustedRoundtripEvidence,
    UnsupportedCategory,
    UserSuppliedRoundtripEvidence,
    ViaStyleModel,
    WriteScope,
)
from diptrace_mcp.errors import (
    CapabilityUnavailableError,
    ExternalToolFailedError,
    ExternalToolUnavailableError,
)
from diptrace_mcp.external_adapters import (
    FreeroutingAdapter,
    NgSpiceAdapter,
    OpenEmsAdapter,
    parse_ngspice_log,
)
from diptrace_mcp.library_mutation import (
    ComponentGraphicSpec,
    ComponentPartSpec,
    ComponentPinSpec,
    ComponentSpec,
    PatternGraphicSpec,
    PatternPadSpec,
    PatternSpec,
)
from diptrace_mcp.pcb_design_intent import (
    PCBComponentOverride,
    PCBElectricalConstraints,
    PCBIntentOverrides,
    PCBNetOverride,
    build_pcb_design_intent,
    intent_confidence,
)
from diptrace_mcp.pcb_whole_board import (
    PCBWholeBoardConfig,
    _ground_name,
    _rectangular_outline_box,
    _two_copper_layers,
    compact_rectangular_board_outline,
)
from diptrace_mcp.services.evidence import (
    _bounded_evidence_comparison,
    _detected_semantic_normalizations,
    _finalize_evidence_response,
    _semantic_roundtrip_check,
    same_file_role,
)
from diptrace_mcp.services.transactions import transaction_response_summary
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _settings(tmp_path: Path, **paths: Path | None) -> Settings:
    return Settings(
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
        state_dir=tmp_path / ".state",
        freerouting_executable=paths.get("freerouting"),
        java_executable=paths.get("java"),
        ngspice_executable=paths.get("ngspice"),
        openems_runner=paths.get("openems"),
    )


def test_external_adapter_contracts_are_local_and_bounded(tmp_path: Path) -> None:
    absent = tmp_path / "absent"
    settings = _settings(tmp_path, freerouting=absent, ngspice=absent, openems=absent)
    for adapter, argument, options in (
        (
            FreeroutingAdapter(settings),
            (tmp_path / "in", tmp_path / "out"),
            {"max_passes": 1, "threads": 1, "ignore_net_classes": []},
        ),
        (NgSpiceAdapter(settings), (tmp_path / "in",), {}),
        (OpenEmsAdapter(settings), (tmp_path / "in", tmp_path / "out"), {}),
    ):
        assert not adapter.probe().available
        with pytest.raises(ExternalToolUnavailableError):
            adapter.command(*argument, **options)

    executable = tmp_path / "runner.py"
    executable.write_text("#!/usr/bin/env python3\n")
    executable.chmod(0o755)
    freerouting = FreeroutingAdapter(_settings(tmp_path, freerouting=executable))
    assert freerouting.probe().available
    assert freerouting.command(
        tmp_path / "a", tmp_path / "b", max_passes=2, threads=3, ignore_net_classes=["USB HS"]
    )[-2:] == ["-inc", "USB HS"]
    for kwargs in (
        {"max_passes": 0, "threads": 1, "ignore_net_classes": []},
        {"max_passes": 1, "threads": 65, "ignore_net_classes": []},
        {"max_passes": 1, "threads": 1, "ignore_net_classes": ["bad\\n"]},
    ):
        with pytest.raises(ExternalToolFailedError):
            freerouting.command(tmp_path / "a", tmp_path / "b", **kwargs)
    assert NgSpiceAdapter(_settings(tmp_path, ngspice=executable)).command(tmp_path / "net")[
        -2:
    ] == ["-b", str(tmp_path / "net")]
    assert OpenEmsAdapter(_settings(tmp_path, openems=executable)).command(
        tmp_path / "in", tmp_path / "out"
    )[-4:] == ["--input", str(tmp_path / "in"), "--output", str(tmp_path / "out")]
    assert parse_ngspice_log(b"Warning: bounded\nError: bad\n")["error_lines"] == ["Error: bad"]


def test_pure_library_specs_reject_invalid_geometry() -> None:
    with pytest.raises(ValueError):
        PatternGraphicSpec(xml_id="g", layer="Top", points=[(float("nan"), 0)])
    with pytest.raises(ValueError):
        ComponentGraphicSpec(xml_id="g", kind="line", points=[(0, float("inf"))])
    with pytest.raises(ValueError):
        PatternSpec(
            name="P",
            style="S",
            pads=[
                PatternPadSpec(xml_id="1", number="1", style="x"),
                PatternPadSpec(xml_id="1", number="2", style="x"),
            ],
        )
    with pytest.raises(ValueError):
        ComponentPartSpec(
            name="P",
            refdes="U",
            pins=[
                ComponentPinSpec(xml_id="1", number="1"),
                ComponentPinSpec(xml_id="1", number="2"),
            ],
        )
    with pytest.raises(ValueError):
        ComponentSpec(name="outer", parts=[ComponentPartSpec(name="inner", refdes="U")])


def test_pcb_intent_and_outline_contracts_use_fixture_only() -> None:
    document = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    snapshot = build_snapshot(document)
    intent = build_pcb_design_intent(
        snapshot,
        PCBIntentOverrides(
            components=[
                PCBComponentOverride(selector="U1", block_id="controller", anchor_component="J1")
            ],
            nets=[
                PCBNetOverride(
                    selector="VCC",
                    constraints=PCBElectricalConstraints(current_a=2.0, edge_rate_ns=1.0),
                )
            ],
        ),
    )
    assert intent.components and intent.nets and 0 <= intent_confidence(intent) <= 1
    assert any(item.block_id == "controller" for item in intent.components)
    assert any(item.criticality > 0 for item in intent.nets)
    assert _two_copper_layers(document) is not None
    assert _ground_name(document, None) in {None, "GND"}
    before = _rectangular_outline_box(document)
    if before is not None:
        changed, did_change, old, new = compact_rectangular_board_outline(document, margin_mm=0.2)
        assert did_change and old != new and _rectangular_outline_box(changed) is not None
    with pytest.raises(CapabilityUnavailableError):
        _ground_name(document, "NOT_A_GROUND")
    assert PCBWholeBoardConfig().compact_outline


def test_evidence_helpers_bound_and_normalize_without_native_tools(tmp_path: Path) -> None:
    assert same_file_role(tmp_path / "a" / "x.xml", tmp_path / "a" / "x.xml")
    assert not same_file_role(tmp_path / "a.xml", tmp_path / "b.xml")
    assert _bounded_evidence_comparison(None)[0] is None
    bounded, bounds = _bounded_evidence_comparison(
        {
            "passed": True,
            "differences": ["x" * 600] * 100,
            "unsupported_categories": [
                {"category": "x" * 600, "severity": "warning", "reason": "unsupported"}
            ],
        }
    )
    assert bounded is not None and bounds["truncated"] is True
    assert _finalize_evidence_response({"ok": True})["ok"]
    before = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    after = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)
    assert _detected_semantic_normalizations(before, after) == []
    result = _semantic_roundtrip_check(before, after)
    assert result["passed"]


def test_transaction_summary_bounds_record_fields() -> None:
    from diptrace_mcp.domain import TransactionRecord

    record = TransactionRecord(
        txid="tx_00000000-0000-4000-8000-000000000000",
        document_id="d",
        target_path="/tmp/a",
        source_sha256="a" * 64,
        status="staged",
        operations=[{"kind": "x"}],
        changed_ids=[f"id-{index}" for index in range(300)],
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    summary = transaction_response_summary(record)
    assert summary["txid"] == record.txid
    assert summary["changed_id_count"] == 300


def test_evidence_models_reject_inconsistent_trust_combinations() -> None:
    manifest = FixtureManifest.model_construct(
        provenance="coverage",
        validation_level=FixtureValidationLevel.external_tool_roundtrip_verified,
    )
    errors = manifest.validate_for_level()
    assert len(errors) >= 9
    exported = manifest.model_copy(
        update={"validation_level": FixtureValidationLevel.diptrace_exported}
    )
    assert any("authoring_method" in error for error in exported.validate_for_level())

    pcb = EvidenceFileRecord(path="same", sha256="a" * 64, source_type="DipTrace-PCB")
    schematic = EvidenceFileRecord(path="saved", sha256="b" * 64, source_type="DipTrace-Schematic")
    comparison = SemanticComparisonEvidence(
        passed=False,
        comparison_complete=False,
        differences=["changed"],
        unsupported_categories=[
            UnsupportedCategory(category="nets", severity="critical", reason="missing")
        ],
    )
    with pytest.raises(ValueError, match="invariant violated"):
        UserSuppliedRoundtripEvidence(
            document_path="board.dipxml",
            document_sha256="c" * 64,
            source=pcb,
            saved=pcb,
            reexport=pcb,
            semantic_comparison=comparison,
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
            created_at="2026-01-01T00:00:00Z",
        )
    with pytest.raises(ValueError, match="source and saved source_type"):
        UserSuppliedRoundtripEvidence(
            document_path="board.dipxml",
            document_sha256="c" * 64,
            source=pcb,
            saved=schematic,
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            created_at="2026-01-01T00:00:00Z",
        )
    with pytest.raises(ValueError, match="source_type must match"):
        UserSuppliedRoundtripEvidence(
            document_path="board.dipxml",
            document_sha256="c" * 64,
            source=pcb,
            saved=schematic,
            reexport=pcb.model_copy(update={"path": "reexport"}),
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            created_at="2026-01-01T00:00:00Z",
        )

    common = {
        "document_path": "board.dipxml",
        "document_sha256": "c" * 64,
        "source": pcb,
        "saved": pcb.model_copy(update={"path": "saved"}),
        "authority": EvidenceAuthority.trusted_bridge,
        "created_at": "2026-01-01T00:00:00Z",
        "status": "passed",
    }
    with pytest.raises(ValueError, match="requires semantic_comparison"):
        TrustedRoundtripEvidence(
            **common,
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
        )
    with pytest.raises(ValueError, match="high-trust"):
        TrustedRoundtripEvidence(
            **common,
            validation_level=FixtureValidationLevel.synthetic_parser_only,
            semantic_comparison=comparison,
        )


def test_provenance_and_geometry_models_reject_cross_field_errors() -> None:
    base = {
        "provenance": "coverage",
        "current_document_sha256": "a" * 64,
        "authority": ProvenanceAuthority.trusted_registry,
    }
    with pytest.raises(ValueError, match="high-trust"):
        DocumentProvenance(
            **base,
            validation_level=FixtureValidationLevel.synthetic_parser_only,
        )
    with pytest.raises(ValueError, match="evidence_manifest_path"):
        DocumentProvenance(
            **base,
            validation_level=FixtureValidationLevel.diptrace_exported,
            trusted_registry_entry_id="entry",
        )
    with pytest.raises(ValueError, match="evidence_manifest_sha256"):
        DocumentProvenance(
            **base,
            validation_level=FixtureValidationLevel.diptrace_exported,
            trusted_registry_entry_id="entry",
            evidence_manifest_path="evidence.json",
        )
    with pytest.raises(ValueError, match="only valid"):
        DocumentProvenance(
            provenance="coverage",
            current_document_sha256="a" * 64,
            validation_level=FixtureValidationLevel.synthetic_parser_only,
            trusted_registry_entry_id="entry",
        )

    invalid_models = (
        lambda: GeometryShape(kind="circle", center={"x": 1.0}),
        lambda: GeometryShape(kind="polygon", points=[{"x": 1.0}]),
        lambda: ObjectRecord(stable_id="part_0000000000000000", kind="part", position={"x": 1.0}),
        lambda: ObjectRecord(stable_id="part_0000000000000000", kind="part", bbox={"min_x": 0}),
        lambda: ViaStyleModel(id="via", diameter_mm=0.5, hole_mm=0.5),
        lambda: ViaStyleModel(id="via", span_source="explicit", span_layer_ids=["top"]),
        lambda: ViaStyleModel(id="via", span_source="unspecified", span_layer_ids=["top"]),
        lambda: QuerySelector(near={"x": 1.0}),
        lambda: ImpedanceInput(
            structure="differential_microstrip",
            width_mm=0.2,
            copper_thickness_mm=0.035,
            dielectric_height_mm=0.18,
            dielectric_constant=4.2,
        ),
        lambda: FieldSolverRequest(
            width_mm=0.2,
            copper_thickness_mm=0.035,
            lower_dielectric_height_mm=0.18,
            upper_dielectric_height_mm=0.18,
            dielectric_constant=4.2,
            frequencies_hz=[-1.0],
        ),
    )
    for build in invalid_models:
        with pytest.raises(ValueError):
            build()

    with pytest.raises(ValueError, match="explicit scope"):
        WriteScope()
    assert WriteScope(whole_document=True).whole_document
    with pytest.raises(ValueError, match="trust invariant"):
        FixtureManifest(
            provenance="coverage",
            validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
        )
