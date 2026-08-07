"""Prepare and validate the irreducibly manual acceptance matrix.

Everything represented here requires observation of an external GUI/application,
a real DipTrace-generated artifact, a clean Windows state, or a human/legal
judgement.  Automatable repository checks must not be added to this matrix.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import DocumentError


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ManualGate(_StrictModel):
    gate_id: str = Field(pattern=r"^[a-z0-9_]+$")
    category: Literal["windows", "diptrace", "client", "distribution", "legal", "optional_external"]
    title: str = Field(min_length=1, max_length=256)
    action: str = Field(min_length=1, max_length=4000)
    pass_criteria: list[str] = Field(min_length=1, max_length=32)
    required_evidence: list[str] = Field(min_length=1, max_length=32)
    blocking_for_stronger_claims: bool = True


class ManualGateResult(_StrictModel):
    gate_id: str = Field(pattern=r"^[a-z0-9_]+$")
    status: Literal["pending", "pass", "fail", "not_applicable"] = "pending"
    observed_version: str = Field(default="", max_length=256)
    notes: str = Field(default="", max_length=8000)
    evidence_files: list[str] = Field(default_factory=list, max_length=64)


class ManualAcceptanceRecord(_StrictModel):
    schema_version: Literal["diptrace-mcp-manual-acceptance-v1"] = (
        "diptrace-mcp-manual-acceptance-v1"
    )
    release_version: str = Field(min_length=1, max_length=64)
    release_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    results: list[ManualGateResult]

    @model_validator(mode="after")
    def _unique_gate_ids(self) -> ManualAcceptanceRecord:
        ids = [item.gate_id for item in self.results]
        if len(set(ids)) != len(ids):
            raise ValueError("manual acceptance gate ids must be unique")
        return self


MANUAL_GATES: tuple[ManualGate, ...] = (
    ManualGate(
        gate_id="windows_clean_install_repair_uninstall",
        category="windows",
        title="Clean Windows 11 install / repair / uninstall",
        action=(
            "On a clean Windows 11 machine or clean VM, install the exact release installer, "
            "run repair, then uninstall. Observe Programs & Features, installed files, PATH/client "
            "state, and leftovers."
        ),
        pass_criteria=[
            "install completes without unexpected warning/error",
            "repair preserves a working installation",
            "uninstall removes owned binaries while preserving user-owned state",
        ],
        required_evidence=["Windows build", "installer SHA-256", "install/repair/uninstall log or screenshots"],
    ),
    ManualGate(
        gate_id="diptrace_current_pcb_roundtrip",
        category="diptrace",
        title="Current DipTrace PCB open/save/re-export",
        action="Open representative generated/modified PCB XML in the current DipTrace 5 build, save it, re-export XML, and inspect the GUI before comparison.",
        pass_criteria=["opens without repair/error", "expected board/connectivity visible", "save and re-export succeed", "semantic comparison has no unexplained change"],
        required_evidence=["exact DipTrace version", "source file SHA-256", "saved/re-export SHA-256", "GUI observation"],
    ),
    ManualGate(
        gate_id="diptrace_current_schematic_roundtrip",
        category="diptrace",
        title="Current DipTrace Schematic open/save/re-export",
        action="Open representative authored/modified schematic XML, inspect connectivity and authored wires, save and re-export.",
        pass_criteria=["opens without repair/error", "authored wires/connectivity are correct", "save and re-export succeed", "semantic comparison has no unexplained change"],
        required_evidence=["exact DipTrace version", "source/saved/re-export hashes", "GUI observation"],
    ),
    ManualGate(
        gate_id="diptrace_component_library_writer_roundtrip",
        category="diptrace",
        title="Component Library writer open/save/re-export",
        action="Use the repository writer fixture to create/update components, pins, fields and explicit pin-to-pad mapping, then open/save/re-export in DipTrace Component Editor.",
        pass_criteria=["library opens without repair/error", "parts/pins/fields are correct", "pattern attachment and pin-pad mapping are correct", "second writer pass is idempotent after re-export"],
        required_evidence=["before/after/re-export hashes", "exact DipTrace version", "GUI observation"],
    ),
    ManualGate(
        gate_id="diptrace_pattern_library_writer_roundtrip",
        category="diptrace",
        title="Pattern Library writer open/save/re-export",
        action="Use the repository writer fixture to create/update a pattern, pads and graphics, then open/save/re-export in DipTrace Pattern Editor.",
        pass_criteria=["library opens without repair/error", "pad positions/numbers/styles and graphics are correct", "unknown data is not lost unexpectedly", "second writer pass is idempotent after re-export"],
        required_evidence=["before/after/re-export hashes", "exact DipTrace version", "GUI observation"],
    ),
    ManualGate(
        gate_id="diptrace_ratline_and_wire_roundtrip",
        category="diptrace",
        title="Authored-wire and generated-ratline roundtrip",
        action="Open generated schematic wires and PCB ratlines in DipTrace, visually inspect them, save and re-export both documents.",
        pass_criteria=["wire endpoints/connectivity are correct", "ratlines connect expected pads/nets", "save/re-export preserves semantics"],
        required_evidence=["exact DipTrace version", "GUI observation", "source/saved/re-export hashes"],
    ),
    ManualGate(
        gate_id="diptrace_mask_paste_courtyard_common_semantics",
        category="diptrace",
        title="Mask/paste/courtyard/Common one-setting exports",
        action="In current DipTrace, change one mask, paste, courtyard or Common setting at a time and export XML for each controlled pair.",
        pass_criteria=["each GUI change maps to a stable understood XML delta", "parser interpretation matches the GUI state"],
        required_evidence=["exact DipTrace version", "controlled before/after XML pairs", "setting names and observed GUI values"],
    ),
    ManualGate(
        gate_id="diptrace_q1_component_angle",
        category="diptrace",
        title="Q1 Component Angle GUI/re-export",
        action="Run the existing Q1 Component Angle evidence procedure in real DipTrace and record the GUI orientation plus re-exported XML.",
        pass_criteria=["GUI angle matches expected interpretation", "re-export delta matches recorded semantics"],
        required_evidence=["Q1 result JSON", "exact DipTrace version", "GUI observation", "re-export hash"],
    ),
    ManualGate(
        gate_id="codex_real_client_restart",
        category="client",
        title="Real Codex configuration/restart/get_capabilities",
        action="Configure the exact release in a real Codex client, restart the client, invoke the server and call get_capabilities.",
        pass_criteria=["server survives restart", "stdio connection succeeds", "get_capabilities returns expected release/version"],
        required_evidence=["Codex version", "sanitized client config", "get_capabilities output"],
    ),
    ManualGate(
        gate_id="claude_desktop_real_client_restart",
        category="client",
        title="Real Claude Desktop configuration/restart/get_capabilities",
        action="Configure the exact release in Claude Desktop, restart it, invoke the server and call get_capabilities.",
        pass_criteria=["server survives restart", "stdio connection succeeds", "get_capabilities returns expected release/version"],
        required_evidence=["Claude Desktop version", "sanitized client config", "get_capabilities output"],
    ),
    ManualGate(
        gate_id="elevated_plugin_install_profile_preservation",
        category="windows",
        title="Elevated plug-in install with profile preservation",
        action="Install the bridge plug-in into an elevated Program Files target while client/user configuration remains in the original non-elevated profile.",
        pass_criteria=["plug-in lands in intended elevated target", "original user profile/config remains owned and usable by the user", "uninstall does not delete unrelated profile data"],
        required_evidence=["target paths", "before/after profile file inventory or hashes", "install log"],
    ),
    ManualGate(
        gate_id="custom_state_preservation",
        category="windows",
        title="Pre-existing custom-state preservation",
        action="Seed non-default state/config before install/repair/uninstall and verify byte-identical or intentionally migrated preservation afterward.",
        pass_criteria=["pre-existing user state is not silently deleted or overwritten", "any migration is explicit and reversible"],
        required_evidence=["before/after file hashes", "state paths", "observed migration notes if any"],
    ),
    ManualGate(
        gate_id="public_asset_redownload_smoke",
        category="distribution",
        title="Public asset redownload/install smoke after a future release",
        action="Only when publishing a new release: redownload every public asset, verify frozen hashes, and repeat install/stdio/uninstall smoke from public bytes.",
        pass_criteria=["public hashes equal frozen release inventory", "public installer/package smoke succeeds"],
        required_evidence=["public URLs", "downloaded hashes", "smoke log"],
        blocking_for_stronger_claims=False,
    ),
    ManualGate(
        gate_id="external_legal_review_if_required",
        category="legal",
        title="External legal/Novarm review if required",
        action="Obtain qualified external review or explicit Novarm/DipTrace permission for any claim/distribution activity that project counsel determines needs it.",
        pass_criteria=["review/permission scope is documented", "repository claims remain within the reviewed scope"],
        required_evidence=["human decision/reference; do not commit confidential legal material"],
        blocking_for_stronger_claims=False,
    ),
    ManualGate(
        gate_id="openems_real_external_validation",
        category="optional_external",
        title="Optional real openEMS integration run",
        action="Run the typed openEMS adapter against a real installed solver and compare the bounded result with an independently inspected run.",
        pass_criteria=["process invocation succeeds", "result artifacts are parseable", "reported solver identity/version is recorded"],
        required_evidence=["openEMS version", "command/result metadata", "result hashes"],
        blocking_for_stronger_claims=False,
    ),
)


def prepare_manual_acceptance_record(version: str, commit: str) -> ManualAcceptanceRecord:
    return ManualAcceptanceRecord(
        release_version=version,
        release_commit=commit,
        results=[ManualGateResult(gate_id=gate.gate_id) for gate in MANUAL_GATES],
    )


def write_manual_acceptance_pack(output_dir: Path, *, version: str, commit: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    record = prepare_manual_acceptance_record(version, commit)
    (output_dir / "manual_acceptance.json").write_text(
        record.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# DipTrace MCP manual-only acceptance",
        "",
        "This checklist intentionally contains only work that requires a real external system, GUI observation, clean-machine state, or human/legal judgement.",
        "",
    ]
    for gate in MANUAL_GATES:
        qualifier = "blocking" if gate.blocking_for_stronger_claims else "optional/claim-specific"
        lines.extend(
            [
                f"## [ ] {gate.gate_id} — {gate.title}",
                "",
                f"**Class:** {gate.category}; {qualifier}.",
                "",
                gate.action,
                "",
                "Pass criteria:",
                *[f"- {item}" for item in gate.pass_criteria],
                "",
                "Evidence:",
                *[f"- {item}" for item in gate.required_evidence],
                "",
            ]
        )
    (output_dir / "MANUAL_ACCEPTANCE.md").write_text("\n".join(lines), encoding="utf-8")


def validate_manual_acceptance_pack(output_dir: Path) -> dict[str, object]:
    path = output_dir / "manual_acceptance.json"
    try:
        record = ManualAcceptanceRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DocumentError(f"invalid manual acceptance record: {exc}") from exc
    expected_ids = {gate.gate_id for gate in MANUAL_GATES}
    actual_ids = {item.gate_id for item in record.results}
    missing = sorted(expected_ids - actual_ids)
    unknown = sorted(actual_ids - expected_ids)
    evidence_errors: list[str] = []
    gate_by_id = {gate.gate_id: gate for gate in MANUAL_GATES}
    for result in record.results:
        if result.status != "pass":
            continue
        gate = gate_by_id.get(result.gate_id)
        if gate is None:
            continue
        if not result.observed_version and gate.category in {"windows", "diptrace", "client", "optional_external"}:
            evidence_errors.append(f"{result.gate_id}: pass requires observed_version")
        if not result.evidence_files:
            evidence_errors.append(f"{result.gate_id}: pass requires evidence_files")
        for relative in result.evidence_files:
            evidence = (output_dir / relative).resolve()
            try:
                evidence.relative_to(output_dir.resolve())
            except ValueError:
                evidence_errors.append(f"{result.gate_id}: evidence path escapes acceptance directory")
                continue
            if not evidence.is_file():
                evidence_errors.append(f"{result.gate_id}: missing evidence file {relative}")
    blocking = {
        gate.gate_id
        for gate in MANUAL_GATES
        if gate.blocking_for_stronger_claims
    }
    status_by_id = {item.gate_id: item.status for item in record.results}
    pending_blocking = sorted(
        gate_id for gate_id in blocking if status_by_id.get(gate_id) != "pass"
    )
    return {
        "ok": not missing and not unknown and not evidence_errors and not pending_blocking,
        "missing_gate_ids": missing,
        "unknown_gate_ids": unknown,
        "evidence_errors": evidence_errors,
        "pending_blocking_gate_ids": pending_blocking,
        "record_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
