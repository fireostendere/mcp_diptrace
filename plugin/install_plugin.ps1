param(
    [string]$DipTraceDir = "C:\Program Files\DipTrace",
    [ValidateSet("PCB", "Schematic", "Both")]
    [string]$Mode = "Both",
    [string]$BridgeExe,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$PluginDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $BridgeExe) {
    $BridgeExe = Join-Path $PluginDir "dist\diptrace_mcp_bridge.exe"
}

if (-not (Test-Path $DipTraceDir -PathType Container)) {
    throw "DipTrace directory not found: $DipTraceDir"
}

$Targets = @()
if ($Mode -in @("PCB", "Both")) {
    $Targets += @{
        Name = "PCB Layout"
        Directory = Join-Path $DipTraceDir "Plugins\Pcb\DipTraceMCP"
        Settings = Join-Path $PluginDir "settings\pcb.settings.xml"
    }
}
if ($Mode -in @("Schematic", "Both")) {
    $Targets += @{
        Name = "Schematic Capture"
        Directory = Join-Path $DipTraceDir "Plugins\Schematic\DipTraceMCP"
        Settings = Join-Path $PluginDir "settings\schematic.settings.xml"
    }
}

if ($Uninstall) {
    foreach ($Target in $Targets) {
        Remove-Item -Recurse -Force $Target.Directory -ErrorAction SilentlyContinue
        Write-Host "Removed $($Target.Name) plug-in: $($Target.Directory)"
    }
    exit 0
}

if (-not (Test-Path $BridgeExe -PathType Leaf)) {
    throw "Bridge executable not found: $BridgeExe. Run plugin\build_bridge.ps1 first."
}

foreach ($Target in $Targets) {
    [xml](Get-Content -Raw $Target.Settings) | Out-Null
    New-Item -ItemType Directory -Force $Target.Directory | Out-Null
    Copy-Item -Force $BridgeExe (Join-Path $Target.Directory "diptrace_mcp_bridge.exe")
    Copy-Item -Force $Target.Settings (Join-Path $Target.Directory "settings.xml")
    Write-Host "Installed for $($Target.Name): $($Target.Directory)" -ForegroundColor Green
}

Write-Host "Restart all DipTrace modules, then use Tools > Plugins > DipTrace MCP Bridge."
