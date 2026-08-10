#!/usr/bin/env bash
# Stage 1 (Steampipe) migrations only — public schema + query_schedules.
# Compliance schema: run in cloud-compliance-engine repo (alembic_version_compliance).
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
if [ -z "$VIRTUAL_ENV" ]; then
  if [ -d "venv" ]; then
    source venv/bin/activate
  fi
fi
alembic upgrade head
echo "Stage 1 migrations applied (001, 002, 007)."
echo "Next: cd ../cloud-compliance-engine && alembic upgrade head && python -m app.scripts.seed_catalog"
