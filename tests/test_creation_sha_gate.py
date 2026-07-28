from __future__ import annotations

from pathlib import Path

import pytest

import diptrace_mcp.service as service_module
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import (
    ConfirmationRequiredError,
    EditError,
    PathAccessError,
    Sha256MismatchError,
)
from diptrace_mcp.scaffolding import (
    SchematicScaffold,
    build_pcb_document,
    build_schematic_document,
)
from diptrace_mcp.server import create_server
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.write_limits import WriteImpact
from diptrace_mcp.xml_document import sha256_bytes

MAX_BYTES = 20_000_000


def _service(workspace: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=workspace / ".state",
            max_document_bytes=MAX_BYTES,
        )
    )


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _assert_refusal_preserved_target_and_state(
    target: Path,
    *,
    target_bytes: bytes,
    sidecar_bytes: bytes,
    state_before: dict[str, bytes],
) -> None:
    assert target.read_bytes() == target_bytes
    assert target.with_suffix(target.suffix + ".provenance.json").read_bytes() == sidecar_bytes
    assert _tree_snapshot(target.parent / ".state") == state_before


def test_synthetic_overwrite_requires_current_target_sha_without_side_effects(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    created = service.create_document("pcb", "board.dip")
    target = tmp_path / "board.dip"
    sidecar = target.with_suffix(".dip.provenance.json")
    target_bytes = target.read_bytes()
    sidecar_bytes = sidecar.read_bytes()
    state_before = _tree_snapshot(tmp_path / ".state")

    with pytest.raises(ConfirmationRequiredError) as missing:
        service.create_document("pcb", "board.dip", overwrite=True)
    assert missing.value.payload.code == "confirmation_required"
    _assert_refusal_preserved_target_and_state(
        target,
        target_bytes=target_bytes,
        sidecar_bytes=sidecar_bytes,
        state_before=state_before,
    )

    with pytest.raises(Sha256MismatchError) as wrong:
        service.create_document(
            "pcb",
            "board.dip",
            overwrite=True,
            expected_sha256="0" * 64,
        )
    assert wrong.value.payload.details == {
        "expected_sha256": "0" * 64,
        "current_sha256": created["result"]["sha256"],
        "path": str(target),
    }
    _assert_refusal_preserved_target_and_state(
        target,
        target_bytes=target_bytes,
        sidecar_bytes=sidecar_bytes,
        state_before=state_before,
    )

    replaced = service.create_document(
        "schematic",
        "board.dip",
        sheets=["Main"],
        overwrite=True,
        expected_sha256=created["result"]["sha256"],
    )

    backup = Path(replaced["result"]["backup"])
    assert replaced["result"]["kind"] == "schematic"
    assert backup.read_bytes() == target_bytes
    assert target.read_bytes() != target_bytes


def test_seed_overwrite_requires_target_sha_distinct_from_seed_sha(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    created = service.create_document("schematic", "target.dch")
    target = tmp_path / "target.dch"
    seed_bytes = build_pcb_document(version="5.3.0.2")
    (tmp_path / "seed.dip").write_bytes(seed_bytes)
    target_bytes = target.read_bytes()
    sidecar = target.with_suffix(".dch.provenance.json")
    sidecar_bytes = sidecar.read_bytes()
    state_before = _tree_snapshot(tmp_path / ".state")

    with pytest.raises(ConfirmationRequiredError):
        service.create_document_from_seed(
            "seed.dip",
            "target.dch",
            overwrite=True,
        )
    _assert_refusal_preserved_target_and_state(
        target,
        target_bytes=target_bytes,
        sidecar_bytes=sidecar_bytes,
        state_before=state_before,
    )

    with pytest.raises(Sha256MismatchError):
        service.create_document_from_seed(
            "seed.dip",
            "target.dch",
            expected_seed_sha256=service.document_info("seed.dip")["result"]["sha256"],
            overwrite=True,
            expected_sha256="f" * 64,
        )
    _assert_refusal_preserved_target_and_state(
        target,
        target_bytes=target_bytes,
        sidecar_bytes=sidecar_bytes,
        state_before=state_before,
    )

    replaced = service.create_document_from_seed(
        "seed.dip",
        "target.dch",
        overwrite=True,
        expected_sha256=created["result"]["sha256"],
    )

    assert target.read_bytes() == seed_bytes
    assert Path(replaced["result"]["backup"]).read_bytes() == target_bytes
    assert replaced["result"]["seed_sha256"] == replaced["result"]["sha256"]


def test_new_creation_targets_do_not_require_expected_sha(tmp_path: Path) -> None:
    service = _service(tmp_path)
    (tmp_path / "seed.dip").write_bytes(build_pcb_document())

    synthetic = service.create_document("pcb", "new.dip")
    seeded = service.create_document_from_seed("seed.dip", "seed-copy.dip")

    assert synthetic["result"]["backup"] is None
    assert seeded["result"]["backup"] is None


def test_new_target_that_appears_during_validation_is_not_overwritten(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    target = tmp_path / "new.dip"
    external_bytes = build_pcb_document(version="5.3.0.2")
    state_before = _tree_snapshot(tmp_path / ".state")
    original_require = service_module.require_write_impact

    def create_external_target(impact: WriteImpact, *, operation: str) -> None:
        target.write_bytes(external_bytes)
        original_require(impact, operation=operation)

    monkeypatch.setattr(service_module, "require_write_impact", create_external_target)

    with pytest.raises(EditError) as appeared:
        service.create_document("pcb", "new.dip")

    assert appeared.value.payload.code == "path_exists"
    assert target.read_bytes() == external_bytes
    assert _tree_snapshot(tmp_path / ".state") == state_before


def test_overwrite_target_disappearance_keeps_write_error_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    created = service.create_document("pcb", "board.dip")
    target = tmp_path / "board.dip"
    original_require = service_module.require_write_impact

    def remove_target_after_validation(impact: WriteImpact, *, operation: str) -> None:
        original_require(impact, operation=operation)
        target.unlink()

    monkeypatch.setattr(
        service_module,
        "require_write_impact",
        remove_target_after_validation,
    )

    with pytest.raises(EditError) as disappeared:
        service.create_document(
            "schematic",
            "board.dip",
            overwrite=True,
            expected_sha256=created["result"]["sha256"],
        )

    assert disappeared.value.payload.code == "schema_write_error"
    assert disappeared.value.payload.details == {"path": str(target)}
    assert "Cannot read target before write" in str(disappeared.value)


def test_overwrite_backup_binds_the_exact_bytes_checked_by_the_caller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    created = service.create_document("pcb", "board.dip")
    target = tmp_path / "board.dip"
    external_bytes = build_schematic_document(
        SchematicScaffold(sheet_names=["External writer"])
    )
    state_before = _tree_snapshot(tmp_path / ".state")
    original_writer = service.backups.write_with_backup

    def race_before_backup(
        path: Path,
        data: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> Path:
        path.write_bytes(external_bytes)
        return original_writer(
            path,
            data,
            expected_sha256=expected_sha256,
        )

    monkeypatch.setattr(service.backups, "write_with_backup", race_before_backup)

    with pytest.raises(Sha256MismatchError) as raced:
        service.create_document(
            "schematic",
            "board.dip",
            sheets=["MCP replacement"],
            overwrite=True,
            expected_sha256=created["result"]["sha256"],
        )

    assert raced.value.payload.details["current_sha256"] == sha256_bytes(external_bytes)
    assert target.read_bytes() == external_bytes
    assert _tree_snapshot(tmp_path / ".state") == state_before


def test_transaction_rechecks_after_backup_state_is_captured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    created = service.create_document("schematic", "main.dch")
    target = tmp_path / "main.dch"
    preview = service.add_sheet("MCP sheet", path="main.dch")
    txid = preview["transaction"]["txid"]
    external_bytes = build_schematic_document(
        SchematicScaffold(sheet_names=["External writer"])
    )
    transaction_store_type = type(service.transactions)
    original_store_backup = transaction_store_type.store_backup

    def store_then_race(
        store: object,
        transaction_id: str,
        raw_bytes: bytes,
    ) -> Path:
        backup = original_store_backup(store, transaction_id, raw_bytes)
        target.write_bytes(external_bytes)
        return backup

    monkeypatch.setattr(transaction_store_type, "store_backup", store_then_race)

    with pytest.raises(Sha256MismatchError):
        service.commit_transaction(txid, created["result"]["sha256"])

    assert target.read_bytes() == external_bytes
    assert service.transactions.read(txid).status == "validated"


def test_overwrite_gate_preserves_path_and_validation_error_precedence(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    created = service.create_document("pcb", "board.dip")

    with pytest.raises(EditError) as exists:
        service.create_document(
            "pcb",
            "board.dip",
            overwrite=False,
            expected_sha256=created["result"]["sha256"],
        )
    assert exists.value.payload.code == "path_exists"

    with pytest.raises(EditError) as invalid_kind:
        service.create_document(
            "library",
            "board.dip",
            overwrite=True,
        )
    assert invalid_kind.value.payload.code == "invalid_request"

    with pytest.raises(PathAccessError):
        service.create_document(
            "pcb",
            "../outside.dip",
            overwrite=True,
        )

    with pytest.raises(EditError, match="Seed SHA-256 mismatch") as seed_mismatch:
        service.create_document_from_seed(
            "board.dip",
            "board.dip",
            expected_seed_sha256="0" * 64,
            overwrite=True,
        )
    assert seed_mismatch.value.payload.code == "sha256_mismatch"


def test_creation_tool_schemas_expose_conditional_target_sha_gate() -> None:
    server = create_server()

    for name in (
        "create_schematic_document",
        "create_pcb_document",
        "create_document_from_seed",
    ):
        tool = server._tool_manager._tools[name]
        expected = tool.parameters["properties"]["expected_sha256"]["anyOf"][0]
        assert expected["pattern"] == "^[0-9a-f]{64}$"
        assert "existing target" in expected["description"]
        assert "expected_sha256" not in tool.parameters.get("required", [])
        assert "current SHA" in (tool.description or "")


def test_scaffold_tool_descriptions_disclose_synthetic_validation() -> None:
    server = create_server()

    for name in ("create_schematic_document", "create_pcb_document"):
        description = server._tool_manager._tools[name].description or ""
        assert "synthetic" in description.casefold()

    schematic_description = (
        server._tool_manager._tools["create_schematic_document"].description or ""
    )
    assert "not DipTrace-verified" in schematic_description


def test_capabilities_include_live_apply_in_required_sha_scope(tmp_path: Path) -> None:
    service = _service(tmp_path)
    limits = service.get_capabilities()["limits"]

    assert limits["expected_sha256_required_for"] == [
        "semantic design-file commit",
        "raw XML design-file write",
        "committed transaction rollback",
        "synthetic document overwrite of an existing target",
        "seed copy overwrite of an existing target",
        "live-session replacement of the external exchange file",
    ]
    assert limits["expected_sha256_not_required_for"] == [
        "creation of a target that does not exist"
    ]
    assert limits["expected_sha256_exemptions"] == []
