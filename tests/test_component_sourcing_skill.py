from __future__ import annotations

import importlib.util
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


def _module():
    path = Path(".agents/skills/easyeda-lcsc-sourcing/fetch_component.py")
    spec = importlib.util.spec_from_file_location("fetch_component", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejects_silent_mpn_substitution() -> None:
    with pytest.raises(SystemExit, match="MPN mismatch"):
        _module().validate_requested_part(
            "TSW-108-07-G-D",
            {"title": "TSW-108-07-G-S-LL"},
        )


def test_lcsc_symbol_pin_coordinates_are_scaled_once() -> None:
    build_elixml = runpy.run_path("scripts/lcsc_library.py")["build_elixml"]

    root = ET.fromstring(
        build_elixml(
            mpn="ESP32-S3-MINI-1U-N8",
            manufacturer="Espressif Systems",
            datasheet_url="vendor/C2980299.pdf",
            lcsc_code="C2980299",
        )
    )
    pin = root.find("./Components/Component/Part/Pins/Pin")
    assert pin is not None
    assert float(pin.get("X", "0")) == pytest.approx(-8.89)
    assert float(pin.get("Length", "0")) == pytest.approx(2.54)
    assert pin.get("Orientation") == "0"
