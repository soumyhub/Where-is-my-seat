#!/usr/bin/env bash
# Start the FastAPI backend (port 8000) and the Next.js frontend (port 3000) together.
# First run installs dependencies. Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

if in_use 8000 && in_use 3000; then
  echo "Where is my Seat is already running: http://localhost:3000"
  exit 0
fi
for port in 8000 3000; do
  if in_use "$port"; then
    echo "Port $port is already used by another program. Stop it, then run ./dev.sh again." >&2
    exit 1
  fi
done

cd "$ROOT/backend"
if [ ! -x .venv/bin/uvicorn ]; then
  echo "First run: setting up the Python environment…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements-dev.txt
fi
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

cd "$ROOT/frontend"
[ -d node_modules ] || npm install
echo "Open http://localhost:3000"
npm run dev -- --port 3000
