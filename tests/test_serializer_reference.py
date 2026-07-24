# ruff: noqa: E501
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest

from diptrace_mcp.library_adapters import get_library_model, validate_library
from diptrace_mcp.serializer_reference import (
    load_serializer_reference,
    serializer_accepts,
    serializer_behavior,
    serializer_enum,
    serializer_rule,
)
from diptrace_mcp.xml_document import DipTraceDocument


def _doc(xml: str, name: str = "fixture.xml") -> DipTraceDocument:
    return DipTraceDocument.from_bytes(Path(name), xml.encode("utf-8"))


def test_serializer_reference_validates_against_bundled_schema() -> None:
    root = files("diptrace_mcp").joinpath("data")
    reference = json.loads(root.joinpath("serializer_reference.json").read_text(encoding="utf-8"))
    schema = json.loads(
        root.joinpath("serializer_reference.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(schema).validate(reference)
    assert len(reference["rules"]) >= 60
    assert len(reference["cross_cutting_behaviors"]) >= 10
    assert len(reference["sources"]) == 13


def test_serializer_reference_is_reference_only_and_fingerprinted() -> None:
    reference = load_serializer_reference()
    assert reference["serializer_revision_claim"] == "7276"
    assert reference["serializer_revision_authenticated"] is False
    assert reference["trust"] == {
        "classification": "user_supplied_reference",
        "trust_effect": "none",
        "may_constrain_implementation": True,
        "may_grant_roundtrip_trust": False,
        "requires_independent_diptrace_5_3_fixtures_for_writers": True,
    }
    hashes = {item["name"]: item["sha256"] for item in reference["sources"]}
    assert hashes["DipTrace_PattEdit_XML_Specification.md"] == (
        "b000a248bdbf7a2f17d24a12b9453928c8a4c1a2b96388800b085aa52838bdf3"
    )
    assert hashes["DipTrace_CompEdit_XML_Specification.md"] == (
        "cf76b6698cab8fa5300e48003a0516e4a53d0e2b58259d40439c600f8ac6fc48"
    )
    assert hashes["60_common_mistakes.md"] == (
        "d1b38e4477ac9dd70251c79c7221315debb952a060d34172b9731ff92fdcf981"
    )


def test_reference_lookup_helpers_cover_enums_and_cross_cutting_behavior() -> None:
    assert serializer_enum("pattern.mainstack.shape") == (
        "Ellipse",
        "Obround",
        "Rectangle",
        "Polygon",
        "D-shape",
        "Fiducial",
    )
    assert serializer_accepts("pattern.mask.mode", "By Paste") is True
    assert serializer_accepts("pattern.mask.mode", "No Solder") is False
    assert serializer_rule("component.pin.pad_id")["reader_notes"].startswith("Accept legacy")
    assert "replacement" in serializer_behavior("shared.nested-list.replace")["title"].lower()
    with pytest.raises(KeyError):
        serializer_rule("does.not.exist")


def test_fiducial_omitted_height_hole_and_maskpaste_sentinels_are_normalized() -> None:
    document = _doc(
        """<?xml version="1.0" encoding="UTF-8"?>
<Library Type="DipTrace-PatternLibrary" Name="Ref" Version="5.3.0.0" Units="mm">
  <PadStyles>
    <PadStyle Name="FID" Type="Surface" Hole="1.2">
      <MainStack Shape="Fiducial" Width="0.8"/>
      <MaskPaste TopMask="Open" TopPaste="Solder" CustomSwell="-1000" CustomShrink="-1000"/>
    </PadStyle>
  </PadStyles>
  <Patterns>
    <Pattern Id="0" RefDes="FD" Width="1" Height="1" Orientation="0" Type="Free">
      <Name>FIDUCIAL</Name><Pads><Pad Id="0" Style="FID" X="0" Y="0" Angle="0" Locked="N" Side="Top"><Number>1</Number></Pad></Pads>
    </Pattern>
  </Patterns>
</Library>"""
    )
    model = get_library_model(document)
    style = model.pad_styles[0]
    pad = model.patterns[0].pads[0]
    assert style.height == pytest.approx(0.8)
    assert style.hole_width is None
    assert style.hole_height is None
    assert style.custom_swell is None
    assert style.custom_shrink is None
    assert style.mask_paste["TopMask"] == "Open"
    assert style.mask_paste["TopPaste"] == "Solder"
    assert pad.geometry is not None
    assert pad.geometry.kind == "circle"
    assert pad.geometry.width == pytest.approx(0.8)
    assert pad.geometry.height == pytest.approx(0.8)
    assert "invalid_annular_ring" not in {item.code for item in validate_library(model)}


def test_d_shape_keeps_conservative_geometry_instead_of_disappearing() -> None:
    document = _doc(
        """<Library Type="DipTrace-PatternLibrary" Units="mm">
<PadStyles><PadStyle Name="D" Type="Surface"><MainStack Shape="D-shape" Width="1.2" Height="0.8"/></PadStyle></PadStyles>
<Patterns><Pattern Id="0" Mounting="SMD"><Name>D</Name><Pads><Pad Id="0" Style="D" X="0" Y="0" Angle="0" Side="Top"><Number>1</Number></Pad></Pads></Pattern></Patterns>
</Library>"""
    )
    pad = get_library_model(document).patterns[0].pads[0]
    assert pad.geometry is not None
    assert pad.geometry.kind == "rectangle"
    assert pad.geometry.approximation == "D-shape is conservatively represented as a rectangle"


def test_model3d_filename_container_and_missing_mounting_are_not_misparsed() -> None:
    document = _doc(
        """<Library Type="DipTrace-PatternLibrary" Units="mm">
<PadStyles/><Patterns><Pattern Id="0"><Name>M</Name><Model3D Units="mm"><Filename><Path>C:\\models\\x.step</Path><Var>%models%\\x.step</Var></Filename><Rotate X="90" Y="0" Z="0"/><Offset X="0" Y="0" Z="0"/><Zoom X="1" Y="1" Z="1"/></Model3D></Pattern></Patterns>
</Library>"""
    )
    pattern = get_library_model(document).patterns[0]
    assert pattern.mounting == ""
    assert pattern.model_3d is not None
    assert pattern.model_3d["filename"] == "C:\\models\\x.step"
    assert pattern.model_3d["filename_path"] == "C:\\models\\x.step"
    assert pattern.model_3d["filename_var"] == "%models%\\x.step"
    assert pattern.model_3d["rotate"]["X"] == "90"


def test_component_editor_legacy_pattern_and_pad_aliases_are_accepted() -> None:
    document = _doc(
        """<Library Type="DipTrace-ComponentLibrary" Units="mm">
<Components><Component Id="0"><Part Id="0" RefDes="U"><Name>LEGACY</Name><Pattern PatternType="LEGACY_PAT"/><Pins><Pin Id="0" X="0" Y="0" Orientation="90" PadIndex="7"><Name>A</Name><PadNumber>7</PadNumber></Pin></Pins></Part></Component></Components>
</Library>"""
    )
    component = get_library_model(document).components[0]
    assert component.pattern_style == "LEGACY_PAT"
    assert component.pins[0].pad_id == "7"
    assert component.pins[0].orientation_deg == 90
