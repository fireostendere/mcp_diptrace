[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$ManifestPath
)

$ErrorActionPreference = "Stop"
$ProductId = "diptrace-mcp"
$AllowedOwnedStatePaths = @(
    "logs",
    "sessions",
    "records",
    "offline_backups",
    "codex_setup.txt"
)

function Normalize-Path([string]$Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
}

function Test-PathWithin([string]$Path, [string]$Root) {
    $candidate = Normalize-Path $Path
    $parent = Normalize-Path $Root
    return $candidate.Equals($parent, [StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith(
            $parent + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        )
}

$manifestTarget = Normalize-Path $ManifestPath
if (-not (Test-Path -LiteralPath $manifestTarget -PathType Leaf)) {
    throw "Installation manifest is missing; refusing state removal: $manifestTarget"
}
try {
    $manifest = Get-Content -LiteralPath $manifestTarget -Raw | ConvertFrom-Json
} catch {
    throw "Installation manifest is invalid; refusing state removal: $manifestTarget"
}
if ($manifest.schema_version -ne 2 -or
    $manifest.product_id -ne $ProductId -or
    -not $manifest.installation_id -or
    -not $manifest.state_dir -or
    -not $manifest.state_marker_file) {
    throw "Installation manifest lacks the required ownership contract"
}

$root = Normalize-Path ([string]$manifest.state_dir)
$driveRoot = [IO.Path]::GetPathRoot($root).TrimEnd('\', '/')
$userProfile = if ($env:USERPROFILE) { Normalize-Path $env:USERPROFILE } else { "" }
if ([string]::IsNullOrWhiteSpace($root) -or
    $root.Equals($driveRoot, [StringComparison]::OrdinalIgnoreCase) -or
    ($userProfile -and $root.Equals($userProfile, [StringComparison]::OrdinalIgnoreCase))) {
    throw "Refusing to remove a broad state path: $root"
}

$markerRelative = [string]$manifest.state_marker_file
if ([IO.Path]::IsPathRooted($markerRelative) -or $markerRelative -match '(^|[\\/])\.\.([\\/]|$)') {
    throw "Invalid state marker path in installation manifest"
}
$markerPath = Normalize-Path (Join-Path $root $markerRelative)
if (-not (Test-PathWithin $markerPath $root) -or
    -not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
    throw "State ownership marker is missing or escaped the state root; refusing removal"
}
try {
    $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json
} catch {
    throw "State ownership marker is invalid; refusing removal: $markerPath"
}
if ($marker.product_id -ne $ProductId -or
    [string]$marker.installation_id -ne [string]$manifest.installation_id -or
    -not (Normalize-Path ([string]$marker.state_dir)).Equals($root, [StringComparison]::OrdinalIgnoreCase)) {
    throw "State ownership marker does not match the installation manifest"
}

foreach ($relativeValue in @($manifest.owned_state_paths)) {
    $relative = [string]$relativeValue
    if ($relative -notin $AllowedOwnedStatePaths) {
        throw "Installation manifest requested an unapproved state path: $relative"
    }
    if ([string]::IsNullOrWhiteSpace($relative) -or
        [IO.Path]::IsPathRooted($relative) -or
        $relative -match '(^|[\\/])\.\.([\\/]|$)') {
        throw "Invalid owned state path in installation manifest: $relative"
    }
    $target = Normalize-Path (Join-Path $root $relative)
    if (-not (Test-PathWithin $target $root) -or
        $target.Equals($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Owned state target escaped the selected state directory: $relative"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Remove-Item -LiteralPath $markerPath -Force
if ((Test-Path -LiteralPath $root -PathType Container) -and
    @(Get-ChildItem -LiteralPath $root -Force).Count -eq 0) {
    Remove-Item -LiteralPath $root -Force
}
