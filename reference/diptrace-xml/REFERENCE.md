# DipTrace XML implementation reference

This guide is project-authored engineering guidance. The companion [`spec_inventory.json`](spec_inventory.json) is a clean-room factual inventory generated from project-owned XML fixtures/controlled observations. It is not a redistributed vendor specification and does not claim universal format coverage.

## Evidence labels

- **Synthetic observation** — project-authored XML exercised by tests.
- **Controlled export** — independently captured DipTrace output with exact version/build, hashes and provenance.
- **Manual/private observation** — real-host evidence useful for project decisions but not automatically package-owned public trust.
- **Open question** — behavior that still requires additional exact-scope host/open-save/re-export evidence.

The committed inventory remains evidence-scoped. A file appearing in the inventory does not by itself grant `diptrace_exported`, `diptrace_open_save_verified` or `diptrace_roundtrip_verified` trust.

## Inventory workflow

```bash
python scripts/extract_spec_inventory.py \
  --sources tests/fixtures \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
```

The generator accepts project-owned XML observations and rejects PDF/page-text inputs. Inventory records bind source bytes by SHA-256 and preserve their source/evidence classification; they contain factual element/attribute/value observations rather than copied normative prose.

## Maintained implementation boundaries

- XML roots and feature-specific structures are detected from content/source type; extension/version strings are not treated as sufficient compatibility proof.
- Unknown XML is preserved outside operation-owned subtrees where the raw-preserving model applies.
- Distances are normalized to millimetres at typed numeric boundaries.
- `Shape/@Angle` follows the existing radians implementation convention.
- `Component/@Angle` is no longer an unanswered project-manual convention: the later DipTrace PCB Layout 5.3.0.3 campaign observed radians plus rotation/change-side behavior and marked Q1 PASS. What remains open is broader/public package-owned evidence and compatibility scope; see `docs/OPEN_QUESTIONS.md`, `docs/XML_COMPATIBILITY.md` and the manual checkpoint.
- Routing clearance resolves explicit request/document DRC/NetClass constraints under the implemented bounded rules and discloses the source used.
- Trace/object review coverage remains feature-specific; no review helper silently becomes full native DRC authority.
- Internal Component/Pattern Library raw-preserving mutation now exists with controlled real-editor evidence, but public native-library mutation remains a separate unregistered API contract.
- PCB Generations A-D may consume exported physical facts conservatively but cannot invent authoritative stackup/current/refill/manufacturing data.

## Trust and legal boundary

Synthetic parser success is not live DipTrace evidence. Controlled/private real-host evidence remains tied to the exact version/candidate/operation tested and requires a separate reviewed promotion decision before becoming package-owned high trust.

No Novarm/DipTrace permission, endorsement or universal compatibility is claimed. Local source materials legitimately held by a maintainer belong outside the public tree under the documented ignored/private paths unless redistribution and provenance are explicitly cleared.
