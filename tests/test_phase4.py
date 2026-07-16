from __future__ import annotations

import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.domain import QuerySelector
from diptrace_mcp.errors import (
    AmbiguousSelectorError,
    EditError,
    LockedObjectError,
    Sha256MismatchError,
)
from diptrace_mcp.operations import (
    AddTestpointOperation,
    AssignNetsToClassOperation,
    GroupComponentsOperation,
    MoveBoardTextsOperation,
    MoveComponentsOperation,
    MoveTestpointsOperation,
    RemoveTestpointsOperation,
    RenameNetOperation,
    RotateBoardTextsOperation,
    RotateComponentsOperation,
    SetComponentLockOperation,
    SetComponentPatternOperation,
    SetComponentPropertiesOperation,
    SetComponentSideOperation,
    SetPinNoConnectOperation,
    SetTextStyleOperation,
    SetTextVisibilityOperation,
    UngroupComponentsOperation,
    UpdateNetClassRulesOperation,
)
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> DipTraceDocument:
    return DipTraceDocument.load(FIXTURES / name, 10_000_000)


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=10_000_000,
        )
    )


def test_component_direct_edits_compile_to_verified_xml() -> None:
    document = _load("pcb.xml")
    result = apply_semantic_operations(
        document,
        [
            RotateComponentsOperation(
                selector=QuerySelector(refdes=["R1"]),
                angle_deg=90,
                mode="absolute",
                allowed_angles=[0, 90, 180, 270],
            ),
            SetComponentSideOperation(
                selector=QuerySelector(refdes=["R1"]),
                side="Bottom",
            ),
            SetComponentPropertiesOperation(
                selector=QuerySelector(refdes=["R1"]),
                value="12k",
                fields={"MPN": "RC0603FR-0712KL"},
            ),
        ],
    )

    root = ET.fromstring(result.raw_bytes)
    component = root.find("./Board/Components/Component[@Id='0']")
    assert component is not None
    assert float(component.get("Angle", "0")) == pytest.approx(math.pi / 2)
    assert component.get("Side") == "Bottom"
    assert component.findtext("./Value") == "12k"
    assert component.findtext("./AddFields/AddField/Name") == "MPN"
    assert component.findtext("./AddFields/AddField/Text") == "RC0603FR-0712KL"
    assert root.find("./Board/FutureExtension[@Vendor='fixture']") is not None

    reparsed = build_snapshot(result.document)
    changed = next(item for item in reparsed.objects.values() if item.refdes == "R1")
    assert changed.rotation_deg == pytest.approx(90)
    assert changed.side == "Bottom"
    assert changed.mirrored is True


def test_documented_component_groups_roundtrip() -> None:
    selector = QuerySelector(refdes=["R1", "U1"])
    grouped = apply_semantic_operations(
        _load("pcb.xml"),
        [GroupComponentsOperation(selector=selector)],
    )
    grouped_root = ET.fromstring(grouped.raw_bytes)
    group = grouped_root.find("./Board/Groups/Group[@Id='0']")
    assert group is not None
    assert {
        item.get("Group")
        for item in grouped_root.findall("./Board/Components/Component")
    } == {"0"}

    ungrouped = apply_semantic_operations(
        grouped.document,
        [UngroupComponentsOperation(selector=selector)],
    )
    ungrouped_root = ET.fromstring(ungrouped.raw_bytes)
    assert ungrouped_root.find("./Board/Groups/Group") is None
    assert {
        item.get("Group")
        for item in ungrouped_root.findall("./Board/Components/Component")
    } == {"-1"}


def test_pattern_swap_requires_exact_pad_mapping() -> None:
    raw = (FIXTURES / "pcb.xml").read_bytes()
    marker = b'<Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm" />'
    library = b"""<Library Type="DipTrace-PatternLibrary" Version="4.3.0.3" Units="mm">
      <PadStyles>
        <PadStyle Name="SMD" Type="Surface" Side="Top">
          <MainStack Shape="Rectangle" Width="1" Height="1" />
        </PadStyle>
      </PadStyles>
      <Patterns>
        <Pattern PatternStyle="AltGood">
          <Name>AltGood</Name><DefPad Style="SMD" /><Pads>
            <Pad Id="0" Style="SMD" X="-1" Y="0"><Number>1</Number></Pad>
            <Pad Id="1" Style="SMD" X="1" Y="0"><Number>2</Number></Pad>
          </Pads>
        </Pattern>
        <Pattern PatternStyle="AltBad">
          <Name>AltBad</Name><DefPad Style="SMD" /><Pads>
            <Pad Id="0" Style="SMD" X="-1" Y="0"><Number>1</Number></Pad>
            <Pad Id="2" Style="SMD" X="1" Y="0"><Number>3</Number></Pad>
          </Pads>
        </Pattern>
      </Patterns>
    </Library>"""
    document = DipTraceDocument.from_bytes(
        FIXTURES / "pattern-swap.xml", raw.replace(marker, library)
    )
    selector = QuerySelector(refdes=["R1"])

    changed = apply_semantic_operations(
        document,
        [SetComponentPatternOperation(selector=selector, pattern_style="AltGood")],
    )
    root = ET.fromstring(changed.raw_bytes)
    component = root.find("./Board/Components/Component[@Id='0']")
    assert component is not None
    assert component.get("PatternStyle") == "AltGood"

    with pytest.raises(EditError) as error:
        apply_semantic_operations(
            document,
            [SetComponentPatternOperation(selector=selector, pattern_style="AltBad")],
        )
    assert error.value.payload.code == "connectivity_regression"


def test_locked_component_rejects_following_move() -> None:
    selector = QuerySelector(refdes=["R1"])
    with pytest.raises(LockedObjectError):
        apply_semantic_operations(
            _load("pcb.xml"),
            [
                SetComponentLockOperation(selector=selector, locked=True),
                MoveComponentsOperation(selector=selector, dx=1),
            ],
        )

    result = apply_semantic_operations(
        _load("pcb.xml"),
        [
            SetComponentLockOperation(selector=selector, locked=True),
            SetComponentLockOperation(selector=selector, locked=False),
            MoveComponentsOperation(selector=selector, dx=1),
        ],
    )
    root = ET.fromstring(result.raw_bytes)
    component = root.find("./Board/Components/Component[@Id='0']")
    assert component is not None
    assert component.get("Locked") == "N"
    assert component.get("X") == "11"


def test_component_and_free_board_text_edits_use_correct_coordinate_space() -> None:
    document = _load("pcb.xml")
    snapshot = build_snapshot(document)
    component_text = next(
        item
        for item in snapshot.objects.values()
        if item.kind == "component_text" and item.attributes["surface"] == "Silk"
    )
    board_text = next(item for item in snapshot.objects.values() if item.kind == "board_text")

    result = apply_semantic_operations(
        document,
        [
            MoveBoardTextsOperation(
                selector=QuerySelector(ids=[component_text.stable_id]),
                absolute_x=12,
                absolute_y=12,
            ),
            RotateBoardTextsOperation(
                selector=QuerySelector(ids=[component_text.stable_id]),
                angle_deg=90,
                mode="absolute",
            ),
            SetTextVisibilityOperation(
                selector=QuerySelector(ids=[component_text.stable_id]),
                visibility="Hide",
            ),
            MoveBoardTextsOperation(
                selector=QuerySelector(ids=[board_text.stable_id]),
                dx=2,
                dy=-3,
            ),
            RotateBoardTextsOperation(
                selector=QuerySelector(ids=[board_text.stable_id]),
                angle_deg=45,
                mode="absolute",
            ),
            SetTextStyleOperation(
                selector=QuerySelector(ids=[board_text.stable_id]),
                font_size=7,
                font_width=1.25,
                horizontal_align="Center",
                mirrored=True,
            ),
        ],
    )

    root = ET.fromstring(result.raw_bytes)
    silk = root.find("./Board/Components/Component[@Id='0']/RefDesMarking/Silk")
    assert silk is not None
    assert float(silk.get("X", "nan")) == pytest.approx(2)
    assert float(silk.get("Y", "nan")) == pytest.approx(2)
    assert float(silk.get("Angle", "nan")) == pytest.approx(math.pi / 2)
    assert silk.get("Show") == "Hide"

    shape = root.find("./Board/Shapes/Shape[@Id='0']")
    assert shape is not None
    anchor = shape.find("./Points/Point")
    assert anchor is not None
    assert (anchor.get("X"), anchor.get("Y")) == ("7", "22")
    assert float(shape.get("Angle", "nan")) == pytest.approx(math.pi / 4)
    assert shape.get("FontSize") == "7"
    assert shape.get("FontWidth") == "1.25"
    assert shape.get("HorzAlign") == "Center"
    assert shape.get("Inverted") == "Y"


def test_schematic_pin_and_net_edits_and_duplicate_guards() -> None:
    document = _load("schematic.xml")
    snapshot = build_snapshot(document)
    pin = next(
        item
        for item in snapshot.objects.values()
        if item.kind == "pin"
        and item.refdes == "U1"
        and item.attributes["NetId"] == "-1"
        and item.attributes["NotConnected"] == "N"
    )

    result = apply_semantic_operations(
        document,
        [
            SetPinNoConnectOperation(
                selector=QuerySelector(ids=[pin.stable_id]),
                no_connect=True,
            ),
            RenameNetOperation(
                selector=QuerySelector(names=["SIGNAL"]),
                new_name="GPIO1",
            ),
        ],
    )
    root = ET.fromstring(result.raw_bytes)
    target_pin = root.find("./Schematic/Components/Part[@Id='1']/Pins/Pin[@NetId='-1']")
    assert target_pin is not None
    assert target_pin.get("NotConnected") == "Y"
    assert root.findtext("./Schematic/Nets/Net[@Id='1']/Name") == "GPIO1"

    with pytest.raises(AmbiguousSelectorError):
        apply_semantic_operations(
            document,
            [
                RenameNetOperation(
                    selector=QuerySelector(names=["SIGNAL"]),
                    new_name="VCC",
                )
            ],
        )
    with pytest.raises(AmbiguousSelectorError):
        apply_semantic_operations(
            document,
            [
                SetComponentPropertiesOperation(
                    selector=QuerySelector(refdes=["R1"]),
                    refdes="U1",
                )
            ],
        )


def test_semantic_tools_append_to_transaction_commit_and_rollback(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    shutil.copyfile(FIXTURES / "pcb.xml", board)
    service = _service(workspace, tmp_path / "state")
    source_sha = DipTraceDocument.load(board, 10_000_000).sha256

    first = service.move_components(
        {"refdes": ["R1"]},
        dx=2,
        path=str(board),
        dry_run=True,
        expected_sha256=source_sha,
    )
    txid = first["transaction"]["txid"]
    second = service.rotate_components(
        {"refdes": ["R1"]},
        90,
        "absolute",
        txid=txid,
    )
    assert len(second["transaction"]["operations"]) == 2
    assert second["transaction"]["compiled_patch_count"] == 3

    committed = service.commit_transaction(txid, source_sha)
    commit_sha = committed["transaction"]["committed_sha256"]
    root = ET.parse(board).getroot()
    component = root.find("./Board/Components/Component[@Id='0']")
    assert component is not None
    assert component.get("X") == "12"
    assert float(component.get("Angle", "0")) == pytest.approx(math.pi / 2)

    rolled_back = service.rollback_transaction(txid, commit_sha)
    assert rolled_back["result"]["restored_sha256"] == source_sha
    assert DipTraceDocument.load(board, 10_000_000).sha256 == source_sha


def test_align_and_distribute_compile_many_moves_as_one_transaction(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    root = ET.fromstring((FIXTURES / "pcb.xml").read_bytes())
    components = root.find("./Board/Components")
    assert components is not None
    third = ET.SubElement(
        components,
        "Component",
        {
            "Id": "2",
            "PatternStyle": "PatType2",
            "X": "30",
            "Y": "14",
            "Side": "Top",
            "Locked": "N",
        },
    )
    ET.SubElement(third, "RefDes").text = "C1"
    ET.SubElement(third, "Name").text = "CAP_0603"
    ET.SubElement(third, "Value").text = "100n"
    ET.SubElement(third, "Pads")
    board.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    service = _service(workspace, tmp_path / "state")
    selector = {"refdes": ["R1", "U1", "C1"]}
    source_sha = DipTraceDocument.load(board, 10_000_000).sha256

    aligned = service.align_components(
        selector,
        "center_y",
        target_value=12,
        path=str(board),
        expected_sha256=source_sha,
    )
    assert len(aligned["transaction"]["operations"]) == 3
    committed = service.commit_transaction(aligned["transaction"]["txid"], source_sha)
    aligned_sha = committed["transaction"]["committed_sha256"]

    distributed = service.distribute_components(
        selector,
        "x",
        spacing=5,
        path=str(board),
        expected_sha256=aligned_sha,
    )
    assert len(distributed["transaction"]["operations"]) == 3
    service.commit_transaction(distributed["transaction"]["txid"], aligned_sha)
    final = ET.parse(board).getroot()
    positions = {
        item.findtext("./RefDes"): (item.get("X"), item.get("Y"))
        for item in final.findall("./Board/Components/Component")
    }
    assert positions == {
        "R1": ("10", "12"),
        "U1": ("15", "12"),
        "C1": ("20", "12"),
    }


def test_semantic_dry_run_rejects_stale_sha(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    shutil.copyfile(FIXTURES / "pcb.xml", board)
    service = _service(workspace, tmp_path / "state")

    with pytest.raises(Sha256MismatchError):
        service.move_components(
            {"refdes": ["R1"]},
            dx=1,
            path=str(board),
            expected_sha256="0" * 64,
        )


def test_net_class_rules_use_documented_layer_properties() -> None:
    result = apply_semantic_operations(
        _load("pcb.xml"),
        [
            UpdateNetClassRulesOperation(
                class_name="Default",
                layer="Top",
                width=0.3,
                clearance=0.22,
                check_length=True,
                fixed_length=25,
                length_delta=0.5,
            ),
            AssignNetsToClassOperation(
                selector=QuerySelector(names=["SIGNAL"]),
                class_name="Default",
            ),
        ],
    )
    root = ET.fromstring(result.raw_bytes)
    net_class = root.find("./Board/NetClasses/NetClass[@Id='0']")
    assert net_class is not None
    assert net_class.get("CheckLength") == "Y"
    assert net_class.get("FixedLength") == "25"
    assert net_class.get("LengthDelta") == "0.5"
    top = net_class.find("./LayProperties/LayProperty[LayerName='Top']")
    bottom = net_class.find("./LayProperties/LayProperty[LayerName='Bottom']")
    assert top is not None and bottom is not None
    assert top.get("Width") == "0.3"
    assert top.get("Clearance") == "0.22"
    assert bottom.get("Width") == "0.25"
    assert result.patch_count == 5


def test_testpoint_add_move_remove_roundtrip() -> None:
    added = apply_semantic_operations(
        _load("pcb.xml"),
        [
            AddTestpointOperation(
                net="VCC",
                x=5,
                y=5,
                side="Top",
                pad_diameter=1.2,
                hole_diameter=0.6,
                refdes="TP1",
            )
        ],
    )
    root = ET.fromstring(added.raw_bytes)
    component = root.find("./Board/Components/Component[RefDes='TP1']")
    assert component is not None
    assert component.get("Type") == "Pad"
    assert component.get("X") == "5"
    component_id = component.get("Id")
    assert root.find(
        f"./Board/Nets/Net[Name='VCC']/Pads/Item[@Comp='{component_id}'][@Pad='0']"
    ) is not None
    pattern_style = component.get("PatternStyle")
    assert root.find(
        f"./Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern[@PatternStyle='{pattern_style}']"
    ) is not None
    snapshot = build_snapshot(added.document)
    assert snapshot.board is not None
    assert len(snapshot.board.testpoints) == 1
    testpoint = snapshot.board.testpoints[0]
    assert testpoint.refdes == "TP1"
    assert testpoint.net_id == "0"
    assert testpoint.position == {"x": 5.0, "y": 5.0}

    moved = apply_semantic_operations(
        added.document,
        [
            MoveTestpointsOperation(
                selector=QuerySelector(refdes=["TP1"]),
                dx=2,
                dy=1,
            )
        ],
    )
    moved_root = ET.fromstring(moved.raw_bytes)
    moved_component = moved_root.find("./Board/Components/Component[RefDes='TP1']")
    assert moved_component is not None
    assert (moved_component.get("X"), moved_component.get("Y")) == ("7", "6")

    removed = apply_semantic_operations(
        moved.document,
        [
            RemoveTestpointsOperation(selector=QuerySelector(refdes=["TP1"]))
        ],
    )
    removed_root = ET.fromstring(removed.raw_bytes)
    assert removed_root.find("./Board/Components/Component[RefDes='TP1']") is None
    assert removed_root.find(f"./Board/Nets/Net/Pads/Item[@Comp='{component_id}']") is None
    assert removed_root.find(
        f"./Library[@Type='DipTrace-PatternLibrary']/Patterns/Pattern[@PatternStyle='{pattern_style}']"
    ) is None
    assert removed_root.find("./Board/FutureExtension[@Vendor='fixture']") is not None


def test_testpoint_rejects_outside_board_and_component_overlap() -> None:
    with pytest.raises(EditError, match="outside the board"):
        apply_semantic_operations(
            _load("pcb.xml"),
            [AddTestpointOperation(net="VCC", x=60, y=5, pad_diameter=1)],
        )
    with pytest.raises(EditError, match="overlaps R1"):
        apply_semantic_operations(
            _load("pcb.xml"),
            [AddTestpointOperation(net="VCC", x=10, y=10, pad_diameter=1)],
        )


def test_testpoint_service_transaction_and_coverage(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    board = workspace / "board.xml"
    shutil.copyfile(FIXTURES / "pcb.xml", board)
    service = _service(workspace, tmp_path / "state")
    source_sha = DipTraceDocument.load(board, 10_000_000).sha256

    candidates = service.find_testpoint_candidates(
        ["VCC"], path=str(board), candidates_per_net=3
    )
    assert candidates["result"]["candidate_count"] == 3
    preview = service.add_testpoints(
        [
            {
                "net": "VCC",
                "x": 5,
                "y": 5,
                "pad_diameter": 1.2,
                "hole_diameter": 0.6,
                "refdes": "TP1",
            }
        ],
        path=str(board),
        expected_sha256=source_sha,
    )
    assert preview["transaction"]["status"] == "validated"
    committed = service.commit_transaction(preview["transaction"]["txid"], source_sha)
    assert committed["transaction"]["compiled_patch_count"] == 6
    listed = service.list_testpoints(str(board))
    assert listed["result"]["matched_count"] == 1
    coverage = service.review_testpoint_coverage(["VCC", "SIGNAL"], str(board))
    assert coverage["result"]["covered_nets"] == ["VCC"]
    assert coverage["result"]["coverage"] == 0.5
