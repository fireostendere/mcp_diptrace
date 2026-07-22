# Synthetic four-layer power fixture

This directory contains a wholly synthetic PCB generated through DipTrace MCP semantic
operations. It is a pre-fixture for validating four-layer parsing, placement, mirrored
Bottom components, traces, via spans, copper-pour refill evidence and a real Specctra
DSN/SES round trip.

The current source is intentionally **not** a completed DipTrace 5.3 fixture pack:

- `source_board.xml` is MCP-generated DipTrace PCB XML format 4.3.0.3;
- `preview.svg` and `preview.json` are MCP previews of that exact source SHA;
- `specctra/source_board.xml` is an identical frozen copy awaiting a DipTrace 5.3.0.2
  open/save before DSN export;
- authoritative pour-before/refill-after XML and real DSN/SES artifacts are absent;
- `manifest.pending.json` is a draft and must not be renamed until the missing evidence
  exists and validates against `../manifest.schema.json`.

`SENSE` is deliberately left without a trace. Its Top-to-Bottom endpoints make it the
primary Freerouting/via exercise. GND and passive power branches also retain unresolved
connectivity for pour and autorouter coverage. The MCP route primitives preserve original
ratline XML, so `list_unrouted_connections` is not used alone as proof of physical routing;
the expected files record the route-details and connectivity-review contract.
