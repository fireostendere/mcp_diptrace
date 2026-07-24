from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from diptrace_mcp.library_adapters import get_library_model
from diptrace_mcp.serializer_reference import (
    load_serializer_reference,
    serializer_allows,
    serializer_behavior,
    serializer_enum,
    serializer_reference_provenance,
    serializer_rule,
)
from diptrace_mcp.xml_document import DipTraceDocument


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "src" / "diptrace_mcp" / "data" / "serializer_reference.json"
SCHEMA_PATH = ROOT / "src" / "diptrace_mcp" / "data" / "serializer_reference.schema.json"


def test_serializer_reference_matches_schema_and_remains_reference_only() -> None:
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(reference)

    loaded = load_serializer_reference()
    assert loaded["reference_kind"] == "serializer_derived_documentation"
    assert loaded["authority"] == "user_supplied_reference"
    assert loaded["trust_effect"] == "none"
    assert loaded["serializer_revision"] == 7276
    assert len(loaded["rules"]) >= 40
    assert len(loaded["behaviors"]) >= 8

    provenance = serializer_reference_provenance()
    assert provenance["trust_effect"] == "none"
    assert all(len(item["sha256"]) == 64 for item in provenance["source_documents"])


def test_serializer_reference_enums_defaults_and_import_semantics() -> None:
    assert serializer_enum("mask.top") == ("Common", "Open", "Tented", "By Paste")
    assert serializer_enum("paste.top") == ("Common", "Solder", "No Solder", "Segments")
    assert serializer_rule("mask.top")["default"] == "Common"
    assert serializer_rule("paste.custom_shrink")["default"] is None
    assert serializer_allows("mainstack.shape", "Fiducial")
    assert not serializer_allows("mainstack.shape", "Triangle")
    assert serializer_behavior("import.nested_lists.replace")["risk"] == "routing_or_wiring_loss"
    assert serializer_behavior("trust.reference_only")["risk"] == "trust_escalation"


def test_fiducial_hole_is_keepout_and_missing_height_uses_width() -> None:
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Library Type="DipTrace-PatternLibrary" Name="Reference" Version="5.3.0.0" Units="mm">
  <PadStyles>
    <PadStyle Name="FID" Type="Surface" Hole="1.2">
      <MainStack Shape="Fiducial" Width="0.8"/>
    </PadStyle>
  </PadStyles>
  <Patterns>
    <Pattern Id="0" RefDes="FID" Mounting="SMD">
      <Name>FIDUCIAL_TEST</Name>
      <DefPad Style="FID"/>
      <Pads><Pad Id="0" Style="FID" X="0" Y="0"><Number>1</Number></Pad></Pads>
    </Pattern>
  </Patterns>
</Library>
'''
    document = DipTraceDocument.from_bytes(Path("fiducial.xml"), xml)
    model = get_library_model(document)

    style = model.pad_styles[0]
    assert style.shape == "Fiducial"
    assert style.width == 0.8
    assert style.height == 0.8
    assert style.hole_width is None
    assert style.hole_height is None
    assert style.fiducial_keepout == 1.2

    geometry = model.patterns[0].pads[0].geometry
    assert geometry is not None
    assert geometry.kind == "circle"
    assert geometry.width == 0.8
    assert geometry.height == 0.8


def test_mask_paste_unset_sentinels_do_not_become_geometry() -> None:
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Library Type="DipTrace-PatternLibrary" Name="Reference" Version="5.3.0.0" Units="mm">
  <PadStyles>
    <PadStyle Name="SMD" Type="Surface">
      <MainStack Shape="Rectangle" Width="1.0" Height="0.5"/>
      <MaskPaste TopMask="Tented" BotPaste="Segments" CustomSwell="-1000" CustomShrink="-1000"
                 Segment_Percent="70" Segment_EdgeGap="0.05" Segment_Gap="0.1" Segment_Side="0.3">
        <BotSegments><Item X1="-0.4" Y1="-0.2" X2="0.4" Y2="0.2"/></BotSegments>
      </MaskPaste>
    </PadStyle>
  </PadStyles>
  <Patterns>
    <Pattern Id="0" RefDes="U" Mounting="SMD">
      <Name>MASK_TEST</Name><DefPad Style="SMD"/>
      <Pads><Pad Id="0" Style="SMD" X="0" Y="0"><Number>1</Number></Pad></Pads>
    </Pattern>
  </Patterns>
</Library>
'''
    document = DipTraceDocument.from_bytes(Path("mask.xml"), xml)
    model = get_library_model(document)
    style = model.pad_styles[0]

    assert style.custom_swell is None
    assert style.custom_shrink is None
    assert style.mask_paste["TopMask"] == "Tented"
    assert style.mask_paste["BotPaste"] == "Segments"
    assert len(style.mask_paste_segments["Bottom"]) == 1

    pad = model.patterns[0].pads[0]
    assert pad.mask_geometry["Top"] == []
    assert len(pad.paste_geometry["Bottom"]) == 1
