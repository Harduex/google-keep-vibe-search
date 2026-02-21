$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)
$ROOT = Get-Location

Write-Host "=== Google Keep Vibe Search - Setup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Python virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating Python virtual environment..."
    python -m venv venv
} else {
    Write-Host "Virtual environment already exists."
}

Write-Host "Installing Python dependencies..."
& venv\Scripts\pip.exe install -q -r requirements.txt

# 2. Node.js dependencies
Write-Host "Installing frontend dependencies..."
Set-Location client
npm install --silent
Set-Location $ROOT

# 3. Environment file
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..."
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "IMPORTANT: Edit .env and set GOOGLE_KEEP_PATH to your Google Keep export folder." -ForegroundColor Yellow
    Write-Host "  Example: GOOGLE_KEEP_PATH=C:\Users\$env:USERNAME\Takeout\Keep"
} else {
    Write-Host ".env file already exists."
}

Write-Host ""
Write-Host "Setup complete! To start developing:" -ForegroundColor Green
Write-Host "  .\scripts\dev.ps1"
Write-Host ""
