from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).parents[1]
_MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
_REFERENCE_LINK = re.compile(r"^\s*\[[^\]\n]+\]:\s*(\S+)", re.MULTILINE)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_ROOT_PATH_PREFIXES = (
    ".github/",
    "benchmarks/",
    "docs/",
    "examples/",
    "plugin/",
    "reference/",
    "scripts/",
    "skills/",
    "src/",
    "tests/",
)


@dataclass(frozen=True)
class MissingTarget:
    source: Path
    line: int
    target: str
    resolved: Path


def _documentation_files(root: Path) -> list[Path]:
    files = list(root.glob("*.md"))
    for directory in ("docs", "reference"):
        files.extend((root / directory).rglob("*.md"))
    return sorted(set(files))


def _non_fenced_lines(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    fence: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is None:
            result.append((line_number, line))
    return result


def _markdown_target(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0] if value else ""


def _inline_repository_path(raw: str) -> str | None:
    value = raw.strip().strip(".,;")
    if not value or any(character.isspace() for character in value):
        return None
    if value.startswith(("./", "../", *_ROOT_PATH_PREFIXES)):
        return value
    return None


def _candidate_target(raw: str) -> str | None:
    value = unquote(raw.strip())
    if not value or value.startswith(("#", "/", "~", "$", "%")):
        return None
    if _WINDOWS_PATH.match(value) or _SCHEME.match(value):
        return None
    value = value.split("#", 1)[0].split("?", 1)[0].split("::", 1)[0]
    value = _LINE_SUFFIX.sub("", value)
    if not value or any(character in value for character in "*{}[]"):
        return None
    return value


def _resolve_target(root: Path, source: Path, raw: str, *, inline: bool) -> Path | None:
    candidate = _candidate_target(raw)
    if candidate is None:
        return None
    if inline and candidate.startswith(_ROOT_PATH_PREFIXES):
        resolved = (root / candidate).resolve()
    else:
        resolved = (source.parent / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _missing_targets(root: Path, files: list[Path]) -> list[MissingTarget]:
    missing: list[MissingTarget] = []
    for source in files:
        for line_number, line in _non_fenced_lines(source.read_text(encoding="utf-8")):
            markdown_targets = [
                _markdown_target(match.group(1))
                for match in _MARKDOWN_LINK.finditer(line)
            ]
            markdown_targets.extend(
                match.group(1) for match in _REFERENCE_LINK.finditer(line)
            )
            inline_targets = [
                target
                for match in _INLINE_CODE.finditer(line)
                if (target := _inline_repository_path(match.group(1))) is not None
            ]
            for raw, inline in [
                *((target, False) for target in markdown_targets),
                *((target, True) for target in inline_targets),
            ]:
                resolved = _resolve_target(root, source, raw, inline=inline)
                if resolved is not None and not resolved.exists():
                    missing.append(
                        MissingTarget(
                            source=source,
                            line=line_number,
                            target=raw,
                            resolved=resolved,
                        )
                    )
    return missing


def test_documentation_relative_targets_exist() -> None:
    missing = _missing_targets(ROOT, _documentation_files(ROOT))

    assert not missing, "\n".join(
        f"{item.source.relative_to(ROOT)}:{item.line}: "
        f"{item.target!r} -> {item.resolved}"
        for item in missing
    )


def test_broken_relative_markdown_link_is_reported(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text("[missing](docs/not-there.md)\n", encoding="utf-8")

    missing = _missing_targets(tmp_path, [document])

    assert [item.target for item in missing] == ["docs/not-there.md"]


def _markdown_section(document: Path, heading: str) -> str:
    text = document.read_text(encoding="utf-8")
    marker = f"## {heading}\n"
    start = text.index(marker) + len(marker)
    end = text.find("\n## ", start)
    return text[start:] if end < 0 else text[start:end]


def test_readmes_publish_equivalent_data_handling_boundaries() -> None:
    sections = [
        _markdown_section(ROOT / "README.md", "Data Handling"),
        _markdown_section(ROOT / "README_RU.md", "Обработка данных"),
    ]
    shared_contract_terms = {
        "DIPTRACE_MCP_WORKSPACE",
        "DIPTRACE_MCP_ALLOWED_ROOTS",
        "DIPTRACE_MCP_STATE_DIR",
        "original.xml",
        "working.xml",
        "apply",
        "cancel",
        "Freerouting",
        "ngspice",
        "openEMS",
        "stdio",
        "streamable-http",
        "127.0.0.1:8765",
    }

    for section in sections:
        assert section.count("\n- ") == 6
        missing_terms = sorted(term for term in shared_contract_terms if term not in section)
        assert not missing_terms
