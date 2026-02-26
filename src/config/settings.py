"""Application settings from environment. See user_input.md for canonical values."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql://localhost/steampipe"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # S3
    S3_BUCKET: str = "steampipe-data-storage"
    S3_REGION: str = "us-east-1"
    USE_LOCAL_STORAGE: bool = False
    LOCAL_STORAGE_PATH: str = "./local/snapshots"
    # Master account: Steampipe assume-role, Secrets Manager, S3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_SESSION_TOKEN: str = ""  # optional, for temporary credentials

    # Steampipe
    STEAMPIPE_PATH: str = "/usr/local/bin/steampipe"
    STEAMPIPE_INSTALL_DIR: str = ""
    STEAMPIPE_CONFIG_DIR: str = "/tmp/steampipe"
    # Port for worker's Steampipe service (default 9194 to avoid conflict with default 9193)
    STEAMPIPE_DATABASE_PORT: int = 9194
    # Set True for local dev to avoid "x509: certificate signed by unknown authority" (steampipe.io CA)
    STEAMPIPE_DATABASE_INSECURE: bool = False
    # Seconds to wait after service is listening before running query (plugin may retry GetCallerIdentity; 10s often too short)
    STEAMPIPE_CONNECTION_INIT_WAIT_SECONDS: int = 45

    # Worker
    MAX_CONCURRENT_EXECUTIONS: int = 3

    # Scheduler
    SCHEDULER_ENABLED: bool = True

    # Executions: bulk and batch chunk size (trigger-tenant, scheduler)
    BULK_QUERY_IDS_MAX: int = 200

    # Auth
    JWT_SECRET_KEY: str = "dev-secret"
    API_AUTH_REQUIRED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_db_url(cls, v: str) -> str:
        return _normalize_postgres_url(v) if isinstance(v, str) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
