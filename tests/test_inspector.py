from pathlib import Path

import pytest

from diptrace_mcp import inspector
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def test_schematic_summary_and_grouped_components() -> None:
    document = load("schematic.xml")
    summary = inspector.summarize(document)
    listing = inspector.components(document)

    assert summary["kind"] == "schematic"
    assert summary["component_count"] == 2
    assert summary["part_count"] == 3
    assert summary["unconnected_pin_count"] == 1
    assert summary["intentional_no_connect_count"] == 1
    assert listing["total"] == 2
    assert next(item for item in listing["items"] if item["refdes"] == "U1")["part_count"] == 2


def test_pcb_summary_components_nets_and_rules() -> None:
    document = load("pcb.xml")
    summary = inspector.summarize(document)
    listing = inspector.nets(document)
    rules = inspector.design_rules(document)

    assert summary["kind"] == "pcb"
    assert summary["component_count"] == 2
    assert summary["copper_layer_count"] == 2
    assert summary["routed_trace_count"] == 1
    assert listing["items"][0]["endpoint_count"] == 2
    assert {endpoint["refdes"] for endpoint in listing["items"][0]["endpoints"]} == {
        "R1",
        "U1",
    }
    assert rules["drc"]["attributes"]["CheckClearance"] == "Y"


def test_component_details_include_connected_nets() -> None:
    details = inspector.component(load("schematic.xml"), "R1")

    assert details["component"]["value"] == "10k"
    assert {net["name"] for net in details["connected_nets"]} == {"VCC", "SIGNAL"}


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

    baseline_settings = inspector.get_board_project_settings(baseline)
    changed_settings = inspector.get_board_project_settings(changed)

    assert baseline_settings.courtyard_line_width_mm == pytest.approx(0.05)
    assert changed_settings.courtyard_line_width_mm == pytest.approx(0.10)
    assert baseline_settings.solder_mask_swell_mm == pytest.approx(0.05)
    assert changed_settings.solder_mask_swell_mm == pytest.approx(0.05)
    assert baseline_settings.paste_mask_shrink_mm == pytest.approx(0.05)
    assert changed_settings.paste_mask_shrink_mm == pytest.approx(0.05)

    baseline_summary = inspector.summarize(baseline)["project_settings"]
    changed_summary = inspector.summarize(changed)["project_settings"]
    assert baseline_summary["courtyard_line_width_mm"] == pytest.approx(0.05)
    assert changed_summary["courtyard_line_width_mm"] == pytest.approx(0.10)
    assert baseline_summary != changed_summary

    changed_rules = inspector.design_rules(changed)["project_settings"]
    assert changed_rules == changed_summary
    changed_board = inspector.get_board_model(changed)
    assert changed_board["rules"]["project_settings"] == changed_summary

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

    settings = inspector.get_board_project_settings(document)

    assert settings.courtyard_line_width_mm is None
    assert settings.solder_mask_swell_mm is None
    assert settings.paste_mask_shrink_mm is None
    assert inspector.summarize(document)["project_settings"] == {
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

    settings = inspector.get_board_project_settings(document)

    assert settings.courtyard_line_width_mm == pytest.approx(1.27)
    assert settings.solder_mask_swell_mm == pytest.approx(0.254)
    assert settings.paste_mask_shrink_mm == pytest.approx(0.508)
