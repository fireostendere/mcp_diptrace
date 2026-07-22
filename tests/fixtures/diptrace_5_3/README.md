# DipTrace 5.3 Fixture Directory

## Trust Model

Fixtures in this directory tree are classified by `validation_level`:

- `synthetic_parser_only` — MCP-generated XML, tested only by the MCP parser.
  Never opened by DipTrace. NOT DipTrace-compatible evidence.

- `synthetic_operation_fixture` — MCP-generated XML, tested by MCP parser +
  semantic operations. Never opened by DipTrace. NOT DipTrace-compatible evidence.

- `diptrace_exported` — XML exported by DipTrace. Opened by DipTrace but not
  necessarily saved or re-exported.

- `diptrace_open_save_verified` — XML that DipTrace opened and saved. The saved
  version is available for comparison.

- `diptrace_roundtrip_verified` — XML that DipTrace opened, saved, and re-exported.
  Semantic comparison between source and re-export passed.

- `external_tool_roundtrip_verified` — Same as above, plus an external tool
  (e.g. Freerouting) round-trip was verified.

## Current state

No redistributable `diptrace_roundtrip_verified` fixtures exist yet. The
`power_multilayer/` directory contains a synthetic MCP-generated fixture classified
as `synthetic_operation_fixture`.

## When evidence is available

Add `manifest.json` conforming to `manifest.schema.json` (v2) and the following
groups:

```text
tests/fixtures/diptrace_5_3/
  manifest.json           ← schema v2 with validation_level fields
  hierarchy/
  pours/
  libraries/
  schematic_roundtrip/<case>/
  geometry/
  specctra/
```

Keep exported XML, DSN, and SES bytes unchanged. Record any controlled GUI change
in the manifest rather than editing the fixture manually. CI should validate hashes
and validation_level before using the files.

## CI enforcement

CI must reject any fixture claiming `diptrace_roundtrip_verified` or higher without:

- exact DipTrace version;
- source hash;
- re-export hash;
- semantic comparison result;
- confirmed manifest with all required fields.
