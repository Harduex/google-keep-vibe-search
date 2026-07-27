$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)

# uv owns the environment and creates .venv (not venv\). Run setup if it is absent.
if (-not (Test-Path -Path ".venv\Scripts\python.exe" -PathType Leaf)) {
    Write-Host "Virtual environment not found; running setup.ps1..." -ForegroundColor Yellow
    & "$PSScriptRoot\setup.ps1"
}

Write-Host "Starting backend + frontend..." -ForegroundColor Cyan

# Bind the backend to 127.0.0.1: this app is single-user and loopback-only by
# design (see README "Security & supported configuration").
Write-Host "Starting backend on http://localhost:8000"
$backend = Start-Process -NoNewWindow -PassThru -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"

Write-Host "Starting frontend on http://localhost:5173"
$frontend = Start-Process -NoNewWindow -PassThru -WorkingDirectory "client" -FilePath "npm.cmd" -ArgumentList "run", "dev"

Write-Host ""
Write-Host "Press Ctrl+C to stop both servers." -ForegroundColor Yellow

try {
    $backend.WaitForExit()
} finally {
    Write-Host "Shutting down..."
    if (!$backend.HasExited) { $backend.Kill() }
    if (!$frontend.HasExited) { $frontend.Kill() }
}
