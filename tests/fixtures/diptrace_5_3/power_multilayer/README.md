# Synthetic four-layer power fixture (MCP-generated, NOT DipTrace-validated)

**Validation level:** `synthetic_operation_fixture`
**Provenance:** `mcp_generated`
**DipTrace validated:** NO

This directory contains a wholly synthetic PCB generated through DipTrace MCP semantic
operations. It is useful for:

- testing the MCP parser and XML normalization;
- testing routing compiler logic, via spans, and connectivity;
- testing semantic operations, transactions, and previews;
- snapshot and normalized model tests.

**This is NOT a DipTrace compatibility fixture.** The source XML was never opened,
saved, or re-exported by DipTrace. It must not be used as evidence that:

- DipTrace 5.3 can open this file;
- DipTrace 5.3 can save this file without changes;
- DipTrace 5.3 re-exports are semantically equivalent;
- copper-pour refill works correctly;
- DSN/SES round-trip works correctly.

## Current state

- `source_board.xml` is MCP-generated DipTrace PCB XML format 4.3.0.3;
- `preview.svg` and `preview.json` are MCP previews of that exact source SHA;
- `specctra/source_board.xml` is an identical frozen copy;
- authoritative pour-before/refill-after XML and real DSN/SES artifacts are absent;
- `manifest.pending.json` uses schema v2 with explicit validation_level=
  `synthetic_operation_fixture`.

## What is needed for acceptance

To promote this fixture to `diptrace_roundtrip_verified`, the following must be
captured manually with a real DipTrace 5.3 installation:

1. Open `source_board.xml` in DipTrace PCB Layout;
2. Save it (this creates a DipTrace-opened/saved version);
3. Re-export as XML (this creates a DipTrace-reexported version);
4. Capture `pours/before_refill.xml` before copper-pour refill;
5. Capture `pours/after_refill.xml` after copper-pour refill;
6. Export DSN from the re-exported version;
7. Run Freerouting and capture SES;
8. Hash all artifacts and update manifest to schema v2 with validation_level=
   `diptrace_roundtrip_verified`.

## Ratlines

`SENSE` is deliberately left without a trace. Its Top-to-Bottom endpoints make it the
primary Freerouting/via exercise. GND and the Bottom-side C4 power branch also retain
unresolved connectivity for pour and autorouter coverage.

Ratline pruning is deferred until the corrected source has been opened and re-exported
by DipTrace 5.3.
