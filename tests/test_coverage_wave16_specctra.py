from __future__ import annotations

from types import SimpleNamespace

import pytest

from diptrace_mcp import specctra
from diptrace_mcp.domain import ObjectRecord, ViaStyleModel
from diptrace_mcp.errors import CapabilityUnavailableError, DocumentError


def test_dsn_quoted_token_and_limitation_matrix() -> None:
    for value in ("bad\nname", 'bad"name', "bad\\name", "плата"):
        assert specctra._quoted_token_limitation(value, "name") is not None
        with pytest.raises(CapabilityUnavailableError):
            specctra._quote(value)
    assert specctra._quote("board") == '"board"'

    component = ObjectRecord(
        stable_id="component_0000000000000000",
        kind="component",
        attributes={"pattern_style": "missing"},
    )
    net = ObjectRecord(
        stable_id="net_0000000000000000",
        kind="net",
        name="N",
        relationships={"endpoints": ["missing"]},
    )
    board = SimpleNamespace(
        outline=None,
        layers=[],
        cutouts=[object()],
        keepouts=[object()],
        copper_pours=[object()],
        patterns=[SimpleNamespace(style="P", pads=[], name="P", stable_id="pattern")],
        pad_styles=[],
        components=[component],
        nets=[net],
        traces=[],
        via_styles=[ViaStyleModel(id="v")],
    )
    snapshot = SimpleNamespace(
        board=board,
        objects={},
        info=SimpleNamespace(document_id="board"),
    )
    reasons = specctra.dsn_export_limitations(snapshot)
    assert any("outline" in reason for reason in reasons)
    assert any("cutouts" in reason for reason in reasons)
    assert any("keepouts" in reason for reason in reasons)
    assert any("Copper pours" in reason for reason in reasons)
    assert any("unresolved pad" in reason for reason in reasons)
    assert specctra.dsn_export_limitations(SimpleNamespace(board=None))


def test_sexpr_parser_comments_limits_and_invalid_tokens() -> None:
    assert specctra._SExprParser("; comment\n# second\n(value)", max_tokens=10, max_depth=3).parse()
    assert specctra._SExprParser("# trailing", max_tokens=10, max_depth=3).parse() == []
    cases = (
        (")", 10, 3, "closing parenthesis"),
        ("", 10, 3, "Unexpected end"),
        ("(x)", 0, 3, "token limit"),
        ("((x))", 10, 0, "nesting limit"),
        ('"open', 10, 3, "Unclosed quoted"),
        ('"bad\\escape"', 10, 3, "Backslash"),
        ('"bad\x01value"', 10, 3, "Control characters"),
        ("(", 10, 3, "Unclosed Specctra"),
    )
    for text, max_tokens, max_depth, message in cases:
        parser = specctra._SExprParser(text, max_tokens=max_tokens, max_depth=max_depth)
        with pytest.raises(DocumentError, match=message):
            parser.parse() if text else parser._value(0)
    with pytest.raises(DocumentError, match="Expected a number"):
        specctra._number([], "test")
    with pytest.raises(DocumentError, match="Invalid number"):
        specctra._number(specctra._Token("bad", 7), "test")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"x" * 4, "exceeds"),
        (b"\xff", "UTF-8"),
        (b"", "exactly one"),
        (b"(pcb x)", "not a session"),
        (b"(session x)", "no routes"),
        (b"(session x (routes))", "resolution"),
        (b"(session x (routes (resolution cm 1)))", "Unsupported"),
        (b"(session x (routes (resolution mm 1)))", "network_out"),
        (
            b"(session x (routes (resolution mm 1) (network_out (net))))",
            "no name",
        ),
        (
            b"(session x (routes (resolution mm 1) (network_out (net N (wire (path Top 1 0 0))))))",
            "invalid path",
        ),
        (
            b"(session x (routes (resolution mm 1) (network_out (net N (via V 1)))))",
            "incomplete",
        ),
    ],
)
def test_parse_ses_error_matrix(payload: bytes, message: str) -> None:
    limit = 3 if payload == b"x" * 4 else 1_000_000
    with pytest.raises(DocumentError, match=message):
        specctra.parse_ses(payload, max_bytes=limit)


def test_parse_ses_ignores_wire_without_path() -> None:
    session = specctra.parse_ses(
        b"(session x (routes (resolution mm 1) (network_out (net N (wire)))))"
    )
    assert session.routes[0].wires == []
