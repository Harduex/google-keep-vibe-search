#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "=== Google Keep Vibe Search - Setup ==="
echo ""

echo "Installing Python dependencies with uv..."
uv sync --all-groups

# Load nvm so npm/node are available in non-interactive shells
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

echo "Installing frontend dependencies..."
cd client
npm ci
cd "$ROOT"

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
echo "  make dev"
echo ""
