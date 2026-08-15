from __future__ import annotations

import hashlib
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from diptrace_mcp.operations import PlacePartOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.services.builtin_library import (
    _component_definitions,
    query_catalog,
)
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _catalog(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "DipTrace"
    library = root / "Lib" / "transistors_mosfet.eli"
    database = root / "Data_Unicode" / "compat.db"
    library.parent.mkdir(parents=True)
    database.parent.mkdir(parents=True)
    (root / "CompEdit.exe").write_bytes(b"test")
    library.write_bytes(b"read-only native library")
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE Files(id INTEGER PRIMARY KEY, uid32 INTEGER, gid INTEGER,
                               name TEXT, caption TEXT);
            CREATE TABLE CCategories(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE PCategories(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE Components(
                id INTEGER PRIMARY KEY, gid INTEGER, file_id INTEGER, category_id INTEGER,
                number INTEGER, ctypes TEXT, cname TEXT, cvalue TEXT, clab TEXT,
                cpattern TEXT, cpossiblenames TEXT, cmanufacturer TEXT, cdatasheet TEXT,
                cadditional TEXT, csupplier TEXT, cmounting TEXT, cdescription TEXT);
            CREATE TABLE Patterns(
                id INTEGER PRIMARY KEY, gid INTEGER, file_id INTEGER, category_id INTEGER,
                number INTEGER, ctypes TEXT, cname TEXT, cvalue TEXT, clab TEXT,
                cpattern TEXT, cpossiblenames TEXT, cmanufacturer TEXT, cdatasheet TEXT,
                cadditional TEXT, csupplier TEXT, cmounting TEXT, cdescription TEXT);
            INSERT INTO Files VALUES(
                1, 1234, 0, 'C:\\build\\Lib\\transistors_mosfet.eli',
                'Transistors - MOSFET');
            INSERT INTO CCategories VALUES(1, 'Transistors');
            INSERT INTO Components VALUES(
                1, 0, 1, 1, 0, 'MOSFET', 'BSS138', '', 'Q', 'SOT23', '', 'onsemi',
                'https://example.invalid/bss138.pdf', '', '', 'SMD', 'N-channel MOSFET');
            """
        )
    return root, database


def test_query_builtin_catalog_is_paginated_and_read_only(tmp_path: Path) -> None:
    root, database = _catalog(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    result = query_catalog(str(root), "component", "bss138", 0, 10)

    assert result["result"]["matched_count"] == 1
    item = result["result"]["items"][0]
    assert item["catalog_id"] == "builtin-component:1234:0"
    assert item["name"] == "BSS138"
    assert item["library_available"] is True
    assert result["result"]["read_only"] is True
    assert result["result"]["native_library_mutation"] is False
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_builtin_component_definition_is_copied_only_into_schematic() -> None:
    source_path = Path("source.elixml")
    source = DipTraceDocument.from_bytes(
        source_path,
        b"""<?xml version="1.0" encoding="utf-8"?>
<Library Type="DipTrace-ComponentLibrary" Units="inch">
  <Library Type="DipTrace-PatternLibrary" Units="inch">
    <PadStyles><PadStyle Name="SourcePad" Type="Surface">
      <MainStack Width="0.05" Height="0.04"/>
    </PadStyle></PadStyles>
    <Patterns><Pattern Id="0" PatternStyle="SourcePattern"><DefPad Style="SourcePad"/>
      <Pads><Pad Id="1" Style="SourcePad" X="0.1" Y="0"><Number>1</Number></Pad></Pads>
    </Pattern></Patterns>
  </Library>
  <Components><Component Id="0"><Part Id="0" RefDes="Q">
    <Pattern Style="SourcePattern"/><Name>BSS138</Name>
    <Pins><Pin Id="0" X="0.1" Length="0.15"/><Pin Id="1"/><Pin Id="2"/></Pins>
  </Part></Component></Components>
</Library>""",
    )
    target = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    row = {"library_index": 0, "name": "BSS138"}

    definitions = _component_definitions(source, target, row)
    operation = PlacePartOperation(
        component_style=definitions["component_style"],
        refdes="Q9",
        name=definitions["name"],
        x=10,
        y=20,
        pin_count=definitions["pin_count"],
        library_component_xml=definitions["component_xml"],
        library_pattern_xml=definitions["pattern_xml"],
        library_pad_style_xml=definitions["pad_style_xml"],
    )
    applied = apply_semantic_operations(target, [operation])
    root = ET.fromstring(applied.raw_bytes)

    style = str(definitions["component_style"])
    assert root.find(f"./Library/Components/Component[@ComponentStyle='{style}']") is not None
    assert root.find("./Schematic/Components/Part[RefDes='Q9']") is not None
    assert len(root.findall("./Schematic/Components/Part[RefDes='Q9']/Pins/Pin")) == 3
    copied_component = root.find(
        f"./Library/Components/Component[@ComponentStyle='{style}']"
    )
    assert copied_component is not None
    assert copied_component.find("./Part/Pins/Pin").get("X") == "2.54"  # type: ignore[union-attr]
    copied_pad = root.find("./Library/Library/Patterns/Pattern/Pads/Pad")
    assert copied_pad is not None and copied_pad.get("X") == "2.54"
    copied_stack = root.find("./Library/Library/PadStyles/PadStyle/MainStack")
    assert copied_stack is not None and copied_stack.get("Width") == "1.27"
    assert b"ComponentStyle" not in source.raw_bytes
    assert applied.patch_count == 4
