$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)

Write-Host "Starting backend + frontend..." -ForegroundColor Cyan

# Start backend in background
Write-Host "Starting backend on http://localhost:8000"
$backend = Start-Process -NoNewWindow -PassThru -FilePath "venv\Scripts\python.exe" -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"

# Start frontend in background
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
