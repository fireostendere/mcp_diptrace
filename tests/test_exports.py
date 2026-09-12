from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.config import Settings
from diptrace_mcp.errors import CapabilityUnavailableError
from diptrace_mcp.service import DipTraceService

FIXTURES = Path(__file__).parent / "fixtures"


def _service(tmp_path: Path, raw: bytes | None = None) -> DipTraceService:
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "board.xml").write_bytes(raw or (FIXTURES / "pcb.xml").read_bytes())
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=tmp_path / "state",
            max_document_bytes=10_000_000,
        )
    )


def test_bom_export_is_bounded_and_does_not_disclose_state_path(tmp_path: Path) -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes().replace(b"<Value>10k</Value>", b"<Value>=cmd</Value>")
    service = _service(tmp_path, raw)

    result = service.export_bom("board.xml")
    record = result["result"]["export"]
    export_id = record["export_id"]

    assert result["ok"] is True
    assert all(uri.startswith(f"diptrace://export/{export_id}/") for uri in result["resources"])
    assert str(tmp_path) not in str(record)
    assert "'=cmd" in service.export_resource(export_id, "bom.csv")
    assert service.list_exports()["result"]["matched_count"] == 1


def test_release_manifest_is_explicitly_not_native_fabrication(tmp_path: Path) -> None:
    service = _service(tmp_path)

    result = service.export_fabrication_outputs("board.xml")
    manifest = result["result"]["export"]["manifest"]

    assert manifest["kind"] == "fabrication_manifest"
    assert "nets_without_traces_count" in manifest["board"]
    assert "unrouted_net_count" not in manifest["board"]
    assert "gerber" in manifest["not_generated"]
    assert any("not fabrication-ready" in item for item in result["limitations"])

    with pytest.raises(CapabilityUnavailableError):
        service.export_fabrication_outputs("board.xml", request_native_outputs=True)


@pytest.mark.parametrize("include_dnp", [False, True])
@pytest.mark.parametrize("field,value", [("DNP", "dnp"), ("Populate", "no")])
def test_assembly_population_is_consistent(
    tmp_path: Path, include_dnp: bool, field: str, value: str
) -> None:
    import csv
    import io

    raw = (FIXTURES / "pcb.xml").read_bytes().replace(
        b"<RefDes>R1</RefDes>",
        (f"<RefDes>R1</RefDes><AddFields><AddField><Name>{field}</Name>"
         f"<Text>{value}</Text></AddField></AddFields>").encode(),
    )
    service = _service(tmp_path, raw)
    result = service.export_assembly_outputs("board.xml", include_dnp=include_dnp)
    record = result["result"]["export"]
    rows = {}
    for name in ("bom.csv", "placement.csv"):
        text = service.export_resource(record["export_id"], name)
        rows[name] = list(csv.DictReader(io.StringIO(text)))
    assert {row["RefDes"] for row in rows["placement.csv"]} == (
        {"R1", "U1"} if include_dnp else {"U1"}
    )
    assert sum(int(row["Quantity"]) for row in rows["bom.csv"]) == len(rows["placement.csv"])
    assert record["manifest"]["include_dnp"] is include_dnp


def test_placement_negative_coordinates_remain_numbers(tmp_path: Path) -> None:
    import csv
    import io

    raw = (FIXTURES / "pcb.xml").read_bytes().replace(b'X="10"', b'X="-10"')
    service = _service(tmp_path, raw)
    record = service.export_assembly_outputs("board.xml")["result"]["export"]
    rows = list(csv.DictReader(io.StringIO(
        service.export_resource(record["export_id"], "placement.csv")
    )))
    assert float(rows[0]["X_mm"]) == -10.0


@pytest.mark.parametrize("value", ["=cmd", " +cmd", "\t@cmd", "\r-cmd", "-1+2"])
def test_csv_text_is_formula_safe_without_corrupting_numbers(value: str) -> None:
    from diptrace_mcp.exports import _safe_csv

    assert _safe_csv(value) == "'" + value
    assert _safe_csv(-1.25) == "-1.25"
    assert _safe_csv(-90) == "-90"


def test_release_bundle_has_source_bound_preflight_and_artifact_digests(tmp_path: Path) -> None:
    import hashlib
    import json

    service = _service(tmp_path)
    record = service.export_assembly_outputs("board.xml")["result"]["export"]
    manifest = record["manifest"]
    export_id = record["export_id"]
    preflight = json.loads(service.export_resource(export_id, "preflight.json"))
    assert preflight["source_sha256"] == record["source_sha256"]
    assert preflight["status"] == "blocked"  # The synthetic board has an explicit ratline.
    assert preflight["native_acceptance"] == "not_run"
    assert preflight["manual_gates"]
    assert manifest["preflight_status"] == preflight["status"]
    for name, identity in manifest["artifact_integrity"].items():
        payload = service.export_resource(export_id, name).encode("utf-8")
        assert identity == {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    assert set(manifest["artifact_integrity"]) == set(record["artifacts"]) - {"manifest.json"}
    assert (tmp_path / "project" / "board.xml").read_bytes() == (FIXTURES / "pcb.xml").read_bytes()



@pytest.mark.parametrize("name", ["placement.csv", "preflight.json", "manifest.json"])
def test_release_artifact_tampering_is_detected(tmp_path: Path, name: str) -> None:
    service = _service(tmp_path)
    record = service.export_assembly_outputs("board.xml")["result"]["export"]
    artifact = tmp_path / "state" / "exports" / record["export_id"] / name
    artifact.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity check failed"):
        service.export_resource(record["export_id"], name)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_csv_rejects_non_finite_numbers(value: float) -> None:
    from diptrace_mcp.exports import _safe_csv

    with pytest.raises(ValueError, match="finite"):
        _safe_csv(value)
