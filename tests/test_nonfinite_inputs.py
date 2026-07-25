from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.domain import QuerySelector, StrictModel
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.library_adapters import get_library_model
from diptrace_mcp.operations import SetTraceWidthOperation
from diptrace_mcp.review import run_checks
from diptrace_mcp.semantic_compiler import apply_semantic_operations
from diptrace_mcp.specctra import parse_ses
from diptrace_mcp.xml_document import DipTraceDocument

FIXTURES = Path(__file__).parent / "fixtures"
NONFINITE_TEXT = ("NaN", "+Inf", "-Inf")


class _NumericEnvelope(StrictModel):
    scalar: float
    coordinates: dict[str, float]
    label: str


def _modified_document(
    fixture: str,
    old: bytes,
    new: bytes,
) -> DipTraceDocument:
    raw = (FIXTURES / fixture).read_bytes()
    assert raw.count(old) >= 1
    return DipTraceDocument.from_bytes(
        FIXTURES / fixture,
        raw.replace(old, new, 1),
    )


def _ses(
    *,
    resolution: str = "1000",
    width: str = "250",
    wire_x: str = "0",
    via_x: str = "0",
    net_name: str = "N",
) -> bytes:
    return f"""(session "result.ses"
  (base_design "board.dsn")
  (routes
    (resolution mm {resolution})
    (library_out)
    (network_out
      (net "{net_name}"
        (wire (path "Top" {width} {wire_x} 0 1 1))
        (via "V" {via_x} 0)
      )
    )
  )
)""".encode()


@pytest.mark.parametrize("value", NONFINITE_TEXT)
def test_pcb_numeric_attributes_reject_nonfinite_values_with_byte_offset(
    value: str,
) -> None:
    document = _modified_document(
        "pcb.xml",
        b'X="10" Y="10"',
        f'X="{value}" Y="10"'.encode(),
    )

    with pytest.raises(DocumentError, match=r"attribute X=.*<Component>.*byte offset") as caught:
        build_snapshot(document)

    assert caught.value.details["element"] == "Component"
    assert caught.value.details["attribute"] == "X"
    assert isinstance(caught.value.details["byte_offset"], int)
    assert caught.value.details["byte_offset"] >= 0


@pytest.mark.parametrize("value", NONFINITE_TEXT)
def test_library_numeric_attributes_reject_nonfinite_values_with_byte_offset(
    value: str,
) -> None:
    document = _modified_document(
        "pattern_library.xml",
        b'Width="0.9"',
        f'Width="{value}"'.encode(),
    )

    with pytest.raises(
        DocumentError,
        match=r"attribute Width=.*<MainStack>.*byte offset",
    ) as caught:
        get_library_model(document)

    assert caught.value.details["element"] == "MainStack"
    assert caught.value.details["attribute"] == "Width"
    assert isinstance(caught.value.details["byte_offset"], int)
    assert caught.value.details["byte_offset"] >= 0


@pytest.mark.parametrize("value", NONFINITE_TEXT)
@pytest.mark.parametrize(
    ("old", "replacement", "element", "attribute"),
    [
        (
            b'Hole="1.0"',
            'Hole="{value}"',
            "PadStyle",
            "Hole",
        ),
        (
            b'TopMask="Common"',
            'CustomSwell="{value}" TopMask="Common"',
            "MaskPaste",
            "CustomSwell",
        ),
        (
            b'Layer="Top Silk" LineWidth="0.15"',
            'Layer="Top Courtyard" LineWidth="{value}"',
            "Shape",
            "LineWidth",
        ),
    ],
)
def test_library_direct_numeric_sites_share_the_finite_guard(
    value: str,
    old: bytes,
    replacement: str,
    element: str,
    attribute: str,
) -> None:
    document = _modified_document(
        "pattern_library.xml",
        old,
        replacement.format(value=value).encode(),
    )

    with pytest.raises(DocumentError) as caught:
        get_library_model(document)

    assert caught.value.details["element"] == element
    assert caught.value.details["attribute"] == attribute
    assert isinstance(caught.value.details["byte_offset"], int)


@pytest.mark.parametrize("value", NONFINITE_TEXT)
def test_review_rules_cannot_use_nonfinite_clearance_to_bypass_comparisons(
    value: str,
) -> None:
    document = _modified_document(
        "pcb.xml",
        b'TraceToTrace="0.2"',
        f'TraceToTrace="{value}"'.encode(),
    )
    snapshot = build_snapshot(document)

    with pytest.raises(DocumentError) as caught:
        run_checks(snapshot, categories={"clearance"})

    assert caught.value.details["element"] == "LayClearance"
    assert caught.value.details["attribute"] == "TraceToTrace"
    assert isinstance(caught.value.details["byte_offset"], int)


@pytest.mark.parametrize("value", NONFINITE_TEXT)
def test_routing_rules_cannot_use_nonfinite_minimum_to_bypass_comparisons(
    value: str,
) -> None:
    document = _modified_document(
        "pcb.xml",
        b'MinTrace="0.15"',
        f'MinTrace="{value}"'.encode(),
    )
    snapshot = build_snapshot(document)
    assert snapshot.board is not None
    trace = snapshot.board.traces[0]

    with pytest.raises(DocumentError) as caught:
        apply_semantic_operations(
            document,
            [
                SetTraceWidthOperation(
                    selector=QuerySelector(ids=[trace.stable_id]),
                    width=0.25,
                )
            ],
        )

    assert caught.value.details["element"] == "LaySize"
    assert caught.value.details["attribute"] == "MinTrace"
    assert isinstance(caught.value.details["byte_offset"], int)


@pytest.mark.parametrize("value", NONFINITE_TEXT)
@pytest.mark.parametrize(
    ("field", "context"),
    [
        ("resolution", "resolution"),
        ("width", "wire width"),
        ("wire_x", "wire for net N"),
        ("via_x", "via x"),
    ],
)
def test_ses_numeric_tokens_reject_nonfinite_values_with_character_offset(
    field: str,
    context: str,
    value: str,
) -> None:
    values = {field: value}

    with pytest.raises(
        DocumentError,
        match=rf"{context}.*character offset",
    ) as caught:
        parse_ses(_ses(**values))

    assert caught.value.details["context"] == context
    assert isinstance(caught.value.details["character_offset"], int)
    assert caught.value.details["character_offset"] >= 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_strict_model_rejects_nonfinite_floats_on_create_and_assignment(
    value: float,
) -> None:
    with pytest.raises(ValidationError):
        _NumericEnvelope(
            scalar=value,
            coordinates={"x": 0.0},
            label="finite",
        )
    with pytest.raises(ValidationError):
        _NumericEnvelope(
            scalar=0.0,
            coordinates={"x": value},
            label="finite",
        )

    model = _NumericEnvelope(
        scalar=0.0,
        coordinates={"x": 0.0},
        label="finite",
    )
    with pytest.raises(ValidationError):
        model.scalar = value


def test_nan_text_remains_valid_in_non_numeric_xml_and_ses_fields() -> None:
    pcb = _modified_document(
        "pcb.xml",
        b"<Value>10k</Value>",
        b"<Value>NaN</Value>",
    )
    library = _modified_document(
        "pattern_library.xml",
        b"<Name>R_0603</Name>",
        b"<Name>NaN</Name>",
    )

    pcb_snapshot = build_snapshot(pcb)
    library_model = get_library_model(library)
    session = parse_ses(_ses(net_name="NaN"))
    envelope = _NumericEnvelope(
        scalar=0.0,
        coordinates={"x": 0.0},
        label="NaN",
    )

    assert any(component.value == "NaN" for component in pcb_snapshot.board.components)
    assert library_model.patterns[0].name == "NaN"
    assert session.routes[0].name == "NaN"
    assert envelope.label == "NaN"


def test_client_parsers_translate_pydantic_errors_to_document_errors() -> None:
    invalid_library = _modified_document(
        "pattern_library.xml",
        b'Width="0.9"',
        b'Width="-1"',
    )

    with pytest.raises(DocumentError, match="Invalid normalized document data"):
        get_library_model(invalid_library)
    with pytest.raises(DocumentError, match="Invalid normalized document data"):
        parse_ses(_ses(width="-1"))
