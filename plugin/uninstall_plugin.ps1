[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$DipTraceDir,
    [string]$InstallScript = (Join-Path $PSScriptRoot "install_plugin.ps1")
)

$ErrorActionPreference = "Stop"
& $InstallScript -DipTraceDir $DipTraceDir -Mode All -Uninstall
if ($LASTEXITCODE -ne 0) { throw "DipTrace MCP plug-in removal failed" }
