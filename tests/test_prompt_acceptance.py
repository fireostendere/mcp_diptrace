# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import cast

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import (
    DocumentProvenance,
    EvidenceAuthority,
    EvidenceFileRecord,
    FixtureValidationLevel,
    ProvenanceAuthority,
    SemanticComparisonEvidence,
    SourceType,
    TrustedRoundtripEvidence,
    UserSuppliedRoundtripEvidence,
)
from diptrace_mcp.errors import EditError
from diptrace_mcp.service import DipTraceService, _semantic_roundtrip_check
from diptrace_mcp.xml_document import DipTraceDocument, utc_now

MAX_BYTES = 10_000_000
FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=tmp_path,
            allowed_roots=(tmp_path,),
            state_dir=tmp_path / ".state",
            max_document_bytes=MAX_BYTES,
        )
    )


def _evidence_file(path: Path, source_type: str) -> EvidenceFileRecord:
    return EvidenceFileRecord(
        path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_type=cast(SourceType, source_type),
    )


def _pcb_trace_xml(
    *,
    middle_x: float = 10.0,
    middle_y: float = 0.0,
    width: float = 0.25,
    middle_layer: str = "0",
    final_layer: str = "3",
    via_style: str = "0",
    via_lay1: str = "0",
    via_lay2: str = "3",
) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">
  <Library Type="DipTrace-ComponentLibrary" Version="4.3.0.3" Units="mm" />
  <Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm" />
  <Board>
    <BoardOutline><Points><Point X="0" Y="0"/><Point X="50" Y="0"/><Point X="50" Y="30"/><Point X="0" Y="30"/></Points></BoardOutline>
    <CopperLayers><Lay Id="0" Type="Signal"><Name>Top</Name></Lay><Lay Id="3" Type="Signal"><Name>Bottom</Name></Lay></CopperLayers>
    <ViaStyles><ViaStyle Id="0" Name="Through" Size="0.6" HoleSize="0.3" Lay1="{via_lay1}" Lay2="{via_lay2}"/></ViaStyles>
    <Components />
    <Nets>
      <Net Id="0" NetClass="0" Locked="N"><Name>VCC</Name><Pads/>
        <Traces><Trace Id="0" Connected1="None" Connected2="None" Locked="N">
          <Points>
            <Point X="0" Y="0" Lay="0" ViaStyle="-1"/>
            <Point X="{middle_x}" Y="{middle_y}" Lay="{middle_layer}" Width="{width}" ViaStyle="{via_style}"/>
            <Point X="20" Y="10" Lay="{final_layer}" Width="{width}" ViaStyle="-1"/>
          </Points>
        </Trace></Traces>
      </Net>
    </Nets>
  </Board>
</Source>
""".encode()


def _schematic_xml(*, wire_x: float = 10.0, endpoint_net: str = "0") -> bytes:
    second_net_endpoint = (
        '<Pins><Item Part="0" Pin="0"/></Pins>' if endpoint_net == "1" else "<Pins/>"
    )
    first_net_endpoint = (
        '<Pins><Item Part="0" Pin="0"/></Pins>' if endpoint_net == "0" else "<Pins/>"
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Source Type="DipTrace-Schematic" Version="4.3.0.3" Units="mm">
  <Library Type="DipTrace-ComponentLibrary" Version="4.3.0.3" Units="mm" />
  <Schematic>
    <SheetSettings><ActiveSheet>0</ActiveSheet><Sheets><Sheet><Id>0</Id><Name>Main</Name><Type>Normal</Type></Sheet></Sheets></SheetSettings>
    <Components><Part Id="0" ComponentStyle="R" ComponentPart="0" PartNumber="1" Sheet="0" X="5" Y="5"><RefDes>R1</RefDes><Name>R</Name><Value>10k</Value><Pins><Pin Number="1" Name="A"/></Pins></Part></Components>
    <Nets>
      <Net Id="0" Locked="N"><Name>N0</Name>{first_net_endpoint}<Wires><Wire Id="0" Sheet="0"><Points><Point X="5" Y="5"/><Point X="{wire_x}" Y="5"/></Points></Wire></Wires></Net>
      <Net Id="1" Locked="N"><Name>N1</Name>{second_net_endpoint}<Wires/></Net>
    </Nets>
    <DifferentialPairs/><Buses/>
  </Schematic>
</Source>
""".encode()


def _compare(left: bytes, right: bytes, suffix: str = ".dip") -> dict[str, object]:
    a = DipTraceDocument.from_bytes(Path("a" + suffix), left)
    b = DipTraceDocument.from_bytes(Path("b" + suffix), right)
    return _semantic_roundtrip_check(a, b)


@pytest.mark.parametrize(
    ("mutation", "category"),
    [
        ({"middle_x": 11.0}, "traces"),
        ({"middle_y": 2.0}, "traces"),
        ({"width": 0.4}, "traces"),
        ({"middle_layer": "3"}, "traces"),
        ({"via_style": "-1"}, "traces"),
        ({"via_lay2": "2"}, "via_styles"),
    ],
)
def test_pcb_trace_semantic_mutations_are_detected(
    mutation: dict[str, object], category: str
) -> None:
    result = _compare(_pcb_trace_xml(), _pcb_trace_xml(**mutation))  # type: ignore[arg-type]
    assert result["passed"] is False
    assert result["comparison_complete"] is True
    assert any(category in item for item in cast(list[str], result["differences"]))


def test_schematic_wire_geometry_change_is_detected() -> None:
    result = _compare(_schematic_xml(wire_x=10.0), _schematic_xml(wire_x=12.0), ".dch")
    assert result["passed"] is False
    assert result["comparison_complete"] is True
    assert any("wire_geometry" in item for item in cast(list[str], result["differences"]))


def test_schematic_pin_net_change_is_detected() -> None:
    result = _compare(_schematic_xml(endpoint_net="0"), _schematic_xml(endpoint_net="1"), ".dch")
    assert result["passed"] is False
    assert result["comparison_complete"] is True
    assert any(
        "pin_net_membership" in item or "schematic_nets" in item
        for item in cast(list[str], result["differences"])
    )


def test_public_pcb_roundtrip_geometry_failure_is_recorded(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = tmp_path / "source.dip"
    saved = tmp_path / "saved.dip"
    reexport = tmp_path / "reexport.dip"
    board = tmp_path / "board.dip"
    source.write_bytes(_pcb_trace_xml())
    saved.write_bytes(_pcb_trace_xml())
    reexport.write_bytes(_pcb_trace_xml(middle_x=11.0))
    board.write_bytes(reexport.read_bytes())

    result = service.record_roundtrip_evidence(
        "board.dip",
        source_path="source.dip",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        saved_path="saved.dip",
        reexport_path="reexport.dip",
        reexport_sha256=hashlib.sha256(reexport.read_bytes()).hexdigest(),
    )
    assert result["ok"] is False
    assert result["evidence_status"] == "failed"
    assert result["authority"] == "user_supplied"
    differences = result["semantic_comparison"]["differences"]
    assert any("traces" in item for item in differences)
    info = service.document_info("board.dip")
    assert info["result"]["validation_level"] == "synthetic_operation_fixture"
    assert info["result"]["requires_diptrace_verification"] is True


def test_public_schematic_roundtrip_connectivity_failure_is_recorded(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    source = tmp_path / "source.dch"
    saved = tmp_path / "saved.dch"
    reexport = tmp_path / "reexport.dch"
    target = tmp_path / "board.dch"
    source.write_bytes(_schematic_xml(endpoint_net="0"))
    saved.write_bytes(_schematic_xml(endpoint_net="0"))
    reexport.write_bytes(_schematic_xml(endpoint_net="1"))
    target.write_bytes(reexport.read_bytes())

    result = service.record_roundtrip_evidence(
        "board.dch",
        source_path="source.dch",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        saved_path="saved.dch",
        reexport_path="reexport.dch",
        reexport_sha256=hashlib.sha256(reexport.read_bytes()).hexdigest(),
    )
    assert result["ok"] is False
    assert result["evidence_status"] == "failed"
    differences = result["semantic_comparison"]["differences"]
    assert any("pin_net_membership" in item or "schematic_nets" in item for item in differences)


def test_self_minted_trusted_manifest_cannot_grant_high_trust(tmp_path: Path) -> None:
    service = _service(tmp_path)
    document = tmp_path / "board.dip"
    source = tmp_path / "source.dip"
    saved = tmp_path / "saved.dip"
    reexport = tmp_path / "reexport.dip"
    for path in (document, source, saved, reexport):
        path.write_bytes(_pcb_trace_xml())
    doc_sha = hashlib.sha256(document.read_bytes()).hexdigest()
    semantic = SemanticComparisonEvidence(
        passed=True,
        comparison_complete=True,
        compared_categories=[
            "source_type",
            "board_outline",
            "copper_layers",
            "components",
            "pads",
            "nets",
            "traces",
            "vias",
            "via_styles",
            "differential_pairs",
        ],
    )
    manifest = TrustedRoundtripEvidence(
        authority=EvidenceAuthority.trusted_bridge,
        document_path=str(document),
        document_sha256=doc_sha,
        source=_evidence_file(source, "DipTrace-PCB"),
        saved=_evidence_file(saved, "DipTrace-PCB"),
        reexport=_evidence_file(reexport, "DipTrace-PCB"),
        semantic_comparison=semantic,
        validation_level=FixtureValidationLevel.diptrace_roundtrip_verified,
        status="passed",
        created_at=utc_now(),
    )
    manifest_path = tmp_path / "trusted.json"
    manifest_path.write_text(manifest.model_dump_json())
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    document.with_suffix(document.suffix + ".provenance.json").write_text(
        json.dumps(
            {
                "schema_version": "diptrace-document-provenance-v1",
                "provenance": "self_minted_trusted_bridge",
                "validation_level": "diptrace_roundtrip_verified",
                "current_document_sha256": doc_sha,
                "authority": "fixture_manifest",
                "evidence_manifest_path": str(manifest_path),
                "evidence_manifest_sha256": manifest_sha,
            }
        )
    )
    info = service.document_info("board.dip")
    assert info["result"]["validation_level"] == "synthetic_parser_only"
    assert info["result"]["requires_diptrace_verification"] is True


def test_evidence_manifest_document_path_mismatch_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    document = tmp_path / "board.dip"
    other = tmp_path / "other.dip"
    source = tmp_path / "source.dip"
    saved = tmp_path / "saved.dip"
    for path in (document, other, source, saved):
        path.write_bytes(_pcb_trace_xml())
    doc_sha = hashlib.sha256(document.read_bytes()).hexdigest()
    manifest = UserSuppliedRoundtripEvidence(
        document_path=str(other),
        document_sha256=doc_sha,
        source=_evidence_file(source, "DipTrace-PCB"),
        saved=_evidence_file(saved, "DipTrace-PCB"),
        semantic_comparison=SemanticComparisonEvidence(
            passed=True, comparison_complete=True, compared_categories=["source_type"]
        ),
        validation_level=FixtureValidationLevel.synthetic_operation_fixture,
        status="recorded",
        created_at=utc_now(),
    )
    manifest_path = tmp_path / "evidence.json"
    manifest_path.write_text(manifest.model_dump_json())
    sidecar = DocumentProvenance(
        provenance="user_supplied_evidence_recorded",
        validation_level=FixtureValidationLevel.synthetic_operation_fixture,
        current_document_sha256=doc_sha,
        authority=ProvenanceAuthority.user_supplied_evidence,
        evidence_manifest_path=str(manifest_path),
        evidence_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    document.with_suffix(document.suffix + ".provenance.json").write_text(sidecar.model_dump_json())
    info = service.document_info("board.dip")
    assert info["result"]["validation_level"] == "synthetic_parser_only"


def test_hardlink_evidence_roles_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = tmp_path / "source.dip"
    saved = tmp_path / "saved.dip"
    target = tmp_path / "board.dip"
    source.write_bytes(_pcb_trace_xml())
    try:
        os.link(source, saved)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")
    target.write_bytes(source.read_bytes())
    with pytest.raises(EditError, match="different files"):
        service.record_roundtrip_evidence(
            "board.dip",
            source_path="source.dip",
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            saved_path="saved.dip",
        )


def test_symlink_evidence_roles_are_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = tmp_path / "source.dip"
    saved = tmp_path / "saved.dip"
    target = tmp_path / "board.dip"
    source.write_bytes(_pcb_trace_xml())
    try:
        saved.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    target.write_bytes(source.read_bytes())
    with pytest.raises(EditError, match="different files"):
        service.record_roundtrip_evidence(
            "board.dip",
            source_path="source.dip",
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            saved_path="saved.dip",
        )


def test_rollback_revalidates_restored_evidence(tmp_path: Path) -> None:
    service = _service(tmp_path)
    board = tmp_path / "board.dip"
    board.write_bytes((FIXTURES / "pcb.xml").read_bytes())
    original_sha = hashlib.sha256(board.read_bytes()).hexdigest()
    source = tmp_path / "source.dip"
    saved = tmp_path / "saved.dip"
    source.write_bytes(board.read_bytes())
    saved.write_bytes(board.read_bytes())
    manifest = UserSuppliedRoundtripEvidence(
        document_path=str(board),
        document_sha256=original_sha,
        source=_evidence_file(source, "DipTrace-PCB"),
        saved=_evidence_file(saved, "DipTrace-PCB"),
        semantic_comparison=SemanticComparisonEvidence(
            passed=True, comparison_complete=True, compared_categories=["source_type"]
        ),
        validation_level=FixtureValidationLevel.synthetic_operation_fixture,
        status="recorded",
        created_at=utc_now(),
    )
    manifest_path = tmp_path / "evidence.json"
    manifest_path.write_text(manifest.model_dump_json())
    provenance = DocumentProvenance(
        provenance="user_supplied_evidence_recorded",
        validation_level=FixtureValidationLevel.synthetic_operation_fixture,
        current_document_sha256=original_sha,
        authority=ProvenanceAuthority.user_supplied_evidence,
        evidence_manifest_path=str(manifest_path),
        evidence_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    board.with_suffix(board.suffix + ".provenance.json").write_text(provenance.model_dump_json())

    begun = service.begin_transaction("board.dip")
    txid = begun["transaction"]["txid"]
    service.stage_operations(
        txid,
        [
            {
                "kind": "set_component_value",
                "selector": {"refdes": ["R1"]},
                "value": "47k",
            }
        ],
    )
    preview = service.preview_transaction(txid)
    committed = service.commit_transaction(txid, preview["transaction"]["source_sha256"])
    manifest_path.write_text('{"tampered": true}')
    service.rollback_transaction(txid, committed["transaction"]["committed_sha256"])

    assert hashlib.sha256(board.read_bytes()).hexdigest() == original_sha
    restored = DocumentProvenance.model_validate_json(
        board.with_suffix(board.suffix + ".provenance.json").read_bytes()
    )
    assert restored.authority == ProvenanceAuthority.runtime
    assert restored.validation_level == FixtureValidationLevel.synthetic_operation_fixture
    assert restored.provenance == "mcp_rollback_synthetic"
