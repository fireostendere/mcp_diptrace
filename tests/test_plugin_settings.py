import xml.etree.ElementTree as ET
from pathlib import Path


def test_plugin_settings_match_official_structure() -> None:
    root = Path(__file__).parents[1] / "plugin" / "settings"
    pcb = ET.parse(root / "pcb.settings.xml").getroot()
    schematic = ET.parse(root / "schematic.settings.xml").getroot()

    assert pcb.tag == "Source"
    assert pcb.get("Type") == "DipTrace_Pcb_Plugin"
    assert pcb.findtext("./Settings/ExpMode") == "All"
    assert pcb.findtext("./Settings/ImpMode") == "All"
    assert schematic.get("Type") == "DipTrace_Schematic_Plugin"
    assert schematic.findtext("./Settings/Patterns") == "Yes"
