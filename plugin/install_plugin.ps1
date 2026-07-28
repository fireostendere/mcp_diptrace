param(
    [string]$DipTraceDir,
    [ValidateSet("PCB", "Schematic", "Component", "Pattern", "Libraries", "Both", "All")]
    [string]$Mode = "All",
    [string]$BridgeExe,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$PluginDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $BridgeExe) {
    $BridgeExe = Join-Path $PluginDir "dist\diptrace_mcp_bridge.exe"
}

function Test-IsElevated {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
    return $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-IsPathWithin {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [string]$Root
    )

    if ([string]::IsNullOrWhiteSpace($Root)) {
        return $false
    }
    $FullPath = [IO.Path]::GetFullPath($Path).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $FullRoot = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    return $FullPath.Equals($FullRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $FullPath.StartsWith(
            $FullRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
}

function Assert-CopiedFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw "Post-copy verification failed for $Label`: destination is missing: $Destination"
    }
    $SourceHash = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash
    $DestinationHash = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
    if (-not $SourceHash.Equals($DestinationHash, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Post-copy verification failed for $Label`: SHA-256 mismatch at $Destination"
    }
}

if (-not $DipTraceDir) {
    $InstallCandidates = @(
        (Join-Path $env:ProgramFiles "DipTrace5"),
        (Join-Path $env:ProgramFiles "DipTrace")
    )
    $DipTraceDir = $InstallCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Container } |
        Select-Object -First 1
    if (-not $DipTraceDir) {
        throw "DipTrace installation not found. Pass -DipTraceDir explicitly."
    }
}

if (-not (Test-Path -LiteralPath $DipTraceDir -PathType Container)) {
    throw "DipTrace directory not found: $DipTraceDir"
}

$ProtectedRoots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Select-Object -Unique
$RequiresElevation = $false
foreach ($ProtectedRoot in $ProtectedRoots) {
    if (Test-IsPathWithin -Path $DipTraceDir -Root $ProtectedRoot) {
        $RequiresElevation = $true
        break
    }
}
if ($RequiresElevation -and -not (Test-IsElevated)) {
    throw (
        "Administrator elevation is required to install or remove the plug-in under " +
        "$DipTraceDir. Reopen PowerShell with 'Run as administrator'."
    )
}

$Targets = @()
if ($Mode -in @("PCB", "Both", "All")) {
    $Targets += @{
        Name = "PCB Layout"
        Directory = Join-Path $DipTraceDir "Plugins\Pcb\DipTraceMCP"
        Settings = Join-Path $PluginDir "settings\pcb.settings.xml"
    }
}
if ($Mode -in @("Schematic", "Both", "All")) {
    $Targets += @{
        Name = "Schematic Capture"
        Directory = Join-Path $DipTraceDir "Plugins\Schematic\DipTraceMCP"
        Settings = Join-Path $PluginDir "settings\schematic.settings.xml"
    }
}
if ($Mode -in @("Component", "Libraries", "All")) {
    $Targets += @{
        Name = "Component Editor (read-only import policy)"
        Directory = Join-Path $DipTraceDir "Plugins\CompEdit\DipTraceMCP"
        Settings = Join-Path $PluginDir "settings\component.settings.xml"
    }
}
if ($Mode -in @("Pattern", "Libraries", "All")) {
    $Targets += @{
        Name = "Pattern Editor (read-only import policy)"
        Directory = Join-Path $DipTraceDir "Plugins\PattEdit\DipTraceMCP"
        Settings = Join-Path $PluginDir "settings\pattern.settings.xml"
    }
}

if ($Uninstall) {
    foreach ($Target in $Targets) {
        Remove-Item -LiteralPath $Target.Directory -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Removed $($Target.Name) plug-in: $($Target.Directory)"
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $BridgeExe -PathType Leaf)) {
    throw "Bridge executable not found: $BridgeExe. Run plugin\build_bridge.ps1 first."
}

foreach ($Target in $Targets) {
    [xml](Get-Content -LiteralPath $Target.Settings -Raw) | Out-Null
    New-Item -ItemType Directory -Force -Path $Target.Directory | Out-Null
    $InstalledBridge = Join-Path $Target.Directory "diptrace_mcp_bridge.exe"
    $InstalledSettings = Join-Path $Target.Directory "settings.xml"
    Copy-Item -LiteralPath $BridgeExe -Destination $InstalledBridge -Force
    Copy-Item -LiteralPath $Target.Settings -Destination $InstalledSettings -Force
    Assert-CopiedFile -Source $BridgeExe -Destination $InstalledBridge -Label "bridge executable"
    Assert-CopiedFile -Source $Target.Settings -Destination $InstalledSettings -Label "settings"
    [xml](Get-Content -LiteralPath $InstalledSettings -Raw) | Out-Null
    Write-Host "Installed for $($Target.Name): $($Target.Directory)" -ForegroundColor Green
}

Write-Host "Restart the installed DipTrace modules, then use Tools > Plugins > DipTrace MCP Bridge."
