from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.inspector import (
    design_rules,
    get_board_model,
    get_board_project_settings,
    summarize,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _pcb_with_project_settings(
    *,
    courtyard: str,
    solder_mask_swell: str = "0.05",
    paste_mask_shrink: str = "0.05",
    units: str = "mm",
) -> bytes:
    raw = (FIXTURES / "pcb.xml").read_bytes()
    if units != "mm":
        raw = raw.replace(b'Units="mm"', f'Units="{units}"'.encode(), 1)
    marker = b"    <Settings>\n"
    addition = (
        "      <LineWidth><Courtyard>"
        f"{courtyard}"
        "</Courtyard></LineWidth>\n"
        f"      <SolderMaskSwell>{solder_mask_swell}</SolderMaskSwell>\n"
        f"      <PasteMaskShrink>{paste_mask_shrink}</PasteMaskShrink>\n"
    ).encode()
    assert marker in raw
    return raw.replace(marker, marker + addition, 1)


def test_courtyard_acceptance_values_are_mcp_visible_and_siblings_preserved() -> None:
    baseline_bytes = _pcb_with_project_settings(courtyard="0.05")
    changed_bytes = _pcb_with_project_settings(courtyard="0.10")
    baseline = DipTraceDocument.from_bytes(Path("courtyard-before.dipxml"), baseline_bytes)
    changed = DipTraceDocument.from_bytes(Path("courtyard-after.dipxml"), changed_bytes)

    baseline_settings = get_board_project_settings(baseline)
    changed_settings = get_board_project_settings(changed)

    assert baseline_settings.courtyard_line_width_mm == pytest.approx(0.05)
    assert changed_settings.courtyard_line_width_mm == pytest.approx(0.10)
    assert baseline_settings.solder_mask_swell_mm == pytest.approx(0.05)
    assert changed_settings.solder_mask_swell_mm == pytest.approx(0.05)
    assert baseline_settings.paste_mask_shrink_mm == pytest.approx(0.05)
    assert changed_settings.paste_mask_shrink_mm == pytest.approx(0.05)

    baseline_summary = summarize(baseline)["project_settings"]
    changed_summary = summarize(changed)["project_settings"]
    assert baseline_summary["courtyard_line_width_mm"] == pytest.approx(0.05)
    assert changed_summary["courtyard_line_width_mm"] == pytest.approx(0.10)
    assert baseline_summary != changed_summary

    changed_rules = design_rules(changed)["project_settings"]
    assert changed_rules == changed_summary
    changed_board = get_board_model(changed)
    assert changed_board["rules"]["project_settings"] == changed_summary

    # Parsing is read-only: sibling and unknown source bytes remain untouched.
    assert baseline.raw_bytes == baseline_bytes
    assert changed.raw_bytes == changed_bytes
    future_extension = (
        b'<FutureExtension Vendor="fixture"><Data Preserve="Y" /></FutureExtension>'
    )
    assert future_extension in changed.raw_bytes


def test_project_setting_omission_is_not_replaced_with_inferred_defaults() -> None:
    document = DipTraceDocument.from_bytes(
        Path("settings-omitted.dipxml"),
        (FIXTURES / "pcb.xml").read_bytes(),
    )

    settings = get_board_project_settings(document)

    assert settings.courtyard_line_width_mm is None
    assert settings.solder_mask_swell_mm is None
    assert settings.paste_mask_shrink_mm is None
    assert summarize(document)["project_settings"] == {
        "courtyard_line_width_mm": None,
        "solder_mask_swell_mm": None,
        "paste_mask_shrink_mm": None,
    }


def test_project_setting_lengths_are_normalized_to_millimetres() -> None:
    document = DipTraceDocument.from_bytes(
        Path("inch-settings.dipxml"),
        _pcb_with_project_settings(
            courtyard="0.05",
            solder_mask_swell="0.01",
            paste_mask_shrink="0.02",
            units="inch",
        ),
    )

    settings = get_board_project_settings(document)

    assert settings.courtyard_line_width_mm == pytest.approx(1.27)
    assert settings.solder_mask_swell_mm == pytest.approx(0.254)
    assert settings.paste_mask_shrink_mm == pytest.approx(0.508)
