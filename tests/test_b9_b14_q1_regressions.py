import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from diptrace_mcp.capabilities import get_capabilities
from diptrace_mcp.errors import AmbiguousSelectorError, EditError, ObjectNotFoundError
from diptrace_mcp.semantic_compiler import _schematic_net_element
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"


def test_net_references_require_explicit_ids_and_reject_duplicates():
    document = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    nets = document.container.find("./Nets")
    nets.clear()
    first = ET.SubElement(nets, "Net", {"Id": "1"})
    ET.SubElement(first, "Name").text = "VCC"
    assert _schematic_net_element(document, "1") is None
    assert _schematic_net_element(document, "xml-id:1") is first
    with pytest.raises(ObjectNotFoundError):
        _schematic_net_element(document, "xml-id:2")
    with pytest.raises(EditError):
        _schematic_net_element(document, "xml-id:")
    second = ET.SubElement(nets, "Net", {"Id": "2"})
    ET.SubElement(second, "Name").text = "1"
    assert _schematic_net_element(document, "1") is second
    second.find("Name").text = "vcc"
    with pytest.raises(AmbiguousSelectorError):
        _schematic_net_element(document, "VCC")
    second.set("Id", "1")
    with pytest.raises(AmbiguousSelectorError):
        _schematic_net_element(document, "xml-id:1")


def test_numeric_name_creation_and_explicit_id_callers():
    from diptrace_mcp.operations import (
        AddNetLabelOperation,
        AddWireOperation,
        ConnectPinsOperation,
        DeleteNetLabelsOperation,
    )
    from diptrace_mcp.semantic_compiler import apply_semantic_operations

    document = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    original = document.container.find("./Nets/Net")
    xml_id = original.get("Id")
    original_name = original.findtext("Name")
    result = apply_semantic_operations(
        document,
        [
            ConnectPinsOperation(
                net=xml_id,
                pins=[{"refdes": "R1", "pin": 0}],
                allow_reconnect=True,
            )
        ],
    )
    assert _schematic_net_element(result.document, xml_id).get("Id") != xml_id
    assert (
        _schematic_net_element(result.document, f"xml-id:{xml_id}").findtext("Name")
        == original_name
    )

    # All three existing-net callers refuse an implicit numeric-id fallback.
    operations = [
        AddNetLabelOperation(net=xml_id, x=0, y=0),
        AddWireOperation(
            net=xml_id,
            points=[{"x": 0, "y": 0}, {"x": 2, "y": 0}],
            start={"type": "Free"},
            end={"type": "Free"},
        ),
        DeleteNetLabelsOperation(net=xml_id),
    ]
    for operation in operations:
        with pytest.raises(ObjectNotFoundError):
            apply_semantic_operations(document, [operation])
    all_operations = operations + [
        ConnectPinsOperation(net=xml_id, pins=[{"refdes": "R1", "pin": 0}])
    ]
    for operation in all_operations:
        for reference, error in (("xml-id:999999", ObjectNotFoundError), ("xml-id:", EditError)):
            with pytest.raises(error):
                apply_semantic_operations(
                    document, [operation.model_copy(update={"net": reference})]
                )
    label = apply_semantic_operations(
        document, [AddNetLabelOperation(net=f"xml-id:{xml_id}", x=0, y=0)]
    )
    assert label.document.container.findtext("./Shapes/Shape/TextLines/TextLine") == original_name
    wire = operations[1].model_copy(update={"net": f"xml-id:{xml_id}"})
    wired = apply_semantic_operations(label.document, [wire])
    assert (
        _schematic_net_element(wired.document, f"xml-id:{xml_id}").find("./Wires/Wire") is not None
    )
    deleted = apply_semantic_operations(
        wired.document, [DeleteNetLabelsOperation(net=f"xml-id:{xml_id}")]
    )
    assert not deleted.document.container.findall("./Shapes/Shape[@Type='Text']")


def test_reserved_prefix_name_escape():
    from diptrace_mcp.operations import ConnectPinsOperation
    from diptrace_mcp.semantic_compiler import apply_semantic_operations

    document = DipTraceDocument.load(FIXTURES / "schematic.xml", 10_000_000)
    result = apply_semantic_operations(
        document,
        [
            ConnectPinsOperation(
                net="name:xml-id:900",
                pins=[{"refdes": "R1", "pin": 0}],
                allow_reconnect=True,
            )
        ],
    )
    assert (
        _schematic_net_element(result.document, "name:xml-id:900").findtext("Name") == "xml-id:900"
    )


def test_registration_mapping_extension_and_invalid_keys():
    from diptrace_mcp.server_inputs import DipTraceFastMCP
    from diptrace_mcp.tool_capabilities import TOOL_CAPABILITIES, tool_capability_mapping

    server = DipTraceFastMCP(name="mapping-test", version="0")
    try:

        @server.tool(capability_keys=["read_capabilities.document_info"])
        def future_tool():
            return {}

        assert tool_capability_mapping(server.tool_bodies)["future_tool"] == [
            "read_capabilities.document_info"
        ]
        with pytest.raises(ValueError, match="Unknown capability"):
            server.tool(capability_keys=["read_capabilities.fake_flag"])(lambda: {})
        with pytest.raises(ValueError, match="No capability mapping"):
            tool_capability_mapping(["unmapped_tool"])
    finally:
        TOOL_CAPABILITIES.pop("future_tool", None)


def test_public_tool_mapping_and_angle_evidence_scopes(tmp_path):
    from diptrace_mcp.config import Settings
    from diptrace_mcp.server_runtime import create_server

    server = create_server(
        Settings(workspace=tmp_path, allowed_roots=(tmp_path,), state_dir=tmp_path / "state")
    )
    report = get_capabilities().model_dump()
    mapping = report["tool_capabilities"]
    assert set(mapping) == set(server.tool_bodies)
    for keys in mapping.values():
        assert keys
        for key in keys:
            group, name = key.split(".", 1)
            assert name in report[group]
    assert all(
        name in mapping
        for name in (
            "pipeline_source_component",
            "pipeline_nativeize_document",
            "pipeline_render_board_preview",
        )
    )
    angle = report["trust_model"]["component_angle_evidence"]
    assert angle["manual_campaign_status"] == "PASS"
    assert angle["package_publicly_validated"] is False
    assert angle["grants_high_trust"] is False
    assert report["evidence_warnings"]
