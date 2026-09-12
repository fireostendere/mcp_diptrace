#!/usr/bin/env python3
"""Build or check the clean DUT Controller SYSTEM_OVERVIEW sheet."""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.config import Settings
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import XmlEdit

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "dut-controller-reva.dchxml"
SEED = ROOT / "i2c-level-shifter-module.dchxml"
STATE = ROOT / ".local" / "state"
SHEET = "SYSTEM_OVERVIEW"
BLOCKS = {
    "ESP32_CONTROL": (-105.0, 10.0, -45.0, 40.0),
    "USB_DUT": (-15.0, 10.0, 30.0, 40.0),
    "POWER": (-108.0, -55.0, -78.0, -25.0),
    "UART": (-73.0, -55.0, -43.0, -25.0),
    "SWITCHES": (-38.0, -55.0, -3.0, -25.0),
    "AUX_ADC": (7.0, -55.0, 42.0, -25.0),
    "CURRENT_SENSE": (52.0, -55.0, 95.0, -25.0),
}
REQUIRED_LABELS = {
    *BLOCKS,
    "CONTROL USB",
    "UPLINK USB",
    "I2C_SDA / I2C_SCL",
    "GPIO ENABLES",
    "UART CTRL",
    "DUT interfaces",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLOCKED: {message}")


def point(parent: ET.Element, x: float, y: float) -> None:
    ET.SubElement(
        parent,
        "Point",
        X=f"{x / 25.4:g}",
        Y=f"{y / 25.4:g}",
    )


def graphic(shapes: ET.Element, kind: str, coordinates: tuple[tuple[float, float], ...]) -> None:
    if kind == "Line" and len(coordinates) > 2:
        for start, end in zip(coordinates, coordinates[1:], strict=False):
            graphic(shapes, kind, (start, end))
        return
    shape = ET.SubElement(
        shapes,
        "Shape",
        Enabled="Y",
        Id=str(len(shapes)),
        Type=kind,
        Sheet="0",
        LineWidth="0.011811",
        NetId="-1",
        BusId="-1",
        Group="-1",
        Selected="N",
        Locked="N",
    )
    points = ET.SubElement(shape, "Points")
    for x, y in coordinates:
        point(points, x, y)


def text(
    shapes: ET.Element,
    x: float,
    y: float,
    value: str,
    size: int = 5,
) -> None:
    shape = ET.SubElement(
        shapes,
        "Shape",
        Enabled="Y",
        Id=str(len(shapes)),
        Type="Text",
        Sheet="0",
        Angle="0",
        HorzAlign="Center",
        VertAlign="Center",
        TextAlign="Center",
        FontVector="Y",
        FontSize=str(size),
        FontWidth="-2",
        FontScale="1",
        LineSpacing="1.2",
        NetId="-1",
        BusId="-1",
        Group="-1",
        Selected="N",
        Locked="N",
    )
    points = ET.SubElement(shape, "Points")
    point(points, x, y)
    ET.SubElement(ET.SubElement(shape, "TextLines"), "TextLine").text = value


def sheet_settings_xml() -> str:
    settings = ET.Element("SheetSettings")
    ET.SubElement(settings, "DisplayTitles").text = "Y"
    ET.SubElement(settings, "DisplaySheet").text = "Y"
    ET.SubElement(settings, "ActiveSheet").text = "0"
    sheets = ET.SubElement(settings, "Sheets")
    sheet = ET.SubElement(sheets, "Sheet")
    for tag, value in (
        ("Id", "0"),
        ("Name", SHEET),
        ("Type", "Normal"),
        ("XPos", "0"),
        ("YPos", "0"),
        ("Scale", "1"),
        ("SheetWidth", "11.692913"),
        ("SheetHeight", "8.267717"),
        ("LeftMargin", "0.393701"),
        ("TopMargin", "0.393701"),
        ("RightMargin", "0.393701"),
        ("BottomMargin", "0.393701"),
    ):
        ET.SubElement(sheet, tag).text = value
    border = ET.SubElement(sheet, "BorderZones")
    for tag, value in (
        ("Visible", "Y"),
        ("HorzZones", "4"),
        ("VertZones", "4"),
        ("Standard", "0"),
        ("FontName", "Arial"),
        ("FontSize", "10"),
        ("FontSizeFloat", "10"),
        ("FontLineWidth", "-2"),
        ("Border", "Y"),
        ("HorzBorderSize", "0.314961"),
        ("VertBorderSize", "0.314961"),
    ):
        ET.SubElement(border, tag).text = value
    return ET.tostring(settings, encoding="unicode")


def shapes_xml() -> str:
    shapes = ET.Element("Shapes")
    text(shapes, 0, 82, "DUT CONTROLLER Rev.A / SYSTEM OVERVIEW", 10)
    text(shapes, 0, 73, "DOCUMENTATION ONLY - no electrical connectivity", 5)
    graphic(shapes, "Rectangle", ((-137, 15), (-115, 35)))
    text(shapes, -126, 25, "HOST / MCP", 4)
    graphic(shapes, "Rectangle", ((110, 15), (137, 35)))
    text(shapes, 123.5, 25, "DUT", 5)

    for name, (x1, y1, x2, y2) in BLOCKS.items():
        graphic(shapes, "Rectangle", ((x1, y1), (x2, y2)))
        text(shapes, (x1 + x2) / 2, (y1 + y2) / 2, name, 6)

    graphic(shapes, "Line", ((-115, 25), (-105, 25)))
    text(shapes, -110, 42, "CONTROL USB", 4)
    graphic(shapes, "Line", ((-126, 35), (-126, 52), (7.5, 52), (7.5, 40)))
    text(shapes, -59, 57, "UPLINK USB", 4)
    graphic(shapes, "Line", ((-45, 25), (-15, 25)))
    text(shapes, -30, 32, "control", 4)
    graphic(shapes, "Line", ((30, 25), (110, 25)))
    text(shapes, 70, 32, "DUT interfaces", 4)

    graphic(shapes, "Line", ((-93, 10), (-93, -25)))
    text(shapes, -103, -8, "GPIO ENABLES", 4)
    graphic(shapes, "Line", ((-58, 10), (-58, -25)))
    text(shapes, -68, -8, "UART CTRL", 4)

    graphic(shapes, "Line", ((-50, 10), (-50, -15), (73.5, -15)))
    for x in (-20.5, 24.5, 73.5):
        graphic(shapes, "Line", ((x, -15), (x, -25)))
    text(shapes, 12, -10, "I2C_SDA / I2C_SCL", 4)
    return ET.tostring(shapes, encoding="unicode")


def check(path: Path = ARTIFACT) -> dict[str, object]:
    root = ET.parse(path).getroot()
    require(root.get("Units") == "inch", "native seed units are not preserved")
    sheets = root.findall("./Schematic/SheetSettings/Sheets/Sheet")
    require(len(sheets) == 1, f"expected one sheet, found {len(sheets)}")
    require(sheets[0].findtext("Name") == SHEET, "sheet 1 is not SYSTEM_OVERVIEW")
    require(sheets[0].findtext("SheetWidth") == "11.692913", "sheet width is not A4")
    require(sheets[0].findtext("SheetHeight") == "8.267717", "sheet height is not A4")
    require(root.find("./Schematic/Settings") is not None, "native Settings missing")
    require(root.find("./Schematic/Simulator") is not None, "native Simulator missing")
    require(
        not root.findall("./Library/Components/Component"),
        "unused seed library components found",
    )
    require(not root.findall("./Schematic/Components/Part"), "electrical parts found")
    require(not root.findall("./Schematic/Nets/Net"), "electrical nets found")
    require(not root.findall("./Schematic/Nets/Net/Wires/Wire"), "electrical wires found")

    shapes = root.findall("./Schematic/Shapes/Shape")
    rectangles = [shape for shape in shapes if shape.get("Type") == "Rectangle"]
    require(
        len(rectangles) == 9,
        f"expected seven blocks and two endpoints, found {len(rectangles)} rectangles",
    )
    labels = {line.text or "" for shape in shapes for line in shape.findall("./TextLines/TextLine")}
    require(labels >= REQUIRED_LABELS, f"missing labels: {sorted(REQUIRED_LABELS - labels)}")
    require(all(shape.get("Sheet") == "0" for shape in shapes), "shape on another sheet")

    line_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    rectangle_bounds: list[tuple[float, float, float, float]] = []
    for shape in shapes:
        coordinates = [
            (float(item.get("X", "0")), float(item.get("Y", "0")))
            for item in shape.findall("./Points/Point")
        ]
        require(coordinates, f"shape {shape.get('Id')} has no point")
        require(
            all(
                -138.5 / 25.4 <= x <= 138.5 / 25.4
                and -95 / 25.4 <= y <= 95 / 25.4
                for x, y in coordinates
            ),
            f"shape {shape.get('Id')} escapes the A4 working area",
        )
        if shape.get("Type") == "Rectangle":
            require(len(coordinates) == 2, f"rectangle {shape.get('Id')} is malformed")
            (x1, y1), (x2, y2) = coordinates
            rectangle_bounds.append((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
        if shape.get("Type") == "Line":
            require(
                len(coordinates) == 2,
                f"shape {shape.get('Id')} must be one native line segment",
            )
            require(
                coordinates[0][0] == coordinates[1][0]
                or coordinates[0][1] == coordinates[1][1],
                f"shape {shape.get('Id')} is not orthogonal",
            )
            require(coordinates[0] != coordinates[1], f"shape {shape.get('Id')} has zero length")
            line_segments.append((coordinates[0], coordinates[1]))

    epsilon = 1e-9

    def between(value: float, first: float, second: float) -> bool:
        return min(first, second) - epsilon <= value <= max(first, second) + epsilon

    def on_segment(
        position: tuple[float, float],
        segment: tuple[tuple[float, float], tuple[float, float]],
    ) -> bool:
        (x, y), ((x1, y1), (x2, y2)) = position, segment
        return (
            abs(x1 - x2) <= epsilon
            and abs(x - x1) <= epsilon
            and between(y, y1, y2)
        ) or (
            abs(y1 - y2) <= epsilon
            and abs(y - y1) <= epsilon
            and between(x, x1, x2)
        )

    def on_rectangle_edge(position: tuple[float, float]) -> bool:
        x, y = position
        return any(
            (
                (abs(x - x1) <= epsilon or abs(x - x2) <= epsilon)
                and between(y, y1, y2)
            )
            or (
                (abs(y - y1) <= epsilon or abs(y - y2) <= epsilon)
                and between(x, x1, x2)
            )
            for x1, y1, x2, y2 in rectangle_bounds
        )

    for index, segment in enumerate(line_segments):
        for endpoint in segment:
            require(
                on_rectangle_edge(endpoint)
                or any(
                    other_index != index and on_segment(endpoint, other)
                    for other_index, other in enumerate(line_segments)
                ),
                f"documentary line endpoint {endpoint} is dangling",
            )
        (a, b) = segment
        for other in line_segments[index + 1 :]:
            c, d = other
            horizontal = abs(a[1] - b[1]) <= epsilon
            other_horizontal = abs(c[1] - d[1]) <= epsilon
            if horizontal != other_horizontal:
                h_start, h_end = (a, b) if horizontal else (c, d)
                v_start, v_end = (c, d) if horizontal else (a, b)
                crossing = (v_start[0], h_start[1])
                if on_segment(crossing, segment) and on_segment(crossing, other):
                    require(
                        crossing in {a, b, c, d},
                        f"documentary lines cross at {crossing}",
                    )
            elif horizontal and abs(a[1] - c[1]) <= epsilon:
                overlap = min(max(a[0], b[0]), max(c[0], d[0])) - max(
                    min(a[0], b[0]), min(c[0], d[0])
                )
                require(overlap <= epsilon, "documentary horizontal lines overlap")
            elif not horizontal and abs(a[0] - c[0]) <= epsilon:
                overlap = min(max(a[1], b[1]), max(c[1], d[1])) - max(
                    min(a[1], b[1]), min(c[1], d[1])
                )
                require(overlap <= epsilon, "documentary vertical lines overlap")

    peer_bounds = {
        BLOCKS[name][1::2]
        for name in ("POWER", "UART", "SWITCHES", "AUX_ADC", "CURRENT_SENSE")
    }
    require(len(peer_bounds) == 1, "service blocks are not aligned to common edges")

    require(len(shapes) == 40, f"expected 40 documentary shapes, found {len(shapes)}")

    return {
        "artifact": str(path),
        "sheet": SHEET,
        "library_components": 0,
        "parts": 0,
        "nets": 0,
        "wires": 0,
        "blocks": len(BLOCKS),
        "shapes": len(shapes),
        "gate": "PASS",
    }


def build() -> dict[str, object]:
    STATE.mkdir(parents=True, exist_ok=True)
    service = DipTraceService(
        Settings(
            workspace=ROOT,
            allowed_roots=(ROOT,),
            state_dir=STATE,
            max_document_bytes=128 * 1024 * 1024,
        )
    )
    seed_sha256 = hashlib.sha256(SEED.read_bytes()).hexdigest()
    if not ARTIFACT.exists():
        service.create_document_from_seed(
            str(SEED),
            str(ARTIFACT),
            expected_seed_sha256=seed_sha256,
        )

    root = ET.parse(ARTIFACT).getroot()
    native_scaffold = root.find("./Schematic/Settings") is not None
    if not native_scaffold:
        require(not root.findall("./Schematic/Components/Part"), "refusing non-empty schematic")
        require(not root.findall("./Schematic/Nets/Net"), "refusing schematic with nets")
        current_sha256 = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
        service.create_document_from_seed(
            str(SEED),
            str(ARTIFACT),
            expected_seed_sha256=seed_sha256,
            overwrite=True,
            expected_sha256=current_sha256,
        )
        root = ET.parse(ARTIFACT).getroot()
    else:
        current_sha256 = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
        require(
            current_sha256 == seed_sha256
            or (
                not root.findall("./Schematic/Components/Part")
                and not root.findall("./Schematic/Nets/Net")
            ),
            "refusing to replace a populated native schematic",
        )

    initial_sha256 = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()

    def commit(edits: list[XmlEdit]) -> None:
        preview = service.apply_edits(edits, str(ARTIFACT), dry_run=True)
        if preview["changed"]:
            service.apply_edits(
                edits,
                str(ARTIFACT),
                dry_run=False,
                expected_sha256=str(preview["before_sha256"]),
            )

    commit([XmlEdit("replace_xml", "./Library/Library/PadStyles", "<PadStyles />")])
    commit([XmlEdit("replace_xml", "./Library/Library/Patterns", "<Patterns />")])
    for _ in root.findall("./Library/Components/Component"):
        commit([XmlEdit("delete_element", "./Library/Components/Component[1]")])
    commit([XmlEdit("replace_xml", "./Schematic/SheetSettings", sheet_settings_xml())])
    commit([XmlEdit("replace_xml", "./Schematic/Components", "<Components />")])
    commit([XmlEdit("replace_xml", "./Schematic/Nets", "<Nets />")])
    existing_shapes = ET.parse(ARTIFACT).getroot().find("./Schematic/Shapes")
    commit(
        [
            XmlEdit(
                "replace_xml" if existing_shapes is not None else "append_xml",
                "./Schematic/Shapes" if existing_shapes is not None else "./Schematic",
                shapes_xml(),
            )
        ]
    )
    final_sha256 = hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
    result = check()
    result.update(
        {
            "mcp_dry_run_before_sha256": initial_sha256,
            "mcp_committed_sha256": final_sha256,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check() if args.check else build(), indent=2))


if __name__ == "__main__":
    main()
