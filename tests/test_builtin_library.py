from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import types
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from diptrace_mcp import headless_gui
from diptrace_mcp.errors import (
    AmbiguousSelectorError,
    CapabilityUnavailableError,
    DocumentError,
    ObjectNotFoundError,
)
from diptrace_mcp.operations import PlacePartOperation
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.services import builtin_library as builtin
from diptrace_mcp.services.builtin_library import BuiltinLibraryService, CatalogLocation
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
                id INTEGER PRIMARY KEY, gid INTEGER, file_id INTEGER,
                category_id INTEGER, number INTEGER, ctypes TEXT, cname TEXT,
                cvalue TEXT, clab TEXT, cpattern TEXT, cpossiblenames TEXT,
                cmanufacturer TEXT, cdatasheet TEXT, cadditional TEXT,
                csupplier TEXT, cmounting TEXT, cdescription TEXT);
            CREATE TABLE Patterns(
                id INTEGER PRIMARY KEY, gid INTEGER, file_id INTEGER,
                category_id INTEGER, number INTEGER, ctypes TEXT, cname TEXT,
                cvalue TEXT, clab TEXT, cpattern TEXT, cpossiblenames TEXT,
                cmanufacturer TEXT, cdatasheet TEXT, cadditional TEXT,
                csupplier TEXT, cmounting TEXT, cdescription TEXT);
            INSERT INTO Files VALUES(
                1, 1234, 0, 'C:\\build\\Lib\\transistors_mosfet.eli',
                'Transistors - MOSFET');
            INSERT INTO CCategories VALUES(1, 'Transistors');
            INSERT INTO PCategories VALUES(1, 'SMD');
            INSERT INTO Components VALUES(
                1, 0, 1, 1, 0, 'MOSFET', 'BSS138', '', 'Q', 'SOT23', '',
                'onsemi', 'https://example.invalid/bss138.pdf', '', '', 'SMD',
                'N-channel MOSFET');
            INSERT INTO Patterns VALUES(
                1, 0, 1, 1, 0, 'SMD', 'SOT23', '', '', 'SOT23', '', '', '',
                '', '', 'SMD', 'Small outline transistor');
            """
        )
    return root, database


def _component_library() -> DipTraceDocument:
    return DipTraceDocument.from_bytes(
        Path("source.elixml"),
        b"""<?xml version="1.0" encoding="utf-8"?>
<Library Type="DipTrace-ComponentLibrary" Units="inch">
  <Library Type="DipTrace-PatternLibrary" Units="inch">
    <PadStyles><PadStyle Name="SourcePad" Type="Surface">
      <MainStack Width="0.05" Height="0.04"/>
    </PadStyle></PadStyles>
    <Patterns><Pattern Id="0" PatternStyle="SourcePattern">
      <DefPad Style="SourcePad"/>
      <Pads><Pad Id="1" Style="SourcePad" X="0.1" Y="0">
        <Number>1</Number>
      </Pad></Pads>
    </Pattern></Patterns>
  </Library>
  <Components><Component Id="0"><Part Id="0" RefDes="Q">
    <Pattern Style="SourcePattern"/><Name>BSS138</Name>
    <Pins><Pin Id="0" X="0.1" Length="0.15"/><Pin Id="1"/><Pin Id="2"/></Pins>
  </Part></Component></Components>
</Library>""",
    )


def test_query_builtin_catalog_is_paginated_and_read_only(tmp_path: Path) -> None:
    root, database = _catalog(tmp_path)
    before = hashlib.sha256(database.read_bytes()).hexdigest()

    result = builtin.query_catalog(str(root), "component", "bss138", 0, 10)

    assert result["result"]["matched_count"] == 1
    item = result["result"]["items"][0]
    assert item["catalog_id"] == "builtin-component:1234:0"
    assert item["name"] == "BSS138"
    assert item["library_available"] is True
    assert result["result"]["read_only"] is True
    assert result["result"]["native_library_mutation"] is False
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_builtin_component_definition_is_copied_only_into_schematic() -> None:
    source = _component_library()
    target = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    row = {"library_index": 0, "name": "BSS138"}

    definitions = builtin._component_definitions(source, target, row)
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
    copied_component = root.find(f"./Library/Components/Component[@ComponentStyle='{style}']")
    assert copied_component is not None
    copied_pin = copied_component.find("./Part/Pins/Pin")
    assert copied_pin is not None and copied_pin.get("X") == "2.54"
    copied_pad = root.find("./Library/Library/Patterns/Pattern/Pads/Pad")
    assert copied_pad is not None and copied_pad.get("X") == "2.54"
    copied_stack = root.find("./Library/Library/PadStyles/PadStyle/MainStack")
    assert copied_stack is not None and copied_stack.get("Width") == "1.27"
    assert b"ComponentStyle" not in source.raw_bytes
    assert applied.patch_count == 4


def test_catalog_library_pattern_selectors_and_validation(tmp_path: Path) -> None:
    root, database = _catalog(tmp_path)

    libraries = builtin.query_catalog(str(root), "library", "mosfet", 0, 10)
    assert libraries["result"]["matched_count"] == 1
    assert libraries["result"]["items"][0]["component_count"] == 1
    assert libraries["result"]["items"][0]["pattern_count"] == 1

    patterns = builtin.query_catalog(str(root), "pattern", "sot23", 0, 10)
    assert patterns["result"]["matched_count"] == 1
    assert patterns["result"]["items"][0]["catalog_id"] == "builtin-pattern:1234:0"

    location = builtin._catalog_location(str(root))
    exact = builtin._component_row(location, "builtin-component:1234:0")
    assert exact["name"] == "BSS138"
    with pytest.raises(ObjectNotFoundError):
        builtin._component_row(location, "missing")

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO Components VALUES(
                2, 0, 1, 1, 1, 'MOSFET', 'BSS138', '', 'Q', 'SOT23', '',
                'other', '', '', '', 'SMD', 'duplicate')
            """
        )
    with pytest.raises(AmbiguousSelectorError):
        builtin._component_row(location, "BSS138")

    with pytest.raises(DocumentError, match="kind"):
        builtin.query_catalog(str(root), "invalid", None, 0, 10)  # type: ignore[arg-type]
    with pytest.raises(DocumentError, match="256"):
        builtin.query_catalog(str(root), "component", "x" * 257, 0, 10)


def test_catalog_location_connect_and_helpers_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, database = _catalog(tmp_path)
    location = builtin._catalog_location(str(root))
    assert location.database == database.resolve()
    assert builtin._library_path(location, r"C:\elsewhere\foo.eli").name == "foo.eli"
    escaped = builtin._like_query(r"A%_\B")
    assert r"\%" in escaped and r"\_" in escaped
    assert builtin._next_numeric_id([ET.Element("X", Id="2"), ET.Element("X", Id="9")]) == 10
    style, next_index = builtin._next_style("PadT", {"padt0", "padt1"}, 0)
    assert (style, next_index) == ("PadT2", 3)

    pin = ET.Element("Pin", X="1")
    builtin._convert_library_units([pin], "mm", "mm")
    assert pin.get("X") == "1"
    with pytest.raises(DocumentError, match="Invalid X geometry"):
        builtin._convert_library_units([ET.Element("Pin", X="bad")], "inch", "mm")

    monkeypatch.setattr(builtin, "detect_diptrace_installations", lambda: [])
    with pytest.raises(CapabilityUnavailableError, match="not found"):
        builtin._catalog_location(None)

    def fail_connect(*_args: object, **_kwargs: object) -> sqlite3.Connection:
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(builtin.sqlite3, "connect", fail_connect)
    with pytest.raises(CapabilityUnavailableError, match="read-only"):
        builtin._connect(location)


def test_component_definition_validation_and_missing_pattern() -> None:
    source = _component_library()
    schematic = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    pcb = DipTraceDocument.load(FIXTURES / "pcb.xml", 10_000_000)

    with pytest.raises(DocumentError, match="component library"):
        builtin._component_definitions(pcb, schematic, {"library_index": 0, "name": "x"})
    with pytest.raises(DocumentError, match="schematics"):
        builtin._component_definitions(source, pcb, {"library_index": 0, "name": "BSS138"})
    with pytest.raises(DocumentError, match="outside"):
        builtin._component_definitions(source, schematic, {"library_index": 8, "name": "x"})
    with pytest.raises(DocumentError, match="does not match"):
        builtin._component_definitions(source, schematic, {"library_index": 0, "name": "BAD"})

    missing_pattern = DipTraceDocument.from_bytes(
        Path("missing.elixml"),
        b"""<Library Type="DipTrace-ComponentLibrary" Units="mm">
<Components><Component Id="0"><Part Id="0"><Name>BSS138</Name>
<Pattern Style="Missing"/><Pins><Pin Id="0"/></Pins></Part></Component></Components>
</Library>""",
    )
    with pytest.raises(DocumentError, match="not exported"):
        builtin._component_definitions(
            missing_pattern,
            schematic,
            {"library_index": 0, "name": "BSS138"},
        )


def test_export_cache_and_semantic_place_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, database = _catalog(tmp_path)
    location = CatalogLocation(root, (root / "Lib").resolve(), database.resolve())
    context = SimpleNamespace(settings=SimpleNamespace(state_dir=tmp_path / "state"))
    target = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)

    class Gateway:
        def load(self, _path: str | None):
            return target, tmp_path / "target.xml"

    captured: dict[str, object] = {}

    def semantic_write(operation, path, dry_run, expected_sha256, lock_token):
        captured.update(
            operation=operation,
            path=path,
            dry_run=dry_run,
            expected_sha256=expected_sha256,
            lock_token=lock_token,
        )
        return {"ok": True}

    service = BuiltinLibraryService(context, Gateway(), semantic_write)  # type: ignore[arg-type]
    calls: list[Path] = []

    def fake_export(_root: Path, _source: Path, target_path: Path) -> dict[str, object]:
        calls.append(target_path)
        target_path.write_bytes(_component_library().raw_bytes)
        return {"ok": True}

    monkeypatch.setattr(builtin, "export_component_library_xml", fake_export)
    row = {
        "library_file": str(location.library_root / "transistors_mosfet.eli"),
        "library_index": 0,
        "name": "BSS138",
        "value": "MOSFET",
    }
    first = service._exported_library(location, row)
    second = service._exported_library(location, row)
    assert first.source_type == second.source_type == "DipTrace-ComponentLibrary"
    assert len(calls) == 1

    outside = tmp_path / "outside.eli"
    outside.write_bytes(b"native")
    with pytest.raises(CapabilityUnavailableError, match="outside"):
        service._exported_library(location, {"library_file": str(outside)})

    monkeypatch.setattr(builtin, "_catalog_location", lambda _root: location)
    monkeypatch.setattr(builtin, "_component_row", lambda _location, _selector: row)
    monkeypatch.setattr(service, "_exported_library", lambda _location, _row: first)
    result = service.place_component(
        "BSS138",
        "Q9",
        10,
        20,
        path="target.xml",
        dry_run=False,
        expected_sha256="abc",
    )
    assert result == {"ok": True}
    operation = captured["operation"]
    assert isinstance(operation, PlacePartOperation)
    assert operation.refdes == "Q9"
    assert operation.value == "MOSFET"
    assert captured["dry_run"] is False
    assert captured["expected_sha256"] == "abc"


def _fake_windows_os() -> types.ModuleType:
    fake_os = types.ModuleType("os")
    fake_os.__dict__.update(os.__dict__)
    fake_os.name = "nt"
    return fake_os


def test_library_export_validation_and_top_level_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DipTrace"
    lib = root / "Lib"
    lib.mkdir(parents=True)
    (root / "CompEdit.exe").write_bytes(b"exe")
    source = lib / "good.eli"
    source.write_bytes(b"library")
    monkeypatch.setattr(
        headless_gui,
        "validate_diptrace_directory",
        lambda _root: SimpleNamespace(root=root),
    )
    target = tmp_path / "exports" / "good.elixml"
    validated = headless_gui._validated_library_export(root, source, target)
    assert validated[1] == source.resolve()

    wrong = lib / "bad.txt"
    wrong.write_bytes(b"bad")
    with pytest.raises(headless_gui.HeadlessGuiError, match="built-in .eli"):
        headless_gui._validated_library_export(root, wrong, tmp_path / "a.elixml")
    outside = tmp_path / "outside.eli"
    outside.write_bytes(b"native")
    with pytest.raises(headless_gui.HeadlessGuiError, match="built-in .eli"):
        headless_gui._validated_library_export(root, outside, tmp_path / "b.elixml")
    with pytest.raises(headless_gui.HeadlessGuiError, match="elixml"):
        headless_gui._validated_library_export(root, source, tmp_path / "bad.xml")
    with pytest.raises(headless_gui.HeadlessGuiError, match="outside"):
        headless_gui._validated_library_export(root, source, root / "inside.elixml")

    monkeypatch.setattr(headless_gui, "os", _fake_windows_os())
    monkeypatch.setattr(
        headless_gui,
        "_validated_library_export",
        lambda *_args: (root, source, target),
    )
    monkeypatch.setattr(headless_gui, "input_desktop_name", lambda: "Default")
    monkeypatch.setattr(headless_gui, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(headless_gui, "process_session_id", lambda pid=None: 3)

    state: dict[str, object] = {"payload": {"ok": True}, "timeout": False}

    class Worker:
        def __init__(self, argv: list[str]) -> None:
            self.argv = argv
            self.wait_count = 0

        def wait(self, _timeout: float):
            self.wait_count += 1
            if state["timeout"] and self.wait_count == 1:
                return None
            result_path = Path(self.argv[self.argv.index("--result") + 1])
            result_path.write_text(json.dumps(state["payload"]), encoding="utf-8")
            return 0

        def terminate(self, _code: int = 1) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    class Desktop:
        def __init__(self, _name: str) -> None:
            pass

        def launch(self, argv):
            return Worker(list(argv))

        def __enter__(self):
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(headless_gui, "HiddenDesktop", Desktop)
    assert headless_gui.export_component_library_xml(root, source, target)["ok"] is True

    state["payload"] = {"ok": False, "error": "boom"}
    with pytest.raises(headless_gui.HeadlessGuiError, match="boom"):
        headless_gui.export_component_library_xml(root, source, target)

    state["timeout"] = True
    with pytest.raises(headless_gui.HeadlessGuiError, match="timed out"):
        headless_gui.export_component_library_xml(root, source, target, timeout_seconds=1)
    with pytest.raises(ValueError, match="timeout_seconds"):
        headless_gui.export_component_library_xml(root, source, target, timeout_seconds=0)


def test_native_menu_dialog_wait_and_worker_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    posted: list[tuple[int, int, int, int]] = []
    monkeypatch.setattr(
        headless_gui,
        "_post_window_message",
        lambda hwnd, message, wparam=0, lparam=0: posted.append((hwnd, message, wparam, lparam)),
    )

    class Menu:
        COMMAND = headless_gui._WM_COMMAND
        handle = 77

    class Item:
        menu = Menu()

        def is_enabled(self):
            return True

        def item_id(self):
            return 123

        def index(self):
            return 2

    window = SimpleNamespace(handle=55)
    headless_gui._post_menu_item(window, Item())
    assert posted[-1] == (55, headless_gui._WM_COMMAND, 123, 0)

    Item.menu.COMMAND = headless_gui._WM_MENUCOMMAND
    headless_gui._post_menu_item(window, Item())
    assert posted[-1] == (55, headless_gui._WM_MENUCOMMAND, 2, 77)

    class Disabled(Item):
        def is_enabled(self):
            return False

    with pytest.raises(headless_gui.HeadlessGuiError, match="disabled"):
        headless_gui._post_menu_item(window, Disabled())

    for class_name in ("#32770", "TFMyMessage", "TForm60"):
        dialog = SimpleNamespace(class_name=lambda value=class_name: value, is_visible=lambda: True)
        app = SimpleNamespace(windows=lambda dialog=dialog, **_kwargs: [dialog])
        assert headless_gui._visible_dialog(app, 1) is dialog
    with pytest.raises(headless_gui.HeadlessGuiError, match="not found"):
        headless_gui._visible_dialog(SimpleNamespace(windows=lambda **_kwargs: []), 0)

    target = tmp_path / "done.elixml"
    target.write_bytes(b"xml")
    monkeypatch.setattr(headless_gui.time, "sleep", lambda _seconds: None)
    headless_gui._wait_for_export(SimpleNamespace(windows=lambda **_kwargs: []), target, 1)
    with pytest.raises(headless_gui.HeadlessGuiError, match="timed out"):
        headless_gui._wait_for_export(
            SimpleNamespace(windows=lambda **_kwargs: []),
            tmp_path / "missing.elixml",
            0,
        )


def test_perform_library_export_worker_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "DipTrace"
    source = tmp_path / "source.eli"
    target = tmp_path / "target.elixml"
    source.write_bytes(b"native")
    monkeypatch.setattr(
        headless_gui,
        "_validated_library_export",
        lambda *_args: (root, source, target),
    )

    class App:
        process = 4242

        def start(self, _command: str, timeout: float):
            assert timeout == 2
            return self

        def wait_for_process_exit(self, timeout: float) -> None:
            assert timeout == 2

        def kill(self, soft: bool = False) -> None:
            assert soft is False

    app = App()
    monkeypatch.setattr(headless_gui, "_pywinauto_application", lambda: lambda **_kwargs: app)
    window = SimpleNamespace(
        handle=99,
        wait=lambda *_args, **_kwargs: None,
        menu_item=lambda _path: object(),
    )
    monkeypatch.setattr(headless_gui, "_main_window", lambda *_args: window)
    monkeypatch.setattr(headless_gui, "_post_menu_item", lambda *_args: None)
    monkeypatch.setattr(
        headless_gui,
        "_visible_dialog",
        lambda *_args: SimpleNamespace(handle=88),
    )
    monkeypatch.setattr(headless_gui, "_save_dialog_as_xml", lambda *_args: None)
    monkeypatch.setattr(headless_gui, "_post_window_message", lambda *_args: None)
    monkeypatch.setattr(headless_gui, "_window_titles", lambda _app: ["Component Editor"])

    def finish(_app, target_path: Path, _timeout: float) -> None:
        target_path.write_bytes(b"<Library Type='DipTrace-ComponentLibrary'/>")

    monkeypatch.setattr(headless_gui, "_wait_for_export", finish)
    result = headless_gui._perform_library_export_worker(root, source, target, 2, "Hidden")
    assert result["ok"] is True
    assert result["diptrace_pid"] == 4242
    assert result["source_sha256"] == result["source_sha256_after"]
    assert result["target_size_bytes"]

    target.unlink()

    def fail_main(*_args):
        raise headless_gui.HeadlessGuiError("boom")

    monkeypatch.setattr(headless_gui, "_main_window", fail_main)
    failed = headless_gui._perform_library_export_worker(root, source, target, 2, "Hidden")
    assert failed["ok"] is False
    assert "boom" in str(failed["error"])
    assert not target.exists()


def test_cmd_library_export_worker_identity_guards(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(
        json.dumps(
            {
                "diptrace_root": "r",
                "source": "s",
                "target": "t",
                "timeout_seconds": 2,
                "_expected_window_station": "WinSta0",
                "_expected_session_id": 5,
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(request=str(request), result=str(result), desktop_name="Hidden")
    monkeypatch.setattr(headless_gui, "thread_desktop_name", lambda: "Hidden")
    monkeypatch.setattr(headless_gui, "process_window_station_name", lambda: "WinSta0")
    monkeypatch.setattr(headless_gui, "process_session_id", lambda pid=None: 5)
    monkeypatch.setattr(
        headless_gui,
        "_perform_library_export_worker",
        lambda *_args: {"ok": True, "native_library_mutated": False},
    )
    assert headless_gui._cmd_library_export_worker(args) == 0
    assert '"ok": true' in result.read_text(encoding="utf-8")

    monkeypatch.setattr(headless_gui, "thread_desktop_name", lambda: "Wrong")
    assert headless_gui._cmd_library_export_worker(args) == 1
    assert "unexpected desktop" in result.read_text(encoding="utf-8")
