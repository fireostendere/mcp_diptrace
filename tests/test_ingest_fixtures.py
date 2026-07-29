from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ingest_fixtures.py"
ACCEPTANCE_ROOT = ROOT / "tests" / "fixtures" / "acceptance"
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_fixtures import (  # noqa: E402
    IngestError,
    build_plan,
    create_synthetic_candidate,
    run_cli,
    synthetic_plan,
    validate_candidate,
)


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _candidate_root(tmp_path: Path) -> tuple[Path, Path, Path]:
    capture_root = tmp_path / "capture"
    destination_root = tmp_path / "destination"
    capture_root.mkdir()
    destination_root.mkdir()
    candidate = create_synthetic_candidate(capture_root)
    return capture_root, candidate, destination_root


def _candidate_with_private_input(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, bytes]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    capture_root, candidate, destination_root = _candidate_root(tmp_path)
    private_dir = capture_root / "private"
    private_dir.mkdir()
    private_input = private_dir / "source-library.eli"
    private_bytes = b"\x00PRIVATE-LEGACY-LIBRARY\xff"
    private_input.write_bytes(private_bytes)

    def add_input(value: dict[str, object]) -> None:
        value["input_artifacts"] = [
            {
                "role": "component_library",
                "name": private_input.name,
                "path": "private/source-library.eli",
                "sha256": hashlib.sha256(private_bytes).hexdigest(),
                "size_bytes": len(private_bytes),
            }
        ]

    _rewrite_manifest(capture_root, candidate, add_input)
    return capture_root, candidate, destination_root, private_input, private_bytes


def _rewrite_manifest(
    capture_root: Path,
    candidate: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    manifest_path = capture_root / candidate
    value = json.loads(manifest_path.read_bytes())
    mutate(value)
    raw = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    manifest_path.write_bytes(raw)
    manifest_sha = hashlib.sha256(raw).hexdigest()
    manifest_path.with_name(manifest_path.name + ".sha256").write_text(
        f"{manifest_sha}  {manifest_path.name}\n",
        encoding="ascii",
    )


def test_synthetic_plan_is_deterministic_and_never_grants_trust() -> None:
    first = synthetic_plan()
    second = synthetic_plan()
    assert first == second
    assert first["mode"] == "synthetic_dry_run"
    assert first["apply_available"] is False
    assert first["apply_unavailable_reason"] == "fixture_apply_not_implemented"
    assert first["candidate"]["authority"] == "operator_supplied_unverified"
    assert first["candidate"]["trust_grant"] == "none"
    assert first["trust"] == {
        "trusted_registry_exists": True,
        "trusted_registry_checked": True,
        "trusted_registry_entry_count": 0,
        "reviewed_ingest_authorization": "none",
        "trust_promoted": False,
        "validation_level_granted": None,
    }


def test_synthetic_cli_does_not_touch_acceptance_tree() -> None:
    before = _tree_hash(ACCEPTANCE_ROOT)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--synthetic", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    plan = json.loads(completed.stdout)
    assert plan["synthetic"] is True
    assert plan["destination"]["conflicts"] == []
    assert "/tmp/" not in completed.stdout
    assert _tree_hash(ACCEPTANCE_ROOT) == before


def test_ci_runs_the_trust_neutral_synthetic_dry_run() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python scripts/ingest_fixtures.py --dry-run --synthetic --json" in workflow


def test_apply_is_typed_refusal_before_any_file_is_created(tmp_path: Path) -> None:
    destination = tmp_path / "must-not-exist"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--apply",
            "--capture-root",
            str(tmp_path / "missing-capture"),
            "--candidate",
            "missing.json",
            "--destination-root",
            str(destination),
            "--fixture-id",
            "would-be-fixture",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 3
    error = json.loads(completed.stderr)
    assert error["error"]["code"] == "fixture_apply_not_implemented"
    assert not destination.exists()


def test_real_dry_run_validates_candidate_and_lists_destinations(tmp_path: Path) -> None:
    capture_root, candidate_path, destination_root = _candidate_root(tmp_path)
    exit_code = run_cli(
        [
            "--dry-run",
            "--capture-root",
            str(capture_root),
            "--candidate",
            str(candidate_path),
            "--destination-root",
            str(destination_root),
            "--fixture-id",
            "review-q1",
            "--json",
        ]
    )
    assert exit_code == 0
    candidate = validate_candidate(capture_root, candidate_path)
    plan = build_plan(
        candidate,
        destination_root=destination_root,
        destination_root_exists=True,
        fixture_id="review-q1",
        synthetic=False,
    )
    assert plan["mode"] == "candidate_dry_run"
    assert plan["ready_for_independent_review"] is True
    assert [item["role"] for item in plan["destination"]["files"]] == [
        "source",
        "open_save",
        "reexport",
        "candidate_manifest",
        "candidate_digest",
    ]
    assert {item["status"] for item in plan["destination"]["files"]} == {"create"}
    assert candidate.input_artifacts == ()
    assert plan["candidate"]["input_artifacts"] == []


def test_private_input_is_revalidated_but_never_planned_for_copy(tmp_path: Path) -> None:
    (
        capture_root,
        candidate_path,
        destination_root,
        private_input,
        private_bytes,
    ) = _candidate_with_private_input(tmp_path)

    candidate = validate_candidate(capture_root, candidate_path)
    plan = build_plan(
        candidate,
        destination_root=destination_root,
        destination_root_exists=True,
        fixture_id="review-private-input",
        synthetic=False,
    )

    assert [(item.role, item.name) for item in candidate.input_artifacts] == [
        ("component_library", "source-library.eli")
    ]
    assert plan["candidate"]["input_artifacts"] == [
        {
            "role": "component_library",
            "name": "source-library.eli",
            "path": "private/source-library.eli",
            "sha256": hashlib.sha256(private_bytes).hexdigest(),
            "size_bytes": len(private_bytes),
        }
    ]
    assert plan["validation"]["input_artifact_hashes_match"] is True
    assert plan["validation"]["input_artifacts_metadata_only"] is True
    assert [item["role"] for item in plan["destination"]["files"]] == [
        "source",
        "open_save",
        "reexport",
        "candidate_manifest",
        "candidate_digest",
    ]
    assert all(
        private_input.name not in item["destination"]
        for item in plan["destination"]["files"]
    )
    assert plan["candidate"]["authority"] == "operator_supplied_unverified"
    assert plan["candidate"]["trust_grant"] == "none"
    assert plan["trust"]["trust_promoted"] is False


def test_private_input_tampering_is_rejected_by_ingest(tmp_path: Path) -> None:
    capture_root, candidate, _destination, private_input, _bytes = (
        _candidate_with_private_input(tmp_path)
    )
    private_input.write_bytes(b"tampered")

    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)

    assert caught.value.code == "candidate_artifact_sha256_mismatch"


def test_private_input_path_symlink_hardlink_and_duplicate_are_rejected(
    tmp_path: Path,
) -> None:
    capture_root, candidate, _destination, private_input, _bytes = (
        _candidate_with_private_input(tmp_path)
    )

    def traverse(value: dict[str, object]) -> None:
        inputs = value["input_artifacts"]
        assert isinstance(inputs, list)
        record = inputs[0]
        assert isinstance(record, dict)
        record["path"] = "../source-library.eli"

    _rewrite_manifest(capture_root, candidate, traverse)
    with pytest.raises(IngestError) as traversal:
        validate_candidate(capture_root, candidate)
    assert traversal.value.code == "unsafe_candidate_path"

    capture_root, candidate, _destination, private_input, _private_bytes = (
        _candidate_with_private_input(tmp_path / "symlink")
    )
    target = private_input.with_name("target.eli")
    private_input.replace(target)
    try:
        private_input.symlink_to(target)
    except OSError:
        pass
    else:
        with pytest.raises(IngestError) as symlinked:
            validate_candidate(capture_root, candidate)
        assert symlinked.value.code == "unsafe_candidate_path"

    capture_root, candidate, _destination, private_input, _bytes = (
        _candidate_with_private_input(tmp_path / "hardlink")
    )
    alias = private_input.with_name("alias.eli")
    try:
        alias.hardlink_to(private_input)
    except OSError:
        pass
    else:
        with pytest.raises(IngestError) as hardlinked:
            validate_candidate(capture_root, candidate)
        assert hardlinked.value.code == "candidate_role_conflict"

    capture_root, candidate, _destination, _private_input, _bytes = (
        _candidate_with_private_input(tmp_path / "duplicate")
    )

    def duplicate(value: dict[str, object]) -> None:
        inputs = value["input_artifacts"]
        assert isinstance(inputs, list)
        inputs.append(dict(inputs[0]))

    _rewrite_manifest(capture_root, candidate, duplicate)
    with pytest.raises(IngestError) as duplicated:
        validate_candidate(capture_root, candidate)
    assert duplicated.value.code == "candidate_role_conflict"


def test_detached_digest_tampering_is_rejected(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)
    (capture_root / candidate).with_name(candidate.name + ".sha256").write_text(
        f"{'0' * 64}  {candidate.name}\n",
        encoding="ascii",
    )
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "candidate_digest_mismatch"


def test_quarantined_artifact_tampering_is_rejected(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)
    manifest = json.loads((capture_root / candidate).read_bytes())
    artifact = capture_root / manifest["stages"]["source"]["quarantine_path"]
    artifact.write_bytes(artifact.read_bytes() + b"<!-- tampered -->")
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "candidate_artifact_sha256_mismatch"


def test_candidate_path_traversal_is_rejected_before_read(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)

    def mutate(value: dict[str, object]) -> None:
        stages = value["stages"]
        assert isinstance(stages, dict)
        source = stages["source"]
        assert isinstance(source, dict)
        source["quarantine_path"] = "../outside.xml"

    _rewrite_manifest(capture_root, candidate, mutate)
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "unsafe_candidate_path"


def test_quarantine_symlink_is_rejected(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are unavailable")
    capture_root, candidate, _destination = _candidate_root(tmp_path)
    manifest = json.loads((capture_root / candidate).read_bytes())
    artifact = capture_root / manifest["stages"]["source"]["quarantine_path"]
    outside = tmp_path / "outside.xml"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    try:
        artifact.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "unsafe_candidate_path"


def test_candidate_trust_boundary_change_is_rejected(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)
    _rewrite_manifest(
        capture_root,
        candidate,
        lambda value: value.__setitem__("trust_grant", "diptrace_roundtrip_verified"),
    )
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "candidate_trust_boundary"


def test_stored_inventory_must_match_fresh_xml_parse(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)

    def mutate(value: dict[str, object]) -> None:
        stages = value["stages"]
        assert isinstance(stages, dict)
        source = stages["source"]
        assert isinstance(source, dict)
        inventory = source["xml_inventory"]
        assert isinstance(inventory, dict)
        inventory["direct_child_counts"] = {"Invented": 1}

    _rewrite_manifest(capture_root, candidate, mutate)
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "candidate_inventory_mismatch"


def test_candidate_roles_may_not_share_a_hard_link(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)
    manifest_path = capture_root / candidate
    manifest = json.loads(manifest_path.read_bytes())
    source_record = manifest["stages"]["source"]
    open_save_record = manifest["stages"]["open_save"]
    source_path = capture_root / source_record["quarantine_path"]
    open_save_path = capture_root / open_save_record["quarantine_path"]
    open_save_path.unlink()
    try:
        os.link(source_path, open_save_path)
    except OSError:
        pytest.skip("hard links are unavailable")

    def mutate(value: dict[str, object]) -> None:
        stages = value["stages"]
        assert isinstance(stages, dict)
        source = stages["source"]
        open_save = stages["open_save"]
        assert isinstance(source, dict)
        assert isinstance(open_save, dict)
        for field in ("sha256", "size_bytes", "xml_inventory"):
            open_save[field] = source[field]

    _rewrite_manifest(capture_root, candidate, mutate)
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "candidate_role_conflict"


def test_destination_conflicts_are_reported_without_writes(tmp_path: Path) -> None:
    capture_root, candidate_path, destination_root = _candidate_root(tmp_path)
    candidate = validate_candidate(capture_root, candidate_path)
    target = destination_root / "review-q1"
    target.mkdir()
    conflicting = target / "source.xml"
    conflicting.write_bytes(b"unrelated")
    before = conflicting.read_bytes()

    plan = build_plan(
        candidate,
        destination_root=destination_root,
        destination_root_exists=True,
        fixture_id="review-q1",
        synthetic=False,
    )
    assert plan["ready_for_independent_review"] is False
    assert plan["destination"]["conflicts"] == [
        {
            "destination": "review-q1/source.xml",
            "reason": "existing_sha256_mismatch",
        }
    ]
    source = next(
        item for item in plan["destination"]["files"] if item["role"] == "source"
    )
    assert source["status"] == "conflict"
    assert conflicting.read_bytes() == before


def test_unsupported_reported_diptrace_version_is_rejected(tmp_path: Path) -> None:
    capture_root, candidate, _destination = _candidate_root(tmp_path)

    def mutate(value: dict[str, object]) -> None:
        claims = value["operator_claims"]
        assert isinstance(claims, dict)
        claims["diptrace_version"] = "4.3.0.3"

    _rewrite_manifest(capture_root, candidate, mutate)
    with pytest.raises(IngestError) as caught:
        validate_candidate(capture_root, candidate)
    assert caught.value.code == "unsupported_diptrace_version"
