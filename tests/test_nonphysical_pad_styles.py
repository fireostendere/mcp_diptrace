"""Synthetic native-cache regression; not a valid physical footprint."""

from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.library_adapters import get_embedded_pattern_model, validate_library
from diptrace_mcp.xml_document import DipTraceDocument


@pytest.mark.parametrize("used", [False, True])
def test_nonphysical_cached_style_does_not_block_logical_inspection(used):
    override = "" if used else 'Style="Good"'
    raw = f"""<Source Type="DipTrace-PCB" Version="5.3.0.3" Units="mm">
      <Library Type="DipTrace-PatternLibrary" Units="mm">
        <PadStyles>
          <PadStyle Name="Legacy" Type="Through" Hole="0.15">
            <MainStack Shape="Ellipse" Width="-0.25" Height="-0.25"/>
          </PadStyle>
          <PadStyle Name="Good" Type="Surface">
            <MainStack Shape="Ellipse" Width="1" Height="1"/>
          </PadStyle>
        </PadStyles>
        <Patterns><Pattern PatternStyle="P0"><Name>Synthetic</Name>
          <DefPad Style="Legacy"/>
          <Pads><Pad Id="1" {override} X="0" Y="0"/></Pads>
        </Pattern></Patterns>
      </Library>
      <Board><Components><Component Id="1" PatternStyle="P0" X="1" Y="1">
        <RefDes>U1</RefDes><Pads><Pad Id="1" NetId="1"/></Pads>
      </Component></Components><Nets><Net Id="1"><Name>Signal</Name></Net></Nets></Board>
    </Source>""".encode()
    document = DipTraceDocument.from_bytes(Path("synthetic.dipxml"), raw)
    library = get_embedded_pattern_model(document)
    assert library is not None
    assert library.pad_styles[0].width == -0.25
    assert any("Legacy" in warning and "nonphysical" in warning for warning in library.warnings)
    pad = library.patterns[0].pads[0]
    assert (pad.geometry is None) is used
    findings = validate_library(library)
    assert any(f.code == "invalid_pad_geometry" for f in findings) is used
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    assert snapshot.board.components[0].refdes == "U1"
    assert any("Legacy" in warning for warning in snapshot.board.warnings)
    assert document.raw_bytes == raw
