$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)
$ROOT = Get-Location

Write-Host "=== Google Keep Vibe Search - Setup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Python dependencies, via uv. uv owns the virtual environment (.venv) and
#    resolves from uv.lock, so the versions match what CI and the Makefile use.
#    Not `--all-groups`: the gpu and cpu torch profiles conflict by design, so
#    asking for both is an error. Plain `uv sync` takes pyproject's defaults
#    (dev + gpu).
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is not installed. Install it, then re-run this script:" -ForegroundColor Red
    Write-Host '  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}

Write-Host "Installing Python dependencies with uv..."
uv sync
Write-Host "  (no NVIDIA GPU? re-run as: uv sync --no-group gpu --group cpu)"

# 2. Node.js dependencies. npm ci, not npm install, so the lockfile is honoured
#    and a Windows setup matches the Linux one.
Write-Host "Installing frontend dependencies..."
Set-Location client
npm ci
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

# 4. Git hooks, matching `make setup`.
Write-Host "Installing git hooks..."
uv run pre-commit install

Write-Host ""
Write-Host "Setup complete! To start developing:" -ForegroundColor Green
Write-Host "  .\scripts\dev.ps1"
Write-Host ""
