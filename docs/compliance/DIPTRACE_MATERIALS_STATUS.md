# DipTrace reference-material status

## Current status

The repository contains engineering extracts and a generated inventory derived
from publicly obtained DipTrace documentation. Those files are useful for
parser/reference work, but the repository does not treat them as Apache-2.0
content automatically and does not claim a permission grant, vendor
endorsement, or correspondence with DipTrace or Novarm.

The release build policy therefore excludes the extracted text bundles and
generated inventory from future wheels, source distributions, and release
assets until a human confirms a defensible redistribution basis. The source
PDF inputs remain local-only and ignored. An operator with legitimately
obtained documents can regenerate the working extracts locally with
`scripts/extract_spec_inventory.py`.

## Evidence boundary

The committed reference guide distinguishes public-specification statements,
observed compatibility, and open questions. A parser passing its own fixtures
does not prove a DipTrace host convention. Real exports, open/save/re-export
evidence, provenance, and redistribution permission remain separate review
requirements.

External permission correspondence is not stored in Git. The repository owner
maintains any such materials privately.
