# Windows bridge bundle inventory

Status checked: 2026-08-03

This Linux/WSL audit host has no Windows runner or PowerShell, so it does not
claim to have built or signed the Windows server, bridge, portable ZIP, or
installer. The current expected state is unsigned development artifacts. No
EXE, ZIP, or installer output is committed.

The unified bundle is staged as `app/` (PyInstaller onedir server), `bridge/`
(the existing bridge artifact), `settings-templates/`, and `tools/` (the
standalone configurator and narrow PowerShell helpers). The server spec
explicitly collects the package, MCP SDK/Pydantic metadata, packaged skills,
schemas, and optional Shapely/GEOS; tests, source PDFs, extracted text, local
materials, secrets, and dev-only packages are excluded. The portable audit
requires the four settings profiles, exact SHA-256 coverage, and rejects the
forbidden classes.

The manual `deep-compliance-audit.yml` workflow performs the missing evidence:

1. build the standalone server with `packaging/diptrace_mcp_server.spec`;
2. build the existing bridge from the checked-out commit using
   `plugin/build_bridge.ps1` and run `diptrace_mcp_bridge.exe --help`;
3. build the configurator and stage the Inno Setup installer plus portable ZIP;
4. run the portable inventory/checksum audit and frozen MCP stdio smoke;
5. run silent install, repair, upgrade simulation, uninstall, state-retention,
   Unicode/spaced-path, and four-settings checks;
6. run `Get-AuthenticodeSignature` on the generated artifacts and require a
   non-zero result from `plugin/verify_signature.ps1 -RequireSigned` for the
   unsigned development path.

The resulting inventory is sorted before comparison. It is an engineering
inventory, not a signing assertion or legal clearance. PyInstaller's own
bootloader and transitive bundled libraries remain subject to human review.
