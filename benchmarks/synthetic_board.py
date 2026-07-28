from __future__ import annotations

import argparse
import math
from io import StringIO

MIN_COMPONENTS = 500
MAX_COMPONENTS = 3_000


def parse_component_count(value: str) -> int:
    try:
        component_count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("components must be an integer") from exc
    if not MIN_COMPONENTS <= component_count <= MAX_COMPONENTS:
        raise argparse.ArgumentTypeError(
            f"components must be between {MIN_COMPONENTS} and {MAX_COMPONENTS}"
        )
    return component_count


def add_component_count_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--components",
        type=parse_component_count,
        default=MIN_COMPONENTS,
        metavar=f"{MIN_COMPONENTS}..{MAX_COMPONENTS}",
        help=(
            "number of generated components "
            f"(inclusive range {MIN_COMPONENTS}..{MAX_COMPONENTS})"
        ),
    )


def generate_synthetic_pcb(component_count: int = MIN_COMPONENTS) -> bytes:
    """Build a deterministic parser/load-test board with no DipTrace provenance."""

    if not MIN_COMPONENTS <= component_count <= MAX_COMPONENTS:
        raise ValueError(
            f"component_count must be between {MIN_COMPONENTS} and {MAX_COMPONENTS}"
        )
    columns = math.ceil(math.sqrt(component_count))
    rows = math.ceil(component_count / columns)
    pitch_mm = 2
    width_mm = (columns + 1) * pitch_mm
    height_mm = (rows + 1) * pitch_mm
    output = StringIO()
    output.write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- MCP-generated synthetic load input; this is not a DipTrace export. -->\n"
        '<Source Type="DipTrace-PCB" Version="4.3.0.3" Units="mm">\n'
        '  <Library Type="DipTrace-ComponentLibrary" Version="4.3.0.3" Units="mm" />\n'
        '  <Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm" />\n'
        "  <Board>\n"
        '    <BoardOutline Locked="N" Selected="N"><Points>\n'
        '      <Point X="0" Y="0" />\n'
        f'      <Point X="{width_mm}" Y="0" />\n'
        f'      <Point X="{width_mm}" Y="{height_mm}" />\n'
        f'      <Point X="0" Y="{height_mm}" />\n'
        "    </Points></BoardOutline>\n"
        "    <Settings>\n"
        '      <Routing TraceWidth="0.25" TraceClearance="0.2" '
        'ViaSize="0.6" ViaHole="0.3" />\n'
        "    </Settings>\n"
        "    <CopperLayers>\n"
        '      <Lay Id="0" Type="Signal"><Name>Top</Name></Lay>\n'
        '      <Lay Id="1" Type="Signal"><Name>Bottom</Name></Lay>\n'
        "    </CopperLayers>\n"
        "    <ViaStyles>\n"
        '      <ViaStyle Id="0" Diameter="0.6" Hole="0.3">'
        "<Name>Default</Name></ViaStyle>\n"
        "    </ViaStyles>\n"
        "    <NetClasses />\n"
        "    <DRC />\n"
        '    <ConnectivityCheck Traces="Y" Shapes="Y" CopperPours="Y" />\n'
        "    <Components>\n"
    )
    for index in range(component_count):
        x_mm = (index % columns + 1) * pitch_mm
        y_mm = (index // columns + 1) * pitch_mm
        output.write(
            f'      <Component Id="{index}" UpdateId="{100_000 + index}" '
            f'PatternStyle="Synthetic2Pin" X="{x_mm}" Y="{y_mm}" '
            'Side="Top" Locked="N" Selected="N">\n'
            f"        <RefDes>C{index + 1}</RefDes>\n"
            "        <Name>SYNTHETIC_LOAD_COMPONENT</Name>\n"
            "        <Value>1nF</Value>\n"
            "        <Pads>\n"
            '          <Pad Id="0" Number="1" />\n'
            '          <Pad Id="1" Number="2" />\n'
            "        </Pads>\n"
            "      </Component>\n"
        )
    output.write(
        "    </Components>\n"
        "    <Ratlines />\n"
        "    <Nets />\n"
        "    <DifferentialPairs />\n"
        "    <Shapes />\n"
        "  </Board>\n"
        "</Source>\n"
    )
    return output.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic synthetic PCB load input on stdout. "
            "The output has no DipTrace provenance."
        )
    )
    add_component_count_argument(parser)
    args = parser.parse_args()
    print(generate_synthetic_pcb(args.components).decode("utf-8"), end="")


if __name__ == "__main__":
    main()
