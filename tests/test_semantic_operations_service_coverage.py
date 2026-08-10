from __future__ import annotations

from typing import Any, cast

from diptrace_mcp.operations import SemanticOperation
from diptrace_mcp.services.semantic_operations import SemanticOperationsService


def test_semantic_operation_wrappers_validate_and_delegate() -> None:
    single: list[SemanticOperation] = []
    batches: list[list[SemanticOperation]] = []

    def semantic_write(
        operation: SemanticOperation,
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        single.append(operation)
        return {"ok": True, "kind": operation.kind}

    def semantic_operations(
        operations: list[SemanticOperation],
        path: str | None,
        dry_run: bool,
        expected_sha256: str | None,
        txid: str | None,
    ) -> dict[str, Any]:
        batches.append(list(operations))
        return {"ok": True, "count": len(operations)}

    service = SemanticOperationsService(
        cast(Any, None),
        cast(Any, None),
        semantic_write,
        semantic_operations,
    )

    service.move_components({}, dx=1.0)
    service.set_component_value({}, "47k")
    service.rotate_components({}, 90.0)
    service.set_component_side({}, "Bottom")
    service.set_component_lock({}, True)
    service.set_component_properties({}, name="Resistor", fields={"MPN": "ABC"})
    service.set_component_pattern({}, "PatType0")
    service.group_components({}, group_id=7)
    service.ungroup_components({})
    service.move_board_texts({}, dx=1.0)
    service.rotate_board_texts({}, 90.0)
    service.set_text_visibility({}, "Show")
    service.set_text_style({}, font_size=10, horizontal_align="Center")
    service.set_pin_no_connect({}, True)
    service.rename_net({}, "RENAMED")
    service.add_sheet("Power")
    service.place_part("CompType0", "U1", 10.0, 20.0, pin_count=2)
    service.connect_pins("SIGNAL", [{"refdes": "U1", "pin": 0}])
    service.disconnect_pins({})
    service.add_wire(
        "SIGNAL",
        [{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
        {"type": "Free"},
        {"type": "Free"},
    )
    service.delete_wire({})
    service.add_net_label("SIGNAL", 5.0, 5.0)
    service.set_panelization({})
    service.clear_panelization()
    service.update_net_class_rules("Default", width=0.25, clearance=0.2)
    service.assign_nets_to_class({}, "Default")
    service.move_testpoints({}, dx=1.0, grid_snap=0.5)
    service.remove_testpoints({})
    service.add_trace(
        net="SIGNAL",
        start_object_id="pad_a",
        end_object_id="pad_b",
        points=[{"x": 0.0, "y": 0.0}, {"x": 10.0, "y": 0.0}],
        layer="Top",
        width=0.25,
        clearance=0.2,
    )
    service.replace_trace(
        "trace_0123456789abcdef",
        [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 0.0}],
        layer="Top",
        width=0.3,
    )
    service.delete_trace({}, allow_connectivity_regression=True)
    service.set_trace_width({}, 0.3, segment_indices=[2, 1, 1])
    service.add_via(
        "trace_0123456789abcdef",
        1.0,
        2.0,
        "Default",
        layer_before="Top",
        layer_after="Bottom",
    )
    service.move_via({}, dx=1.0)
    service.delete_via({})
    service.set_via_style({}, "Default")
    service.add_testpoints(
        [
            {
                "net": "SIGNAL",
                "x": 1.0,
                "y": 2.0,
                "pad_diameter": 1.0,
                "refdes": "TP1",
            }
        ]
    )

    expected_single_kinds = {
        "move_components",
        "set_component_value",
        "rotate_components",
        "set_component_side",
        "set_component_lock",
        "set_component_properties",
        "set_component_pattern",
        "group_components",
        "ungroup_components",
        "move_board_texts",
        "rotate_board_texts",
        "set_text_visibility",
        "set_text_style",
        "set_pin_no_connect",
        "rename_net",
        "add_sheet",
        "place_part",
        "connect_pins",
        "disconnect_pins",
        "add_wire",
        "delete_wire",
        "add_net_label",
        "set_panelization",
        "clear_panelization",
        "update_net_class_rules",
        "assign_nets_to_class",
        "move_testpoints",
        "remove_testpoints",
        "add_trace",
        "replace_trace",
        "delete_trace",
        "set_trace_width",
        "add_via",
        "move_via",
        "delete_via",
        "set_via_style",
    }
    assert {operation.kind for operation in single} == expected_single_kinds
    assert len(batches) == 1
    assert [operation.kind for operation in batches[0]] == ["add_testpoint"]
