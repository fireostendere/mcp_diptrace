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
    $Extras = if ($NoGeometry) { ".[bridge]" } else { ".[bridge,geometry]" }
    & $VenvPython -m pip install --disable-pip-version-check -c $Constraints $Extras
    if ($LASTEXITCODE -ne 0) { throw "Unable to install pinned server packaging dependencies" }

    if ($NoGeometry) {
        $env:DIPTRACE_MCP_INCLUDE_GEOMETRY = "0"
    } else {
        $env:DIPTRACE_MCP_INCLUDE_GEOMETRY = "1"
    }
    New-Item -ItemType Directory -Force -Path $ResolvedOutput, $BuildDir | Out-Null
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $ResolvedOutput `
        --workpath $BuildDir `
        (Join-Path $RepoRoot "packaging\diptrace_mcp_server.spec")
    if ($LASTEXITCODE -ne 0) { throw "Standalone server PyInstaller build failed" }
} finally {
    Remove-Item Env:DIPTRACE_MCP_INCLUDE_GEOMETRY -ErrorAction SilentlyContinue
    Pop-Location
}

$Executable = Join-Path $ResolvedOutput "diptrace_mcp_server\diptrace_mcp_server.exe"
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Standalone server executable was not created: $Executable"
}
Write-Host "Standalone server built: $Executable" -ForegroundColor Green
