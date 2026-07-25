from __future__ import annotations

import builtins
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import capture_diptrace_evidence as capture_module  # noqa: E402
from capture_diptrace_evidence import (  # noqa: E402
    CANDIDATE_SCHEMA,
    SECURE_DIR_FD_AVAILABLE,
    CaptureError,
    CaptureRepository,
    _interactive_answers,
    inspect_xml,
    run_cli,
)


def write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def recipe(*, expected_source_type: str | None = "DipTrace-PCB") -> dict[str, object]:
    return {
        "schema_version": "diptrace-capture-recipe-v1",
        "recipe_id": "pcb-angle-probe",
        "title": "PCB angle probe",
        "purpose": "Collect operator-produced XML for an unresolved format question.",
        "expected_source_type": expected_source_type,
        "required_features": ["one visibly rotated component", "one unrotated control"],
        "operator_checklist": [
            {
                "id": "features_seen",
                "prompt": "Confirm both requested controls are visible in DipTrace.",
                "required": True,
                "stage": "source",
            },
            {
                "id": "unrelated_change",
                "prompt": "Record whether DipTrace changed unrelated objects.",
                "required": False,
                "stage": "reexport",
            },
        ],
    }


def answers(*, redistribution_permitted: bool = True) -> dict[str, object]:
    return {
        "operator_label": "lab-operator-a",
        "diptrace_version": "5.3.0.1",
        "diptrace_build": "build-123",
        "operating_system": "Windows 11 24H2",
        "redistribution_permitted": redistribution_permitted,
        "redistribution_basis": "Original test design created for this project"
        if redistribution_permitted
        else "",
        "notes": "No customer data.",
    }


def attestations(stage: str) -> dict[str, bool]:
    return {
        "source": {
            "direct_diptrace_export": True,
            "no_programmatic_xml_generation": True,
        },
        "open_save": {
            "opened_in_diptrace": True,
            "saved_by_diptrace": True,
        },
        "reexport": {
            "fresh_diptrace_export": True,
            "no_programmatic_xml_generation": True,
        },
    }[stage]


def xml_bytes(
    *,
    source_type: str = "DipTrace-PCB",
    version: str = "5.3.0.1",
    units: str = "mm",
    marker: str = "",
) -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Source Type="{source_type}" Version="{version}" Units="{units}">'
        f"<Components><Component Id=\"1\"><Pads><Pad Id=\"2\"/></Pads></Component>"
        f"</Components>{marker}</Source>"
    ).encode()


@pytest.fixture
def capture_root(tmp_path: Path) -> Path:
    write_json(tmp_path / "recipe.json", recipe())
    return tmp_path


def initialized_repository(
    capture_root: Path,
    *,
    session: str = "capture-001",
    redistribution_permitted: bool = True,
) -> CaptureRepository:
    repository = CaptureRepository(capture_root)
    repository.init_session(
        session,
        "recipe.json",
        answers(redistribution_permitted=redistribution_permitted),
    )
    return repository


def record_all(
    repository: CaptureRepository,
    root: Path,
    *,
    session: str = "capture-001",
) -> None:
    for index, stage in enumerate(("source", "open_save", "reexport"), start=1):
        path = root / f"{stage}.xml"
        path.write_bytes(xml_bytes(marker=f"<!-- stage {index} -->"))
        repository.record_stage(session, stage, path, attestations(stage))


def make_ready(
    repository: CaptureRepository,
    root: Path,
    *,
    session: str = "capture-001",
) -> None:
    record_all(repository, root, session=session)
    repository.answer_checklist(session, "features_seen", "yes", note="Observed on screen")


def test_inspect_xml_records_literal_identity_and_object_counts() -> None:
    inventory = inspect_xml(xml_bytes())
    assert inventory.source_type == "DipTrace-PCB"
    assert inventory.version == "5.3.0.1"
    assert inventory.units == "mm"
    assert inventory.element_count == 4
    assert inventory.element_counts == {
        "Component": 1,
        "Components": 1,
        "Pad": 1,
        "Pads": 1,
    }
    assert inventory.direct_child_counts == {"Components": 1}


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16-le", "utf-16-be"])
def test_entity_or_doctype_is_rejected_in_supported_encodings(encoding: str) -> None:
    hostile = (
        '<?xml version="1.0"?><!DOCTYPE Source [<!ENTITY x "boom">]>'
        '<Source Type="DipTrace-PCB" Version="5.3.0.1" Units="mm"><X>&x;</X></Source>'
    ).encode(encoding)
    with pytest.raises(CaptureError, match="DTDs or entities") as caught:
        inspect_xml(hostile)
    assert caught.value.code == "forbidden_xml_declaration"
    assert caught.value.exit_code == 3


def test_parser_level_handler_rejects_doctype_if_outer_guard_is_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hostile = (
        b'<!DOCTYPE Source [<!ENTITY x "boom">]>'
        b'<Source Type="DipTrace-PCB"><X>&x;</X></Source>'
    )
    monkeypatch.setattr(capture_module, "reject_unsafe_xml", lambda _data: None)
    with pytest.raises(CaptureError) as caught:
        inspect_xml(hostile)
    assert caught.value.code == "forbidden_xml_declaration"


def test_clean_utf16_document_is_accepted() -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Source Type="DipTrace-Schematic" Version="5.3.0.1" Units="inch">'
        "<Sheets><Sheet/></Sheets></Source>"
    )
    inventory = inspect_xml(text.encode("utf-16"))
    assert inventory.source_type == "DipTrace-Schematic"
    assert inventory.units == "inch"
    assert inventory.element_counts == {"Sheet": 1, "Sheets": 1}


def test_wrong_root_source_type_and_units_are_typed_errors() -> None:
    with pytest.raises(CaptureError) as wrong_root:
        inspect_xml(b"<Board/>")
    assert wrong_root.value.code == "not_diptrace_source"

    with pytest.raises(CaptureError) as wrong_type:
        inspect_xml(b'<Source Type="Not-DipTrace"/>')
    assert wrong_type.value.code == "unsupported_source_type"

    with pytest.raises(CaptureError) as wrong_units:
        inspect_xml(b'<Source Type="DipTrace-PCB" Units="cm"/>')
    assert wrong_units.value.code == "unsupported_document_units"


def test_allowed_root_rejects_files_outside_it(capture_root: Path) -> None:
    outside = Path(str(capture_root) + "-outside.xml")
    outside.write_bytes(xml_bytes())
    repository = CaptureRepository(capture_root)
    try:
        with pytest.raises(CaptureError) as caught:
            repository.allowed_file(outside, role="stage_file")
        assert caught.value.code == "path_outside_allowed_root"
        assert caught.value.exit_code == 3
    finally:
        outside.unlink()


def test_allowed_root_rejects_symlink_escape(capture_root: Path) -> None:
    outside = Path(str(capture_root) + "-outside.xml")
    outside.write_bytes(xml_bytes())
    link = capture_root / "escaped.xml"
    try:
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symlinks are unavailable on this platform")
        repository = CaptureRepository(capture_root)
        with pytest.raises(CaptureError) as caught:
            repository.allowed_file(link, role="stage_file")
        assert caught.value.code == "path_outside_allowed_root"
    finally:
        link.unlink(missing_ok=True)
        outside.unlink()


def test_session_directory_symlink_cannot_redirect_state_write(capture_root: Path) -> None:
    repository = CaptureRepository(capture_root)
    outside = Path(str(capture_root) + "-outside-session")
    outside.mkdir()
    redirected = repository.sessions / "redirected-session"
    try:
        try:
            redirected.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("Symlinks are unavailable on this platform")
        with pytest.raises(CaptureError) as caught:
            repository.init_session("redirected-session", "recipe.json", answers())
        assert caught.value.code == "unsafe_store_path"
        assert not (outside / "state.json").exists()
        assert not (outside / ".lock").exists()
    finally:
        redirected.unlink(missing_ok=True)
        outside.rmdir()


def test_quarantine_descendant_symlink_cannot_redirect_artifact(
    capture_root: Path,
) -> None:
    repository = initialized_repository(capture_root)
    outside = Path(str(capture_root) + "-outside-quarantine")
    outside.mkdir()
    session_quarantine = repository.quarantine / "capture-001"
    session_quarantine.mkdir()
    redirected = session_quarantine / "source"
    source = capture_root / "source.xml"
    source.write_bytes(xml_bytes())
    try:
        try:
            redirected.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("Symlinks are unavailable on this platform")
        with pytest.raises(CaptureError) as caught:
            repository.record_stage(
                "capture-001",
                "source",
                source,
                attestations("source"),
            )
        assert caught.value.code == "unsafe_store_path"
        assert not (outside / "source.xml").exists()
    finally:
        redirected.unlink(missing_ok=True)
        outside.rmdir()


@pytest.mark.skipif(
    not SECURE_DIR_FD_AVAILABLE,
    reason="Descriptor-relative containment is a POSIX safety contract",
)
def test_posix_root_descriptor_prevents_concurrent_root_redirection(tmp_path: Path) -> None:
    root = tmp_path / "capture-root"
    root.mkdir()
    write_json(root / "recipe.json", recipe())
    repository = initialized_repository(root)
    moved_root = tmp_path / "capture-root-pinned"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.rename(moved_root)
    root.symlink_to(outside, target_is_directory=True)
    try:
        result = repository.resume("capture-001")
        assert result["status"] == "active"
        assert (moved_root / ".diptrace-capture/sessions/capture-001/state.json").is_file()
        assert not (outside / ".diptrace-capture").exists()
    finally:
        root.unlink()
        moved_root.rename(root)


@pytest.mark.skipif(
    not SECURE_DIR_FD_AVAILABLE,
    reason="Descriptor-relative containment is a POSIX safety contract",
)
def test_posix_input_swap_after_validation_is_refused(
    capture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = CaptureRepository(capture_root)
    source = capture_root / "source.xml"
    source.write_bytes(xml_bytes())
    outside = Path(str(capture_root) + "-outside.xml")
    outside.write_bytes(xml_bytes(marker="<!-- outside -->"))
    original_allowed_file = repository.allowed_file

    def validate_then_swap(path: Path | str, *, role: str) -> Path:
        resolved = original_allowed_file(path, role=role)
        source.unlink()
        source.symlink_to(outside)
        return resolved

    monkeypatch.setattr(repository, "allowed_file", validate_then_swap)
    try:
        with pytest.raises(CaptureError) as caught:
            repository.read_allowed_file(source, role="stage_file")
        assert caught.value.code == "unsafe_stage_file"
        assert caught.value.exit_code == 3
    finally:
        source.unlink(missing_ok=True)
        outside.unlink()


def test_recipe_snapshot_and_sha_come_from_one_read(
    capture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = CaptureRepository(capture_root)
    recipe_path = capture_root / "recipe.json"
    original_bytes = recipe_path.read_bytes()
    original_reader = repository._read_root_file
    reads = 0

    def read_then_change(path: Path, *, base: Path, role: str) -> bytes:
        nonlocal reads
        reads += 1
        result = original_reader(path, base=base, role=role)
        recipe_path.write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(repository, "_read_root_file", read_then_change)
    state = repository.init_session("single-read", "recipe.json", answers())
    assert reads == 1
    assert state["recipe"]["source_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert state["recipe"]["snapshot"]["recipe_id"] == "pcb-angle-probe"


def test_corrupt_state_is_a_typed_error(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    state_path = repository.state_path("capture-001")
    state = json.loads(state_path.read_bytes())
    del state["events"]
    write_json(state_path, state)
    with pytest.raises(CaptureError) as caught:
        repository.status("capture-001")
    assert caught.value.code == "invalid_session_state"
    assert caught.value.exit_code == 3


def test_recipe_and_answers_are_strict(capture_root: Path) -> None:
    bad_recipe = recipe()
    bad_recipe["invented"] = True
    write_json(capture_root / "bad-recipe.json", bad_recipe)
    repository = CaptureRepository(capture_root)
    with pytest.raises(CaptureError) as caught:
        repository.init_session("bad-recipe", "bad-recipe.json", answers())
    assert caught.value.code == "invalid_recipe"

    bad_answers = answers()
    bad_answers["redistribution_permitted"] = "yes"
    with pytest.raises(CaptureError) as caught:
        repository.init_session("bad-answers", "recipe.json", bad_answers)
    assert caught.value.code == "invalid_answers"


def test_end_to_end_emits_review_only_hash_bound_candidate(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    make_ready(repository, capture_root)
    assert repository.status("capture-001")["recorded_stages"] == [
        "source",
        "open_save",
        "reexport",
    ]

    result = repository.finalize("capture-001")
    manifest_path = capture_root / result["manifest_path"]
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)

    assert manifest["schema_version"] == CANDIDATE_SCHEMA
    assert manifest["authority"] == "operator_supplied_unverified"
    assert manifest["trust_grant"] == "none"
    assert manifest["candidate_only"] is True
    assert manifest["review_status"] == "pending_independent_review"
    assert manifest["requires_independent_review"] is True
    assert manifest["must_not_copy_to_acceptance_without_review"] is True
    assert manifest["capture_invariants"]["trust_promoted_by_capture_tool"] is False
    assert set(manifest["stages"]) == {"source", "open_save", "reexport"}
    assert manifest["capture_invariants"]["stages_recorded_in_order"] is True
    assert manifest["stages"]["source"]["xml_inventory"]["source_type"] == "DipTrace-PCB"
    assert manifest["stages"]["source"]["xml_inventory"]["version"] == "5.3.0.1"
    assert manifest["stages"]["source"]["xml_inventory"]["units"] == "mm"
    assert result["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    digest_path = capture_root / result["digest_path"]
    assert digest_path.read_text().startswith(result["manifest_sha256"])
    assert "tests/fixtures/acceptance" not in str(manifest_path)


def test_quarantine_is_a_byte_identical_copy(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    source = capture_root / "source.xml"
    original = xml_bytes(marker="<!-- exact bytes -->")
    source.write_bytes(original)
    record = repository.record_stage(
        "capture-001",
        "source",
        source,
        attestations("source"),
    )
    quarantined = capture_root / record["quarantine_path"]
    assert quarantined.read_bytes() == original
    assert record["sha256"] == hashlib.sha256(original).hexdigest()
    assert record["original_path"] == "source.xml"
    assert not Path(record["original_path"]).is_absolute()


def test_stages_must_be_recorded_in_order(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    path = capture_root / "reexport.xml"
    path.write_bytes(xml_bytes())
    with pytest.raises(CaptureError) as caught:
        repository.record_stage(
            "capture-001",
            "reexport",
            path,
            attestations("reexport"),
        )
    assert caught.value.code == "stage_out_of_order"


def test_stages_cannot_reuse_one_source_file(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    path = capture_root / "shared.xml"
    path.write_bytes(xml_bytes())
    repository.record_stage(
        "capture-001",
        "source",
        path,
        attestations("source"),
    )
    with pytest.raises(CaptureError) as caught:
        repository.record_stage(
            "capture-001",
            "open_save",
            path,
            attestations("open_save"),
        )
    assert caught.value.code == "evidence_role_conflict"


def test_stage_type_must_match_recipe_and_first_stage(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    wrong = capture_root / "source.xml"
    wrong.write_bytes(xml_bytes(source_type="DipTrace-Schematic"))
    with pytest.raises(CaptureError) as caught:
        repository.record_stage(
            "capture-001",
            "source",
            wrong,
            attestations("source"),
        )
    assert caught.value.code == "source_type_mismatch"


def test_attestations_must_be_explicit_and_are_never_treated_as_authority(
    capture_root: Path,
) -> None:
    repository = initialized_repository(capture_root)
    source = capture_root / "source.xml"
    source.write_bytes(xml_bytes())
    with pytest.raises(CaptureError) as caught:
        repository.record_stage(
            "capture-001",
            "source",
            source,
            {
                "direct_diptrace_export": True,
                "no_programmatic_xml_generation": False,
            },
        )
    assert caught.value.code == "attestation_not_confirmed"


def test_checklist_item_cannot_be_answered_before_its_stage(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    with pytest.raises(CaptureError) as caught:
        repository.answer_checklist("capture-001", "features_seen", "yes")
    assert caught.value.code == "checklist_stage_not_recorded"
    assert caught.value.exit_code == 4

    source = capture_root / "source.xml"
    source.write_bytes(xml_bytes())
    repository.record_stage(
        "capture-001",
        "source",
        source,
        attestations("source"),
    )
    assert repository.answer_checklist("capture-001", "features_seen", "yes")["answer"] == "yes"


def test_incomplete_session_cannot_finalize(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    with pytest.raises(CaptureError) as caught:
        repository.finalize("capture-001")
    assert caught.value.code == "capture_incomplete"
    status = repository.status("capture-001")
    assert status["readiness"]["next_stage"] == "source"
    assert status["readiness"]["pending_required_checklist"] == ["features_seen"]


def test_quarantine_tampering_blocks_finalization(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    make_ready(repository, capture_root)
    state = repository.load_state("capture-001")
    stage_path = capture_root / state["stages"]["source"]["quarantine_path"]
    stage_path.write_bytes(b"tampered")

    status = repository.status("capture-001")
    assert status["readiness"]["ready_to_finalize"] is False
    assert status["readiness"]["integrity_errors"] == ["source:quarantine_sha256_mismatch"]
    with pytest.raises(CaptureError) as caught:
        repository.finalize("capture-001")
    assert caught.value.code == "capture_incomplete"


def test_finalize_is_idempotent_and_detects_later_manifest_tampering(
    capture_root: Path,
) -> None:
    repository = initialized_repository(capture_root)
    make_ready(repository, capture_root)
    first = repository.finalize("capture-001")
    assert repository.finalize("capture-001") == first

    manifest_path = capture_root / first["manifest_path"]
    manifest_path.write_text("{}", encoding="utf-8")
    with pytest.raises(CaptureError) as caught:
        repository.finalize("capture-001")
    assert caught.value.code == "candidate_sha256_mismatch"


def test_candidate_digest_tampering_is_reported(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    make_ready(repository, capture_root)
    result = repository.finalize("capture-001")
    digest_path = capture_root / result["digest_path"]
    digest_path.write_text("0" * 64 + "  wrong.json\n", encoding="ascii")
    status = repository.status("capture-001")
    assert status["candidate_integrity_errors"] == ["candidate_digest_mismatch"]
    with pytest.raises(CaptureError) as caught:
        repository.finalize("capture-001")
    assert caught.value.code == "candidate_digest_mismatch"


def test_finalize_recovers_after_interruption_between_manifest_and_state(
    capture_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = initialized_repository(capture_root)
    make_ready(repository, capture_root)
    original = repository._bind_candidate_to_state

    def interrupt(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(repository, "_bind_candidate_to_state", interrupt)
    with pytest.raises(RuntimeError, match="interruption"):
        repository.finalize("capture-001")
    monkeypatch.setattr(repository, "_bind_candidate_to_state", original)

    recovered = repository.finalize("capture-001")
    state = repository.load_state("capture-001")
    assert state["status"] == "candidate_ready"
    assert state["events"][-1]["kind"] == "candidate_recovered"
    assert recovered["manifest_sha256"]


def test_existing_lock_file_does_not_block_resume(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    lock_path = repository.session_dir("capture-001") / ".lock"
    lock_path.write_text("stale text from terminated process", encoding="utf-8")
    result = repository.resume("capture-001")
    assert result["status"] == "active"


def test_live_lock_conflict_is_typed(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    with (
        repository.mutation_lock("capture-001"),
        pytest.raises(CaptureError) as caught,
        repository.mutation_lock("capture-001"),
    ):
        pass
    assert caught.value.code == "session_locked"
    assert caught.value.exit_code == 4


def test_abort_preserves_quarantine_and_cannot_resume(capture_root: Path) -> None:
    repository = initialized_repository(capture_root)
    source = capture_root / "source.xml"
    source.write_bytes(xml_bytes())
    record = repository.record_stage(
        "capture-001",
        "source",
        source,
        attestations("source"),
    )
    quarantined = capture_root / record["quarantine_path"]
    result = repository.abort("capture-001", "Operator found the wrong design revision")
    assert result["status"] == "aborted"
    assert quarantined.exists()
    assert repository.load_state("capture-001")["abort_reason"].startswith("Operator")
    with pytest.raises(CaptureError) as caught:
        repository.resume("capture-001")
    assert caught.value.code == "session_not_active"


def test_no_redistribution_permission_is_a_review_blocker_not_a_trust_claim(
    capture_root: Path,
) -> None:
    repository = initialized_repository(capture_root, redistribution_permitted=False)
    make_ready(repository, capture_root)
    result = repository.finalize("capture-001")
    manifest = json.loads((capture_root / result["manifest_path"]).read_bytes())
    assert manifest["eligible_for_registry_review"] is False
    assert manifest["review_blockers"] == ["redistribution_permission_not_granted"]
    assert manifest["trust_grant"] == "none"


def test_noninteractive_cli_requires_answers_and_attestations(capture_root: Path) -> None:
    with pytest.raises(CaptureError) as missing_answers:
        run_cli(
            [
                "init",
                "--root",
                str(capture_root),
                "--session",
                "cli-session",
                "--recipe",
                "recipe.json",
                "--non-interactive",
            ]
        )
    assert missing_answers.value.code == "answers_required"

    write_json(capture_root / "answers.json", answers())
    assert (
        run_cli(
            [
                "init",
                "--root",
                str(capture_root),
                "--session",
                "cli-session",
                "--recipe",
                "recipe.json",
                "--answers",
                "answers.json",
                "--non-interactive",
                "--json",
            ]
        )
        == 0
    )
    stage_file = capture_root / "source.xml"
    stage_file.write_bytes(xml_bytes())
    with pytest.raises(CaptureError) as missing_attestations:
        run_cli(
            [
                "record",
                "--root",
                str(capture_root),
                "--session",
                "cli-session",
                "--stage",
                "source",
                "--file",
                "source.xml",
                "--non-interactive",
            ]
        )
    assert missing_attestations.value.code == "attestations_required"


def test_interactive_answers_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter(
        [
            "operator-b",
            "5.3.0.1",
            "build-456",
            "Windows 11",
            "yes",
            "Owned by project",
            "session note",
        ]
    )
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(replies))
    value = _interactive_answers()
    assert value["operator_label"] == "operator-b"
    assert value["redistribution_permitted"] is True
    assert value["redistribution_basis"] == "Owned by project"


def test_committed_quick_start_completes_literal_cli_cycle(tmp_path: Path) -> None:
    examples = Path(__file__).resolve().parents[1] / "docs" / "evidence_capture"
    script = Path(__file__).resolve().parents[1] / "scripts" / "capture_diptrace_evidence.py"
    for source in examples.iterdir():
        if source.is_file():
            (tmp_path / source.name).write_bytes(source.read_bytes())
    answers_template = json.loads((tmp_path / "operator-answers.template.json").read_bytes())
    assert answers_template["redistribution_permitted"] is False
    assert answers_template["redistribution_basis"] == ""
    answers_template.update(
        {
            "operator_label": "example-operator",
            "diptrace_version": "5.3.0.1",
            "diptrace_build": "example-build",
            "operating_system": "Windows 11",
            "redistribution_permitted": True,
            "redistribution_basis": "Synthetic test stand-in generated under tmp_path",
        }
    )
    write_json(tmp_path / "operator-answers.json", answers_template)
    repository = CaptureRepository(tmp_path)
    repository.init_session(
        "example-session",
        "pcb-format-question.recipe.template.json",
        answers_template,
    )
    assert repository.status("example-session")["recipe_id"] == "pcb-format-question-template"

    for stage in ("source", "open_save", "reexport"):
        (tmp_path / f"{stage}.xml").write_bytes(
            xml_bytes(marker=f"<!-- synthetic {stage} stand-in -->")
        )
        template_path = tmp_path / {
            "source": "source.attestations.template.json",
            "open_save": "open-save.attestations.template.json",
            "reexport": "reexport.attestations.template.json",
        }[stage]
        stage_attestations = json.loads(template_path.read_bytes())
        assert stage_attestations and not any(stage_attestations.values())
        write_json(
            tmp_path / f"{stage}.attestations.json",
            {key: True for key in stage_attestations},
        )

    def invoke(*arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, str(script), *arguments],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        value = json.loads(completed.stdout)
        assert isinstance(value, dict)
        return value

    common = ("--root", str(tmp_path), "--session", "q1-example-session", "--json")
    initialized = invoke(
        "init",
        *common,
        "--recipe",
        "q1-component-angle.recipe.json",
        "--answers",
        "operator-answers.json",
        "--non-interactive",
    )
    assert initialized["status"] == "active"
    status = invoke("status", *common)
    readiness = status["readiness"]
    assert isinstance(readiness, dict)
    assert readiness["next_stage"] == "source"

    checklist_by_stage = {
        "source": (
            "same_component_definition",
            "control_refdes_and_angle",
            "probe_refdes_and_angle",
            "direct_source_export",
        ),
        "open_save": ("open_save_without_design_edit",),
        "reexport": ("fresh_reexport", "literal_values_not_interpreted"),
    }
    for stage in ("source", "open_save", "reexport"):
        recorded = invoke(
            "record",
            *common,
            "--stage",
            stage,
            "--file",
            f"{stage}.xml",
            "--attestations",
            f"{stage}.attestations.json",
            "--non-interactive",
        )
        assert recorded["stage"] == stage
        for item_id in checklist_by_stage[stage]:
            checked = invoke(
                "check",
                *common,
                "--item",
                item_id,
                "--answer",
                "yes",
                "--note",
                f"Synthetic CLI exercise for {item_id}",
            )
            assert checked["answer"] == "yes"

    finalized = invoke("finalize", *common)
    assert finalized["review_status"] == "pending_independent_review"
    manifest_path = tmp_path / str(finalized["manifest_path"])
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["trust_grant"] == "none"
    assert manifest["candidate_only"] is True
    assert manifest["filesystem_safety"]["mode"] == (
        "descriptor_relative_posix"
        if SECURE_DIR_FD_AVAILABLE
        else "cooperative_static_checks"
    )
