# Independent review package

## Purpose and status

This is a sanitized technical package for a future independent review. It is
not an independent audit, legal opinion, vendor approval, signing approval, or
release acceptance record. No independent reviewer is identified here because
none has completed this review.

## Inspection binding

- Inspected date: `2026-08-02`.
- Baseline commit inspected: `e57422e545c6b94aefe52c044c64d72a74a8c373`.
- Project version at that commit: `0.1.2`.
- Project license: Apache-2.0, recorded in [`LICENSE`](../../LICENSE).
- Current review branch: `compliance/open-source-readiness`.

The binding identifies the source tree used for the baseline reports. A future
review must record the exact PR head it actually inspects.

## Package contents

- [dependency inventory](dependency-inventory.json) — deterministic direct
  declarations from `pyproject.toml` covering runtime, geometry, bridge,
  development, and build groups;
- [CycloneDX SBOM](sbom.cdx.json) — the same declarative component set, with
  unresolved and special-license items explicitly marked for human review;
- [third-party notices](THIRD_PARTY_NOTICES.md) — engineering notice summary,
  not a legal clearance;
- [provenance inventory](PROVENANCE_INVENTORY.csv) — sanitized path/pattern
  inventory with distribution surfaces and human-action flags;
- [DipTrace material status](DIPTRACE_MATERIALS_STATUS.md) — neutral source
  and redistribution boundary; and
- [signing preparation](../SIGNING.md) — technical unsigned/signed artifact
  boundary without account identifiers.

## Reproduction commands

Run from a clean checkout with the baseline commit or the exact review commit:

```bash
git rev-parse HEAD
git ls-files
git status --ignored --short
python scripts/check_public_privacy.py --commit "$(git rev-parse HEAD)"
python scripts/check_provenance_inventory.py
python scripts/generate_compliance_inventory.py --check
python -m hatchling build -d release-dist
python scripts/audit_release_artifacts.py \
  --dist-dir release-dist --check-allowlist
python -m pytest -q tests/test_release_artifacts.py tests/test_ci_workflow.py
```

If a tool is unavailable, record the exact missing tool and command rather than
substituting an unverified result. The full project gates remain documented in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) and
[`RELEASE_PROCESS.md`](../RELEASE_PROCESS.md).

## Release-surface observations

The public v0.1.2 release was inspected as a historical reference:

- the wheel contained 79 members and project license metadata;
- the source distribution contained the versioned source allowlist and
  historical announcement drafts that are no longer retained in the current
  Git tree;
- the Windows plug-in ZIP contained the bridge executable, installer, four
  settings profiles, license, exchange-path guidance, and installation guide;
- the bridge was a 64-bit Windows PE/PyInstaller executable and was unsigned;
  full PyInstaller archive extraction was not available in the Linux audit
  environment; and
- the five selected public assets downloaded for this audit matched the
  corresponding entries in `SHA256SUMS.txt`. The manifest also named five
  additional historical assets that were not downloaded in this run.

These observations do not clear bundled dependencies, native libraries,
reference extracts, or historical release bytes for redistribution.

## Questions for the reviewer

1. Is the Apache-2.0 grant supported for every project-authored tracked path,
   including fixtures, schemas, skills, and documentation?
2. Are all direct and transitive runtime/development dependencies accompanied
   by current license texts and required notices?
3. What exact files and native libraries are bundled in the Windows bridge,
   and are their notices included in the release package?
4. Is there a verified redistribution basis for the DipTrace reference extracts
   and generated inventory? If not, should they be removed from public Git and
   generated only from user-supplied local documents?
5. Does the future SignPath configuration enforce the intended signer,
   timestamp, artifact identity, and release approval boundary?
6. Are the DCO, privacy deny-list, provenance inventory, and release allowlist
   checks sufficient for the intended contribution workflow?

## Scope limitations

This package does not inspect private application materials, correspondence,
identity records, account settings, or signing credentials. It does not claim
DipTrace permission, an independent audit, a signed artifact, external
adoption, vendor endorsement, or OpenAI acceptance.
