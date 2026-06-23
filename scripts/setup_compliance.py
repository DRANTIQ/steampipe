#!/usr/bin/env python3
"""One-shot setup for the compliance engine: migrate DB, apply queries, seed catalog."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], env: dict | None = None) -> None:
    print("+", " ".join(cmd))
    merged = os.environ.copy()
    if env:
        merged.update(env)
    subprocess.check_call(cmd, cwd=REPO_ROOT, env=merged)


def main() -> None:
    py_path = f"{REPO_ROOT / 'cloud-compliance-engine'}{os.pathsep}{REPO_ROOT}"
    env = {"PYTHONPATH": py_path}

    print("=== 1/3 Alembic migrations ===")
    run([sys.executable, "-m", "alembic", "upgrade", "head"])

    print("=== 2/3 Apply queries (Stage 1 public.queries) ===")
    run([sys.executable, "scripts/apply_queries_document.py"], env=env)

    print("=== 3/3 Seed compliance catalog (controls + rule_versions) ===")
    run([sys.executable, "-m", "app.scripts.seed_catalog"], env=env)

    print("\nDone. Start services:")
    print("  docker compose -f docker-compose.remote.yml up compliance-api compliance-worker --scale worker=4")


if __name__ == "__main__":
    main()
