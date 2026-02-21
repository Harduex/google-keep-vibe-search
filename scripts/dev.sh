#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

echo "Starting backend + frontend..."

# Start backend in background
echo "Starting backend on http://localhost:8000"
venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on http://localhost:5173"
cd client
npm run dev &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID 2>/dev/null
  kill $FRONTEND_PID 2>/dev/null
}
trap cleanup EXIT INT TERM

wait
