# DipTrace MCP Inno Setup source

`DipTraceMCP.iss` is compiled with Inno Setup 6.4.2 (`ISCC.exe`). The build
wrapper requires the compiler to be present locally or on the pinned Windows
runner; it never downloads anything during a user's installation.

The installer itself runs as `PrivilegesRequired=lowest` and installs the
standalone bundle under `%LOCALAPPDATA%\Programs\DipTraceMCP`. Only the
DipTrace plug-in copy/removal helper is launched with `runas` when the selected
DipTrace root is protected. Client configuration always runs in the original
user context.
