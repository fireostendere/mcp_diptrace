# Synthetic four-layer power fixture (MCP-generated, NOT DipTrace-validated)

**Validation level:** `synthetic_operation_fixture`
**Provenance:** `mcp_generated`
**DipTrace validated:** NO — permanently synthetic, no promotion path exists.

This directory contains a wholly synthetic PCB generated through DipTrace MCP semantic
operations. It is useful for:

- testing the MCP parser and XML normalization;
- testing routing compiler logic, via spans, and connectivity;
- testing semantic operations, transactions, and previews;
- snapshot and normalized model tests.

**This fixture is permanently synthetic.** It must NOT be promoted to
`diptrace_exported` or `diptrace_roundtrip_verified`. No promotion workflow
exists and none should be created. A real acceptance fixture must start
from a separate genuine DipTrace-exported seed placed in
`tests/fixtures/acceptance/diptrace_5_3/seeds/`.

## Current state

- `source_board.xml` is MCP-generated DipTrace PCB XML format 4.3.0.3;
- `preview.svg` and `preview.json` are MCP previews of that exact source SHA;
- `specctra/source_board.xml` is an identical frozen copy;
- `manifest.pending.json` uses schema `diptrace-fixture-manifest-pending-v1` with
  explicit validation_level=`synthetic_operation_fixture`.

## Ratlines

`SENSE` is deliberately left without a trace. Its Top-to-Bottom endpoints make it the
primary Freerouting/via exercise. GND and the Bottom-side C4 power branch also retain
unresolved connectivity for pour and autorouter coverage.
