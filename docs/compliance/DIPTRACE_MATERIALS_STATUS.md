# DipTrace reference-material status

## Current decision

No written Novarm/DipTrace permission or response is recorded. The current
public tree contains no verbatim documentation extracts or source PDFs. The
removed files were copied to the ignored maintainer-only path
`.local/open-source-readiness/novarm-reference/` for local recovery and were not
added to any release surface. Git history was not rewritten.

This is a containment decision, not a legal clearance statement. The project
does not claim vendor permission, endorsement, or non-affiliation beyond the
descriptive use already reviewed by the maintainer.

## Replacement inventory

`reference/diptrace-xml/spec_inventory.json` now has schema
`diptrace-factual-inventory-v1`. It is generated only from project-authored XML
fixtures and future evidence files explicitly marked `controlled_real_export`.
Each source has a SHA-256, source kind, evidence id, version when observed,
redistribution basis, and third-party-design flag. Each fact has observed XML
names/values and a short project-authored note; it has no copied documentation
description or example.

All committed sources currently have `source_kind=synthetic_fixture`, so the
inventory is useful for parser coverage only. It does not increase DipTrace
trust and does not establish DipTrace 5.3 compatibility.

## Human action required

- Keep any permission draft and correspondence local; do not commit it.
- Decide whether a permission request is appropriate. No request is claimed to
  have been sent.
- Before accepting a real export, complete the evidence capture and provenance
  audit, including redistribution basis and exact DipTrace build.
