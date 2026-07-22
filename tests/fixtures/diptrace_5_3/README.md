# Deferred DipTrace 5.3 Evidence Pack

This directory reserves the public fixture layout described in `docs/ROADMAP.md`. Do not
commit installed DipTrace examples or derived exports here until redistribution permission
is clear. Prefer small project files created specifically for this repository.

When evidence is available, add `manifest.json` conforming to `manifest.schema.json` and
the following groups:

- `hierarchy/`
- `pours/`
- `libraries/`
- `schematic_roundtrip/<case>/`
- `geometry/`
- `specctra/`

Keep exported XML, DSN, and SES bytes unchanged. Record any controlled GUI change in the
manifest rather than editing the fixture manually. CI should validate hashes before using
the files.
