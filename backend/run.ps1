param(
    [string]$BindAddress = '127.0.0.1',
    [ValidateRange(1, 65535)][int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create backend/.venv with Python 3.12+ and install backend/requirements.txt first. See README.md.'
}

$previousPythonPath = $env:PYTHONPATH
Push-Location $PSScriptRoot
try {
    # Some local setups keep their installed packages in .deps instead of .venv.
    $dependencyPath = Join-Path $PSScriptRoot '.deps'
    if (Test-Path -LiteralPath $dependencyPath) {
        $env:PYTHONPATH = (@($dependencyPath, $previousPythonPath) | Where-Object { $_ }) -join [IO.Path]::PathSeparator
    }
    & $projectPython -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Recreate backend/.venv with Python 3.12 or newer.' }
    & $projectPython -c 'import uvicorn; from core.keyframer import process_video; from core.query_service import query_memory'
    if ($LASTEXITCODE -ne 0) {
        throw 'Backend dependencies are missing or incompatible. Install requirements.txt into backend/.venv and retry.'
    }
    & $projectPython -m uvicorn main:app --host $BindAddress --port $Port
    if ($LASTEXITCODE -ne 0) { throw "Backend exited with code $LASTEXITCODE. Check the error above." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
