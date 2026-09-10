#!/usr/bin/env bash
# Starts the FastAPI backend (port 8765; 8000 is used by another local service) and the Vite dev server (port 5173).
set -euo pipefail
cd "$(dirname "$0")"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT

(cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload) &
(cd frontend && npm run dev -- --host 127.0.0.1 --port 5173) &
wait
