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
& $VenvPython -m pip install "pyinstaller>=6.14,<7"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install PyInstaller"
}

New-Item -ItemType Directory -Force $BuildDir, $DistDir | Out-Null
& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
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
