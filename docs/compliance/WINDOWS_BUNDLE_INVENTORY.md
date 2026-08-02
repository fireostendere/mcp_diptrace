# Windows bridge bundle inventory

Status checked: 2026-08-02

This Linux/WSL audit host has no Windows runner or PowerShell, so it does not
claim to have built or signed `diptrace_mcp_bridge.exe`. The current expected
state is an unsigned development bridge. No new EXE or plugin ZIP is committed.

The manual `deep-compliance-audit.yml` workflow performs the missing evidence:

1. build the bridge from the checked-out commit using the repository's
   `plugin/build_bridge.ps1`;
2. run `diptrace_mcp_bridge.exe --help`;
3. run `pyi-archive_viewer --recursive` and normalize the listing with
   `scripts/summarize_pyinstaller_inventory.py`;
4. classify Python modules, DLL/native files, embedded metadata/licenses, and
   unexpected files;
5. run `Get-AuthenticodeSignature` and retain only sanitized status output;
6. set `SIGNING_REQUIRED=true` against the unsigned build and require a
   non-zero result from `plugin/verify_signature.ps1`.

The resulting inventory is sorted before comparison. It is an engineering
inventory, not a signing assertion or legal clearance. PyInstaller's own
bootloader and transitive bundled libraries remain subject to human review.
