[CmdletBinding()]
param(
    [string]$Version = "0.2.1",
    [string]$PythonCommand = "py",
    [string]$BridgePath,
    [string]$IsccPath,
    [string]$OutputDir = "dist\windows-artifacts",
    [switch]$NoGeometry,
    [switch]$SkipBuild,
    [switch]$SigningRequired,
    [string]$ExpectedSignerSubject = $env:EXPECTED_SIGNER_SUBJECT
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutputRoot = [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))
$Stage = Join-Path ([IO.Path]::GetTempPath()) ("diptrace-mcp-installer-" + [guid]::NewGuid().ToString("N"))
$ServerDist = Join-Path $RepoRoot "dist\windows-server\diptrace_mcp_server"
$ConfiguratorDist = Join-Path $RepoRoot "dist\windows-configurator\diptrace_mcp_configure"
$BridgeDefault = Join-Path $RepoRoot "plugin\dist\diptrace_mcp_bridge.exe"
$InstallerDir = Join-Path $OutputRoot "installer"
$PortableDir = Join-Path $OutputRoot "portable"
$InstallerOutput = Join-Path $InstallerDir ("DipTrace-MCP-Setup-{0}.exe" -f $Version)
$PortableOutput = Join-Path $PortableDir ("DipTrace-MCP-Portable-{0}.zip" -f $Version)

function Assert-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label is missing: $Path" }
}

function Assert-Directory([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "$Label is missing: $Path" }
}

function Invoke-Checked([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code ${LASTEXITCODE}: $File" }
}

function Relative-PortablePath([string]$Root, [string]$Path) {
    return $Path.Substring($Root.Length + 1).Replace('\', '/')
}

function Write-ShaManifest([string]$Root) {
    $lines = @()
    foreach ($file in Get-ChildItem -LiteralPath $Root -File -Recurse | Sort-Object FullName) {
        $relative = Relative-PortablePath $Root $file.FullName
        if ($relative -eq 'SHA256SUMS.txt') { continue }
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $lines += "$hash  $relative"
    }
    [IO.File]::WriteAllLines((Join-Path $Root 'SHA256SUMS.txt'), $lines, [Text.UTF8Encoding]::new($false))
}

function Write-ReleaseAssetShaManifest([string]$Path, [string[]]$Assets) {
    $lines = foreach ($asset in $Assets) {
        Assert-File $asset 'release asset'
        $hash = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $([IO.Path]::GetFileName($asset))"
    }
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

function Test-StagedBundle([string]$Root) {
    Assert-File (Join-Path $Root 'app\diptrace_mcp_server.exe') 'standalone server'
    Assert-File (Join-Path $Root 'bridge\diptrace_mcp_bridge.exe') 'bridge'
    Assert-File (Join-Path $Root 'tools\diptrace_mcp_configure\diptrace_mcp_configure.exe') 'configurator'
    Assert-File (Join-Path $Root 'tools\install_portable.ps1') 'portable installer helper'
    foreach ($name in @('pcb.settings.xml', 'schematic.settings.xml', 'component.settings.xml', 'pattern.settings.xml')) {
        Assert-File (Join-Path $Root ("settings-templates\$name")) "settings template $name"
        Assert-File (Join-Path $Root ("tools\settings\$name")) "portable plugin setting $name"
    }
    foreach ($file in Get-ChildItem -LiteralPath $Root -File -Recurse) {
        $relative = Relative-PortablePath $Root $file.FullName
        if ($relative -match '(?i)(^|/)(tests?|\.git|source_pdfs?|extracted_text|\.local)(/|$)' -or
            $relative -match '(?i)\.pdf$') {
            throw "Forbidden file in Windows bundle: $relative"
        }
    }
}

function Assert-Signature([string]$Path, [bool]$Required) {
    $verify = Join-Path $RepoRoot 'plugin\verify_signature.ps1'
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $verify, '-Path', $Path)
    if ($Required) {
        $args += '-Required'
        if (-not [string]::IsNullOrWhiteSpace($ExpectedSignerSubject)) {
            $args += @('-ExpectedSubject', $ExpectedSignerSubject)
        }
    }
    Invoke-Checked 'powershell' $args
}

try {
    if (-not $SkipBuild) {
        $serverArgs = @('-ExecutionPolicy', 'Bypass', '-File', (Join-Path $RepoRoot 'scripts\build_windows_server.ps1'), '-PythonCommand', $PythonCommand, '-OutputDir', 'dist\windows-server', '-Clean')
        if ($NoGeometry) { $serverArgs += '-NoGeometry' }
        Invoke-Checked 'powershell' $serverArgs
        Invoke-Checked 'powershell' @('-ExecutionPolicy', 'Bypass', '-File', (Join-Path $RepoRoot 'scripts\build_windows_configurator.ps1'), '-PythonCommand', $PythonCommand, '-OutputDir', 'dist\windows-configurator', '-Clean')
        Invoke-Checked 'powershell' @('-ExecutionPolicy', 'Bypass', '-File', (Join-Path $RepoRoot 'plugin\build_bridge.ps1'), '-PythonCommand', $PythonCommand, '-Clean')
    }

    Assert-Directory $ServerDist 'standalone server distribution'
    Assert-Directory $ConfiguratorDist 'configurator distribution'
    if ([string]::IsNullOrWhiteSpace($BridgePath)) { $BridgePath = $BridgeDefault }
    $BridgePath = [IO.Path]::GetFullPath($BridgePath)
    Assert-File $BridgePath 'bridge executable'

    Assert-Signature $BridgePath ([bool]$SigningRequired)
    Assert-Signature (Join-Path $ServerDist 'diptrace_mcp_server.exe') ([bool]$SigningRequired)
    Assert-Signature (Join-Path $ConfiguratorDist 'diptrace_mcp_configure.exe') ([bool]$SigningRequired)

    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Stage | Out-Null
    Copy-Item -LiteralPath $ServerDist -Destination (Join-Path $Stage 'app') -Recurse
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'bridge') | Out-Null
    Copy-Item -LiteralPath $BridgePath -Destination (Join-Path $Stage 'bridge\diptrace_mcp_bridge.exe')
    Copy-Item -LiteralPath $ConfiguratorDist -Destination (Join-Path $Stage 'tools\diptrace_mcp_configure') -Recurse
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'tools\settings') | Out-Null
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'plugin\settings\*.xml') -Destination (Join-Path $Stage 'tools\settings')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'plugin\install_plugin.ps1') -Destination (Join-Path $Stage 'tools')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'plugin\uninstall_plugin.ps1') -Destination (Join-Path $Stage 'tools')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\install_portable.ps1') -Destination (Join-Path $Stage 'tools')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\remove_owned_state.ps1') -Destination (Join-Path $Stage 'tools')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\write_installation_manifest.ps1') -Destination (Join-Path $Stage 'tools')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\README_FIRST.txt') -Destination $Stage
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'LICENSE') -Destination $Stage
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'docs') | Out-Null
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'SECURITY.md') -Destination (Join-Path $Stage 'docs')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\INSTALL_FROM_RELEASE.md') -Destination (Join-Path $Stage 'docs')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\SECURITY_AND_POLICY.md') -Destination (Join-Path $Stage 'docs')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\compliance\THIRD_PARTY_NOTICES.md') -Destination (Join-Path $Stage 'docs')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\compliance\dependency-inventory.json') -Destination (Join-Path $Stage 'docs')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\compliance\sbom.cdx.json') -Destination (Join-Path $Stage 'docs')
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'docs\compliance\PROVENANCE_INVENTORY.csv') -Destination (Join-Path $Stage 'docs')

    Test-StagedBundle $Stage
    Write-ShaManifest $Stage

    New-Item -ItemType Directory -Force -Path $InstallerDir | Out-Null
    New-Item -ItemType Directory -Force -Path $PortableDir | Out-Null

    if ([string]::IsNullOrWhiteSpace($IsccPath)) {
        $candidate = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
        if (Test-Path -LiteralPath $candidate) { $IsccPath = $candidate }
    }
    if ([string]::IsNullOrWhiteSpace($IsccPath)) { throw 'ISCC.exe was not found; pass -IsccPath' }
    Assert-File $IsccPath 'Inno Setup compiler'

    $iss = Join-Path $RepoRoot 'installer\DipTraceMCP.iss'
    Invoke-Checked $IsccPath @("/DAppVersion=$Version", "/DStageDir=$Stage", "/DOutputDir=$InstallerDir", $iss)
    Assert-File $InstallerOutput 'installer output'
    Assert-Signature $InstallerOutput ([bool]$SigningRequired)

    if (Test-Path -LiteralPath $PortableOutput) { Remove-Item -LiteralPath $PortableOutput -Force }
    Compress-Archive -LiteralPath (Join-Path $Stage '*') -DestinationPath $PortableOutput -CompressionLevel Optimal
    Assert-File $PortableOutput 'portable output'

    Write-ReleaseAssetShaManifest (Join-Path $OutputRoot 'SHA256SUMS.txt') @($InstallerOutput, $PortableOutput)

    Write-Host "Installer: $InstallerOutput"
    Write-Host "Portable: $PortableOutput"
    Write-Host "Checksums: $(Join-Path $OutputRoot 'SHA256SUMS.txt')"
}
finally {
    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
