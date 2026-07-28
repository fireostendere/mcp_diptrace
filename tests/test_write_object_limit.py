from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from diptrace_mcp.capability_model import MAX_WRITE_OBJECTS
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError
from diptrace_mcp.scaffolding import build_pcb_document
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import XmlEdit

FIXTURES = Path(__file__).parent / "fixtures"
MAX_BYTES = 20_000_000


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=MAX_BYTES,
        )
    )


def _pattern_library(pattern_count: int, *, units: str = "mm") -> bytes:
    patterns = "".join(
        (
            f'<Pattern PatternStyle="P{index}"><Name>P{index}</Name>'
            f'<Pads><Pad Id="0" Style="S" X="0" Y="0"><Number>1</Number>'
            "</Pad></Pads></Pattern>"
        )
        for index in range(pattern_count)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Library Type="DipTrace-PatternLibrary" Version="4.3.0.1" Units="{units}">'
        '<PadStyles><PadStyle Name="S" Type="Surface" Side="Top">'
        '<MainStack Shape="Rectangle" Width="1" Height="1"/>'
        "</PadStyle></PadStyles>"
        f"<Patterns>{patterns}</Patterns></Library>"
    ).encode()


def _component_library(pin_count: int) -> bytes:
    pins = "".join(
        (
            f'<Pin Id="{index}" X="{index}" Y="0" Locked="N" Type="Default" '
            f'ElectricType="Passive" Orientation="0"><Name>P{index}</Name>'
            f"<PadNumber>{index}</PadNumber></Pin>"
        )
        for index in range(pin_count)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Library Type="DipTrace-ComponentLibrary" Version="4.3.0.1" Units="mm">'
        '<Components><Component><Part RefDes="U"><Name>SYNTHETIC</Name>'
        f"<Pins>{pins}</Pins></Part></Component></Components></Library>"
    ).encode()


def _sync_operation(pad_count: int) -> dict[str, object]:
    pads = "".join(
        f'<Pad Id="{index}" Style="S" X="{index}" Y="0"><Number>{index}</Number></Pad>'
        for index in range(pad_count)
    )
    return {
        "kind": "sync_schematic_to_pcb",
        "schematic_sha256": "0" * 64,
        "components": [
            {
                "refdes": "U1",
                "name": "SYNTHETIC",
                "pattern_style": "P1",
                "x": 0.0,
                "y": 0.0,
                "pad_numbers": [str(index) for index in range(pad_count)],
            }
        ],
        "pattern_xml": [f'<Pattern PatternStyle="P1"><Name>P1</Name><Pads>{pads}</Pads></Pattern>'],
    }


def test_capability_report_discloses_limit_and_exact_exemptions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    limits = service.get_capabilities()["limits"]

    assert limits["max_write_objects"] == MAX_WRITE_OBJECTS
    assert "raw XML edits" in limits["max_write_objects_scope"]
    assert limits["max_write_objects_exemptions"] == [
        "exact conflict-checked transaction rollback",
        "live-session external apply handshake (pending WO-15 enforcement)",
    ]


def test_place_part_over_limit_is_rejected_before_transaction_creation(
    tmp_path: Path,
) -> None:
    shutil.copy2(FIXTURES / "schematic.xml", tmp_path / "schematic.dch")
    service = _service(tmp_path, tmp_path / ".state")

    with pytest.raises(EditError) as raised:
        service.place_part(
            "SyntheticStyle",
            "U500",
            0.0,
            0.0,
            pin_count=MAX_WRITE_OBJECTS + 1,
            path="schematic.dch",
        )

    assert raised.value.payload.code == "write_object_limit_exceeded"
    assert service.transactions.list() == []


def test_sync_embedded_pattern_children_are_rejected_before_staging(
    tmp_path: Path,
) -> None:
    (tmp_path / "board.dip").write_bytes(build_pcb_document())
    service = _service(tmp_path, tmp_path / ".state")
    begun = service.begin_transaction("board.dip")
    txid = begun["transaction"]["txid"]

    with pytest.raises(EditError) as raised:
        service.stage_operations(txid, [_sync_operation(MAX_WRITE_OBJECTS + 1)])

    assert raised.value.payload.code == "write_object_limit_exceeded"
    assert service.transactions.read(txid).operations == []
    assert service.transactions.read(txid).status == "staged"


def test_raw_utf16_subtree_limit_and_exact_boundary(tmp_path: Path) -> None:
    source = (FIXTURES / "schematic.xml").read_text(encoding="utf-8")
    source = source.replace('encoding="UTF-8"', 'encoding="UTF-16"')
    (tmp_path / "schematic.dch").write_bytes(source.encode("utf-16-be"))
    service = _service(tmp_path, tmp_path / ".state")
    exact_fragment = "<Future>" + "<Item/>" * (MAX_WRITE_OBJECTS - 1) + "</Future>"

    accepted = service.apply_edits(
        [
            XmlEdit(
                operation="append_xml",
                xpath="./Schematic/Components",
                value=exact_fragment,
            )
        ],
        path="schematic.dch",
        dry_run=True,
    )
    assert accepted["write_object_count"] == MAX_WRITE_OBJECTS

    oversized_fragment = "<Future>" + "<Item/>" * MAX_WRITE_OBJECTS + "</Future>"
    with pytest.raises(EditError) as raised:
        service.apply_edits(
            [
                XmlEdit(
                    operation="append_xml",
                    xpath="./Schematic/Components",
                    value=oversized_fragment,
                )
            ],
            path="schematic.dch",
            dry_run=True,
        )
    assert raised.value.payload.code == "write_object_limit_exceeded"


def test_raw_expected_match_error_precedes_impact_accounting(tmp_path: Path) -> None:
    shutil.copy2(FIXTURES / "schematic.xml", tmp_path / "schematic.dch")
    service = _service(tmp_path, tmp_path / ".state")

    with pytest.raises(
        EditError,
        match=r"Edit 0: XPath './Missing' matched 0 elements, expected 1",
    ) as raised:
        service.apply_edits(
            [
                XmlEdit(
                    operation="append_xml",
                    xpath="./Missing",
                    value="<Future>" + "<Item/>" * (MAX_WRITE_OBJECTS + 1) + "</Future>",
                )
            ],
            path="schematic.dch",
            dry_run=True,
        )

    assert raised.value.payload.code == "schema_write_error"


def test_global_library_units_change_is_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "patterns.lib").write_bytes(_pattern_library(100))
    service = _service(tmp_path, tmp_path / ".state")

    with pytest.raises(EditError) as raised:
        service.apply_edits(
            [
                XmlEdit(
                    operation="set_attribute",
                    xpath=".",
                    attribute="Units",
                    value="inch",
                )
            ],
            path="patterns.lib",
            dry_run=True,
        )

    assert raised.value.payload.code == "write_object_limit_exceeded"
    assert raised.value.details["structural_element_count"] > MAX_WRITE_OBJECTS


def test_seed_create_and_overwrite_refuse_oversized_library_before_write(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "seed.lib"
    seed.write_bytes(_pattern_library(MAX_WRITE_OBJECTS + 1))
    target = tmp_path / "target.lib"
    original = _pattern_library(1)
    target.write_bytes(original)
    service = _service(tmp_path, tmp_path / ".state")

    with pytest.raises(EditError) as create_error:
        service.create_document_from_seed("seed.lib", "new.lib")
    assert create_error.value.payload.code == "write_object_limit_exceeded"
    assert not (tmp_path / "new.lib").exists()

    with pytest.raises(EditError) as overwrite_error:
        service.create_document_from_seed("seed.lib", "target.lib", overwrite=True)
    assert overwrite_error.value.payload.code == "write_object_limit_exceeded"
    assert target.read_bytes() == original


def test_component_library_pin_models_contribute_to_seed_limit(tmp_path: Path) -> None:
    (tmp_path / "components.lib").write_bytes(_component_library(MAX_WRITE_OBJECTS + 1))
    service = _service(tmp_path, tmp_path / ".state")

    with pytest.raises(EditError) as raised:
        service.create_document_from_seed("components.lib", "copy.lib")

    assert raised.value.payload.code == "write_object_limit_exceeded"
    assert raised.value.details["normalized_object_count"] > MAX_WRITE_OBJECTS
    assert not (tmp_path / "copy.lib").exists()


def test_create_document_refuses_oversized_scaffold_and_preserves_overwrite(
    tmp_path: Path,
) -> None:
    target = tmp_path / "schematic.dch"
    original = (FIXTURES / "schematic.xml").read_bytes()
    target.write_bytes(original)
    service = _service(tmp_path, tmp_path / ".state")
    sheets = [f"Sheet {index}" for index in range(256)]

    with pytest.raises(EditError) as raised:
        service.create_document(
            "schematic",
            "schematic.dch",
            sheets=sheets,
            overwrite=True,
        )

    assert raised.value.payload.code == "write_object_limit_exceeded"
    assert target.read_bytes() == original


def test_normalized_changed_ids_include_created_part_pins(tmp_path: Path) -> None:
    shutil.copy2(FIXTURES / "schematic.xml", tmp_path / "schematic.dch")
    service = _service(tmp_path, tmp_path / ".state")

    preview = service.place_part(
        "SyntheticStyle",
        "U99",
        0.0,
        0.0,
        pin_count=2,
        path="schematic.dch",
    )
    changed_ids = preview["result"]["changed_ids"]

    assert len(changed_ids) == 3
    assert sum(item.startswith("pin_") for item in changed_ids) == 2


def test_commit_rechecks_object_limit_before_writing(tmp_path: Path) -> None:
    target = tmp_path / "schematic.dch"
    original = (FIXTURES / "schematic.xml").read_bytes()
    target.write_bytes(original)
    service = _service(tmp_path, tmp_path / ".state")
    begun = service.begin_transaction("schematic.dch")
    txid = begun["transaction"]["txid"]
    service.stage_operations(
        txid,
        [
            {
                "kind": "place_part",
                "component_style": "SyntheticStyle",
                "refdes": "U999",
                "x": 0.0,
                "y": 0.0,
                "pin_count": 1,
            }
        ],
    )
    service.preview_transaction(txid)
    service.transactions.update(
        txid,
        status="validated",
        operations=[
            {
                "kind": "place_part",
                "component_style": "SyntheticStyle",
                "refdes": "U1000",
                "x": 0.0,
                "y": 0.0,
                "pin_count": MAX_WRITE_OBJECTS + 1,
            }
        ],
    )

    with pytest.raises(EditError) as raised:
        service.commit_transaction(txid, begun["transaction"]["source_sha256"])

    assert raised.value.payload.code == "write_object_limit_exceeded"
    assert target.read_bytes() == original
