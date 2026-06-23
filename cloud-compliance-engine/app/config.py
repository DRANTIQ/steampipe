"""Compliance engine config from environment. Uses parent repo settings when available."""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

_ENGINE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _ENGINE_ROOT.parent


def _load_env_files() -> None:
    """Load repo root .env then engine .env (cwd may be cloud-compliance-engine/)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env")
    load_dotenv(_ENGINE_ROOT / ".env", override=True)


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


@lru_cache
def get_settings() -> "ComplianceSettings":
    return ComplianceSettings()


class ComplianceSettings:
    """Settings from env. When run from parent repo, DATABASE_URL etc. can come from parent .env."""

    def __init__(self) -> None:
        _load_env_files()
        try:
            if str(_REPO_ROOT) not in sys.path:
                sys.path.insert(0, str(_REPO_ROOT))
            from src.config import get_settings as parent_settings
            p = parent_settings()
            self.DATABASE_URL = _normalize_postgres_url(p.DATABASE_URL)
            self.REDIS_URL = p.REDIS_URL
            self.S3_BUCKET = p.S3_BUCKET
            self.S3_REGION = getattr(p, "S3_REGION", "us-east-1")
            self.USE_LOCAL_STORAGE = getattr(p, "USE_LOCAL_STORAGE", False)
            self.LOCAL_STORAGE_PATH = getattr(p, "LOCAL_STORAGE_PATH", "./local/snapshots")
            self.AWS_ACCESS_KEY_ID = getattr(p, "AWS_ACCESS_KEY_ID", "") or os.environ.get("AWS_ACCESS_KEY_ID", "")
            self.AWS_SECRET_ACCESS_KEY = getattr(p, "AWS_SECRET_ACCESS_KEY", "") or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
            self.AWS_SESSION_TOKEN = getattr(p, "AWS_SESSION_TOKEN", "") or os.environ.get("AWS_SESSION_TOKEN", "")
        except Exception:
            self.DATABASE_URL = _normalize_postgres_url(os.environ.get("DATABASE_URL", "postgresql://localhost/steampipe"))
            self.REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            self.S3_BUCKET = os.environ.get("S3_BUCKET", "steampipe-data-storage")
            self.S3_REGION = os.environ.get("AWS_REGION", "us-east-1")
            self.USE_LOCAL_STORAGE = os.environ.get("USE_LOCAL_STORAGE", "false").lower() in ("1", "true", "yes")
            self.LOCAL_STORAGE_PATH = os.environ.get("LOCAL_STORAGE_PATH", "./local/snapshots")
            self.AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
            self.AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
            self.AWS_SESSION_TOKEN = os.environ.get("AWS_SESSION_TOKEN", "")

        self.COMPLIANCE_QUEUE_KEY = os.environ.get("COMPLIANCE_QUEUE_KEY", "steampipe:job_completed")
        self.DEFAULT_TENANT_ID = os.environ.get("DEFAULT_TENANT_ID", "")
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @property
    def S3_ENDPOINT_URL(self) -> Optional[str]:
        return os.environ.get("S3_ENDPOINT_URL") or None
