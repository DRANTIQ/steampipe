#!/usr/bin/env bash
# Create tables if missing and run all Alembic migrations.
# Use this to keep local dev DB in sync. Production: run migrations via CI/CD before deploy.
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
if [ -z "$VIRTUAL_ENV" ]; then
  if [ -d "venv" ]; then
    source venv/bin/activate
  fi
fi
alembic upgrade head
echo "Database initialized and migrations applied."
