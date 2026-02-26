#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
if [ -d "venv" ]; then
  source venv/bin/activate
fi
exec python -c "
from src.workers.execution_worker import run_worker_loop
run_worker_loop()
"
