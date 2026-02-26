#!/usr/bin/env bash
set -e
lsof -ti :8000 | xargs -r kill -9
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
if [ -d "venv" ]; then
  source venv/bin/activate
fi
exec uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
