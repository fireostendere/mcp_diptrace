# Engineering memory

The durable engineering record has three layers:

1. `PCB_BUILD.md` and `SCHEMATIC_BUILD.md` are the authoritative live handoffs:
   gate status, exact SHAs, failure evidence, resume command, deviations, and
   checkpoint. A schematic-only run must not rewrite the PCB handoff.
2. `docs/engineering-memory/*.md` is an append-only retrieval mirror. It contains
   only quality-gate results and source-bound observations, not chat history or
   model guesses.
3. The external `mcp-rag` service indexes that directory for retrieval; it is a
   search layer, not an authority and never promotes a gate to `PASS`.

After updating a project's handoff, capture the current result:

```bash
PYTHONPATH=src .venv/bin/python scripts/record_quality_gate_memory.py . \
  --board dut-controller-reva-pcb.dipxml \
  --schematic dut-controller-reva.dchxml \
  --memory docs/engineering-memory/dut-controller-reva.md
```

The command is idempotent for the same handoff/artifact state. A blocked result
is still recorded, so the root cause and next action survive a new session. To
make it searchable in `mcp-rag`, ingest this directory once and repeat after
new events:

`CONSISTENT` means the handoff is mechanically coherent; pending/manual gates
remain listed and are not silently promoted to `PASS`.

```text
knowledge_ingest(source="/mnt/c/Users/fireo/mcp_diptrace/docs/engineering-memory")
knowledge_ingest(source="/mnt/c/Users/fireo/mcp_diptrace/PCB_BUILD.md")
```

Never record an unverified datasheet claim as a fact. Put the source, revision,
locator, units, and applicability in `PCB_BUILD.md` or a rule file first; the
RAG copy may retrieve it but cannot replace that evidence.

The DUT PCB routing stages now preserve the existing board. The no-argument
command is the explicit placement rebuild; `--manual`, `--route`, and
`--finish` operate on the current artifact and therefore can resume after a
failed gate without silently erasing prior routes.
