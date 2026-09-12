from __future__ import annotations

from pathlib import Path

import pytest

from diptrace_mcp.adapters import _schematic_library_pin_types
from diptrace_mcp.xml_document import DipTraceDocument


def _document(
    *,
    part_type: str = "Net Port",
    style: str | None = "Port_Out",
    pins: str = '<Pin NetId="0"/>',
    extra_component: str = "",
) -> DipTraceDocument:
    placed_style = f' ComponentStyle="{style}"' if style is not None else ""
    return DipTraceDocument.from_bytes(
        Path("native-net-port.dch"),
        f'''<Source Type="DipTrace-Schematic">
  <Library Type="DipTrace-ComponentLibrary"><Components>
    <Component ComponentStyle="Port_Out"><Part Id="0" RefDes="PS" PartType="{part_type}"><Name>Port_Out</Name><Pins><Pin Id="10" ElectricType="Passive"/></Pins></Part></Component>{extra_component}
  </Components></Library>
  <Schematic><Components>
    <Part Id="0"{placed_style} ComponentPart="0"><RefDes>NETPORT</RefDes><Name>REQ_C1</Name><Pins>{pins}</Pins></Part>
  </Components></Schematic>
</Source>'''.encode(),
    )


@pytest.mark.parametrize("part_type", ["Net Port", "2"])
def test_explicit_native_net_port_inherits_type_by_position(part_type: str) -> None:
    document = _document(part_type=part_type)

    assert _schematic_library_pin_types(document) == {("0", 0): "Passive"}
    assert b'Pin Id="10"' in document.raw_bytes
    assert b'<Pin NetId="0"/>' in document.raw_bytes


def test_normal_or_ambiguous_style_does_not_relax_identity() -> None:
    assert _schematic_library_pin_types(_document(part_type="Normal")) == {}
    assert _schematic_library_pin_types(_document(style=None)) == {}
    assert _schematic_library_pin_types(
        _document(extra_component='<Component ComponentStyle="Port_Out"><Part Id="0" RefDes="PS" PartType="Net Port"><Name>Port_Out</Name><Pins><Pin Id="10" ElectricType="Passive"/></Pins></Part></Component>')
    ) == {}


def test_native_net_port_rejects_pin_count_mismatch() -> None:
    assert _schematic_library_pin_types(_document(pins='<Pin NetId="0"/><Pin NetId="1"/>')) == {}


def test_power_port_uses_library_type_without_renaming_net() -> None:
    original = _document().raw_bytes
    raw = original.replace(b'ElectricType="Passive"', b'ElectricType="Power"').replace(
        b"<Name>Port_Out</Name>", b"<Name>VCC</Name>"
    ).replace(b"<Name>REQ_C1</Name>", b"<Name>+3V3</Name>")
    document = DipTraceDocument.from_bytes(Path("power-port.dch"), raw)
    assert _schematic_library_pin_types(document) == {("0", 0): "Power"}
    assert document.raw_bytes == raw


def test_named_port_relaxation_is_single_pin_only() -> None:
    raw = _document(pins='<Pin NetId="0"/><Pin NetId="1"/>').raw_bytes.replace(
        b'<Pin Id="10" ElectricType="Passive"/>',
        b'<Pin Id="10" ElectricType="Passive"/><Pin Id="11" ElectricType="Passive"/>',
    )
    document = DipTraceDocument.from_bytes(Path("multi-pin-port.dch"), raw)
    assert _schematic_library_pin_types(document) == {}
