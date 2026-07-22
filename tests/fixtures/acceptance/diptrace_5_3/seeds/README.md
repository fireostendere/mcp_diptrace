# Acceptance Seeds — Real DipTrace Exports Only

This directory is reserved exclusively for **real XML exports from DipTrace**.
No synthetic, MCP-generated, or hand-crafted XML belongs here.

## Rules

1. **Real DipTrace only.** Every seed must be a genuine export from DipTrace 5.3
   (PCB, Schematic, ComponentLibrary, or PatternLibrary).
2. **Redistribution permission required.** A provenance manifest must include
   explicit `redistribution_permitted=true` and a `redistribution_basis` string
   explaining the license.
3. **SHA-256 mandatory.** Every seed file must have a documented SHA-256 hash.
4. **Version and OS required.** The manifest must record the exact DipTrace
   version, build number, and operating system used for the export.
5. **No MCP generation.** Seeds must not be created via MCP tools, scaffolding,
   or any programmatic XML generation.
6. **No third-party projects.** Seeds must not contain proprietary or
   third-party design data without explicit permission.
7. **MCP modification invalidates trust.** Any MCP edit to a seed document
   automatically downgrades its validation level to `synthetic_operation_fixture`.
   The parent seed provenance is preserved in the sidecar.
8. **Re-verification required.** After MCP modification, the document must
   undergo a fresh open/save/re-export cycle in DipTrace to regain a verified
   status.

## How to add a new seed

1. Export the design from DipTrace 5.3 as XML.
2. Place the XML file in this directory.
3. Create a `.provenance.json` sidecar using `DocumentProvenance` with
   `validation_level="diptrace_exported"`.
4. Record DipTrace version, build, OS, and SHA-256.
5. Commit both the XML and the sidecar.
6. Do NOT use `create_document_from_seed` with `claimed_validation_level` —
   that parameter no longer exists. Trust is determined from the sidecar.
