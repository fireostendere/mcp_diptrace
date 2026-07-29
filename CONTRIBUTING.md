# Contributing to DipTrace MCP

## Contribution status

DipTrace MCP does not currently contain a project-wide `LICENSE` file. The
repository therefore grants no project-wide open-source license and is not
open for general code or documentation contributions.

Do not open a pull request unless the repository owner has requested the
specific change. Unsolicited pull requests may be closed without review. This
policy avoids accepting work before copyright ownership, contribution
provenance, and an OSI-approved license are settled.

Non-sensitive bug reports, feature requests, and compatibility evidence may be
submitted through the repository's GitHub issue forms. Do not put proprietary
designs, credentials, personal data, export-controlled material, or
redistribution-restricted files in an issue.

The repository does not yet publish a verified private vulnerability-reporting
channel. Do not disclose a suspected vulnerability in a public issue. The
absence of a private channel is a public-release blocker recorded in
[the release checklist](docs/PUBLIC_RELEASE_CHECKLIST.md).

## Evidence standards

Reports about DipTrace behavior must identify their source:

- an official specification with the document and page;
- a controlled real-DipTrace export with provenance and permission to share;
  or
- a synthetic test, clearly labelled as synthetic.

Unknown behavior belongs in
[OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md), not in code or documentation as a
fact. Never create, modify, normalize, or promote material under
`tests/fixtures/acceptance/` outside the reviewed evidence workflow.

## Engineering workflow for requested changes

Use Python 3.10 or newer. The geometry-enabled development environment used by
the main coverage job is:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev,geometry]"
```

Run the maintained gates before review:

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m ruff check --no-cache src tests benchmarks scripts plugin
./.venv/bin/python -m mypy --no-incremental src/diptrace_mcp plugin
./.venv/bin/python scripts/generate_pcb_skills.py --check
./.venv/bin/python scripts/generate_mcp_tools_snapshot.py --check
./.venv/bin/python -m hatchling build -d release-dist
./.venv/bin/python scripts/audit_release_artifacts.py \
  --dist-dir release-dist \
  --check-allowlist
./.venv/bin/python scripts/extract_spec_inventory.py \
  --sources reference/diptrace-xml/extracted_text \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
./.venv/bin/python scripts/report_format_coverage.py --check
./.venv/bin/python scripts/make_probe_pack.py --check
./.venv/bin/python scripts/audit_acceptance_seeds.py
```

See [TESTING.md](docs/TESTING.md) for coverage, geometry, bridge, ingest, and
large-board commands.

Requested changes must:

- keep safety gates fail-closed;
- preserve unknown XML and byte locality outside the intended edit;
- reject non-finite engineering inputs;
- keep public claims consistent with code and runtime `get_capabilities`;
- add tests for behavior, error contracts, and unsafe inputs;
- regenerate derived artifacts when their sources change;
- avoid invented fabrication, impedance, clearance, and DFM thresholds; and
- exclude proprietary, personal, customer, and redistribution-restricted
  design files.

The exact implementation checklist for a write operation is in
[DEVELOPMENT.md](docs/DEVELOPMENT.md).
