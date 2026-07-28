from __future__ import annotations

from pathlib import Path

import pytest

from scripts.make_probe_pack import (
    ProbePackError,
    github_heading_slug,
    main,
    parse_open_questions,
    render_probe_pack,
)

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "docs" / "OPEN_QUESTIONS.md"
GENERATED = ROOT / "docs" / "PROBE_PACK.md"


def _question(number: int, *, fields: str | None = None) -> str:
    body = fields or f"""\
**Question:** What remains unknown for probe {number}?

**Why the code depends on it:** `src/diptrace_mcp/example.py::symbol_{number}` depends on it.

**Experiment:** Perform one literal observation and retain the result.

**Who can perform:** Human operator.
"""
    return f"## Q{number}: What remains unknown for probe {number}?\n\n{body.rstrip()}\n"


def _source(*blocks: str) -> str:
    return (
        "# Open Questions — DipTrace XML Format\n\n"
        "Maintained unknowns only.\n\n"
        "---\n\n"
        + "\n---\n\n".join(block.rstrip() for block in blocks)
        + "\n"
    )


def test_committed_probe_pack_is_fresh_and_complete() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    questions = parse_open_questions(source)

    assert [question.number for question in questions] == list(range(1, 19))
    assert render_probe_pack(questions) == GENERATED.read_text(encoding="utf-8")
    generated = GENERATED.read_text(encoding="utf-8")
    assert generated.count("### Operator recipe") == len(questions)
    assert generated.count("**Capture handoff:**") == len(questions)
    assert "grant provenance" in generated
    assert "`tests/fixtures/acceptance/`" in generated

    for question in questions:
        assert question.question in generated
        assert question.dependency in generated
        assert question.experiment in generated
        assert question.operator in generated


def test_pack_uses_concrete_recipe_only_when_source_links_one() -> None:
    questions = parse_open_questions(SOURCE.read_text(encoding="utf-8"))
    by_number = {question.number: question for question in questions}

    assert (
        by_number[1].recipe_path
        == "evidence_capture/q1-component-angle.recipe.json"
    )
    assert by_number[2].recipe_path is None

    rendered = render_probe_pack(questions)
    q1, remainder = rendered.split("## Q2", maxsplit=1)
    assert "Use the committed [Q1 concrete recipe]" in q1
    assert "strict recipe template" in remainder


def test_source_links_use_stable_github_heading_slugs() -> None:
    assert (
        github_heading_slug("Q1: Is `Component/@Angle` in radians or degrees?")
        == "q1-is-componentangle-in-radians-or-degrees"
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            _source(
                _question(1).replace(
                    "**Experiment:** Perform one literal observation and retain the result.\n\n",
                    "",
                )
            ),
            "missing, duplicated, or out of order",
        ),
        (
            _source(_question(1), _question(3)),
            "contiguous from Q1",
        ),
        (
            _source(
                _question(1).replace(
                    "**Who can perform:**",
                    "**Result:** Unknown.\n\n**Who can perform:**",
                )
            ),
            "unknown structured field",
        ),
        (
            _source(
                _question(1).replace(
                    "`src/diptrace_mcp/example.py::symbol_1`",
                    "`example.symbol_1`",
                )
            ),
            "stable src/...py::symbol reference",
        ),
    ],
)
def test_parser_fails_closed_on_malformed_structure(
    source: str,
    message: str,
) -> None:
    with pytest.raises(ProbePackError, match=message):
        parse_open_questions(source)


def test_parser_refuses_missing_inter_question_separator() -> None:
    malformed = _source(_question(1), _question(2)).replace(
        "\n---\n\n## Q2",
        "\n\n## Q2",
    )

    with pytest.raises(ProbePackError, match="missing '---' separator"):
        parse_open_questions(malformed)


def test_check_is_deterministic_and_never_repairs_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "PROBE_PACK.md"

    assert main(["--source", str(SOURCE), "--out", str(output), "--check"]) == 1
    assert not output.exists()
    assert main(["--source", str(SOURCE), "--out", str(output)]) == 0
    expected = output.read_bytes()
    assert main(["--source", str(SOURCE), "--out", str(output), "--check"]) == 0

    output.write_text("stale\n", encoding="utf-8")
    assert main(["--source", str(SOURCE), "--out", str(output), "--check"]) == 1
    assert output.read_bytes() == b"stale\n"

    assert main(["--source", str(SOURCE), "--out", str(output)]) == 0
    assert output.read_bytes() == expected


def test_source_and_output_must_differ(tmp_path: Path) -> None:
    source = tmp_path / "questions.md"
    source.write_text(_source(_question(1)), encoding="utf-8")
    before = source.read_bytes()

    assert main(["--source", str(source), "--out", str(source)]) == 2
    assert source.read_bytes() == before
