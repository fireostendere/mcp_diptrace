## Scope

Explain the bounded change and the user-visible outcome. Link the issue or
decision record that authorized the work when one exists.

## DCO and provenance

- [ ] Every commit has a `Signed-off-by:` line under [`DCO`](../DCO).
- [ ] I disclosed the origin, license, and redistribution basis for code,
      fixtures, schemas, examples, documentation, and generated files.
- [ ] I disclosed meaningful AI assistance, if any, and described the human
      review performed.
- [ ] I remain responsible for correctness, security, provenance, and the
      right to redistribute the submitted work.

## Safety, security, and privacy

- [ ] Safety gates remain fail-closed.
- [ ] New DipTrace claims cite an official specification or controlled
      real-export evidence.
- [ ] Synthetic evidence is labelled as synthetic.
- [ ] Unknown XML and bytes outside the intended edit are preserved.
- [ ] No proprietary, customer, personal, secret, private, restricted, or
      submission/application material is included.
- [ ] Security-sensitive details are handled through `SECURITY.md`, not this
      pull request.

## Generated artifacts

- [ ] MCP tool snapshot changes were regenerated and reviewed, or no public
      tool descriptor changed.
- [ ] Specification inventory and format-coverage outputs were regenerated
      when their inputs changed.
- [ ] Compliance inventory, SBOM, provenance, and release allowlists were
      regenerated or checked when their inputs changed.
- [ ] Documentation and code claims remain equivalent.

## Verification

List the exact commands and environments used. State any platform, licensed
DipTrace, signing, or external-tool checks that were not run.

## Review notes

Explain error-contract, transaction, evidence-level, performance, signing,
packaging, and rollback effects. A passing round trip through this repository's
own reader and writer is not proof of a DipTrace convention.
