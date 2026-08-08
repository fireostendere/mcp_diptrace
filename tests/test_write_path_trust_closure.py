from __future__ import annotations

import shutil
from pathlib import Path

from diptrace_mcp.config import Settings
from diptrace_mcp.domain import DocumentProvenance, FixtureValidationLevel
from diptrace_mcp.scaffolding import build_pcb_document
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.sessions import SessionStore
from diptrace_mcp.xml_document import sha256_bytes

FIXTURES = Path(__file__).parent / "fixtures"
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


def _write_runtime_sidecar(service: DipTraceService, path: Path) -> None:
    raw = path.read_bytes()
    service._write_provenance_sidecar(
        path,
        DocumentProvenance(
            provenance="mcp_generated",
            validation_level=FixtureValidationLevel.synthetic_operation_fixture,
            current_document_sha256=sha256_bytes(raw),
        ),
    )


def _assert_transaction_invalidation(service: DipTraceService, path: Path) -> None:
    sidecar = service._load_seed_provenance(path)
    assert sidecar is not None
    assert sidecar.current_document_sha256 == sha256_bytes(path.read_bytes())
    assert sidecar.validation_level == FixtureValidationLevel.synthetic_operation_fixture
    assert sidecar.last_modified_by == "mcp_transaction_commit"


def _make_value_plan(
    service: DipTraceService,
    path: Path,
    *,
    plan_type: str,
):
    info = service.document_info(str(path))["result"]
    return service.plans.create(
        plan_type=plan_type,
        document_id=info["document_id"],
        source_sha256=info["sha256"],
        target_path=path,
        config={},
        operations=[
            {
                "kind": "set_component_value",
                "selector": {"refdes": ["R1"]},
                "value": "47k",
            }
        ],
        changed_ids=[],
        unresolved=[],
        candidates=[],
        score={},
        metrics={},
        assumptions=[],
        warnings=[],
        limitations=[],
    )


def test_generic_plan_apply_invalidates_trust_after_real_commit(tmp_path: Path) -> None:
    board = tmp_path / "board.dip"
    shutil.copy2(FIXTURES / "pcb.xml", board)
    service = _service(tmp_path)
    _write_runtime_sidecar(service, board)
    plan = _make_value_plan(service, board, plan_type="trust_regression")

    result = service._apply_stored_plan(
        plan.plan_id,
        expected_plan_type="trust_regression",
        dry_run=False,
        expected_sha256=plan.source_sha256,
        txid=None,
    )

    assert result["written"] is True
    assert result["transaction"]["status"] == "committed"
    _assert_transaction_invalidation(service, board)


def test_ses_import_entry_point_invalidates_trust_after_real_commit(tmp_path: Path) -> None:
    board = tmp_path / "board.dip"
    shutil.copy2(FIXTURES / "pcb.xml", board)
    service = _service(tmp_path)
    _write_runtime_sidecar(service, board)
    plan = _make_value_plan(service, board, plan_type="autorouter_ses_import")

    result = service.import_autorouter_ses(
        plan.plan_id,
        dry_run=False,
        expected_sha256=plan.source_sha256,
    )

    assert result["written"] is True
    assert result["plan"]["status"] == "committed"
    _assert_transaction_invalidation(service, board)


def test_schematic_to_pcb_sync_invalidates_trust_after_real_commit(tmp_path: Path) -> None:
    schematic = tmp_path / "schematic.dch"
    pattern_library = tmp_path / "patterns.lib"
    board = tmp_path / "board.dip"
    shutil.copy2(FIXTURES / "schematic.xml", schematic)
    shutil.copy2(FIXTURES / "pattern_library.xml", pattern_library)
    board.write_bytes(build_pcb_document())
    service = _service(tmp_path)
    _write_runtime_sidecar(service, board)
    source_sha = sha256_bytes(board.read_bytes())

    result = service.sync_schematic_to_pcb(
        str(schematic),
        str(board),
        component_mappings=[
            {"refdes": "R1", "pattern_style": "PatType0"},
            {
                "refdes": "U1",
                "pattern_style": "PatType1",
                "pin_map": [
                    {"part_id": "1", "pin": 0, "pad_number": "1"},
                    {"part_id": "2", "pin": 0, "pad_number": "2"},
                ],
            },
        ],
        pattern_library_paths=[str(pattern_library)],
        dry_run=False,
        expected_sha256=source_sha,
    )

    assert result["written"] is True
    assert result["transaction"]["status"] == "committed"
    _assert_transaction_invalidation(service, board)


def test_live_apply_cannot_preserve_stale_exchange_trust(tmp_path: Path) -> None:
    exchange = tmp_path / "plugin_exchange.xml"
    shutil.copy2(FIXTURES / "pcb.xml", exchange)
    service = _service(tmp_path)
    _write_runtime_sidecar(service, exchange)
    original_sha = sha256_bytes(exchange.read_bytes())

    metadata = service.sessions.create(exchange)
    session_id = str(metadata["session_id"])
    working = service.sessions.working_path(session_id)
    changed = working.read_bytes().replace(b"<Value>10k</Value>", b"<Value>68k</Value>")
    working.write_bytes(changed)
    changed_sha = sha256_bytes(changed)

    request = service.sessions.request_finish("apply", changed_sha)
    result = service.sessions.finalize(
        session_id,
        "apply",
        str(request["expected_sha256"]),
    )

    assert result["status"] == "applied"
    assert sha256_bytes(exchange.read_bytes()) == changed_sha
    assert changed_sha != original_sha
    effective = service.resolve_effective_document_trust(exchange, changed_sha)
    assert effective.validation_level == FixtureValidationLevel.synthetic_parser_only
    assert effective.requires_diptrace_verification is True
    assert effective.warnings


def test_live_session_store_is_the_same_binding_used_by_service(tmp_path: Path) -> None:
    service = _service(tmp_path)
    assert isinstance(service.sessions, SessionStore)
