# Reference-materials and provenance audit

## Decision for this branch

No written Novarm/DipTrace redistribution permission is present in the
repository or in the accessible workspace. The conservative public-tree decision
is therefore:

- remove verbatim documentation extracts from the tracked tree;
- remove the source-derived inventory that depended on those extracts;
- keep any legitimately held PDFs/extracts only in the ignored local path
  `.local/open-source-readiness/novarm-reference/`;
- do not rewrite Git history, and do not claim that the historical commits are
  legally cleared;
- use a clean-room factual inventory generated from project-owned XML fixtures
  and future controlled exports.

The ignored local backup created during this branch is not a release input and
must not be committed, copied into a wheel/sdist, or attached to a public PR.

## Material classification

| Category | Current disposition | Trust/legal status |
| --- | --- | --- |
| Verbatim or close documentation text | Removed from current Git tree; ignored local backup only | Redistribution basis unresolved |
| XML element/attribute names | `reference/diptrace-xml/spec_inventory.json` facts generated from own XML | Project-authored observations; not normative |
| Controlled real exports | None available for this branch | Human capture and acceptance required |
| Synthetic fixtures | Existing `tests/fixtures/*.xml` and pending 5.3 pack | Synthetic only; no live compatibility claim |
| Source-derived structure | Old inventory retained only in ignored backup | Must not be regenerated from documentation text |
| Unclear-origin local material | Not used by generator or release surfaces | Human provenance review required |

## Inventory of affected paths

| Material or surface | Before this branch | Current tree | Release disposition |
| --- | --- | --- | --- |
| `reference/diptrace-xml/extracted_text/*.json` | Tracked extracted page text | Deleted; ignored local backup only | Blocked by allowlist/build/archive checks |
| `reference/diptrace-xml/sources/*.pdf` | Tracked source PDFs | Removed; ignored local backup only | Blocked by allowlist/build/archive checks |
| `reference/diptrace-xml/spec_inventory.json` | Generated from source-derived page text | Replaced by XML-observation inventory | Public project-authored observation data; not normative |
| `REFERENCE.md`, `SKILL.md`, and coverage docs | Referred to source-derived material | Rewritten to state provenance and evidence limits | Documentation only; no source text packaged |
| Python package, wheel, sdist, ZIP, and release allowlist | Audited against the previous tree | Re-audited to reject removed paths and private material | No verbatim material permitted |
| Git history | Contains the old tracked paths in earlier commits | Intentionally unchanged | Historical presence is not retroactively cleared |

The historical references are recorded as provenance/audit facts only. They are
not copied into the factual inventory and are not treated as permission.

Generated JSON is not treated as free of rights merely because code generated
it. The new generator accepts XML observation inputs only, records the source
hash and source kind, and rejects PDF/page-text inputs. Fact notes are
project-authored summaries and do not reproduce explanatory paragraphs,
examples, or documentation tables.

## Public-surface checks

The release allowlist and build hook reject the removed material, source PDFs,
private working paths, and other blocked content. The factual inventory is
allowed only as project-authored data and is excluded from the wheel because it
is reference/test data rather than runtime package data. Archive tests inspect
both names and contents.

The current tree contains no tracked extracted-text files; no tracked source PDFs are present;
the three old extracted JSON files and old inventory remain only in Git history.
History is intentionally not rewritten by this branch.

## Required human actions

1. A maintainer must decide whether to contact Novarm and, if so, send any
   permission request outside Git. This branch does not claim that a request was
   sent or answered.
2. A human with DipTrace 5.3 PCB Layout must perform Q1 and the fixture-pack
   capture recipe, including exact build, independent GUI edit/re-export,
   semantic comparison and acceptance audit.
3. Any real export must be sanitized, project-owned or redistribution-cleared,
   and placed under the acceptance procedure before trust is raised.

## Historical context

Earlier audits and commits described the removed extracts as local engineering
inputs. Those historical claims are not copied into the current inventory, and
the removal does not retroactively grant or deny rights in prior Git objects.
Reviewers should treat the current-tree removal and the absence of a written
permission record as the authoritative status for this branch.
