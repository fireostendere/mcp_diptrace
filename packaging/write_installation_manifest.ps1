[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath,
    [Parameter(Mandatory = $true)] [string]$AppRoot,
    [Parameter(Mandatory = $true)] [string]$Version,
    [Parameter(Mandatory = $true)] [string]$StateDir,
    [string[]]$PluginRoots = @()
)

$ErrorActionPreference = "Stop"
$ProductId = "diptrace-mcp"
$MarkerName = ".diptrace-mcp-state-owner.json"
$OwnedStatePaths = @("logs", "sessions", "records", "offline_backups", "codex_setup.txt")

function Normalize-Path([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Test-PathWithin([string]$Path, [string]$Root) {
    if ([string]::IsNullOrWhiteSpace($Root)) { return $false }
    $candidate = Normalize-Path $Path
    $parent = Normalize-Path $Root
    return $candidate.Equals($parent, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith(
            $parent + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
}

function Write-AtomicJson([string]$Path, [object]$Value) {
    $target = Normalize-Path $Path
    $parent = Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temporary = Join-Path $parent ("." + [IO.Path]::GetFileName($target) + "." + [guid]::NewGuid().ToString("N") + ".tmp")
    $backup = Join-Path $parent ("." + [IO.Path]::GetFileName($target) + "." + [guid]::NewGuid().ToString("N") + ".bak")
    try {
        $json = $Value | ConvertTo-Json -Depth 8
        [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            [IO.File]::Replace($temporary, $target, $backup, $true)
        } else {
            [IO.File]::Move($temporary, $target)
        }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
    Get-Content -LiteralPath $target -Raw | ConvertFrom-Json | Out-Null
}

$app = Normalize-Path $AppRoot
$state = Normalize-Path $StateDir
$manifestTarget = Normalize-Path $ManifestPath
$driveRoot = [IO.Path]::GetPathRoot($state).TrimEnd('\', '/')
$userProfile = if ($env:USERPROFILE) { Normalize-Path $env:USERPROFILE } else { "" }
if ([string]::IsNullOrWhiteSpace($state) -or
    $state.Equals($driveRoot, [StringComparison]::OrdinalIgnoreCase) -or
    ($userProfile -and $state.Equals($userProfile, [StringComparison]::OrdinalIgnoreCase)) -or
    (Test-PathWithin $state $app)) {
    throw "Refusing unsafe state directory ownership: $state"
}
foreach ($protected in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if ($protected -and (Test-PathWithin $state $protected)) {
        throw "State must not be stored under Program Files: $state"
    }
}

if (Test-Path -LiteralPath $state) {
    if (-not (Test-Path -LiteralPath $state -PathType Container)) {
        throw "State path is not a directory: $state"
    }
} else {
    New-Item -ItemType Directory -Force -Path $state | Out-Null
}

$markerPath = Join-Path $state $MarkerName
$installationId = $null
if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
    } catch {
        throw "State ownership marker is invalid and was not replaced: $markerPath"
    }
    if ($marker.product_id -ne $ProductId -or
        -not $marker.installation_id -or
        -not (Normalize-Path ([string]$marker.state_dir)).Equals($state, [StringComparison]::OrdinalIgnoreCase)) {
        throw "State ownership marker does not belong to this DipTrace MCP state root: $markerPath"
    }
    $installationId = [string]$marker.installation_id
} else {
    $entries = @(Get-ChildItem -LiteralPath $state -Force -ErrorAction Stop)
    if ($entries.Count -ne 0) {
        throw "Refusing to claim a non-empty state directory without a DipTrace MCP ownership marker: $state"
    }
    $installationId = [guid]::NewGuid().ToString("D")
    $marker = [ordered]@{
        schema_version = 1
        product_id = $ProductId
        installation_id = $installationId
        state_dir = $state
        created_by = "DipTrace-MCP Inno Setup"
    }
    Write-AtomicJson -Path $markerPath -Value $marker
}

$manifest = [ordered]@{
    schema_version = 2
    product_id = $ProductId
    version = $Version
    installation_id = $installationId
    app_root = $app
    state_dir = $state
    state_marker_file = $MarkerName
    plugin_roots = @($PluginRoots | Where-Object { $_ } | ForEach-Object { Normalize-Path $_ })
    owned_state_paths = $OwnedStatePaths
    created_by = "DipTrace-MCP Inno Setup"
}
Write-AtomicJson -Path $manifestTarget -Value $manifest
