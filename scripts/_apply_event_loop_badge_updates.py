# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


badges = (
    "[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/"
    "badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/"
    "workflows/ci.yml)\n"
    "[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)\n\n"
)

replace_once(
    Path("README.md"),
    "**English** | [Русский](README_RU.md)\n\n",
    "**English** | [Русский](README_RU.md)\n\n" + badges,
)
replace_once(
    Path("README_RU.md"),
    "[English](README.md) | **Русский**\n\n",
    "[English](README.md) | **Русский**\n\n" + badges,
)

replace_once(
    Path("README.md"),
    "See [the roadmap](docs/ROADMAP.md) for the current priority order and exit criteria. Runtime truth for a specific document always comes from `get_capabilities`.\n",
    "See [the roadmap](docs/ROADMAP.md) for the current priority order and exit criteria. Runtime truth for a specific document always comes from `get_capabilities`. The synchronous FastMCP worker-thread contract and connected responsiveness probes are documented in [Async Execution and Event-Loop Safety](docs/ASYNC_EXECUTION.md).\n",
)
replace_once(
    Path("README_RU.md"),
    "Актуальный порядок работ и критерии завершения находятся в [roadmap](docs/ROADMAP.md). Фактическую доступность конкретной операции всегда определяет `get_capabilities`.\n",
    "Актуальный порядок работ и критерии завершения находятся в [roadmap](docs/ROADMAP.md). Фактическую доступность конкретной операции всегда определяет `get_capabilities`. Синхронный worker-thread контракт FastMCP и connected responsiveness-тесты описаны в [Async Execution and Event-Loop Safety](docs/ASYNC_EXECUTION.md).\n",
)

replace_once(
    Path(".github/workflows/ci.yml"),
    "      - run: python scripts/generate_compliance_inventory.py --check\n      - name: Verify consolidated skill delivery\n",
    "      - run: python scripts/generate_compliance_inventory.py --check\n"
    "      - run: python scripts/audit_event_loop.py --json\n"
    "      - run: python scripts/generate_coverage_badge.py --check\n"
    "      - name: Verify event-loop responsiveness and README badges\n"
    "        run: python -m pytest -q tests/test_event_loop_responsiveness.py tests/test_badges.py\n"
    "      - name: Verify consolidated skill delivery\n",
)

replace_once(
    Path("docs/TESTING.md"),
    "python scripts/check_coverage.py coverage.json\npython scripts/ingest_fixtures.py --dry-run --synthetic --json\n",
    "python scripts/check_coverage.py coverage.json\n"
    "python scripts/generate_coverage_badge.py --check\n"
    "python scripts/audit_event_loop.py --json\n"
    "pytest -q tests/test_event_loop_responsiveness.py\n"
    "python scripts/ingest_fixtures.py --dry-run --synthetic --json\n",
)
replace_once(
    Path("docs/TESTING.md"),
    "The declared development constraint remains `pytest>=8.4,<9`. Pytest 9 is\nchecked only in a separate clean environment against the same project and MCP\nSDK versions; a successful probe does not by itself change the supported CI\nmatrix or dependency constraint.\n",
    "The maintained development constraint is `pytest>=9.0.3,<10`, and the same\nconstraint is installed by the supported CI matrix.\n\n"
    "The public MCP tools intentionally remain synchronous callables. FastMCP\n"
    "executes that surface through its AnyIO worker-thread boundary. The static\n"
    "registry audit rejects an accidental async tool until it receives an explicit\n"
    "non-blocking review, while connected protocol probes prove that synthetic\n"
    "blocking-I/O and CPU-heavy calls do not prevent an event-loop heartbeat. See\n"
    "[ASYNC_EXECUTION.md](ASYNC_EXECUTION.md) for cancellation and mutation limits.\n",
)

replace_once(
    Path("CHANGELOG.md"),
    "- add Windows CI smoke/audit coverage for no-Python installation, settings\n  profiles, Unicode paths, client-config backups, checksums, and unsigned status;\n",
    "- add Windows CI smoke/audit coverage for no-Python installation, settings\n"
    "  profiles, Unicode paths, client-config backups, checksums, and unsigned status;\n"
    "- audit the FastMCP synchronous worker-thread boundary and add connected\n"
    "  responsiveness probes for blocking I/O and CPU-heavy work;\n"
    "- publish CI status and deterministic coverage-gate badges whose threshold is\n"
    "  generated from the enforced workflow value;\n",
)

allowlist_path = Path("scripts/release_artifact_allowlist.txt")
entries = [
    line.strip()
    for line in allowlist_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
permanent_entries = {
    "docs/ASYNC_EXECUTION.md",
    "docs/badges/coverage.svg",
    "scripts/audit_event_loop.py",
    "scripts/generate_coverage_badge.py",
    "tests/test_badges.py",
    "tests/test_event_loop_responsiveness.py",
}
temporary_entries = {
    ".github/workflows/one-shot-event-loop-badges.yml",
    "scripts/_apply_event_loop_badge_updates.py",
    "scripts/_apply_event_loop_offload.py",
}
new_entries = permanent_entries | temporary_entries
if new_entries.intersection(entries):
    raise RuntimeError("one or more event-loop/badge paths are already allowlisted")
entries.extend(new_entries)
if len(entries) != len(set(entries)):
    raise RuntimeError("release allowlist contains duplicate paths")
allowlist_path.write_text("\n".join(sorted(entries)) + "\n", encoding="utf-8")

# The one-shot workflow must pass the release-surface audit while its three
# temporary implementation files are still tracked. Immediately before the
# final commit, the workflow removes those files. This local hook then removes
# their matching allowlist entries, verifies the final tracked tree, and stages
# the corrected allowlist. The hook lives only in the ephemeral Actions clone.
hook_path = Path(".git/hooks/pre-commit")
hook_path.write_text(
    """#!/usr/bin/env bash
set -euo pipefail
python - <<'PY'
from pathlib import Path

path = Path("scripts/release_artifact_allowlist.txt")
temporary = {
    ".github/workflows/one-shot-event-loop-badges.yml",
    "scripts/_apply_event_loop_badge_updates.py",
    "scripts/_apply_event_loop_offload.py",
}
entries = [
    line.strip()
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip() and line.strip() not in temporary
]
path.write_text("\\n".join(sorted(entries)) + "\\n", encoding="utf-8")
PY
git add scripts/release_artifact_allowlist.txt
python -m pytest -q tests/test_release_artifacts.py
""",
    encoding="utf-8",
)
hook_path.chmod(0o755)
