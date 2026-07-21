from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import EditError
from diptrace_mcp.scaffolding import (
    LayerSpec,
    PcbScaffold,
    SchematicScaffold,
    build_pcb_document,
    build_schematic_document,
    default_layers,
)
from diptrace_mcp.service import DipTraceService
from diptrace_mcp.xml_document import DipTraceDocument

MAX_BYTES = 10_000_000


def _load(raw: bytes, name: str = "generated.xml") -> DipTraceDocument:
    return DipTraceDocument.from_bytes(Path(name), raw)


def test_schematic_scaffold_parses_and_normalizes() -> None:
    raw = build_schematic_document(SchematicScaffold(sheet_names=["Main", "Power"]))
    document = _load(raw)
    assert document.kind == "schematic"
    assert document.source_type == "DipTrace-Schematic"
    snapshot = build_snapshot(document)
    assert snapshot.schematic is not None
    assert [sheet["name"] for sheet in snapshot.schematic.sheets] == ["Main", "Power"]
    assert snapshot.warnings == []
    erc = snapshot.schematic.erc
    assert erc["vcctemplate"] == "V*"
    assert erc["gndtemplate"] == "GND*"


def test_schematic_scaffold_rejects_duplicate_sheet_names() -> None:
    with pytest.raises(ValueError, match="unique"):
        SchematicScaffold(sheet_names=["Main", "main"])


def test_pcb_scaffold_parses_and_normalizes() -> None:
    raw = build_pcb_document(PcbScaffold(width_mm=80.0, height_mm=60.0))
    document = _load(raw)
    assert document.kind == "pcb"
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    assert [layer["name"] for layer in snapshot.board.layers] == ["Top", "Bottom"]
    outline = snapshot.board.outline
    assert outline is not None
    assert outline["bbox"] == {"min_x": 0.0, "min_y": 0.0, "max_x": 80.0, "max_y": 60.0}
    stackup = snapshot.board.stackup
    assert stackup.source == "LayerStackItems"
    dielectrics = [
        item for item in stackup.layers if item.material.material_type == "dielectric"
    ]
    conductors = [
        item for item in stackup.layers if item.material.material_type == "conductor"
    ]
    assert len(conductors) == 2
    assert len(dielectrics) == 1
    assert dielectrics[0].material.thickness_mm == pytest.approx(1.6)
    assert dielectrics[0].material.dielectric_constant == pytest.approx(4.5)
    assert len(snapshot.board.net_classes) == 1
    assert len(snapshot.board.via_styles) == 1
    via_style = snapshot.board.via_styles[0]
    assert via_style.diameter_mm == pytest.approx(0.6)
    assert via_style.hole_mm == pytest.approx(0.3)


def test_pcb_scaffold_multilayer_names() -> None:
    layers = default_layers(4)
    assert [layer.name for layer in layers] == ["Top", "L2", "L3", "Bottom"]
    raw = build_pcb_document(PcbScaffold(layers=layers))
    snapshot = build_snapshot(_load(raw))
    assert snapshot.board is not None
    assert [layer["name"] for layer in snapshot.board.layers] == ["Top", "L2", "L3", "Bottom"]
    conductors = [
        item
        for item in snapshot.board.stackup.layers
        if item.material.material_type == "conductor"
    ]
    dielectrics = [
        item
        for item in snapshot.board.stackup.layers
        if item.material.material_type == "dielectric"
    ]
    assert len(conductors) == 4
    assert len(dielectrics) == 3


def test_pcb_scaffold_plane_layers_and_custom_rules() -> None:
    raw = build_pcb_document(
        PcbScaffold(
            width_mm=100.0,
            height_mm=50.0,
            layers=[
                LayerSpec(name="Top"),
                LayerSpec(name="GND", type="Plane"),
                LayerSpec(name="Bottom"),
            ],
            trace_width_mm=0.3,
            clearance_mm=0.25,
            dielectric_thickness_mm=0.2,
        )
    )
    root = ET.fromstring(raw)
    lay_types = [lay.get("Type") for lay in root.findall("./Board/CopperLayers/Lay")]
    assert lay_types == ["Signal", "Plane", "Signal"]
    snapshot = build_snapshot(_load(raw))
    net_class = snapshot.board.net_classes[0]  # type: ignore[index]
    assert net_class["name"] == "Default"
    lay_props = ET.fromstring(raw).findall(
        "./Board/NetClasses/NetClass/LayProperties/LayProperty"
    )
    assert len(lay_props) == 3
    assert all(prop.get("Width") == "0.3" for prop in lay_props)
    assert all(prop.get("Clearance") == "0.25" for prop in lay_props)
    assert net_class["attributes"]["MaxUncoupledLength"] == "10"


def test_pcb_scaffold_validates_via_geometry() -> None:
    with pytest.raises(ValueError, match="via_hole"):
        PcbScaffold(via_diameter_mm=0.3, via_hole_mm=0.3)


def _service(workspace: Path, state: Path) -> DipTraceService:
    return DipTraceService(
        Settings(
            workspace=workspace,
            allowed_roots=(workspace,),
            state_dir=state,
            max_document_bytes=MAX_BYTES,
        )
    )


def test_create_document_service_round_trip(tmp_path: Path) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    created = service.create_document(
        "pcb", "project/board.dip", pcb={"width_mm": 120.0, "height_mm": 80.0}
    )
    assert created["ok"] is True
    assert created["result"]["summary"]["layers"] == 2
    assert created["result"]["backup"] is None
    written = tmp_path / "project" / "board.dip"
    assert written.exists()
    info = service.document_info("project/board.dip")
    assert info["result"]["kind"] == "pcb"
    assert info["result"]["sha256"] == created["result"]["sha256"]


def test_create_document_refuses_overwrite_without_flag(tmp_path: Path) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    service.create_document("schematic", "main.dch")
    with pytest.raises(EditError, match="overwrite"):
        service.create_document("schematic", "main.dch")
    replaced = service.create_document("schematic", "main.dch", sheets=["A", "B"], overwrite=True)
    assert replaced["result"]["backup"] is not None
    assert replaced["result"]["summary"]["sheets"] == 2


def test_create_document_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    with pytest.raises(Exception, match="outside allowed roots"):
        service.create_document("pcb", "../outside.dip")


def test_create_document_rejects_unknown_kind(tmp_path: Path) -> None:
    service = _service(tmp_path, tmp_path / ".state")
    with pytest.raises(EditError, match="Unsupported document kind"):
        service.create_document("library", "x.xml")
