param(
    [string]$PythonCommand = "py",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$PluginDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $PluginDir
$VenvDir = Join-Path $RepoRoot ".venv-bridge"
$BuildDir = Join-Path $RepoRoot ".build\pyinstaller"
$DistDir = Join-Path $PluginDir "dist"
$EntryPoint = Join-Path $PluginDir "bridge_entry.py"
$Constraints = Join-Path $RepoRoot "packaging\windows-constraints.txt"

if ($Clean) {
    Remove-Item -Recurse -Force $VenvDir, $BuildDir, $DistDir -ErrorAction SilentlyContinue
}

if (-not (Test-Path $VenvDir)) {
    if ((Split-Path -Leaf $PythonCommand) -eq "py") {
        & $PythonCommand -3 -m venv $VenvDir
    } else {
        & $PythonCommand -m venv $VenvDir
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create bridge virtual environment"
    }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
# Install the project with its runtime dependencies (mcp, pydantic,
# typing-extensions) plus PyInstaller from the bridge extra. PyInstaller only
# bundles modules importable in this environment, so a PyInstaller-only venv
# produces an executable that fails with ModuleNotFoundError at runtime.
Push-Location $RepoRoot
try {
    & $VenvPython -m pip install --disable-pip-version-check -c $Constraints ".[bridge]"
} finally {
    Pop-Location
}
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install the project and PyInstaller into the bridge environment"
}

New-Item -ItemType Directory -Force $BuildDir, $DistDir | Out-Null
# Console subsystem is required for `--help` and tracebacks to work; the
# console window is hidden immediately so DipTrace launches stay clean.
& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --hide-console hide-early `
    --name "diptrace_mcp_bridge" `
    --paths (Join-Path $RepoRoot "src") `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $BuildDir `
    $EntryPoint
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed"
}

$Executable = Join-Path $DistDir "diptrace_mcp_bridge.exe"
Write-Host "Bridge built: $Executable" -ForegroundColor Green
