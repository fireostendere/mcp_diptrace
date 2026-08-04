[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Workspace,
    [ValidateSet("codex", "claude", "both", "none")] [string]$Client = "none",
    [string]$StateDir = (Join-Path $env:LOCALAPPDATA "DipTraceMCP"),
    [string]$DipTraceDir,
    [switch]$ServerOnly
)

$ErrorActionPreference = "Stop"
$BundleRoot = Split-Path -Parent $PSScriptRoot
$Server = Join-Path $BundleRoot "app\diptrace_mcp_server.exe"
$Configurator = Join-Path $BundleRoot "tools\diptrace_mcp_configure\diptrace_mcp_configure.exe"
$InstallPlugin = Join-Path $BundleRoot "tools\install_plugin.ps1"
$UninstallPlugin = Join-Path $BundleRoot "tools\uninstall_plugin.ps1"
$Bridge = Join-Path $BundleRoot "bridge\diptrace_mcp_bridge.exe"

foreach ($required in @($Server, $Configurator, $InstallPlugin, $UninstallPlugin, $Bridge)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Portable bundle is incomplete: $required"
    }
}

$workspacePath = [IO.Path]::GetFullPath($Workspace)
$statePath = [IO.Path]::GetFullPath($StateDir)
New-Item -ItemType Directory -Force -Path $workspacePath, $statePath | Out-Null

& $Server --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Portable standalone server verification failed" }

$pluginInstalled = $false
try {
    if (-not $ServerOnly -and $DipTraceDir) {
        & $InstallPlugin -DipTraceDir $DipTraceDir -Mode All -BridgeExe $Bridge
        if ($LASTEXITCODE -ne 0) { throw "Portable DipTrace integration failed" }
        $pluginInstalled = $true
    }

    if ($Client -ne "none") {
        $arguments = @(
            "--client", $Client,
            "--workspace", $workspacePath,
            "--state-dir", $statePath,
            "--server", $Server,
            "--json"
        )
        & $Configurator @arguments
        if ($LASTEXITCODE -ne 0) { throw "Portable MCP client configuration failed" }
    }
} catch {
    if ($pluginInstalled -and $DipTraceDir) {
        try {
            & $UninstallPlugin -DipTraceDir $DipTraceDir -InstallScript $InstallPlugin
        } catch {
            Write-Warning "Automatic plug-in rollback failed; remove only DipTraceMCP plug-in directories manually."
        }
    }
    throw
}

Write-Host "DipTrace MCP portable setup completed. Restart the selected MCP client." -ForegroundColor Green
