[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BridgePath,
    [Parameter(Mandatory = $true)]
    [string]$OutputZip,
    [string]$ExpectedSignerSubject = $env:EXPECTED_SIGNER_SUBJECT,
    [switch]$RequireSigned
)

$ErrorActionPreference = "Stop"
$PluginDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $PluginDir
$Verifier = Join-Path $PluginDir "verify_signature.ps1"
$ResolvedOutput = [IO.Path]::GetFullPath($OutputZip)
$Stage = Join-Path ([IO.Path]::GetTempPath()) ("diptrace-mcp-plugin-" + [guid]::NewGuid().ToString("N"))

try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Verifier `
        -Path $BridgePath `
        -ExpectedSignerSubject $ExpectedSignerSubject `
        -RequireSigned:$RequireSigned | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Bridge signature verification failed"
    }

    New-Item -ItemType Directory -Force -Path $Stage, (Join-Path $Stage "settings") | Out-Null
    Copy-Item -LiteralPath $BridgePath -Destination (Join-Path $Stage "diptrace_mcp_bridge.exe")
    Copy-Item -LiteralPath (Join-Path $RepoRoot "LICENSE") -Destination (Join-Path $Stage "LICENSE")
    Copy-Item -LiteralPath (Join-Path $PluginDir "install_plugin.ps1") -Destination (Join-Path $Stage "install_plugin.ps1")
    Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\INSTALL_FROM_RELEASE.md") -Destination (Join-Path $Stage "INSTALL_FROM_RELEASE.md")
    Copy-Item -LiteralPath (Join-Path $RepoRoot "docs\LIVE_EXCHANGE_PATHS.md") -Destination (Join-Path $Stage "LIVE_EXCHANGE_PATHS.md")
    Copy-Item -LiteralPath (Join-Path $PluginDir "settings\*.settings.xml") -Destination (Join-Path $Stage "settings")
    Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $ResolvedOutput -Force
    Get-FileHash -LiteralPath $ResolvedOutput -Algorithm SHA256 | Format-Table -AutoSize
}
finally {
    if (Test-Path -LiteralPath $Stage) {
        Remove-Item -LiteralPath $Stage -Recurse -Force
    }
}
