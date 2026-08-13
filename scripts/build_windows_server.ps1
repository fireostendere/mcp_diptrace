[CmdletBinding()]
param(
    [string]$PythonCommand = "py",
    [string]$OutputDir = "dist\windows-server",
    [switch]$Clean,
    [switch]$NoGeometry
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvDir = Join-Path $RepoRoot ".venv-server"
$BuildDir = Join-Path $RepoRoot ".build\pyinstaller-server"
$ServerBuildDir = Join-Path $BuildDir "server"
$HeadlessBuildDir = Join-Path $BuildDir "headless-gui"
$ResolvedOutput = [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))
$Constraints = Join-Path $RepoRoot "packaging\windows-constraints.txt"

if ($Clean) {
    Remove-Item -LiteralPath $VenvDir, $BuildDir, $ResolvedOutput -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $VenvDir -PathType Container)) {
    if ((Split-Path -Leaf $PythonCommand) -eq "py") {
        & $PythonCommand -3.12 -m venv $VenvDir
    } else {
        & $PythonCommand -m venv $VenvDir
    }
    if ($LASTEXITCODE -ne 0) { throw "Unable to create the server packaging virtual environment" }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
Push-Location $RepoRoot
try {
    $Extras = if ($NoGeometry) {
        ".[bridge,headless-gui]"
    } else {
        ".[bridge,geometry,headless-gui]"
    }
    & $VenvPython -m pip install --disable-pip-version-check -c $Constraints $Extras
    if ($LASTEXITCODE -ne 0) { throw "Unable to install pinned server packaging dependencies" }

    if ($NoGeometry) {
        $env:DIPTRACE_MCP_INCLUDE_GEOMETRY = "0"
    } else {
        $env:DIPTRACE_MCP_INCLUDE_GEOMETRY = "1"
    }
    New-Item -ItemType Directory -Force -Path $ResolvedOutput, $ServerBuildDir | Out-Null
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $ResolvedOutput `
        --workpath $ServerBuildDir `
        (Join-Path $RepoRoot "packaging\diptrace_mcp_server.spec")
    if ($LASTEXITCODE -ne 0) { throw "Standalone server PyInstaller build failed" }

    $HeadlessDistRoot = Join-Path $ResolvedOutput "diptrace_mcp_server\tools"
    New-Item -ItemType Directory -Force -Path $HeadlessDistRoot, $HeadlessBuildDir | Out-Null
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $HeadlessDistRoot `
        --workpath $HeadlessBuildDir `
        (Join-Path $RepoRoot "packaging\diptrace_mcp_headless_gui.spec")
    if ($LASTEXITCODE -ne 0) { throw "Headless GUI PyInstaller build failed" }
} finally {
    Remove-Item Env:DIPTRACE_MCP_INCLUDE_GEOMETRY -ErrorAction SilentlyContinue
    Pop-Location
}

$Executable = Join-Path $ResolvedOutput "diptrace_mcp_server\diptrace_mcp_server.exe"
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Standalone server executable was not created: $Executable"
}

$HeadlessExecutable = Join-Path $ResolvedOutput `
    "diptrace_mcp_server\tools\diptrace_mcp_headless_gui\diptrace_mcp_headless_gui.exe"
if (-not (Test-Path -LiteralPath $HeadlessExecutable -PathType Leaf)) {
    throw "Headless GUI executable was not created: $HeadlessExecutable"
}
& $HeadlessExecutable --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Headless GUI executable startup smoke failed" }

Write-Host "Standalone server built: $Executable" -ForegroundColor Green
Write-Host "Headless GUI helper built: $HeadlessExecutable" -ForegroundColor Green
