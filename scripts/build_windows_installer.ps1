[CmdletBinding()]
param(
    [string]$Version = "0.2.0",
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
    Assert-File (Join-Path $Root 'tools\diptrace_mcp_configure\_internal\python312.dll') 'configurator runtime'
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

try {
    if (-not $SkipBuild) {
        & (Join-Path $RepoRoot 'scripts\build_windows_server.ps1') `
            -PythonCommand $PythonCommand -OutputDir 'dist\windows-server' -Clean -NoGeometry:$NoGeometry
        if ($LASTEXITCODE -ne 0) { throw "Windows server build failed with exit code $LASTEXITCODE" }
        & (Join-Path $RepoRoot 'scripts\build_windows_configurator.ps1') `
            -PythonCommand $PythonCommand -OutputDir 'dist\windows-configurator' -Clean
        if ($LASTEXITCODE -ne 0) { throw "Windows configurator build failed with exit code $LASTEXITCODE" }
        if (-not $BridgePath) { $BridgePath = $BridgeDefault }
        if (-not (Test-Path -LiteralPath $BridgePath -PathType Leaf)) {
            & (Join-Path $RepoRoot 'plugin\build_bridge.ps1') -PythonCommand $PythonCommand -Clean
            if ($LASTEXITCODE -ne 0) { throw "Windows bridge build failed with exit code $LASTEXITCODE" }
        }
    }
    if (-not $BridgePath) { $BridgePath = $BridgeDefault }
    Assert-Directory $ServerDist 'server distribution'
    Assert-Directory $ConfiguratorDist 'configurator distribution'
    Assert-File $BridgePath 'bridge executable'

    New-Item -ItemType Directory -Force -Path $Stage, $InstallerDir, $PortableDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $Stage 'app'), (Join-Path $Stage 'bridge'), (Join-Path $Stage 'settings-templates'), (Join-Path $Stage 'tools'), (Join-Path $Stage 'tools\settings'), (Join-Path $Stage 'tools\diptrace_mcp_configure') | Out-Null
    Copy-Item -Path (Join-Path $ServerDist '*') -Destination (Join-Path $Stage 'app') -Recurse -Force
    Copy-Item -LiteralPath $BridgePath -Destination (Join-Path $Stage 'bridge\diptrace_mcp_bridge.exe') -Force
    Copy-Item -Path (Join-Path $RepoRoot 'plugin\settings\*') -Destination (Join-Path $Stage 'settings-templates') -Force
    Copy-Item -Path (Join-Path $RepoRoot 'plugin\settings\*') -Destination (Join-Path $Stage 'tools\settings') -Force
    Copy-Item -Path (Join-Path $ConfiguratorDist '*') -Destination (Join-Path $Stage 'tools\diptrace_mcp_configure') -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'plugin\install_plugin.ps1') -Destination (Join-Path $Stage 'tools\install_plugin.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'plugin\uninstall_plugin.ps1') -Destination (Join-Path $Stage 'tools\uninstall_plugin.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\install_portable.ps1') -Destination (Join-Path $Stage 'tools\install_portable.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\write_installation_manifest.ps1') -Destination (Join-Path $Stage 'tools\write_installation_manifest.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\remove_owned_state.ps1') -Destination (Join-Path $Stage 'tools\remove_owned_state.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'LICENSE') -Destination (Join-Path $Stage 'LICENSE') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'packaging\README_FIRST.txt') -Destination (Join-Path $Stage 'README_FIRST.txt') -Force
    [IO.File]::WriteAllText((Join-Path $Stage 'VERSION'), $Version + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    $template = [ordered]@{
        schema_version = 2
        product_id = 'diptrace-mcp'
        version = $Version
        state_marker_file = '.diptrace-mcp-state-owner.json'
        owned_install_relative_paths = @('app', 'bridge', 'settings-templates', 'tools', 'LICENSE', 'README_FIRST.txt', 'VERSION', 'installation-manifest.json')
        owned_state_paths = @('logs', 'sessions', 'records', 'offline_backups', 'codex_setup.txt')
        signing_status = if ($SigningRequired) { 'signed-required' } else { 'unsigned-until-verified' }
    }
    [IO.File]::WriteAllText((Join-Path $Stage 'installation-manifest.template.json'), ($template | ConvertTo-Json -Depth 4) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Test-StagedBundle $Stage
    $inventory = @(
        Get-ChildItem -LiteralPath $Stage -File -Recurse | Sort-Object FullName | ForEach-Object {
            [ordered]@{
                path = Relative-PortablePath $Stage $_.FullName
                bytes = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    )
    [IO.File]::WriteAllText((Join-Path $Stage 'artifact-inventory.json'), ($inventory | ConvertTo-Json -Depth 4) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    Write-ShaManifest $Stage

    if (Test-Path -LiteralPath $PortableOutput) { Remove-Item -LiteralPath $PortableOutput -Force }
    Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $PortableOutput -CompressionLevel Optimal
    Assert-File $PortableOutput 'portable package'

    if (-not $IsccPath) {
        $isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($isccCommand) { $IsccPath = $isccCommand.Source }
    }
    Assert-File $IsccPath 'pinned Inno Setup ISCC.exe'
    $isccVersions = @()
    $fileVersion = (Get-Item -LiteralPath $IsccPath).VersionInfo.ProductVersion -replace '\s', ''
    if ($fileVersion -and $fileVersion -ne '0.0.0.0') { $isccVersions += $fileVersion }
    foreach ($registryPath in @(
            'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
            'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
            'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
        )) {
        $displayVersion = (Get-ItemProperty -LiteralPath $registryPath -Name DisplayVersion -ErrorAction SilentlyContinue).DisplayVersion
        if ($displayVersion) { $isccVersions += ([string]$displayVersion -replace '\s', '') }
    }
    if (-not ($isccVersions | Where-Object { $_.StartsWith('6.4.2') } | Select-Object -First 1)) {
        $argument = '/?'
        $isccBanner = (& $IsccPath $argument 2>&1 | Out-String)
        $isccMatch = [regex]::Match($isccBanner, '(?im)Inno Setup(?: Compiler)?\s+([0-9]+\.[0-9]+\.[0-9]+)')
        if ($isccMatch.Success) { $isccVersions += $isccMatch.Groups[1].Value }
    }
    $isccVersion = $isccVersions | Where-Object { $_.StartsWith('6.4.2') } | Select-Object -First 1
    if (-not $isccVersion) { throw "Inno Setup 6.4.2 is required; found $($isccVersions -join ', ')" }
    $issArgs = @(
        ("/DAppVersion={0}" -f $Version)
        ("/DStageDir={0}" -f $Stage)
        ("/DOutputDir={0}" -f $InstallerDir)
        (Join-Path $RepoRoot 'installer\DipTraceMCP.iss')
    )
    Write-Host ("ISCC compile arguments ({0}): {1}" -f $issArgs.Count, ($issArgs -join ' | '))
    Invoke-Checked -File $IsccPath -Arguments $issArgs
    Assert-File $InstallerOutput 'Inno Setup installer'

    $verifyScript = Join-Path $RepoRoot 'plugin\verify_signature.ps1'
    $signatureTargets = @(
        $InstallerOutput,
        $BridgePath,
        (Join-Path $ServerDist 'diptrace_mcp_server.exe'),
        (Join-Path $ConfiguratorDist 'diptrace_mcp_configure.exe')
    )
    foreach ($signatureTarget in $signatureTargets) {
        $verifyArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $verifyScript, '-Path', $signatureTarget)
        if ($SigningRequired) {
            $verifyArgs += @('-ExpectedSignerSubject', $ExpectedSignerSubject, '-RequireSigned')
        }
        Invoke-Checked 'powershell.exe' $verifyArgs
    }
    $releaseChecksums = Join-Path $OutputRoot 'SHA256SUMS.txt'
    Write-ReleaseAssetShaManifest -Path $releaseChecksums -Assets @($InstallerOutput, $PortableOutput)
    Assert-File $releaseChecksums 'release asset checksum manifest'
    Write-Host "Installer: $InstallerOutput" -ForegroundColor Green
    Write-Host "Portable: $PortableOutput" -ForegroundColor Green
    Write-Host "Checksums: $releaseChecksums" -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
}
