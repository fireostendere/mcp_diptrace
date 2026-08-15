DipTrace MCP — Windows no-Python bundle

Recommended path
----------------
Run DipTrace-MCP-Setup-0.3.0.exe and follow the wizard.

Portable fallback
-----------------
1. Extract the ZIP to a user-owned directory.
2. Open PowerShell in the extracted directory.
3. Run, for example:

   powershell -ExecutionPolicy Bypass -File .\tools\install_portable.ps1 `
     -Workspace "$HOME\Documents\DipTrace" `
     -Client codex `
     -ServerOnly

For DipTrace plug-in integration, omit -ServerOnly and add:

   -DipTraceDir "C:\Program Files\DipTrace5"

A protected Program Files target requires an elevated PowerShell window. The
portable helper uses bridge\diptrace_mcp_bridge.exe and the configurator at
tools\diptrace_mcp_configure\diptrace_mcp_configure.exe. It rolls back plug-in
files when later client configuration fails.

The bundle does not download code, install Python, or change Defender or
SmartScreen. Development artifacts are unsigned unless the release record says
otherwise. Verify the external release SHA256SUMS.txt before extraction. Projects
are never removed by the helper or installer.
