# Transactions

State machine: `planned -> staged -> validated -> committed`. A transaction may move to
`rolled_back` from an allowed state; an error moves it to `failed`.

## Pipeline

1. `begin_transaction` records the document ID, source SHA, and immutable snapshot.
2. `stage_operations` accepts only typed semantic operations.
3. `preview_transaction` compiles changes against a clone into byte-span patches over the
   original XML, reparses the result, and produces XML diff, SVG, and JSON previews.
4. Validation compares connectivity and DRC errors before and after the change.
5. `commit_transaction` requires an exact expected SHA, creates a backup, and performs an atomic write.
6. The document is reparsed after the write; the backup is restored if an exception occurs.
7. `rollback_transaction` checks for conflicts and restores the snapshot or backup.

A single high-level operation may contain many XML patches while remaining one
transaction. Unknown XML and original formatting outside modified nodes are preserved
byte-for-byte. Existing attribute and text changes patch only their raw spans; new
subtrees are serialized from typed operations. After compilation, the reparsed tree is
compared with the mutated domain/XML model. A mismatch fails instead of being written.
The low-level `apply_xml_edits` tool uses the same raw-preserving approach and remains a
separate expert API limited to 50 edits.

## Semantic Operations v1

- component and part move, rotate, side, lock, value, fields, pattern, and group operations;
- text move, rotate, visibility, and style operations;
- schematic no-connect and net rename;
- NetClass, differential-pair, and length rules, plus net assignment;
- test-point add, move, and remove;
- trace/via add, replace, move, delete, and style operations.

## Resources

`summary`, `operations`, `diff`, `preview.svg`, and `preview.json` are available at
`diptrace://transaction/{txid}/...`. PNG output is not advertised.
