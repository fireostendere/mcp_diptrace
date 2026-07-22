# Specctra DSN/SES evidence — pending manual DipTrace/Freerouting work

`source_board.xml` is the frozen MCP-generated source revision. Its current SHA-256 is
`c972afc80eb4c944938370672e6bb2b6ad42cc2145bd9355a30d5478e9f8924d`.
No `input.dsn` or `output.ses` is present yet.

1. Open `source_board.xml` in DipTrace PCB Layout 5.3.0.2 and recalculate the ratsnest.
2. Confirm that `SENSE` (`R1:2` → Bottom-side `R2:1`) remains unrouted, existing routes
   remain unchanged, and SIGNAL_B still contains two through vias.
3. Save/export the official DipTrace XML back to `source_board.xml`; record its new
   SHA-256 and exact DipTrace/OS versions before exporting DSN.
4. Export a real Specctra design as `input.dsn`.
5. Start real Freerouting with that DSN. Preserve existing routes and route `SENSE` with
   at least one multilayer transition/via. Additional unresolved branches may remain, but
   document them explicitly.
6. Save the real session as `output.ses`.
7. Re-run MCP capability discovery. If SES inspection is available, inspect `output.ses`
   against the frozen board revision before import. Do not import on identity mismatch.
8. Create and inspect an MCP preview, then import SES into a copy of the board.
9. Run connectivity review, DRC, clearance and via-span checks on that copy.
10. Confirm from DSN/SES metadata and hashes that both artifacts belong to this exact
    `source_board.xml` revision. Record all hashes in the final manifest.

The MCP did not generate these files because discovery reports
`autorouter_dsn_export=false`, the Freerouting adapter is not configured, and the current
server has no active DipTrace GUI session. `autorouter_ses_import=true` does not authorize
inventing a SES or importing one that does not exist.
