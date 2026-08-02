# Contributing to DipTrace MCP

## Contribution status

Issues and pull requests are welcome for safe, reviewable improvements. The
repository owner retains merge authority; opening a pull request does not
guarantee review or acceptance. Contributions are accepted under the
Developer Certificate of Origin 1.1 in [`DCO`](DCO) and the Apache License 2.0
in [`LICENSE`](LICENSE).

Every commit in a pull request must include a sign-off. Create a signed-off
commit with:

```bash
git commit -s
```

The `Signed-off-by:` line certifies that the contributor has the right to
submit the work under the applicable project license or another compatible
open-source license. It is a provenance attestation, not a statement that the
project has independently audited the contribution.

Issues and pull requests must not contain proprietary designs, customer data,
credentials, personal data, private correspondence, account identifiers,
identity documents, restricted exports, or submission/application drafts.
Keep private working material outside the repository. Do not attach raw audit
reports containing workstation paths or usernames.

## Provenance and AI assistance

Disclose the origin of every material contribution, including code, fixtures,
schemas, examples, documentation, generated files, and copied snippets. State
the upstream project or source, revision or URL when known, license or
permission basis, and whether the material was generated specifically for this
repository. Do not treat possession of a DipTrace export or a passing parser
round trip as redistribution permission.

Meaningfully disclose AI assistance in the pull request description. Identify
the parts for which an AI system was used and summarize the human review that
was performed. The contributor remains responsible for correctness, security,
provenance, copyright, license compliance, and the right to redistribute every
submitted part.

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
./.venv/bin/python scripts/check_dco.py --base <base-sha> --head <head-sha>
./.venv/bin/python scripts/check_public_privacy.py
./.venv/bin/python scripts/check_provenance_inventory.py
./.venv/bin/python scripts/generate_compliance_inventory.py --check
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
[DEVELOPMENT.md](docs/DEVELOPMENT.md). The public compliance and signing
boundaries are summarized in [docs/compliance/](docs/compliance/) and
[docs/SIGNING.md](docs/SIGNING.md).
