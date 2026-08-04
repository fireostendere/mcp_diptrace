# Windows signing preparation

## Status

The Windows bridge, standalone server, portable ZIP, and installer are currently unsigned. This document
describes the technical boundary for future SignPath integration; it does not
claim a SignPath account, organization, project, policy, certificate, signed
artifact, or vendor approval.

The normal PR CI remains independent of signing credentials. Signing is a
manual or protected-release operation and must never make ordinary tests pass
by weakening a safety or packaging check.

## Pipeline boundary

Keep these stages distinct:

1. build the bridge from the exact source commit;
2. run the Windows tests and `--help` smoke test;
3. retain the unsigned executable as a clearly labelled intermediate artifact;
4. submit that exact artifact through a protected SignPath integration;
5. verify the returned Authenticode signature, expected signer subject, and
   timestamp;
6. package the verified executable with the installer, four settings profiles,
   license, and exchange-path/install guidance; and
7. calculate checksums and publish only after the release approval gates pass.

The ordinary development workflow builds unsigned artifacts without requiring
SignPath credentials. The installer and server carry explicit unsigned status
in their build metadata; a SHA-256 match proves file identity, not trust. The
portable ZIP also carries `SHA256SUMS.txt` and `artifact-inventory.json`.

The repository provides `plugin/verify_signature.ps1` and
`plugin/package_plugin.ps1` for stages 5–7. With no signing requirement,
`package_plugin.ps1` explicitly permits `NotSigned` and the output remains an
unsigned development artifact. With `-RequireSigned` or
`SIGNING_REQUIRED=true`, it requires a valid signature, a non-empty expected
signer subject, and an Authenticode timestamp. If `signtool.exe` is available,
it also runs `signtool verify /pa /v`.

## Configuration boundary

Use environment variables or protected GitHub variables/secrets only; never
commit their values. Direct packaging treats `SIGNING_REQUIRED=true` exactly
like `-RequireSigned`; unknown values fail closed:

```text
SIGNPATH_ORGANIZATION_ID     # protected variable; not a public identifier
SIGNPATH_PROJECT_ID          # protected variable
SIGNPATH_SIGNING_POLICY_ID   # protected variable
SIGNPATH_API_TOKEN           # protected secret
EXPECTED_SIGNER_SUBJECT      # protected variable, exact certificate subject
SIGNING_REQUIRED             # false for development, true for approved release
```

The public workflow `.github/workflows/windows-signing.yml` is manual and
contains only a protected handoff placeholder. It refuses to pretend that a
SignPath request occurred until the owner wires and reviews the approved
SignPath integration. Account registration, identity verification, project
creation, policy selection, certificate issuance, and real IDs belong in the
owner-only checklist outside Git.

## Verification examples

Unsigned development artifact:

```powershell
.\plugin\verify_signature.ps1 `
  -Path .\plugin\dist\diptrace_mcp_bridge.exe
```

Release-gated artifact:

```powershell
$env:EXPECTED_SIGNER_SUBJECT = "<configured protected value>"
.\plugin\verify_signature.ps1 `
  -Path .\plugin\dist\diptrace_mcp_bridge.exe `
  -ExpectedSignerSubject $env:EXPECTED_SIGNER_SUBJECT `
  -RequireSigned
```

The placeholder subject above is not a certificate identity. A release record
must bind the signed file hash to the exact source commit, CI run, signing
request, signer subject, timestamp, package hash, and checksum manifest.

Inno Setup is a maintainer/CI prerequisite, never an end-user download. The
repository records version `6.4.2`, its official download URL, and the expected
SHA-256 in [`packaging/inno_setup_prerequisite.json`](../packaging/inno_setup_prerequisite.json);
CI must verify the hash before invoking `ISCC.exe`.

## Human review gates

Before enabling `SIGNING_REQUIRED=true`, the owner must confirm the SignPath
integration, protected environment, least-privilege permissions, reviewer
approval, signer subject, timestamp authority, artifact retention, and rollback
procedure. No public documentation may say that a binary is signed until the
signature verification output is retained for that exact artifact.
