# License Options and Release Blocker

## Current status

No project-wide `LICENSE` file is committed. DipTrace MCP grants no
project-wide open-source license and must not be announced as open source,
published to a package index, or opened for general contributions until an
accountable owner selects an OSI-approved license and completes the ownership
and redistribution audit.

This is an engineering comparison, not legal advice. It does not select a
license.

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

The same commit that adds a project license must record the SPDX identifier,
copyright holder and years, patent rationale, contribution provenance,
documentation and fixture treatment, dependency/notice audit, trademark
review, decision date, and approving Git commit. It must also update package
metadata, citation metadata, both READMEs, and the public-release checklist.
