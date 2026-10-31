# Runs the whole SpatialTrace app: backend (FastAPI, port 8000) and
# frontend (Next.js, port 3000), each in its own window.
# Close those two windows to stop the servers.
#
# Usage:  .\run.ps1            (mock mode, from backend/.env)
#         .\run.ps1 -Mode live (live model APIs)

param(
    [ValidateSet('mock', 'live')]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# Friendly errors instead of cryptic ones when first-time setup is missing.
if (-not (Test-Path "$root\backend\.venv\Scripts\python.exe")) {
    throw "Backend not set up yet. Run the one-time setup in README.md first."
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    throw "Frontend not set up yet. Run: cd frontend; npm ci"
}

# Backend (backend/run.ps1 picks backend/.venv and backend/.deps for you).
# A -Mode passed here is inherited by the backend window via the environment.
if ($Mode) { $env:SPATIALTRACE_MODE = $Mode }
Start-Process powershell -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$root\backend\run.ps1`"" -WorkingDirectory "$root\backend"

# Frontend
Start-Process powershell -ArgumentList '-NoExit', '-Command', 'npm run dev -- --hostname 127.0.0.1' -WorkingDirectory "$root\frontend"

Write-Host "Starting SpatialTrace..."
Write-Host "  Backend:  http://127.0.0.1:8000/health"
Write-Host "  App:      http://127.0.0.1:3000  (opening in your browser)"
Write-Host "Close the backend/frontend windows to stop the servers."

Start-Sleep -Seconds 3
Start-Process 'http://127.0.0.1:3000'
