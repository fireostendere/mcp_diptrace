[CmdletBinding()]
param(
    [string]$PythonCommand = "py",
    [string]$OutputDir = "dist\windows-configurator",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvDir = Join-Path $RepoRoot ".venv-configurator"
$BuildDir = Join-Path $RepoRoot ".build\pyinstaller-configurator"
$ResolvedOutput = [IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDir))
$Constraints = Join-Path $RepoRoot "packaging\windows-constraints.txt"

if ($Clean) {
    Remove-Item -LiteralPath $VenvDir, $BuildDir, $ResolvedOutput -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path -LiteralPath $VenvDir -PathType Container)) {
    if ((Split-Path -Leaf $PythonCommand) -eq "py") { & $PythonCommand -3.12 -m venv $VenvDir }
    else { & $PythonCommand -m venv $VenvDir }
    if ($LASTEXITCODE -ne 0) { throw "Unable to create configurator packaging environment" }
}
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
Push-Location $RepoRoot
try {
    & $VenvPython -m pip install --disable-pip-version-check -c $Constraints ".[bridge]"
    if ($LASTEXITCODE -ne 0) { throw "Unable to install configurator packaging dependencies" }
    New-Item -ItemType Directory -Force -Path $ResolvedOutput, $BuildDir | Out-Null
    & $VenvPython -m PyInstaller --noconfirm --clean `
        --distpath $ResolvedOutput --workpath $BuildDir `
        (Join-Path $RepoRoot "packaging\diptrace_mcp_configure.spec")
    if ($LASTEXITCODE -ne 0) { throw "Configurator PyInstaller build failed" }
} finally { Pop-Location }
$Executable = Join-Path $ResolvedOutput "diptrace_mcp_configure\diptrace_mcp_configure.exe"
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { throw "Configurator executable was not created" }
Write-Host "Configurator built: $Executable" -ForegroundColor Green
