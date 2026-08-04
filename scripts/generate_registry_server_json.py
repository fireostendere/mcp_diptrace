#!/usr/bin/env python3
"""Generate a concrete official MCP Registry server.json for an MCPB asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).absolute().parents[1]
TEMPLATE = REPO_ROOT / "packaging" / "registry" / "server.template.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RegistryMetadataError(ValueError):
    """Raised when registry metadata cannot be generated safely."""


def _replace(value: object, replacements: dict[str, str]) -> object:
    if isinstance(value, str):
        for token, replacement in replacements.items():
            value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate(version: str, mcpb_url: str, digest: str) -> dict[str, object]:
    parsed = urlparse(mcpb_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RegistryMetadataError("MCPB URL must be a public HTTPS URL")
    if "mcp" not in mcpb_url.lower():
        raise RegistryMetadataError("MCPB URL must contain the string 'mcp'")
    digest = digest.lower()
    if not SHA256_RE.fullmatch(digest):
        raise RegistryMetadataError("MCPB SHA-256 must be 64 lowercase hex characters")
    if not version.strip() or any(character.isspace() for character in version):
        raise RegistryMetadataError("version must be a non-empty token")

    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    replacements = {
        "__VERSION__": version,
        "__MCPB_URL__": mcpb_url,
        "__MCPB_SHA256__": digest,
    }
    replaced = _replace(template, replacements)
    if not isinstance(replaced, dict):
        raise RegistryMetadataError("registry template root must be an object")
    result = cast(dict[str, object], replaced)
    encoded = json.dumps(result, sort_keys=True)
    if "__" in encoded:
        raise RegistryMetadataError("unresolved registry template placeholder")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--mcpb-url", required=True)
    digest = parser.add_mutually_exclusive_group(required=True)
    digest.add_argument("--mcpb-file", type=Path)
    digest.add_argument("--mcpb-sha256")
    parser.add_argument("--output", type=Path, default=Path("server.json"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    digest = _sha256(args.mcpb_file) if args.mcpb_file else args.mcpb_sha256.lower()
    result = generate(args.version, args.mcpb_url, digest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RegistryMetadataError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
