# DipTrace XML implementation reference

This guide is project-authored engineering guidance. The companion
[`spec_inventory.json`](spec_inventory.json) is a clean-room factual inventory
generated from the repository's own XML fixtures and controlled exports. It
contains observed element/attribute names and bounded values only; it is not a
copy of a vendor specification and does not claim universal format coverage.

## Evidence labels

- **Synthetic observation** — a project-authored XML fixture exercised by tests.
- **Controlled export** — an independently captured DipTrace export with an
  exact version/build, SHA-256, scenario and acceptance audit.
- **Open question** — behavior that still requires independent DipTrace GUI or
  open/save/re-export evidence.

The current committed fixture inventory is synthetic. No fixture in this tree
automatically grants `diptrace_exported`, `diptrace_open_save_verified`, or
`diptrace_roundtrip_verified` trust.

## Inventory workflow

Generate and validate the factual inventory from project-owned XML only:

```bash
python scripts/extract_spec_inventory.py \
  --sources tests/fixtures \
  --out reference/diptrace-xml/spec_inventory.json \
  --check
```

The generator rejects PDF and page-text inputs. Each source record binds an XML
file by SHA-256 and marks it `synthetic_fixture` or `controlled_real_export`.
The inventory intentionally contains no normative descriptions, copied
examples, or extracted documentation text.

## Observed implementation boundaries

- XML roots and feature-specific structures are detected from the source type;
  unknown XML is preserved outside an operation-owned subtree.
- Distances are normalized to millimetres at numeric input boundaries.
- `Shape/@Angle` is handled as radians by the existing implementation.
- `Component/@Angle` remains an unverified semantic gate; see Q1 in
  [`docs/OPEN_QUESTIONS.md`](../../docs/OPEN_QUESTIONS.md).
- Routing clearance uses the maximum of an explicit request, board DRC default,
  and affected NetClass rules; every routing result discloses the resolution.
- Trace-to-object review paths still use their object-specific board DRC rules;
  review output marks this partial coverage.

## Trust and legal boundary

Synthetic parser success is not live DipTrace evidence. A controlled export is
not accepted trust evidence until the project acceptance procedure verifies the
exact source, independent re-export, semantic comparison, hashes, and
redistribution basis. No Novarm/DipTrace permission or endorsement is claimed.
Local source materials, if legitimately held by a maintainer, belong under the
ignored `.local/open-source-readiness/novarm-reference/` directory and are not
part of the public tree.
