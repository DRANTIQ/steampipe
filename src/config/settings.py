"""Application settings from environment. See user_input.md for canonical values."""
from __future__ import annotations

import os
import socket
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _prefer_ipv4_database_url(url: str) -> str:
    """Resolve Postgres host to IPv4 (hostaddr query param). Prefer postgres_connect_args() for engines."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or host in ("localhost", "127.0.0.1", "postgres"):
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "hostaddr" in query:
        return url
    ipv4 = resolve_postgres_host_ipv4(host, parsed.port or 5432)
    if not ipv4:
        return url
    query["hostaddr"] = ipv4
    return urlunparse(parsed._replace(query=urlencode(query)))


def resolve_postgres_host_ipv4(host: str, port: int = 5432) -> str | None:
    """Return IPv4 address for a Postgres hostname, or None if lookup fails."""
    if host in ("localhost", "127.0.0.1", "postgres"):
        return None
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        return infos[0][4][0] if infos else None
    except OSError:
        return None


def postgres_connect_args(database_url: str, prefer_ipv4: bool = True) -> dict[str, str]:
    """
    psycopg2 connect_args to force IPv4 (hostaddr).
    Docker Desktop often has no IPv6 route to Supabase; libpq still picks AAAA without this.
    """
    if not prefer_ipv4:
        return {}
    parsed = urlparse(database_url)
    host = parsed.hostname
    if not host:
        return {}
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if "hostaddr" in query:
        return {"hostaddr": query["hostaddr"]}
    ipv4 = resolve_postgres_host_ipv4(host, parsed.port or 5432)
    return {"hostaddr": ipv4} if ipv4 else {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql://localhost/steampipe"
    # When true, add libpq hostaddr (IPv4) — needed for Supabase from Docker Desktop (no IPv6 route)
    DATABASE_PREFER_IPV4: bool = True

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
        if not isinstance(v, str):
            return v
        url = _normalize_postgres_url(v)
        prefer_ipv4 = os.environ.get("DATABASE_PREFER_IPV4", "true").lower() in ("1", "true", "yes")
        if prefer_ipv4:
            url = _prefer_ipv4_database_url(url)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
