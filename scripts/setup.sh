#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "=== Google Keep Vibe Search - Setup ==="
echo ""

# 1. Python virtual environment
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
else
  echo "Virtual environment already exists."
fi

echo "Upgrading pip..."
venv/bin/python -m pip install --upgrade pip -q

echo "Installing Python dependencies..."
if ! venv/bin/pip install -q -r requirements.txt; then
  echo ""
  echo "ERROR: pip install failed. Check the output above for dependency conflicts."
  echo "You may need to delete the venv folder and try again:"
  echo "  rm -rf venv"
  echo "  ./scripts/setup.sh"
  exit 1
fi

# 2. Node.js dependencies
echo "Installing frontend dependencies..."
cd client
npm install --silent
cd "$ROOT"

# 3. Environment file
if [ ! -f ".env" ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  echo ""
  echo "IMPORTANT: Edit .env and set GOOGLE_KEEP_PATH to your Google Keep export folder."
  echo "  Example: GOOGLE_KEEP_PATH=/home/$USER/Takeout/Keep"
else
  echo ".env file already exists."
fi

echo ""
echo "Setup complete! To start developing:"
echo "  ./scripts/dev.sh"
echo ""
