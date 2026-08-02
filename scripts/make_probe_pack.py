#!/usr/bin/env python3
"""Generate the operator probe pack from structured open questions.

The generated document is an execution aid, not evidence.  It copies the
maintained unknown, dependency, experiment, and operator fields without
deriving an answer or granting a provenance level.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "OPEN_QUESTIONS.md"
DEFAULT_OUTPUT = ROOT / "docs" / "PROBE_PACK.md"

_EXPECTED_H1 = "# Open Questions — DipTrace XML Format"
_QUESTION_HEADING = re.compile(r"^## Q(?P<number>[1-9][0-9]*): (?P<title>.+)$", re.MULTILINE)
_ANY_LEVEL_TWO = re.compile(r"^## .+$", re.MULTILINE)
_FIELD_MARKER = re.compile(
    r"^\*\*(?P<label>"
    r"Question|Why the code depends on it|What is documented|Experiment|Who can perform"
    r"):\*\*[ \t]*",
    re.MULTILINE,
)
_ANY_FIELD_MARKER = re.compile(r"^\*\*(?P<label>[^*\n]+):\*\*[ \t]*", re.MULTILINE)
_CODE_SYMBOL = re.compile(
    r"`src/diptrace_mcp/[a-z0-9_]+\.py::[A-Za-z_][A-Za-z0-9_.]*`"
)
_RECIPE_LINK = re.compile(r"\((?P<path>evidence_capture/[^)\s]+\.recipe\.json)\)")
_VALID_FIELD_ORDERS = {
    (
        "Question",
        "Why the code depends on it",
        "Experiment",
        "Who can perform",
    ),
    (
        "Question",
        "Why the code depends on it",
        "What is documented",
        "Experiment",
        "Who can perform",
    ),
}


class ProbePackError(ValueError):
    """The maintained source does not satisfy the probe-pack contract."""


@dataclass(frozen=True)
class OpenQuestion:
    """One strictly parsed question from ``OPEN_QUESTIONS.md``."""

    number: int
    title: str
    question: str
    dependency: str
    experiment: str
    operator: str
    documented: str | None = None
    recipe_path: str | None = None

    @property
    def source_anchor(self) -> str:
        return github_heading_slug(f"Q{self.number}: {self.title}")


def github_heading_slug(value: str) -> str:
    """Return the GitHub-style slug needed by the generated source links."""

    without_code_ticks = value.replace("`", "")
    kept = "".join(
        character
        for character in without_code_ticks.casefold()
        if character.isalnum() or character in {" ", "-", "_"}
    )
    return re.sub(r"-+", "-", re.sub(r"\s+", "-", kept)).strip("-")


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProbePackError(f"cannot read UTF-8 source {path}: {exc}") from exc


def _strip_question_separator(raw_body: str, *, number: int, final: bool) -> str:
    body = raw_body.rstrip()
    has_separator = body.endswith("\n---")
    if final:
        if has_separator:
            raise ProbePackError(f"Q{number}: unexpected trailing question separator")
        return body.strip()
    if not has_separator:
        raise ProbePackError(f"Q{number}: missing '---' separator before the next question")
    body = body[: -len("\n---")].rstrip()
    if "\n---\n" in body:
        raise ProbePackError(f"Q{number}: ambiguous horizontal rule inside question block")
    return body.strip()


def _parse_fields(body: str, *, number: int) -> dict[str, str]:
    unknown_markers = [
        match.group("label")
        for match in _ANY_FIELD_MARKER.finditer(body)
        if match.group("label")
        not in {
            "Question",
            "Why the code depends on it",
            "What is documented",
            "Experiment",
            "Who can perform",
        }
    ]
    if unknown_markers:
        unknown_labels_text = ", ".join(repr(label) for label in unknown_markers)
        raise ProbePackError(
            f"Q{number}: unknown structured field(s): {unknown_labels_text}"
        )

    markers = list(_FIELD_MARKER.finditer(body))
    field_labels = tuple(match.group("label") for match in markers)
    if field_labels not in _VALID_FIELD_ORDERS:
        expected = (
            "Question, Why the code depends on it, optional What is documented, "
            "Experiment, Who can perform"
        )
        observed = ", ".join(field_labels) if field_labels else "none"
        raise ProbePackError(
            f"Q{number}: fields are missing, duplicated, or out of order; "
            f"expected {expected}; observed {observed}"
        )
    if not markers:  # Defensive for type narrowing if the valid orders change.
        raise ProbePackError(f"Q{number}: no structured fields")

    prefix = body[: markers[0].start()].strip()
    if prefix:
        raise ProbePackError(f"Q{number}: text appears before the Question field")

    fields: dict[str, str] = {}
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
        value = body[marker.end() : end].strip()
        label = marker.group("label")
        if not value:
            raise ProbePackError(f"Q{number}: {label} field is empty")
        fields[label] = value

    if _CODE_SYMBOL.search(fields["Why the code depends on it"]) is None:
        raise ProbePackError(
            f"Q{number}: Why the code depends on it lacks a stable src/...py::symbol reference"
        )
    return fields


def parse_open_questions(source: str) -> list[OpenQuestion]:
    """Parse all questions, refusing ambiguous or incomplete source structure."""

    if source.startswith("\ufeff"):
        raise ProbePackError("source must be UTF-8 without a BOM")
    if "\x00" in source:
        raise ProbePackError("source contains a NUL byte")
    lines = source.splitlines()
    if not lines or lines[0] != _EXPECTED_H1:
        raise ProbePackError(f"source must begin with {_EXPECTED_H1!r}")

    headings = list(_QUESTION_HEADING.finditer(source))
    if not headings:
        raise ProbePackError("source contains no structured Q<number> headings")
    all_level_two = list(_ANY_LEVEL_TWO.finditer(source))
    if [match.group(0) for match in all_level_two] != [
        match.group(0) for match in headings
    ]:
        raise ProbePackError("source contains an unrecognized level-two heading")

    preamble = source[: headings[0].start()].rstrip()
    if not preamble.endswith("\n---"):
        raise ProbePackError("source preamble must end with a '---' separator")

    numbers = [int(match.group("number")) for match in headings]
    expected_numbers = list(range(1, len(headings) + 1))
    if numbers != expected_numbers:
        raise ProbePackError(
            f"question numbers must be contiguous from Q1; observed {numbers}"
        )

    questions: list[OpenQuestion] = []
    for index, heading in enumerate(headings):
        number = int(heading.group("number"))
        title = heading.group("title").strip()
        if not title or not title.endswith("?"):
            raise ProbePackError(f"Q{number}: title must be a non-empty question")
        next_start = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        raw_body = source[heading.end() : next_start]
        body = _strip_question_separator(
            raw_body,
            number=number,
            final=index + 1 == len(headings),
        )
        fields = _parse_fields(body, number=number)
        recipe_paths = sorted(set(_RECIPE_LINK.findall(body)))
        if len(recipe_paths) > 1:
            raise ProbePackError(
                f"Q{number}: multiple concrete capture recipes are ambiguous: {recipe_paths}"
            )
        questions.append(
            OpenQuestion(
                number=number,
                title=title,
                question=fields["Question"],
                dependency=fields["Why the code depends on it"],
                documented=fields.get("What is documented"),
                experiment=fields["Experiment"],
                operator=fields["Who can perform"],
                recipe_path=recipe_paths[0] if recipe_paths else None,
            )
        )
    return questions


def _capture_handoff(question: OpenQuestion) -> str:
    if question.recipe_path is not None:
        recipe = (
            f"Use the committed [Q{question.number} concrete recipe]"
            f"({question.recipe_path})."
        )
    else:
        recipe = (
            "Create a question-specific `diptrace-capture-recipe-v1` by copying the "
            "[strict recipe template]"
            "(evidence_capture/pcb-format-question.recipe.template.json). Replace its "
            "generic feature and checklist text only with observations required by the "
            "experiment above; do not encode an expected result."
        )
    return (
        f"{recipe} Then follow the [interactive capture sequence]"
        "(EVIDENCE_CAPTURE.md#interactive-run) with distinct `source`, `open_save`, and "
        "`reexport` XML files.\n\n"
        "The collector applies only when this probe yields all three valid XML roles. "
        "Never substitute a screenshot, log, malformed file, or repeated path for a missing "
        "role. If the experiment cannot produce the triple, stop the capture and keep the "
        "question open; extending the evidence schema is a separate reviewed code change."
    )


def render_probe_pack(questions: Sequence[OpenQuestion]) -> str:
    """Render a deterministic, answer-free operator document."""

    parts = [
        "<!-- Generated by scripts/make_probe_pack.py from docs/OPEN_QUESTIONS.md. "
        "Do not edit by hand. -->",
        "",
        "# DipTrace Operator Probe Pack",
        "",
        "This generated pack turns each maintained open question into an operator-facing "
        "procedure. It reproduces project-authored question and experiment text; it does "
        "not answer the "
        "question, authenticate an export, grant provenance, or promote anything into "
        "`tests/fixtures/acceptance/`.",
        "",
        f"It currently contains **{len(questions)} open probes**. Edit "
        "[OPEN_QUESTIONS.md](OPEN_QUESTIONS.md), then regenerate this file.",
        "",
        "## Common capture workflow",
        "",
        "Before opening DipTrace:",
        "",
        "1. Read the complete question and perform the preparation stated in its operator "
        "recipe on a disposable design copy.",
        "2. Put the concrete recipe and every input/export under one private allowed root. "
        "Do not use the repository or acceptance fixture tree as that root.",
        "3. Run [`scripts/capture_diptrace_evidence.py`]"
        "(../scripts/capture_diptrace_evidence.py) in the order documented by "
        "[Operator-assisted DipTrace evidence capture](EVIDENCE_CAPTURE.md): `init`, "
        "`record source`, `record open_save`, `record reexport`, every required `check`, "
        "then `finalize`.",
        "4. Treat the resulting manifest only as an untrusted review candidate. Preserve "
        "literal bytes and report discrepancies; never repair an export or infer the "
        "unknown answer.",
        "",
        "The exact CLI flags, attestation templates, containment rules, resume behavior, "
        "and review boundary are maintained in "
        "[EVIDENCE_CAPTURE.md](EVIDENCE_CAPTURE.md#interactive-run).",
    ]
    for question in questions:
        parts.extend(
            [
                "",
                "---",
                "",
                f"## Q{question.number} — {question.title}",
                "",
                f"[Maintained source question]"
                f"(OPEN_QUESTIONS.md#{question.source_anchor})",
                "",
                "### Unknown to test",
                "",
                question.question,
                "",
                "### Why the implementation depends on it",
                "",
                question.dependency,
            ]
        )
        if question.documented is not None:
            parts.extend(
                [
                    "",
                    "### Documented boundary",
                    "",
                    question.documented,
                ]
            )
        parts.extend(
            [
                "",
                "### Operator recipe",
                "",
                question.experiment,
                "",
                f"**Operator required:** {question.operator}",
                "",
                "**Capture handoff:**",
                "",
                _capture_handoff(question),
            ]
        )
    return "\n".join(parts).rstrip() + "\n"


def generate(source_path: Path) -> str:
    """Load, validate, and render one source document."""

    return render_probe_pack(parse_open_questions(_read_source(source_path)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate docs/PROBE_PACK.md from structured open questions."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if --out is missing or differs; never write",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_path: Path = args.source
    output_path: Path = args.out
    try:
        if source_path.resolve() == output_path.resolve():
            raise ProbePackError("source and output paths must differ")
        rendered = generate(source_path)
    except ProbePackError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    expected = rendered.encode("utf-8")
    if args.check:
        try:
            actual = output_path.read_bytes()
        except OSError as exc:
            print(f"FAIL: cannot read generated output {output_path}: {exc}", file=sys.stderr)
            return 1
        if actual != expected:
            print(
                f"FAIL: {output_path} differs from generated probe pack",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {output_path} matches structured open questions")
        return 0

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(expected)
    except OSError as exc:
        print(f"FAIL: cannot write generated output {output_path}: {exc}", file=sys.stderr)
        return 2
    print(f"Generated {output_path} from {source_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
