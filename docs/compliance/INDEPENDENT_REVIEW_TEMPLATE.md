# Independent review template

Use this template only after selecting a reviewer and granting access to the
exact public commit under review. Do not add private correspondence, invoices,
contact details, identity records, or legal advice to Git.

## Review identity

- Review date: `YYYY-MM-DD`
- Exact commit SHA:
- Scope agreed with the project owner:
- Reviewer independence/conflict disclosure:
- Review status: `not started | in progress | complete | blocked`

## Technical scope

- [ ] Project license and copyright/provenance boundaries inspected.
- [ ] Runtime, geometry, bridge, development, and build dependency inventory
      compared with a clean environment.
- [ ] CycloneDX SBOM and third-party notices checked against resolved packages.
- [ ] PyInstaller bridge bundle extracted and native libraries inventoried.
- [ ] Wheel and sdist contents compared with the release allowlist.
- [ ] Provenance inventory checked against Git, source archives, wheel, bridge,
      plugin ZIP, and release assets.
- [ ] DipTrace reference extracts reviewed separately from project-authored code.
- [ ] DCO and privacy regression checks reproduced.
- [ ] Signing workflow reviewed without receiving private signing credentials.

## Findings

Record each finding with a stable identifier, exact path, severity, evidence
reference, and recommended disposition. Do not copy secrets or personal data
into the finding.

| ID | Severity | Path/component | Evidence | Finding | Disposition |
| --- | --- | --- | --- | --- | --- |
| R-001 |  |  |  |  |  |

## Conclusion

This template must not be changed to say “independently reviewed” until the
reviewer has completed the agreed scope and the owner has published a factual,
dated decision record. A reviewer may leave unresolved legal or provenance
questions open; open questions are not approvals.
