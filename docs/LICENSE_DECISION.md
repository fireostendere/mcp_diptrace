# License Options and Release Blocker

## Current status

The repository owner selected the Apache License 2.0 on 2026-07-29. The full
license text is committed as [`LICENSE`](../LICENSE), and the SPDX identifier
`Apache-2.0` is recorded in package and citation metadata. The remaining
public-release blockers are tracked in
[PUBLIC_RELEASE_CHECKLIST.md](PUBLIC_RELEASE_CHECKLIST.md).

The comparison below is kept for the record. It is an engineering comparison,
not legal advice.

## Decision matrix

| Question | MIT | Apache License 2.0 | Mozilla Public License 2.0 |
| --- | --- | --- | --- |
| General model | Permissive | Permissive | File-level copyleft |
| Required notices | Preserve copyright and license notice | Preserve license; retain required notices and changes notices; evaluate whether a `NOTICE` file is needed | Preserve license notices; make source for modified MPL-covered files available when distribution triggers the license |
| Express patent terms | No express patent license in the standard text | Express contributor patent license with termination provisions | Express contributor patent license with file-level copyleft terms |
| Combining with proprietary code | Generally permits it subject to notice | Generally permits it subject to license and notice obligations | Permits a larger work while modified MPL-covered files remain under MPL terms |
| Main operational advantage | Short and widely understood | More explicit patent and contribution terms | Keeps changes to covered files available without applying copyleft to the entire larger work |
| Main review burden | Patent posture and contribution provenance must be handled elsewhere | Longer compliance process; patent and `NOTICE` handling must be understood | File boundaries and source-availability obligations need release discipline |
| Repository-specific question | Is a minimal permissive grant sufficient for the server, bridge, documentation, and packaged skills? | Are explicit patent terms worth the additional release process? | Is file-level reciprocity a project goal for bridge and packaged-skill changes? |

The three candidates are listed as approved licenses by the Open Source
Initiative:

- [MIT](https://opensource.org/license/mit);
- [Apache-2.0](https://opensource.org/license/apache-2.0);
- [MPL-2.0](https://opensource.org/license/mpl-2.0).

The matrix is intentionally limited to these three candidates and is not a
conclusion that any one of them is legally or strategically correct.

## Audit required before selection

- Confirm who owns copyright in every committed code and documentation path.
- Confirm that the selecting party can license existing commits.
- Inventory direct and bundled dependencies, licenses, notices, and binary
  distribution requirements.
- Review the PyInstaller-built Windows bridge and everything bundled into it.
- Review wheel-shipped `skills/` content and its shared schema.
- Review `reference/diptrace-xml/extracted_text/`, generated inventory data,
  official-document excerpts, and redistribution obligations.
- Review every fixture and evidence artifact. Possession of a DipTrace export
  does not itself grant redistribution permission.
- Review descriptive use of DipTrace and Novarm names and marks.
- Decide whether documentation needs a separate license and whether the
  selected license requires a `NOTICE` or source-availability material.
- Select a contribution provenance mechanism before accepting external work.

The reference-material audit explains why untracked binaries and generated
notes without provenance cannot become shipped evidence:
[REFERENCE_MATERIALS_AUDIT.md](REFERENCE_MATERIALS_AUDIT.md).

## Selection record

The selection commit adds the `LICENSE` file and records the decision here,
in package metadata, citation metadata, both READMEs, and the public-release
checklist.

- SPDX identifier: `Apache-2.0`, committed as `LICENSE` and declared in
  `pyproject.toml` (`license = "Apache-2.0"`) and `CITATION.cff`.
- Copyright holder and years: the repository owner,
  [@fireostendere](https://github.com/fireostendere), 2026.
- Patent rationale: the project distributes an MCP server and a Windows bridge
  that downstream users combine with proprietary EDA tooling. The express
  contributor patent license with termination provisions was preferred over
  MIT's silence on patents, and MPL-2.0 file-level copyleft was not a project
  goal for bridge and packaged-skill changes.
- Contribution provenance: new contributions use the Developer Certificate of
  Origin 1.1 in [`DCO`](../DCO), with the workflow and AI/provenance disclosure
  requirements in [CONTRIBUTING.md](../CONTRIBUTING.md). Existing commits were
  authored by the repository owner, who can license them. This record does not
  claim that every historical commit has a DCO sign-off.
- Documentation and fixture treatment: code, documentation, and packaged
  skills are covered by the same license. Fixtures and evidence artifacts with
  unresolved redistribution permission are not distributed: the release
  allowlist excludes `tests/fixtures/acceptance/`; it also excludes the
  intentionally untracked docs/private directory.
- Dependency and notice audit: direct runtime dependencies are `mcp` (MIT),
  `pydantic` (MIT), and `typing-extensions` (PSF); the optional geometry extra
  adds `shapely` (BSD-3-Clause). No third-party code is vendored into the
  repository, so no `NOTICE` file is required. Bundled-content review for the
  PyInstaller bridge build remains a release-checklist item.
- Trademark review: DipTrace and Novarm names are used descriptively to
  identify compatibility; no affiliation or endorsement is claimed.
- Decision date: 2026-07-29, approved by the repository owner in the commit
  that adds the `LICENSE` file together with this record.
