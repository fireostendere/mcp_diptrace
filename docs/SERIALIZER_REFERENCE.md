# Serializer-derived XML reference

The repository includes a machine-readable DipTrace XML reference at
`src/diptrace_mcp/data/serializer_reference.json` and a coding-agent skill at
`skills/diptrace-xml-reference/`.

The reference was distilled from documentation supplied to the project whose Markdown files
state that they were generated from or verified against DipTrace serializer repository revision
7276. Their exact SHA-256 fingerprints are stored in the JSON. The repository does not have an
independent way to authenticate that revision claim, so the material is deliberately classified
as `user_supplied_reference` with `trust_effect=none`.

This distinction is intentional:

- serializer reference can constrain enums, defaults, omission rules, import semantics, parser
  normalization, and regression tests;
- it cannot grant `diptrace_exported`, `diptrace_open_save_verified`,
  `diptrace_roundtrip_verified`, or `external_tool_roundtrip_verified`;
- capability discovery must not enable currently blocked library writers merely because a field
  is documented;
- real DipTrace 5.3 open/save/re-export fixture evidence remains the gate for native writer
  support.

Initial reconciliation against the reference identified three concrete Pattern Library parser
issues and regression coverage is included for them:

1. `MainStack Shape="Fiducial"` omits `Height`; the normalized copper geometry must use `Width`
   as both dimensions.
2. `PadStyle/Hole` on a Fiducial is a keepout diameter, not a drilled hole.
3. `MaskPaste CustomSwell="-1000"` and `CustomShrink="-1000"` are unset sentinels and must not
   become physical mask/paste offsets.

The agent skill also records high-risk edit-import rules such as `Enabled="N"` deletion,
Selected-filter behavior, nested-list replacement semantics, IDs for new versus existing
objects, radians versus discrete orientation/degrees, and textual `Layer` versus numeric `Lay`.
