#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
if [ -d "venv" ]; then
  source venv/bin/activate
fi
exec python -c "
from src.scheduler.cron_scheduler import run_scheduler
run_scheduler()
"
