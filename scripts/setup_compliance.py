#!/usr/bin/env python3
"""Stage 1 query catalog setup. Compliance DB seeding lives in cloud-compliance-engine repo."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    print("=== Stage 1: apply queries to public.queries ===")
    subprocess.check_call(
        [sys.executable, "scripts/apply_queries_document.py"],
        cwd=REPO_ROOT,
    )
    print("\n=== Stage 2: run in cloud-compliance-engine repo ===")
    print("  cd ../cloud-compliance-engine")
    print("  python scripts/setup.py    # alembic + seed_catalog")
    print("  docker compose up -d       # compliance-api + compliance-worker")
    print("\nDocs: ../infra-state-docs/platform/SPLIT_COMPLIANCE_REPO.md")


if __name__ == "__main__":
    main()
