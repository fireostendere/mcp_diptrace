"""Hatch build hook that includes only reviewed, versioned release files."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_ALLOWLIST = "scripts/release_artifact_allowlist.txt"
_BLOCKED_PARTS = frozenset({".agents", ".codex", ".git", ".vscode", "etc"})
_BLOCKED_PREFIXES = (
    "docs/private/",
    "tests/fixtures/acceptance/",
    "reference/diptrace-xml/extracted_text/",
    "reference/diptrace-xml/sources/",
)
_BLOCKED_PATHS = frozenset({"reference/diptrace-xml/spec_inventory.json"})


def _validated_release_paths(root: Path) -> tuple[str, ...]:
    manifest = root / _ALLOWLIST
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError(f"release allowlist is missing or unsafe: {_ALLOWLIST}")

    paths: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        relative = raw_line.strip()
        if not relative or relative.startswith("#"):
            continue
        path = PurePosixPath(relative)
        folded = relative.casefold()
        if (
            relative != path.as_posix()
            or path.is_absolute()
            or ".." in path.parts
            or any(part.casefold() in _BLOCKED_PARTS for part in path.parts)
            or any(folded.startswith(prefix.casefold()) for prefix in _BLOCKED_PREFIXES)
            or folded in {blocked.casefold() for blocked in _BLOCKED_PATHS}
        ):
            raise ValueError(
                f"unsafe release path in {_ALLOWLIST}:{line_number}: {relative!r}"
            )
        if relative in seen:
            raise ValueError(
                f"duplicate release path in {_ALLOWLIST}:{line_number}: {relative!r}"
            )
        source = root / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError(
                f"release path is missing, not a file, or a symlink: {relative!r}"
            )
        seen.add(relative)
        paths.append(relative)

    if _ALLOWLIST not in seen:
        raise ValueError(f"release allowlist must include itself: {_ALLOWLIST}")
    return tuple(paths)


class CustomBuildHook(BuildHookInterface[BuilderConfig]):
    """Replace Hatch's tree walk with exact, reviewed file mappings."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        del version
        root = Path(self.root)
        paths = _validated_release_paths(root)

        # Hatch otherwise includes untracked files that are not ignored by Git. Exclude
        # the whole project tree, then add only exact regular files from the allowlist.
        self.build_config.set_exclude_all()
        force_include: dict[str, str] = build_data["force_include"]

        if self.target_name == "sdist":
            for relative in paths:
                force_include[str(root / relative)] = relative
            return

        if self.target_name == "wheel":
            for relative in paths:
                if relative.startswith("src/diptrace_mcp/"):
                    distribution_path = relative.removeprefix("src/")
                elif relative.startswith("skills/"):
                    distribution_path = f"diptrace_mcp/{relative}"
                else:
                    continue
                force_include[str(root / relative)] = distribution_path
